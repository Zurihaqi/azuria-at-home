"""Small local supervised encounter model. No model downloads or game writes.

Only native solo kills/deaths are labels. A contextual nearest-neighbour model
estimates completion probability and successful fight duration. It abstains
outside observed equipment, map, level and enemy support. Selection defaults to
shadow mode; a chronological session holdout must pass before activation.
"""
import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sqlite3
import struct
import time
import uuid

VERSION = 1
BOT_IDS = frozenset((50000002, 50000003))
LABELS = frozenset(('kill', 'death'))
OUTCOMES = LABELS | frozenset(('assisted', 'interrupted', 'timeout', 'disconnect', 'migration', 'lost_target'))
# Curated ordinary Port Skandia enemies, from the matching installed table.
# This is an allowlist, not permission to attack every biology template.
ENEMIES = {40323: 3, 40324: 3, 40325: 5, 40326: 6,
           40327: 7, 40328: 8, 40329: 9, 40330: 9}


@dataclass(frozen=True)
class Features:
    map_id: int
    bot_level: int
    enemy: int
    enemy_level: int
    capability: str

    def valid(self):
        return (all(type(v) is int for v in (self.map_id,self.bot_level,self.enemy,self.enemy_level)) and
                self.map_id == 2 and self.enemy in ENEMIES and
                self.enemy_level == ENEMIES[self.enemy] and
                1 <= self.bot_level <= 150 and isinstance(self.capability, str) and
                1 <= len(self.capability) <= 180)

    def as_dict(self):
        return dict(map_id=self.map_id, bot_level=self.bot_level, enemy=self.enemy,
                    enemy_level=self.enemy_level, capability=self.capability)


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), timeout=.1)
        self.path.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=DELETE')
        self.db.execute('''CREATE TABLE IF NOT EXISTS encounters(
            id TEXT PRIMARY KEY, version INTEGER NOT NULL, session TEXT NOT NULL,
            actor INTEGER NOT NULL, started REAL NOT NULL, map_id INTEGER NOT NULL,
            bot_level INTEGER NOT NULL, enemy INTEGER NOT NULL, enemy_level INTEGER NOT NULL,
            capability TEXT NOT NULL, outcome TEXT NOT NULL, seconds REAL NOT NULL,
            damage_out INTEGER NOT NULL, damage_in INTEGER NOT NULL,
            contaminated INTEGER NOT NULL, xp_gain INTEGER)''')
        if 'exclusion' not in {row[1] for row in self.db.execute('PRAGMA table_info(encounters)')}:
            self.db.execute("ALTER TABLE encounters ADD COLUMN exclusion TEXT NOT NULL DEFAULT ''")
        self.db.commit()

    def record(self, *, ident, session, actor, started, features, outcome, seconds,
               damage_out=0, damage_in=0, contaminated=False, exclusion=''):
        if (actor not in BOT_IDS or not features.valid() or outcome not in OUTCOMES or
                not math.isfinite(seconds) or not 0 <= seconds <= 3600 or
                damage_out < 0 or damage_in < 0):
            raise ValueError('Invalid dedicated-bot encounter')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO encounters '
                '(id,version,session,actor,started,map_id,bot_level,enemy,enemy_level,capability,'
                'outcome,seconds,damage_out,damage_in,contaminated,xp_gain,exclusion) '
                'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (ident, VERSION, session, actor, started, features.map_id, features.bot_level,
                 features.enemy, features.enemy_level, features.capability, outcome,
                 seconds, damage_out, damage_in, int(contaminated), None, exclusion[:200]))
            # Bound retention; censored failures still remain available for diagnostics.
            self.db.execute('DELETE FROM encounters WHERE rowid NOT IN '
                            '(SELECT rowid FROM encounters ORDER BY rowid DESC LIMIT 5000)')

    def rows(self):
        return [dict(r) for r in self.db.execute('SELECT * FROM encounters ORDER BY rowid')]

    def close(self):
        self.db.close()


def clean(rows):
    return [r for r in rows if r['version'] == VERSION and r['actor'] in BOT_IDS and
            r['outcome'] in LABELS and not r['contaminated'] and r['seconds'] >= .1 and
            Features(**{k:r[k] for k in ('map_id','bot_level','enemy','enemy_level','capability')}).valid()]


def predict(examples, features):
    """Distance-weighted Beta estimate plus geometric mean successful duration."""
    if not features.valid():
        return None
    neighbours = []
    for row in examples:
        if (row['map_id'] != features.map_id or row['capability'] != features.capability or
                abs(row['bot_level'] - features.bot_level) > 2 or
                abs((row['enemy_level'] - row['bot_level']) -
                    (features.enemy_level - features.bot_level)) > 2):
            continue
        distance = (abs(row['bot_level'] - features.bot_level) * .5 +
                    abs(row['enemy_level'] - features.enemy_level) +
                    (0 if row['enemy'] == features.enemy else 2))
        neighbours.append((distance, row))
    neighbours.sort(key=lambda pair: pair[0])
    neighbours = neighbours[:32]
    exact = sum(r['enemy'] == features.enemy for _,r in neighbours)
    if len(neighbours) < 12 or exact < 6:
        return None
    weights = [(math.exp(-distance), row) for distance,row in neighbours]
    mass = sum(w for w,_ in weights)
    won = [(w,r) for w,r in weights if r['outcome'] == 'kill']
    win_mass = sum(w for w,_ in won)
    if mass < 8:
        return None
    seconds = math.exp(sum(w * math.log(r['seconds']) for w,r in won) / win_mass) if win_mass >= 3 else None
    return dict(completion_probability=(win_mass + 1) / (mass + 2),
                seconds=seconds, support=len(neighbours), exact_support=exact,
                effective_support=round(mass, 2))


def train(rows):
    usable = clean(rows)[-2000:]
    sessions = list(dict.fromkeys(r['session'] for r in usable))
    result = dict(version=VERSION, method='contextual-nearest-neighbours', approved=False,
                  training_rows=0, holdout_rows=0, reason='Need at least 40 labels across 3 sessions',
                  created_at=time.time(), examples=[])
    if len(usable) < 40 or len(sessions) < 3:
        return result
    # Entire latest session is held out. No random fight-level leakage.
    split = sessions[-1]
    training = [r for r in usable if r['session'] != split]
    holdout = [r for r in usable if r['session'] == split]
    result.update(training_rows=len(training), holdout_rows=len(holdout))
    if len(training) < 30 or len(holdout) < 10:
        result['reason'] = 'Need 30 training labels and 10 labels in the held-out session'
        return result
    base_probability = (sum(r['outcome']=='kill' for r in training) + 1) / (len(training) + 2)
    times = [math.log(r['seconds']) for r in training if r['outcome']=='kill']
    if not times:
        result['reason'] = 'No native successful fights in training data'
        return result
    base_time = sum(times) / len(times)
    brier, baseline, duration, baseline_duration = [], [], [], []
    for row in holdout:
        features = Features(**{k:row[k] for k in ('map_id','bot_level','enemy','enemy_level','capability')})
        prediction = predict(training, features)
        if prediction is None:
            continue
        y = int(row['outcome']=='kill')
        brier.append((prediction['completion_probability'] - y) ** 2)
        baseline.append((base_probability - y) ** 2)
        if y and prediction['seconds'] is not None:
            duration.append(abs(math.log(prediction['seconds']) - math.log(row['seconds'])))
            baseline_duration.append(abs(base_time - math.log(row['seconds'])))
    metrics = dict(coverage=len(brier)/len(holdout), evaluated=len(brier),
                   brier=sum(brier)/len(brier) if brier else None,
                   baseline_brier=sum(baseline)/len(baseline) if baseline else None,
                   log_time_mae=sum(duration)/len(duration) if duration else None,
                   baseline_log_time_mae=sum(baseline_duration)/len(baseline_duration) if duration else None)
    passed = (len(brier) >= 10 and metrics['coverage'] >= .6 and len(duration) >= 5 and
              metrics['brier'] <= metrics['baseline_brier'] and
              metrics['log_time_mae'] <= metrics['baseline_log_time_mae'])
    result.update(metrics=metrics, approved=passed,
                  reason='Holdout gate passed' if passed else 'Holdout gate failed; keep shadow/rules mode')
    # Ship exactly the evaluated training set, without fitting on the holdout.
    result['examples'] = [{k:r[k] for k in ('map_id','bot_level','enemy','enemy_level',
                                          'capability','outcome','seconds')} for r in training]
    return result


def load_model(path):
    try:
        path = Path(path)
        if path.stat().st_size > 2_000_000:
            return None
        model = json.loads(path.read_text())
        examples = model.get('examples', [])
        if (model.get('version') != VERSION or model.get('approved') is not True or
                model.get('method') != 'contextual-nearest-neighbours' or not 0 < len(examples) <= 2000):
            return None
        for row in examples:
            f = Features(**{k:row[k] for k in ('map_id','bot_level','enemy','enemy_level','capability')})
            if not f.valid() or row['outcome'] not in LABELS or not .1 <= row['seconds'] <= 3600:
                return None
        return model
    except (OSError, ValueError, TypeError, KeyError):
        return None


def save_model(model, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(model, allow_nan=False)
    if len(payload.encode('utf-8')) > 2_000_000:
        raise ValueError('Model exceeds bounded artifact size')
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    try:
        temporary.write_text(payload, encoding='utf-8')
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def rank(model, *, map_id, level, capability, candidates):
    """Rank only pre-authorized, ordinary, level-bounded candidate templates."""
    ranked = []
    if model.get('approved') is not True:
        return ranked
    for enemy in candidates:
        if enemy not in ENEMIES or not max(1,level-3) <= ENEMIES[enemy] <= level + 1:
            continue
        p = predict(model['examples'], Features(map_id,level,enemy,ENEMIES[enemy],capability))
        if p is not None and p['completion_probability'] >= .85 and p['seconds'] is not None:
            ranked.append(dict(enemy=enemy, score=p['completion_probability']/p['seconds'], **p))
    return sorted(ranked, key=lambda row: (-row['score'], row['enemy']))


class Tracker:
    """Observes one actor's fight, independently from gameplay task cancellation."""
    def __init__(self, store, protocol, emit=lambda message: None, clock=time.monotonic):
        self.store, self.protocol, self.emit, self.clock = store, protocol, emit, clock
        self.session = uuid.uuid4().hex
        self.actor = None
        self.map_id = None
        self.level = None
        self.capability = None
        self.active = None
        self.enabled = True
        self.multi_spell = {value for name,value in protocol.items() if
                            name.startswith('CNC_CZ_ClientMultiSpell')}

    def begin(self, actor, enemy_actor, template):
        self.finish('interrupted')
        if not self.enabled or actor not in BOT_IDS or self.level is None or self.capability is None:
            return
        f = Features(self.map_id,self.level,template,ENEMIES.get(template,0),self.capability)
        if not f.valid():
            return
        self.actor = actor
        self.active = dict(ident=uuid.uuid4().hex, session=self.session, actor=actor,
                           started=time.time(), features=f, enemy_actor=enemy_actor,
                           tick=self.clock(), damage_out=0, damage_in=0, contaminated=False,
                           reasons=set())

    def exclude(self, reason):
        self.active['contaminated'] = True
        self.active['reasons'].add(reason)

    def observe(self, opcode, payload):
        current = self.active
        if current is None:
            return
        target = current['enemy_actor']
        # Blast/BlastOK are visual/cast acknowledgements, not evidence of
        # assistance. Actual single-target hit/cast headers identify participants.
        # Unknown multi-target packets remain conservatively excluded.
        if opcode in self.multi_spell:
            self.exclude('unparsed_multi_spell')
        if opcode in (self.protocol.get('CNC_CZ_ClientSpellHitToLife'),
                      self.protocol.get('CNC_CZ_ClientSpellCast')):
            if len(payload) != 24:
                self.exclude('malformed_spell_header')
            else:
                _,caster,victim = struct.unpack_from('<HII',payload)
                if victim in (target,self.actor) and caster not in (target,self.actor):
                    self.exclude('external_spell')
        if opcode == self.protocol.get('CNC_CZ_ClientMeleeAttack') and len(payload) in (16,18):
            attacker, victim, damage = struct.unpack_from('<IIi', payload)
            if damage < 0:
                return
            if attacker == self.actor and victim == target:
                current['damage_out'] += damage
            elif victim == target and attacker != self.actor and damage:
                self.exclude('external_melee')
            elif victim == self.actor:
                current['damage_in'] += damage
                if attacker != target and damage:
                    self.exclude('multiple_attackers')
        if opcode == self.protocol.get('CNC_CZ_ClientDie') and len(payload)==11:
            victim,killer,_,_ = struct.unpack('<IIBH',payload)
            if victim == self.actor:
                self.finish('death')
            elif victim == target:
                self.finish('kill' if killer == self.actor else 'assisted')
        elif opcode == self.protocol.get('CNC_CZ_ClientCantSee') and len(payload)==4:
            if struct.unpack('<I',payload)[0] == target:
                self.finish('lost_target')

    def finish(self, outcome):
        current, self.active = self.active, None
        if current is None:
            return
        current['seconds'] = max(0, self.clock() - current.pop('tick'))
        current.pop('enemy_actor')
        current['exclusion'] = ','.join(sorted(current.pop('reasons')))
        try:
            self.store.record(outcome=outcome, **current)
            self.emit('Encounter recorded: ' + outcome + '; seconds=' + str(round(current['seconds'],1)) +
                      ('; excluded=' + current['exclusion'] if current['contaminated'] else '; clean'))
        except (sqlite3.Error, OSError):
            self.enabled = False
            self.emit('Encounter recording disabled after a storage failure; gameplay continues.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status','train'))
    parser.add_argument('--db', required=True)
    parser.add_argument('--out')
    args = parser.parse_args()
    if not Path(args.db).is_file():
        parser.error('No encounter database exists yet; collect real bot fights first')
    store = Store(args.db)
    try:
        rows = store.rows()
    finally:
        store.close()
    if args.action == 'status':
        print(json.dumps(dict(encounters=len(rows), labelled=len(clean(rows)),
                              sessions=len({r['session'] for r in clean(rows)}),
                              outcomes={outcome:sum(r['outcome']==outcome for r in rows) for outcome in sorted(OUTCOMES)},
                              exclusions={reason:sum((r.get('exclusion') or 'legacy-unattributed')==reason for r in rows if r['contaminated'])
                                          for reason in sorted({r.get('exclusion') or 'legacy-unattributed' for r in rows if r['contaminated']})}), indent=2))
    else:
        if not args.out:
            parser.error('train requires --out')
        model = train(rows)
        save_model(model, args.out)
        print(json.dumps({k:v for k,v in model.items() if k!='examples'}, indent=2))


if __name__ == '__main__':
    main()
