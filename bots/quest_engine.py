"""Database-driven quest planning, bounded execution and recovery telemetry.

The native server is the sole progression authority. Journal entries describe
attempts, never substitute for mission state and cannot complete a quest.
"""
import asyncio
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import time

import objectives
import crafting
from npc import ACTIVE, FINISHED, READY
from quests import active, offers, objective_plan, turn_in_npc
from wire import ProtocolError
from worldmap import objective_template


@dataclass(frozen=True)
class Step:
    quest: int
    index: int
    kind: str
    command: str
    args: tuple
    driver: str


@dataclass(frozen=True)
class Plan:
    quest: int
    steps: tuple
    blockers: tuple

    @property
    def executable(self):
        return not self.blockers


# Explicit semantic overrides have evidence, rather than inferring that every
# MonsterKilled objective is permission to melee a friendly actor.
OVERRIDES = {
    (1010, 0): ('wake_workers', 'item 30297 / enchant 45131 / actor 40338'),
    (1014, 0): ('drink_quest_potion', 'granted item 30300 / enchant 45138 / client objective says drink'),
    (2092, 0): ('craft_then_equip', 'S_Combine recipes 134 -> 137; granted 30702/30703/30711 -> trophy 30714'),
}
MIN_ARGS = {'equip': 1, 'kill': 2, 'collect_drop': 4, 'travel': 1,
            'collect': 1, 'deliver': 1, 'buff': 1, 'level': 1}


def compile_quest(quest):
    steps, blockers = [], []
    for objective in objective_plan(quest):
        override = OVERRIDES.get((quest.id, objective.index))
        driver = override[0] if override else objective.kind
        if objectives.driver_for(objective.kind) is None:
            blockers.append(f'{objective.command}: driver unavailable')
        if len(objective.args) < MIN_ARGS.get(objective.kind, 0):
            blockers.append(f'{objective.command}: missing required arguments')
        if objective.kind == 'use_item' and objective.command != 'NPCItem':
            blockers.append(f'{objective.command}: item/target semantics unverified')
        if objective.kind == 'collect':
            blockers.append(f'{objective.command}: item source has not been resolved')
        if objective.kind == 'kill' and objective.args and objective.args[0] == 40338 and not override:
            blockers.append('Friendly worker requires a verified item-interaction override')
        steps.append(Step(quest.id, objective.index, objective.kind, objective.command,
                          objective.args, driver))
    return Plan(quest.id, tuple(steps), tuple(blockers))


def progress(session, quest):
    """Only native state for this quest; unrelated chat/movement is not progress."""
    personal = getattr(session, 'personal', {})
    return (session.states.get(quest), tuple(session.progress.get(quest, ())),
            tuple(sorted((key, value) for key, value in personal.items() if key >> 32 == quest)))


def failure_kind(error):
    text = str(error).lower()
    if isinstance(error, asyncio.TimeoutError):
        return 'deadline'
    if 'died' in text or 'death' in text:
        return 'combat_loss'
    if any(word in text for word in ('moveself', 'route', 'collision', 'position', 'path')):
        return 'navigation'
    if any(word in text for word in ('not in the npc dialog', 'offer', 'dialog')):
        return 'npc_offer'
    if any(word in text for word in ('not in the tracked inventory', 'item', 'inventory')):
        return 'inventory_or_item'
    if any(word in text for word in ('no driver', 'unverified', 'unavailable', 'not authored')):
        return 'unsupported_content'
    if any(word in text for word in ('progress', 'ready', 'expected state')):
        return 'no_progress'
    return 'native_action'


class Journal:
    """Bounded bot-local attempt metadata, including reconnect-stable cooldowns."""
    def __init__(self, path=None, clock=time.time, driver_revision=None):
        self.path = Path(path) if path else None
        self.clock = clock
        self.driver_revision = driver_revision
        self.failures, self.events = {}, []
        if self.path and self.path.exists():
            if self.path.stat().st_size > 1_000_000:
                raise ProtocolError('Quest attempt journal exceeds size bound')
            data = json.loads(self.path.read_text())
            if data.get('version') != 1:
                raise ProtocolError('Unsupported quest attempt journal version')
            self.failures = data.get('failures', {})
            self.events = data.get('events', [])[-500:]
            if data.get('driver_revision') != driver_revision:
                self.failures = {}
                self.events.append(dict(time=self.clock(), quest=0, stage='driver_update', outcome='retry_budget_reset'))

    def allowed(self, quest):
        return self.failures.get(str(quest), {}).get('retry_at', 0) <= self.clock()

    def append(self, quest, stage, outcome, **details):
        self.events.append(dict(time=self.clock(), quest=quest, stage=stage, outcome=outcome, **details))
        self.events = self.events[-500:]
        self.save()

    def failed(self, quest, stage, error):
        old = self.failures.get(str(quest), {})
        count = min(10, old.get('count', 0) + 1)
        cooldown = min(1800, 60 * (2 ** (count - 1)))
        self.failures[str(quest)] = dict(count=count, retry_at=self.clock() + cooldown,
                                       kind=failure_kind(error), stage=stage)
        self.append(quest, stage, 'failed', reason=str(error)[:200], kind=failure_kind(error),
                    retry_seconds=cooldown)
        return cooldown

    def succeeded(self, quest, stage):
        self.failures.pop(str(quest), None)
        self.append(quest, stage, 'confirmed')

    def save(self):
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(dict(version=1, driver_revision=self.driver_revision,
                                  failures=self.failures, events=self.events), allow_nan=False)
        if len(payload.encode()) > 1_000_000:
            raise ProtocolError('Quest attempt journal exceeds size bound')
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(payload)
        temporary.chmod(0o600)
        temporary.replace(self.path)


class Engine:
    def __init__(self, table, journal, emit=lambda level, message: None,
                 status=lambda **kwargs: None, drivers=None, locate=None, travel=None):
        self.table, self.journal = table, journal
        self.emit, self.status = emit, status
        self.locate, self.travel = locate, travel
        self.drivers = dict(objectives.DRIVERS if drivers is None else drivers)
        self.drivers['wake_workers'] = objectives.wake_workers
        self.drivers['drink_quest_potion'] = objectives.drink_quest_potion
        self.drivers['craft_then_equip'] = crafting.craft_then_equip
        self.plans = {qid: compile_quest(quest) for qid, quest in table.items()}

    def candidates(self, session, level, weapon, reachable, node):
        running = active(self.table, session.states)
        available = offers(self.table, session.states, level, weapon, reachable, node)
        # A ready quest can be turned in even if its objective driver is missing.
        return [quest for quest in running + available
                if self.journal.allowed(quest.id) and
                (session.states.get(quest.id) == READY or self.plans[quest.id].executable)]

    async def execute(self, quest, ctx, talk_to, close, recover, get_node=None):
        stage = 'accept'

        async def ensure(template, label):
            """Travel to the authored map of an actor before touching it."""
            if self.locate is None or self.travel is None or get_node is None or not template:
                return
            target = self.locate(template)
            if target is None or target == get_node():
                return
            self.status(task=f'Quest {quest.id}: travelling to map {target}')
            self.emit('info', f'Quest framework: {label} {template} is authored on map '
                              f'{target}; routing through ordinary portals.')
            await self.travel(target)
            if get_node() != target:
                raise ProtocolError(f'Native server did not admit the route to map {target}')

        try:
            state = ctx.session.states.get(quest.id)
            if state not in (ACTIVE, READY):
                self.status(quest=quest.id, task=f'Quest {quest.id}: accepting at authored NPC')
                await ensure(quest.accept_npc, 'accept NPC')
                actor = await asyncio.wait_for(talk_to(quest.accept_npc), 60)
                await ctx.session.accept(actor, quest.id, timeout=20)
                if ctx.session.states.get(quest.id) not in (ACTIVE, READY):
                    raise ProtocolError('Native server did not confirm quest acceptance')
                self.journal.succeeded(quest.id, stage)
                await close()
            if ctx.session.states.get(quest.id) == ACTIVE:
                ctx.quest = quest
                for step in self.plans[quest.id].steps:
                    if ctx.session.states.get(quest.id) == READY:
                        break
                    stage = f'objective:{step.index}:{step.driver}'
                    driver = self.drivers.get(step.driver)
                    if driver is None:
                        raise ProtocolError(f'Driver unavailable: {step.driver}')
                    await ensure(objective_template(step, quest), 'objective actor')
                    before = progress(ctx.session, quest.id)
                    self.status(quest=quest.id, task=f'Quest {quest.id}: {step.command} ({step.index + 1})')
                    self.emit('info', f'Quest framework: {quest.id} {stage}; native progress required.')
                    self.journal.append(quest.id, stage, 'started')
                    # A healthy starter character can take over a minute to
                    # defeat an authored solo boss. Keep the outer deadline
                    # longer than the battle driver's bounded encounter budget.
                    combat_step = step.kind == 'kill' or (step.kind == 'collect_drop'
                        and step.args and step.args[0] not in getattr(ctx, 'resources', (40334, 40335, 40336)))
                    await asyncio.wait_for(driver(ctx, step), timeout=240 if combat_step else 90)
                    after = progress(ctx.session, quest.id)
                    self.journal.append(quest.id, stage,
                        'progress_observed' if after != before else 'returned_without_progress')
                stage = 'verify_ready'
                await ctx.session.state(quest.id, READY, timeout=10)
            if ctx.session.states.get(quest.id) != READY:
                raise ProtocolError('Native server did not mark quest ready')
            stage = 'turn_in'
            self.status(quest=quest.id, task=f'Quest {quest.id}: claiming native rewards')
            await ensure(turn_in_npc(quest), 'turn-in NPC')
            actor = await asyncio.wait_for(talk_to(turn_in_npc(quest)), 60)
            await ctx.session.turn_in(actor, quest.id, timeout=20)
            if ctx.session.states.get(quest.id) != FINISHED:
                raise ProtocolError('Native server did not confirm quest completion')
            await close()
            self.journal.succeeded(quest.id, 'finished')
            self.status(quest=None, last_completed_quest=quest.id,
                        task=f'Quest {quest.id}: completed', last_failure='')
            self.emit('info', f'Quest framework: {quest.id} completed through native turn-in.')
            return True
        except (ProtocolError, asyncio.TimeoutError) as error:
            cooldown = self.journal.failed(quest.id, stage, error)
            kind = failure_kind(error)
            self.status(quest=quest.id, last_failure=f'{kind}: {str(error) or "action deadline"}')
            self.emit('warning', f'Quest framework: {quest.id} failed at {stage} ({kind}); retry in {cooldown}s.')
            try:
                await asyncio.wait_for(recover(kind), timeout=15)
            except (ProtocolError, asyncio.TimeoutError):
                self.emit('warning', f'Quest framework: recovery refresh failed for {quest.id}; keeping cooldown.')
            return False
        except asyncio.CancelledError:
            # Party invitation, shutdown or budget cancellation is not a
            # failed action. A native death is: the character lost the fight,
            # so the retry budget must pay for it and the deadly objective
            # yields to growth (fallback grinding) until the cooldown lands.
            combat = getattr(ctx, 'combat', None)
            death = getattr(combat, 'last_death', None) if combat else None
            if death is not None and time.monotonic() - death[1] <= 30:
                ctx.combat.last_death = None
                text = f'character died to biology {death[0]} during {stage}'
                cooldown = self.journal.failed(quest.id, stage, ProtocolError(text))
                self.status(quest=quest.id, last_failure=f'death: {text}')
                self.emit('warning', f'Quest framework: {quest.id} {stage} is beyond the '
                                     f'character for now; charging the retry budget '
                                     f'(cooldown {cooldown}s) so growth work can run.')
            else:
                self.journal.append(quest.id, stage, 'interrupted')
            raise

    async def run(self, ctx, *, level, weapon, reachable, get_node, close, recover, max_quests=12):
        origin = get_node()
        completed = 0
        for _ in range(max_quests):
            if get_node() != origin:
                return completed
            npcs = reachable() if callable(reachable) else reachable
            candidates = self.candidates(ctx.session, level(), weapon, npcs, get_node())
            if not candidates:
                blocked = [quest.id for quest in active(self.table, ctx.session.states)
                           if not self.plans[quest.id].executable]
                self.emit('info', f'Quest framework: no eligible quest; unsupported active quests={blocked[:12]}.')
                return completed
            quest = candidates[0]
            result = await self.execute(quest, ctx, ctx.talk_to, close, recover, get_node)
            completed += int(result)
        return completed


def audit(table):
    plans = [compile_quest(quest) for quest in table.values()]
    commands = Counter(o.command for quest in table.values() for o in quest.objectives)
    blockers = Counter(reason for plan in plans for reason in plan.blockers)
    return dict(total_quests=len(plans), executable_by_declared_drivers=sum(p.executable for p in plans),
                live_validation='Required per quest; compile coverage is not correctness coverage',
                commands=dict(commands.most_common()), blockers=dict(blockers.most_common()),
                semantic_overrides=[dict(quest=q, objective=i, driver=v[0], evidence=v[1])
                                    for (q, i), v in OVERRIDES.items()])


if __name__ == '__main__':
    import argparse
    from content import parse_quests
    parser = argparse.ArgumentParser()
    parser.add_argument('mission_table')
    parser.add_argument('--output')
    args = parser.parse_args()
    result = json.dumps(audit(parse_quests(args.mission_table)), indent=2)
    if args.output:
        Path(args.output).write_text(result)
    else:
        print(result)
