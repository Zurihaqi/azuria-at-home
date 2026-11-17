"""One unprivileged lab-only login probe. Never logs packets or credentials."""
import asyncio
import json
from pathlib import Path
import os
import hashlib
import sys
import socket
import time
import struct
import math
import traceback
import builtins
import signal
from reporting import Reporter
from runtime import NORMAL_WORLD, STATE, normal_config, server_ip
from social import LocalChat
from party import Party
from assist import Assist
from content import Scene, parse_quests
from navigation import Grid
from game_packets import first_inventory_item, equip_from_inventory
from movement import Segment, Sync, blob_cell, blob_point, encode_blob, plan, wire_speed
from tutorial import Tutorial
from wire import Connection, ProtocolError, Reader, string
import combat as combat_module
import objectives
import grind as grind_module
import encounter_learning as learning
import potential as potential_module
import portals
import quest_engine
import battle
import evasion
import worldmap
from inventory import Inventory
from npc import READY, Session, parse_mission_list
from quests import active, next_offer, supported, turn_in_npc

REPORTER = None


def world_keepalive_payload():
    # Matching V15 Deserialize: 8 strings, i32, 2 strings, i16. This
    # headless client has no desktop/hardware telemetry to report in the strings.
    return string('') * 8 + struct.pack('<i', 0) + string('') * 2 + struct.pack('<h', 0)


async def keep_session_alive(connection, command, payload=b'', interval=15):
    """Maintain the earlier native service session during zone gameplay."""
    connection.idle_timeout = 3600
    async def drain():
        while True:
            await connection.receive()
    receiver = asyncio.create_task(drain())
    try:
        while True:
            if receiver.done():
                await receiver
            await connection.send(command, payload)
            # Earlier services can be silent during zone gameplay. Their lack
            # of a reply must not stop outgoing keepalives after eight seconds.
            await asyncio.sleep(interval)
    except ProtocolError as error:
        if REPORTER:
            REPORTER.emit('warning', 'Earlier service connection ended: ' + str(error))
    finally:
        receiver.cancel()
        await asyncio.gather(receiver, return_exceptions=True)


def report(message, **options):
    builtins.print(message, **options)
    if REPORTER:
        REPORTER.message(message)


async def zone_session(ticket):
    protocol = json.loads((STATE / 'zone-protocol.json').read_text())
    reverse = {v:k for k,v in protocol.items() if k.startswith('CNC_CZ_')}
    address, port = socket.inet_ntoa(ticket[8:12]), struct.unpack_from('<H', ticket, 12)[0]
    if address != server_ip() or port != 10020:
        raise ProtocolError(f'Unexpected isolated zone endpoint: {address}:{port}')
    reader, writer = await asyncio.open_connection(address, port, local_addr=('127.0.0.1', 0))
    conn = Connection(reader, writer)
    loaded = set()
    migration_done = False
    seen = set()
    spell_logs = 0
    map_state = None
    player_id = None
    tasks = []
    quitting = False
    revives = 0
    login_hp = None
    moved = False
    native_position = None
    position_observed_at = None
    mobs = {}
    starter_slot = None
    equipment_ready = asyncio.Event()
    starter_requested = False
    tutorial = None
    correction_count = 0
    combat_result = asyncio.Event()
    scene = None
    entered_gateways = set()
    movement_sync = Sync()
    self_move_reports = 0
    positional_confirmation = True
    movement = 1.0
    level = 1
    quest_session = Session(lambda name, payload=b'': conn.send(protocol['CNE_CZ_ZoneServer' + name], payload), report)
    quest_combat = combat_module.Combat(protocol, 0)
    battle_controller = None
    potential_allocator = potential_module.Allocator()
    if '--battle-framework' in sys.argv:
        gear_catalog = json.loads(Path('/opt/ak-bot-prototype/maps/gear-catalog.json').read_text())
        battle_controller = battle.Controller(
            emit=lambda severity, message: REPORTER.emit(severity, message) if REPORTER else None,
            catalog=gear_catalog)
        quest_combat.controller = battle_controller
    learning_store = None
    learning_tracker = None
    if NORMAL_WORLD and '--encounter-learning' in sys.argv:
        try:
            learning_store = learning.Store(STATE / 'encounters.sqlite3')
            learning_tracker = learning.Tracker(learning_store, protocol,
                emit=lambda message: REPORTER.emit('info', message) if REPORTER else None)
            quest_combat.learning = learning_tracker
        except (OSError, learning.sqlite3.Error):
            if REPORTER:
                REPORTER.emit('warning', 'Encounter recorder unavailable; ordinary gameplay continues.')
    quest_inventory = Inventory()
    last_quest = None
    local_chat = LocalChat(name=normal_config()['character_name'] if NORMAL_WORLD else 'Awan')
    party_state = Party()
    shared_activity = NORMAL_WORLD and '--continuous' in sys.argv and any(
        flag in sys.argv for flag in ('--quests', '--companion'))
    companion_assist = Assist(json.loads(Path('/opt/ak-bot-prototype/maps/hostile-templates.json').read_text())) if shared_activity else Assist(())
    idle_task = None
    hunting_exclusions = {}
    companion_started = False
    social_started = False
    fallback_context = None
    fallback_started = False
    alive_event = asyncio.Event()
    map_ready = asyncio.Event()
    revive_pending = False
    resume_after_revive = None

    async def resume_activity(factory):
        # Let the native respawn position arrive before planning a new route.
        await asyncio.sleep(5)
        await alive_event.wait()
        if not quitting and revives <= 3:
            tasks.append(asyncio.create_task(factory()))

    def suspend_activity():
        nonlocal resume_after_revive
        for task in list(tasks):
            name = task.get_coro().__name__
            if name in ('quest_worker', 'fallback_worker', 'companion_worker', 'autonomous_worker', 'resume_activity'):
                if name == 'quest_worker':
                    resume_after_revive = quest_worker
                elif name == 'fallback_worker':
                    resume_after_revive = lambda: fallback_worker(fallback_context, 'Resuming after native respawn')
                elif name == 'companion_worker':
                    resume_after_revive = companion_worker
                task.cancel()
                tasks.remove(task)

    async def observe_party(short, payload):
        try:
            companion_assist.observe(short, payload, party_state.leader)
            if short == 'GetSelectLifeTarget':
                companion_assist.selected(payload, party_state.leader, node)
            if short.startswith('Team'):
                (STATE / ('party-last-' + short + '.bin')).write_bytes(payload)
            if short == 'TeamInviteNotice':
                answer, inviter, context = party_state.invitation(payload)
                await conn.send(protocol['CNE_CZ_ZoneServerTeamInviteAnswer'], answer)
                if REPORTER:
                    REPORTER.emit('info', f'Party acceptance sent for {inviter}; waiting for the native roster.')
            elif short == 'TeamAllMembersInfo':
                party_state.roster(payload)
                if REPORTER:
                    REPORTER.emit('info', f'Native party roster: leader={party_state.leader}; members={[(m.slot,m.id,m.name) for m in party_state.members.values()]}')
            elif short == 'TeamMemberPosition':
                party_state.position(payload)
            elif short == 'TeamLeaved':
                party_state.leave(payload, player_id)
            elif short == 'MoveChar' and len(payload) == 12:
                actor, px, py = struct.unpack('<Iff', payload)
                party_state.move(actor, node, px, py)
            elif short == 'MovePrediction' and len(payload) in (32, 36):
                actor, px, py = struct.unpack_from('<IHH', payload)
                party_state.move(actor, node, px / 16, py / 16)
        except ProtocolError as error:
            party_state.leader = None
            party_state.positions.clear()
            if REPORTER:
                REPORTER.emit('warning', 'Following paused: native party message could not be decoded: ' + str(error))

    async def ensure_starter_weapon():
        """Buy one normal level-1 sword/shield from Colen and equip it."""
        await asyncio.wait_for(alive_event.wait(), 35)
        await asyncio.sleep(2)
        receipt = STATE / 'outfit-receipt.json'
        if receipt.exists():
            return
        if node != 2 or not scene:
            raise ProtocolError('Starter merchant is available in Port Skandia')
        points = scene.positions(10210)
        if not points:
            raise ProtocolError('Weapon merchant is not authored on this map')
        merchant_point = min(points,key=lambda p: math.dist(native_position,p))
        map_dir = Path('/opt/ak-bot-prototype/maps')
        map_asset = json.loads((map_dir/'manifest.json').read_text())[str(node)]['asset']
        await walk(Grid.read(map_dir/map_asset).approach(merchant_point))
        candidates = [(mid,mob) for mid,mob in mobs.items() if mob['template']==10210]
        if not candidates:
            raise ProtocolError('Weapon merchant did not become visible')
        actor = min(candidates,key=lambda pair: math.dist(pair[1]['position'],native_position))[0]
        view = await quest_session.talk(actor)
        choices = [i for i,o in enumerate(view.options) if o.index==5172]
        if len(choices)!=1:
            raise ProtocolError('Weapon merchant did not offer its normal store')
        await quest_session.choose(view,choices[0])
        await quest_session.expect('EnterShop',timeout=8)
        # S_Store 2, zero-based slot 1 = item 10001. Server checks price/gold.
        await quest_session.send('BuyItems',struct.pack('<HHb',1,1,0))
        location = await objectives.wait_for(lambda: quest_inventory.first(10001),timeout=8)
        if location is None:
            raise ProtocolError('Starter weapon purchase was not confirmed by inventory')
        await quest_session.send('LeaveShop')
        await quest_session.send('TalkToNPC',struct.pack('<I',0))
        await quest_session.send('SwitchItemLocation',quest_inventory.equip_payload(*location))
        result = await quest_session.expect('SwitchItemLocationOK',timeout=8)
        if result[-1]!=1:
            raise ProtocolError('Starter sword/shield equip was rejected')
        quest_inventory.discard(*location)
        receipt.write_text(json.dumps(dict(item=10001,bought_normally=True,equipped=True,time=time.time())))
        if REPORTER:
            REPORTER.emit('info','Bought and equipped level-1 sword/shield through the normal weapon merchant.')

    async def close_interaction():
        await quest_session.send('LeaveShop')
        await quest_session.send('TalkToNPC', struct.pack('<I', 0))

    async def outfit_only():
        await ensure_starter_weapon()
        await logout()

    async def companion_worker():
        nonlocal idle_task
        await asyncio.wait_for(alive_event.wait(),35)
        await asyncio.sleep(2)
        # Earn the merchant price through the early dialogue/delivery quests;
        # the wake-up reward alone is less than the starter sword's price.
        if not (STATE / 'outfit-receipt.json').exists():
            await quest_worker(intro=True)
        await ensure_starter_weapon()
        await close_interaction()
        blocked={}
        failed_goal = None
        failed_attempts = 0
        last_route_warning = 0
        while not quitting:
            await alive_event.wait()
            await map_ready.wait()
            if revives>3:
                if REPORTER:REPORTER.update(phase='paused',task='Following paused after repeated deaths')
                await asyncio.sleep(3);continue
            grouped = len(party_state.members) > 1
            if not grouped:
                if idle_task is None or idle_task.done():
                    idle_task = asyncio.create_task(autonomous_worker())
                    tasks.append(idle_task)
                await asyncio.sleep(.25)
                continue
            if idle_task is not None:
                idle_task.cancel()
                await asyncio.gather(idle_task, return_exceptions=True)
                if idle_task in tasks:
                    tasks.remove(idle_task)
                idle_task = None
                await close_interaction()
            destination=party_state.destination()
            if not party_state.leader or destination is None:
                if REPORTER:REPORTER.update(task='Waiting for a party invite or leader position')
                await asyncio.sleep(1);continue
            target_node,tx,ty=destination
            assets=Path('/opt/ak-bot-prototype/maps')
            manifest=json.loads((assets/'manifest.json').read_text())
            if str(node) not in manifest:
                if REPORTER:REPORTER.update(task=f'Following paused: map {node} has no collision data')
                await asyncio.sleep(3);continue
            grid=Grid.read(assets/manifest[str(node)]['asset'])
            target = companion_assist.target(party_state, quest_combat, node, native_position)
            if target is not None:
                leader = party_state.leader
                async def approach_enemy(actor):
                    if (party_state.leader != leader or
                            companion_assist.target(party_state, quest_combat, node, native_position) != actor):
                        raise ProtocolError('Assist ended: leader or target changed, or moved out of range')
                    enemy = quest_combat.mobs[actor]
                    if math.dist(native_position, enemy.position) > 1.2:
                        await walk(grid.approach(enemy.position))
                try:
                    if REPORTER:
                        REPORTER.update(task=f'Assisting party leader against {target}')
                        REPORTER.emit('info', f'Assisting leader {leader} against visible hostile {target}.')
                    await approach_enemy(target)
                    async def assist_send(command, payload):
                        if (party_state.leader != leader or
                                companion_assist.target(party_state, quest_combat, node, native_position) != target):
                            raise ProtocolError('Assist ended: target died, changed, or moved out of range')
                        await conn.send(command, payload)
                    await combat_module.engage(quest_combat, assist_send, target, timeout=12,
                        report=report, follow=approach_enemy, record=False)
                except ProtocolError as error:
                    if REPORTER:
                        REPORTER.emit('info', str(error) + '; resuming party follow.')
                await asyncio.sleep(.25)
                continue
            if target_node!=node:
                graph=json.loads((assets/'portals.json').read_text())
                public_maps = set(json.loads((assets/'public-maps.json').read_text()))
                available = {int(key) for key in manifest} & public_maps
                route = portals.route(graph, node, target_node, available, blocked)
                if not route:
                    if REPORTER:REPORTER.update(task=f'Waiting: leader is on map {target_node}; no allowed portal route')
                    await asyncio.sleep(3);continue
                edge=route[0]
                old=node
                try:
                    if REPORTER: REPORTER.update(task=f'Following through ordinary portal: map {old} to {edge["target"]}')
                    crossed = await portals.cross(edge, lambda: node, lambda: native_position,
                        grid.approach, walk, quest_session.send,
                        lambda: asyncio.wait_for(map_ready.wait(), timeout=35))
                except (ProtocolError, asyncio.TimeoutError) as error:
                    crossed = False
                    if REPORTER: REPORTER.emit('warning', 'Portal follow paused: ' + str(error))
                if not crossed:
                    blocked[(old,edge['event'])]=time.monotonic()+60
                    if REPORTER:REPORTER.emit('warning','Normal portal did not admit the companion; waiting or trying another authored route.')
                continue
            here=native_position
            distance=math.dist(here,(tx,ty))
            if distance<=4:
                if REPORTER:REPORTER.update(task='Following the party leader; nearby')
                await asyncio.sleep(.5);continue
            goal = (target_node, round(tx / 4), round(ty / 4))
            if failed_goal == goal and failed_attempts >= 3:
                if REPORTER:
                    REPORTER.update(phase='paused', task='Following blocked by terrain; waiting for the leader to move')
                await asyncio.sleep(1)
                continue
            if failed_goal != goal:
                failed_goal, failed_attempts = goal, 0
            target=(tx+(here[0]-tx)*3/distance,ty+(here[1]-ty)*3/distance)
            try:
                endpoint = grid.approach(target, limit=40)
                route = await asyncio.to_thread(grid.route, here, endpoint, max_expansions=200000)
                point=route[min(24,len(route)-1)]
                if REPORTER:REPORTER.update(phase='online', task='Following the party leader')
                await walk(point)
                failed_attempts = 0
            except ProtocolError as error:
                failed_attempts += 1
                if REPORTER and time.monotonic() - last_route_warning > 10:
                    REPORTER.emit('warning', 'Leader route blocked; replanning from the next position: ' + str(error))
                    last_route_warning = time.monotonic()
                await asyncio.sleep(1)
            await asyncio.sleep(.2)

    async def party_target_worker():
        while not quitting:
            await asyncio.sleep(1)
            leader = party_state.leader
            destination = party_state.destination()
            if (not alive_event.is_set() or len(party_state.members) < 2 or
                    not map_ready.is_set() or
                    leader is None or leader == player_id or destination is None or
                    destination[0] != node):
                continue
            request = companion_assist.query(leader, node)
            if request is not None:
                await conn.send(protocol['CNE_CZ_ZoneServerGetSelectLifeTarget'], request)

    async def autonomous_worker():
        """One serialized quest/grind loop, cancelled when a party takes priority."""
        while not quitting:
            manifest = json.loads(Path('/opt/ak-bot-prototype/maps/manifest.json').read_text())
            if str(node) not in manifest:
                if REPORTER: REPORTER.update(task=f'Waiting: map {node} has no packaged collision data')
                await asyncio.sleep(5)
                continue
            reason = 'No supported quest currently available'
            try:
                await asyncio.wait_for(quest_worker(background=True), timeout=600)
            except (ProtocolError, asyncio.TimeoutError) as error:
                reason = str(error) or 'Quest activity reached its ten-minute budget'
                if REPORTER: REPORTER.emit('warning', reason + '; hunting before the next quest retry.')
            if REPORTER:
                reason = REPORTER.state.get('last_failure') or reason
            await close_interaction()
            if '--quest-framework-only' in sys.argv:
                if REPORTER: REPORTER.update(task='Quest framework: waiting for eligible quest or retry cooldown')
                if '--grind' in sys.argv and fallback_context is not None:
                    try:
                        await fallback_worker(fallback_context, reason, duration=120)
                    except ProtocolError as error:
                        if REPORTER: REPORTER.emit('warning', str(error) + '; resting before retry.')
                    await asyncio.sleep(15)
                    continue
                await asyncio.sleep(15)
                continue
            if fallback_context is not None and (node == 2 or '--grind' in sys.argv):
                try:
                    await fallback_worker(fallback_context, reason, duration=180)
                except ProtocolError as error:
                    if REPORTER: REPORTER.emit('warning', str(error) + '; resting before retry.')
            await asyncio.sleep(15)

    async def fallback_worker(context, reason, duration=None):
        nonlocal fallback_started
        fallback_started = True
        context.quest = None  # The blocked quest remains unchanged on the server.
        if REPORTER:
            REPORTER.update(phase='online', task='Fallback hunting: level-appropriate local enemies', last_failure=reason)
            REPORTER.emit('warning', 'Quest blocked; hunting temporarily, then retrying quests. Quest progress is preserved.')
        local_chat.event('grind')
        failures = 0
        excluded_targets = hunting_exclusions
        deadline = time.monotonic() + duration if duration is not None else float('inf')
        grind_catalog = grind_module.load_catalog(
            Path('/opt/ak-bot-prototype/maps/mob-catalog.json'))
        if REPORTER and grind_catalog:
            REPORTER.emit('info', f'Grind catalog ready: {len(grind_catalog)} hostile templates.')
        while not quitting and time.monotonic() < deadline:
            try:
                present = {spawn['template'] for spawn in context.scene.spawns.values()}
                pool = grind_module.targets(grind_catalog, max(3, level), present)
                candidates = [ident for ident in pool
                              if excluded_targets.get(ident, 0) < time.monotonic()]
                if not candidates:
                    # Legacy Port Skandia allowlist when this map has no grind pool.
                    candidates = [ident for ident, enemy_level in learning.ENEMIES.items()
                                  if enemy_level <= max(3, level) and context.scene.positions(ident)
                                  and excluded_targets.get(ident, 0) < time.monotonic()]
                if not candidates:
                    await asyncio.sleep(5)
                    continue
                if candidates[0] in grind_catalog:
                    # The grind pool arrives strongest-level first.
                    target = candidates[0]
                else:
                    target = max(candidates, key=lambda ident: (learning.ENEMIES.get(ident, 0), -ident))
                if learning_tracker is not None and learning_tracker.enabled and learning_tracker.capability is not None:
                    model = learning.load_model(STATE / 'encounter-model.json')
                    if model is not None and learning_tracker.level is not None:
                        candidates = [ident for ident in learning.ENEMIES if context.scene.positions(ident)
                                      and excluded_targets.get(ident, 0) < time.monotonic()]
                        ranked = learning.rank(model, map_id=node, level=learning_tracker.level,
                                               capability=learning_tracker.capability, candidates=candidates)
                        if ranked:
                            proposed = ranked[0]
                            active_policy = '--learned-targets' in sys.argv
                            if REPORTER:
                                REPORTER.emit('info', ('Learned' if active_policy else 'Shadow') +
                                    f" target: {proposed['enemy']}; predicted completion={proposed['completion_probability']:.2f}, seconds={proposed['seconds']:.1f}")
                            if active_policy:
                                target = proposed['enemy']
                await objectives.hunt(context, target, 1)
                await objectives.loot(context)
                await quest_session.send('EnterNodeInventory')
                failures = 0
                if REPORTER:
                    REPORTER.update(task=f'Fallback hunting: template {target}')
                await asyncio.sleep(2)
            except ProtocolError as error:
                excluded_targets[target] = time.monotonic() + 120
                failures += 1
                if failures >= 3:
                    raise ProtocolError('Fallback hunting paused after repeated failures: ' + str(error))
                await asyncio.sleep(5 * failures)

    async def learning_worker():
        last_trained = -20
        last_reason = None
        while not quitting:
            await asyncio.sleep(30)
            try:
                rows = learning_store.rows()
                usable = len(learning.clean(rows))
                if REPORTER:
                    REPORTER.update(learning_labels=usable)
                if usable < 40 or usable < last_trained + 20:
                    continue
                model = await asyncio.to_thread(learning.train, rows)
                await asyncio.to_thread(learning.save_model, model, STATE / 'encounter-model.json')
                last_trained = usable
                if REPORTER:
                    REPORTER.update(learning_model='evaluated-shadow' if model['approved'] else 'not-ready',
                                    learning_train_reason=model['reason'])
                    if model['reason'] != last_reason:
                        REPORTER.emit('info', 'Shadow training: ' + model['reason'])
                last_reason = model['reason']
            except Exception as error:
                # The optional learner cannot take down the native game session.
                if REPORTER:
                    REPORTER.emit('warning', 'Shadow trainer stopped: ' + type(error).__name__ + '; gameplay continues.')
                return

    async def social_worker():
        await asyncio.sleep(6)
        while not quitting:
            local_chat.mode = ('combat' if quest_combat.target and quest_combat.alive(quest_combat.target)
                               else 'party' if len(party_state.members) > 1
                               else 'grind' if fallback_started else 'quest' if last_quest else 'idle')
            payload = local_chat.next_payload()
            if payload:
                await conn.send(protocol['CNE_CZ_ZoneServerTextCommand'], payload)
                if REPORTER:
                    REPORTER.emit('info', 'Scripted proximity chat requested')
            await asyncio.sleep(15)

    async def exit_finished_tutorial():
        # S610 event area 13 is the completed-tutorial wake-up trigger at
        # the initial spawn. Ordinary trigger checks still enforce mission 1003.
        await asyncio.sleep(2)
        if node != 610:
            return
        history = json.loads((STATE / 'quest-history.json').read_text())
        if history.get('character_id') != player_id or history['states'].get('1003') != 1:
            raise ProtocolError('Tutorial exit requires the completed native final tutorial quest')
        # This request can acknowledge only an event already offered by the
        # server's per-character pending-event list; it cannot run arbitrary events.
        await conn.send(protocol['CNE_CZ_ZoneServerTriggerNodeEvent'], struct.pack('<H', 303))
        report('Quest objective: acknowledged the completed-tutorial wake-up event.', flush=True)
        for _ in range(40):
            if node != 610:
                report(f'Tutorial checkpoint: normal exit reached map {node}.', flush=True)
                await logout()
                return
            await asyncio.sleep(.25)
        await logout()

    async def check_gateways(position):
        nonlocal entered_gateways
        if not scene:
            return
        inside = scene.inside_gateways(position)
        for ident in sorted(inside - entered_gateways):
            # CheckNodeExit carries the gateway row's *trigger* id (column 7).
            # Flag 0 fires the condition-0 ("step on") event; flag 1 fires
            # condition-1 ("step off") events on the way out.
            gateway = scene.gateways.get(ident)
            if gateway is None:
                continue
            await conn.send(protocol['CNE_CZ_ZoneServerCheckNodeExit'],
                            struct.pack('<hhi', gateway['trigger'], 0, 0))
            report(f'Quest objective: entered native gateway trigger {gateway["trigger"]}.', flush=True)
        for ident in sorted(entered_gateways - inside):
            gateway = scene.gateways.get(ident)
            if gateway is not None:
                await conn.send(protocol['CNE_CZ_ZoneServerCheckNodeExit'],
                                struct.pack('<hhi', gateway['trigger'], 0, 1))
        entered_gateways = inside

    async def equip_starter(bag, slot):
        # The real tutorial client closes quest/shop interaction before equipping.
        # A destination of -1 asks the native server to choose the weapon slot.
        await conn.send(protocol['CNE_CZ_ZoneServerLeaveShop'])
        await asyncio.sleep(.5)
        await conn.send(protocol['CNE_CZ_ZoneServerSwitchItemLocation'],
                        equip_from_inventory(bag, slot))
        report('Requested ordinary automatic weapon-slot selection.', flush=True)

    async def heartbeat():
        while True:
            await asyncio.sleep(3)
            if REPORTER:
                position = (dict(x=native_position[0], y=native_position[1], map=node,
                                 observed_at=position_observed_at)
                            if native_position is not None and position_observed_at is not None else None)
                REPORTER.update(position=position, battle=battle_controller.summary() if battle_controller else None)
            await conn.send(protocol['CNE_CZ_ZoneServerHello'])

    async def walk(destination, ignore_barriers=False):
        nonlocal moved
        origin_node = node
        if REPORTER:
            REPORTER.update(task=f'Travel to {destination[0]:.1f}, {destination[1]:.1f}')
        manifest = json.loads(Path('/opt/ak-bot-prototype/maps/manifest.json').read_text())
        grid = Grid.read(Path('/opt/ak-bot-prototype/maps', manifest[str(node)]['asset']))
        if scene and not ignore_barriers:
            grid.obstacles = scene.active_obstacles(mobs)
        step_seconds = .5 / max(movement, 1.0)

        async def send_segment(segment):
            await conn.send(protocol['CNE_CZ_ZoneServerMoveSelf'],
                            segment.payload(movement_sync.next()))

        async def await_advance(segment):
            # Native clients confirm each hop with a self move report; when a build
            # stays silent the hop is paced by distance instead.
            nonlocal positional_confirmation
            wanted = blob_cell(segment.f1, segment.f2)
            if positional_confirmation:
                deadline = time.monotonic() + max(.3, segment.steps * step_seconds) + 1.2
                while time.monotonic() < deadline:
                    if native_position and blob_cell(*native_position) == wanted:
                        return True
                    await asyncio.sleep(.02)
                if self_move_reports or correction_count:
                    return False
                positional_confirmation = False
                report('No self move report observed; pacing movement by distance.', flush=True)
            await asyncio.sleep(max(.1, segment.steps * step_seconds))
            return True

        for attempt in range(3):
            generation = correction_count
            start = native_position or (map_state[:2] if map_state else None)
            if start is None:
                raise ProtocolError('Movement requested before the server reported a position')
            if blob_cell(*start) == blob_cell(*destination):
                break
            route = await asyncio.to_thread(grid.route, start, destination,
                                           radius=0 if grid.obstacles else .5,
                                           max_expansions=200000)
            segments = plan(route, grid, step_limit=12)
            report(f'Collision-checked route: {len(route)} waypoints in {len(segments)} move '
                   f'segments; direct={grid.line_clear(start, destination)}; attempt={attempt + 1}.', flush=True)
            for segment in segments:
                if node != origin_node:
                    raise ProtocolError('Map changed during movement; old route discarded')
                if generation != correction_count:
                    break
                await send_segment(segment)
                if not await await_advance(segment):
                    # A stale sync is dropped silently, so retry once with a fresh one.
                    report(f'MoveSelf unconfirmed at {segment.cells[-1]}; retrying with a new sync.', flush=True)
                    await send_segment(segment)
                    if not await await_advance(segment):
                        raise ProtocolError(f'MoveSelf was not acknowledged at {segment.cells[-1]}')
                if '--gateways' in sys.argv:
                    await check_gateways((segment.f1, segment.f2))
            if generation == correction_count:
                break
            await asyncio.sleep(.3)
        else:
            raise ProtocolError('Repeated native movement corrections; route paused')
        await asyncio.sleep(.3)
        if native_position is None or math.dist(native_position, destination) > 1:
            raise ProtocolError('Native position did not confirm route endpoint; movement paused')
        moved = True
        report('Native movement endpoint confirmed at ' + str(native_position), flush=True)

    async def break_wall():
        # Lab experiment: prove the authored Fire Wall actor is an ordinary
        # killable barrier and that its death clears the scene's dynamic block.
        await asyncio.sleep(3)
        spawn = scene.spawns.get(3) if scene else None
        if not spawn:
            raise ProtocolError('Scene has no authored barrier spawn 3')
        authored_point = spawn['position']
        report(f'Authored barrier 3 is template {spawn["template"]} at '
               f'({authored_point[0]:.2f},{authored_point[1]:.2f}).', flush=True)
        here = native_position or map_state[:2]
        approach = (authored_point[0], authored_point[1] - 7.5)
        if math.dist(here, approach) > 2:
            await walk(approach)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            walls = [(mid, mob) for mid, mob in mobs.items()
                     if mob['template'] == spawn['template']
                     and math.dist(mob['position'], authored_point) < 2]
            if walls:
                break
            await asyncio.sleep(.2)
        else:
            raise ProtocolError('Authored barrier actor never became visible')
        wall_id, wall = walls[0]
        report(f'Barrier actor {wall_id} visible at '
               f'({wall["position"][0]:.2f},{wall["position"][1]:.2f}); '
               f'distance {math.dist(native_position, wall["position"]):.2f}.', flush=True)
        try:
            await combat_module.engage(quest_combat, conn.send, wall_id, timeout=20, report=report)
            report('Barrier actor died.', flush=True)
        except ProtocolError as error:
            report(f'Barrier attack did not land: {error}', flush=True)
        await asyncio.sleep(1)
        report('Barrier actor still tracked: ' + str(wall_id in mobs), flush=True)
        await walk((210, 178))
        report('Walked past the authored barrier to the arena.', flush=True)
        await logout()

    async def cross_wall():
        # Lab experiment: decide whether `[dynamic_block]` is enforced by the
        # running server. Stage just north of the authored band, then ask for
        # single half-cell steps into it and watch for a native correction.
        await asyncio.sleep(3)
        spawn = scene.spawns.get(3) if scene else None
        if not spawn:
            raise ProtocolError('Scene has no authored barrier spawn 3')
        wall_point = spawn['position']
        report(f'Barrier 3 authored at ({wall_point[0]:.2f},{wall_point[1]:.2f}).', flush=True)
        await walk((wall_point[0] - .05, wall_point[1] - 7.55))
        report(f'Staged north of barrier at {native_position}.', flush=True)

        async def one_step(delta):
            before = blob_cell(*native_position)
            target = (before[0] + delta[0], before[1] + delta[1])
            blob = encode_blob([before, target])
            x, y = blob_point(*target)
            await conn.send(protocol['CNE_CZ_ZoneServerMoveSelf'],
                            Segment((before, target), blob, x, y, x, y)
                            .payload(movement_sync.next()))
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                await asyncio.sleep(.02)
                if native_position and blob_cell(*native_position) != before:
                    break
            return before, native_position

        crossed = False
        for index in range(18):
            before, after = await one_step((0, 1))
            after_cell = blob_cell(*after) if after else None
            delta_row = after_cell[1] - before[1] if after_cell else None
            report(f'South step {index + 1}: {before} -> {after_cell} '
                   f'(row delta {delta_row}).', flush=True)
            if not delta_row or delta_row <= 0:
                break
            crossed = after_cell[1] >= blob_cell(*wall_point)[1] + 6
            if crossed:
                break
        if crossed:
            report('Server accepted movement through the authored dynamic block.',
                   flush=True)
            await walk((210, 178), ignore_barriers=True)
            report(f'Arena reached at {native_position}.', flush=True)
        else:
            report('Server refused movement at the authored dynamic block.', flush=True)
        await logout()

    async def node_event():
        # Lab experiment: send the same packet the native client uses for its
        # authored step-on triggers, and see whether the server runs the scene
        # event chain (event 601 emits an environment message, 814 removes the
        # Fire Wall that seals the arena).
        await asyncio.sleep(3)
        barriers = sorted(mid for mid, mob in mobs.items() if mob['template'] == 20724)
        report(f'Barrier actors before node events: {barriers}.', flush=True)
        for event in (601, 814):
            await conn.send(protocol['CNE_CZ_ZoneServerTriggerNodeEvent'],
                            struct.pack('<H', event))
            report(f'Sent native node event {event}.', flush=True)
            await asyncio.sleep(4)
            alive = sorted(mid for mid, mob in mobs.items() if mob['template'] == 20724)
            report(f'Barrier actors after node event {event}: {alive}.', flush=True)
        if not any(mob['template'] == 20724 for mob in mobs.values()):
            await walk((210, 178), ignore_barriers=True)
            report(f'Arena reached at {native_position}.', flush=True)
        else:
            report('Barrier actors survived; no route change.', flush=True)
        await logout()

    async def abandon_mission():
        # Ordinary client action: give a mission up so the next session can accept
        # it again through its authored NPC and replay the accept-side scene event.
        quest_id = int(sys.argv[sys.argv.index('--abandon-mission') + 1])
        await asyncio.sleep(2)
        await conn.send(protocol['CNE_CZ_ZoneServerMissionListOp'],
                        struct.pack('<hiH', 5, quest_id, 65535))
        report(f'Requested ordinary abandonment of mission {quest_id}.', flush=True)
        await asyncio.sleep(6)
        await logout()

    async def request_revive(reason):
        nonlocal revives, revive_pending
        if revive_pending or quitting:
            return
        revive_pending = True
        revives += 1
        if revives > 3:
            for task in list(tasks):
                if task.get_coro().__name__ in ('quest_worker','fallback_worker'):
                    task.cancel()
                    tasks.remove(task)
            if REPORTER:
                REPORTER.update(phase='paused',task='Recovering; combat paused after repeated deaths')
        report(f'Requesting a native revive ({reason}, attempt {revives}).', flush=True)
        if REPORTER:
            REPORTER.update(task='Dead; requesting normal respawn')
        await asyncio.sleep(1.5)
        await conn.send(protocol['CNE_CZ_ZoneServerRevive'], struct.pack('<i', 1))
        report('Sent the native revive request.', flush=True)

    async def logout():
        nonlocal quitting, resume_after_revive
        if quitting:
            return
        if REPORTER:
            REPORTER.update(task='Logging out through the normal countdown')
        quitting = True
        suspend_activity()
        resume_after_revive = None
        await conn.send(protocol['CNE_CZ_ZoneServerSafeQuitReq'], struct.pack('<Ibi', player_id, 0, -1))
        report('Requested normal game logout.', flush=True)

    async def shutdown():
        await logout()
        await asyncio.sleep(15)
        # SafeQuit can be refused during combat. Closing the native connection
        # after a bounded grace period lets the server perform its normal quit.
        await conn.close()

    async def combat_probe():
        # One known learned starter skill against one authored quest target.
        # No automated cast loop until acknowledgements/cooldowns are decoded.
        table_path = Path('/opt/ak-bot-prototype/maps/S_Mission.ini')
        objective = ([item.command for item in parse_quests(table_path)[2008].objectives]
                     if table_path.exists() else [])
        report('Quest objective: ' + json.dumps({'quest': 2008, 'objectives': objective}), flush=True)
        if REPORTER:
            REPORTER.update(quest=2008, task='Quest-only: route to Demon Commander, then use a learned skill')
        await asyncio.sleep(6)
        targets = [(key, value) for key, value in mobs.items() if value['template'] == 20289]
        if len(targets) != 1:
            raise ProtocolError('Authored combat target unavailable')
        target_id, target = targets[0]
        if '--cast-probe' not in sys.argv:
            await walk((210, 178))
            if math.dist(native_position, target['position']) > 3:
                raise ProtocolError('Combat target outside authored melee range')
        await conn.send(protocol['CNE_CZ_ZoneServerSpellCastToLife'], struct.pack('<HIH', 51401, target_id, 0))
        report('Requested one ordinary Sword Slash cast on the tutorial commander.', flush=True)
        await asyncio.wait_for(combat_result.wait(), 12)
        await logout()

    async def spell_test():
        # Lab experiment: the native CheckCanCast gate decides whether the story
        # weapon's spell is usable. Cast at a real hostile actor (the authored
        # Fire Wall is an ordinary killable barrier) because a self target is
        # rejected for every spell and hides the gate's decision.
        await asyncio.sleep(3)
        spell = int(sys.argv[sys.argv.index('--spell-test') + 1])
        flags = ([int(value) for value in sys.argv[sys.argv.index('--spell-flags') + 1].split(',')]
                 if '--spell-flags' in sys.argv else [0])
        await walk((244.5, 97.0))
        await asyncio.sleep(1)
        walls = [(mid, mob) for mid, mob in mobs.items() if mob['template'] == 20724]
        target_id = (min(walls, key=lambda item: math.dist(item[1]['position'], native_position))[0]
                     if walls else player_id)
        report(f'Spell test target is {target_id}.', flush=True)
        for flag in flags:
            await conn.send(protocol['CNE_CZ_ZoneServerSpellCastToLife'],
                            struct.pack('<HIH', spell, target_id, flag))
            report(f'Spell test: spell={spell} target={target_id} control_flag={flag}.', flush=True)
            await asyncio.sleep(2)
        await asyncio.sleep(3)
        await logout()

    async def walk_and_quit():
        if '--equip' in sys.argv:
            await asyncio.wait_for(equipment_ready.wait(), 10)
        await asyncio.sleep(.5)
        x, y, _ = map_state
        destination = (x + 1, y)
        if '--route' in sys.argv:
            at = sys.argv.index('--route')
            destination = float(sys.argv[at + 1]), float(sys.argv[at + 2])
        await walk(destination)
        if '--talk' in sys.argv:
            template = int(sys.argv[sys.argv.index('--talk') + 1])
            candidates = [(mid, mob) for mid, mob in mobs.items() if mob['template'] == template and
                          math.dist(destination, mob['position']) <= 4]
            if len(candidates) != 1:
                raise ProtocolError('Expected one nearby authored NPC')
            await conn.send(protocol['CNE_CZ_ZoneServerTalkToNPC'], struct.pack('<I', candidates[0][0]))
            report('Requested normal NPC interaction: ' + str(template), flush=True)
            await asyncio.sleep(1)
            if '--quest-info' in sys.argv:
                quest_id = int(sys.argv[sys.argv.index('--quest-info') + 1])
                await conn.send(protocol['CNE_CZ_ZoneServerMissionListOp'], struct.pack('<hiH', 1, quest_id, 0))
                report('Requested ordinary quest details: ' + str(quest_id), flush=True)
            await asyncio.sleep(4)
        await logout()

    async def finish_quit(count):
        if not 0 <= count <= 60:
            raise ProtocolError('Unexpected native logout countdown')
        await asyncio.sleep(count + .5)
        await conn.send(protocol['CNE_CZ_ZoneServerSafeQuitCountDownOver'], struct.pack('<h', 0))
        report('Native logout countdown completed.', flush=True)

    async def verify_arrival():
        """Read the relocated pilot's map and quest state, then log out normally."""
        await asyncio.sleep(2)
        if node != 2:
            raise ProtocolError(f'Expected Port Skandia after tutorial skip; got map {node}')
        await quest_session.query()
        await asyncio.sleep(2)
        report(f'Tutorial checkpoint: relocated pilot loaded on Port Skandia at {native_position or map_state[:2]}.', flush=True)
        await logout()

    async def quest_worker(intro=False, background=False):
        nonlocal last_quest, fallback_context, fallback_started
        fallback_started = False
        await asyncio.sleep(2)
        await asyncio.wait_for(alive_event.wait(),35)
        if '--ensure-gear' in sys.argv:
            await ensure_starter_weapon()
        map_dir = Path('/opt/ak-bot-prototype/maps')
        manifest = json.loads((map_dir / 'manifest.json').read_text())
        if str(node) not in manifest:
            raise ProtocolError(f'Map {node} has no packaged collision data')
        graph = json.loads((map_dir / 'portals.json').read_text())
        available = {int(key) for key in manifest}
        world = worldmap.load(map_dir / 'world-index.json')
        portal_blocked = {}
        grid = Grid.read(map_dir / manifest[str(node)]['asset'])
        authored = Scene(map_dir / f'S{node:03}.ini')
        table = parse_quests(map_dir / 'S_Mission.ini')
        weapon = int(sys.argv[sys.argv.index('--weapon') + 1]) if '--weapon' in sys.argv else 1
        reachable = {0} | {spawn['template'] for spawn in authored.spawns.values()}

        def refresh_reachable():
            nonlocal reachable
            reachable = {0} | {spawn['template'] for spawn in authored.spawns.values()}

        def relocate():
            """Rebuild collision and scene data after a native map change."""
            nonlocal grid, authored
            if str(node) not in manifest:
                raise ProtocolError(f'Map {node} has no packaged collision data')
            grid = Grid.read(map_dir / manifest[str(node)]['asset'])
            authored = Scene(map_dir / f'S{node:03}.ini')
            refresh_reachable()
            context.scene, context.grid = authored, grid

        async def travel_to(target):
            """Walk the authored portal graph to `target`, then rebind locals."""
            nonlocal grid, authored
            for _ in range(10):
                if node == target:
                    relocate()
                    return
                path = portals.route(graph, node, target, available, portal_blocked)
                if not path:
                    raise ProtocolError(f'No authored portal route from map {node} to quest map {target}')
                edge = path[0]
                old = node
                if REPORTER:
                    REPORTER.update(task=f'Travelling: map {old} to map {edge["target"]}')
                    REPORTER.emit('info', f'Quest framework: taking authored gateway {old}->{edge["target"]} '
                                          f'(event {edge["event"]}) toward map {target}.')
                crossed = await portals.cross(
                    edge, lambda: node, lambda: native_position, grid.approach, walk,
                    quest_session.send,
                    lambda: asyncio.wait_for(map_ready.wait(), timeout=40))
                if not crossed:
                    portal_blocked[(old, edge['event'])] = time.monotonic() + 120
                    raise ProtocolError(f'Normal gateway {old}->{edge["target"]} did not admit the pilot')
                relocate()
            if node != target:
                raise ProtocolError(f'Portal route did not reach quest map {target}')

        def locate(template):
            """Ask the world index which map currently reachable holds `template`."""
            if world is None:
                return None
            choice = worldmap.choose(world, template, node, graph, available, portal_blocked)
            return choice[0] if choice else None

        async def quest_walk(point):
            # Accept-side scene events open authored barriers on their own
            # schedule (the Andre group walks to the Fire Wall and event 814
            # despawns it). Wait for that live actor to disappear instead of
            # routing through a closed block or skipping the barrier.
            deadline = time.monotonic() + 240
            replayed = 0
            while True:
                grid.obstacles = authored.active_obstacles(mobs)
                try:
                    await walk(grid.approach(point))
                    return
                except ProtocolError:
                    barriers = sorted(authored.live_barriers(mobs))
                    if not barriers or time.monotonic() >= deadline:
                        raise
                    report('Authored barrier(s) ' + str(barriers) +
                           ' still closed; waiting for the scene event to open the route.', flush=True)
                    if replayed < 2 and '--gateway-replay' in sys.argv:
                        # Replay the authored trigger for the scene's
                        # anti-disconnect areas (31/17) so their event chain
                        # re-arms after a reconnect.
                        wanted = (31, 17)[replayed]
                        gateway = next((g for g in authored.gateways.values()
                                        if g['area'] == wanted), None)
                        if gateway is not None:
                            await conn.send(protocol['CNE_CZ_ZoneServerCheckNodeExit'],
                                            struct.pack('<hhi', gateway['trigger'], 0, 0))
                            report(f'Native anti-disconnect replay: trigger {gateway["trigger"]} '
                                   're-arms the authored scene chain.', flush=True)
                        replayed += 1
                        await asyncio.sleep(8)
                    else:
                        await asyncio.sleep(2)

        async def actor_for(template, timeout=10):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                matches = [(mid, mob) for mid, mob in mobs.items() if mob['template'] == template]
                if matches:
                    here = native_position or map_state[:2]
                    return min(matches, key=lambda item: math.dist(item[1]['position'], here))[0]
                await asyncio.sleep(.1)
            visible = sorted({mob['template'] for mob in mobs.values()})
            raise ProtocolError(f'Authored NPC {template} never became visible '
                                f'(visible templates: {visible})')

        async def quest_talk(template):
            if not template:
                return 0
            points = authored.positions(template)
            if not points:
                raise ProtocolError(f'Quest NPC {template} is not authored on map {node}')
            here = native_position or map_state[:2]
            await quest_walk(min(points, key=lambda point: math.dist(point, here)))
            # Turn-in NPCs can appear only after the scene's post-kill cutscene
            # chain (event 709 -> 917 spawns 10330); allow that chain to finish.
            return await actor_for(template, timeout=75)

        context = objectives.Context(
            session=quest_session, combat=quest_combat, scene=authored,
            inventory=quest_inventory, quest=None,
            position=lambda: native_position or (map_state[:2] if map_state else None),
            walk=quest_walk, talk_to=quest_talk, send=quest_session.send,
            report=report, grid=grid, raw_send=conn.send,
            resources=frozenset(json.loads(Path('/opt/ak-bot-prototype/maps/resource-templates.json').read_text())),
            spell=int(sys.argv[sys.argv.index('--spell') + 1])
            if '--spell' in sys.argv else None,
            prepare_combat=(lambda: battle_controller.prepare(quest_session.send)) if battle_controller else None)
        fallback_context = context
        if battle_controller is not None:
            quest_combat.evasion = evasion.Controller(context,
                emit=lambda severity, message: REPORTER.emit(severity, message) if REPORTER else None)

        await quest_session.query()
        starter = quest_inventory.first(30275)
        if starter is not None:
            await conn.send(protocol['CNE_CZ_ZoneServerTalkToNPC'], struct.pack('<I', 0))
            await conn.send(protocol['CNE_CZ_ZoneServerLeaveShop'])
            await conn.send(protocol['CNE_CZ_ZoneServerSwitchItemLocation'],
                            quest_inventory.equip_payload(*starter))
            result = await quest_session.expect('SwitchItemLocationOK', timeout=8)
            if result[-1] != 1:
                raise ProtocolError('Native server rejected equipping the pilot starter weapon')
            quest_inventory.discard(*starter)
            report('Requested ordinary starter weapon equipped before continuing quests.', flush=True)
        history_path = (STATE / 'quest-history.json')
        if history_path.exists():
            history = json.loads(history_path.read_text())
            if history.get('character_id') != player_id:
                raise ProtocolError('Saved quest history belongs to a different character')
            for quest_id, state in history['states'].items():
                if int(state) == 1:
                    quest_session.states.setdefault(int(quest_id), 1)
        if REPORTER:
            REPORTER.update(task='Following authored quests')
        if background:
            async def recover_quest(kind):
                await close_interaction()
                await quest_session.send('EnterNodeInventory')
                await quest_session.send('EnterNodePlayerData')
                await quest_session.query()
            driver_revision = hashlib.sha256(b''.join((Path(__file__).parent / name).read_bytes()
                for name in ('objectives.py', 'movement.py', 'battle.py', 'evasion.py', 'portals.py',
                             'worldmap.py', 'quest_engine.py', 'crafting.py'))).hexdigest()[:12]
            engine = quest_engine.Engine(table, quest_engine.Journal(STATE / 'quest-attempts.json', driver_revision=driver_revision),
                emit=lambda severity, message: REPORTER.emit(severity, message) if REPORTER else None,
                status=lambda **values: REPORTER.update(**values) if REPORTER else None,
                locate=locate, travel=travel_to)
            await engine.run(context, level=lambda: level, weapon=weapon, reachable=lambda: reachable,
                get_node=lambda: node, close=close_interaction, recover=recover_quest)
            return
        for _ in range(60):
            current = [quest for quest in active(table, quest_session.states) if supported(quest)]
            if current:
                quest = current[0]
                if intro and quest.id >= 1008:
                    return
                if quest_session.states[quest.id] == READY:
                    actor = await quest_talk(turn_in_npc(quest))
                    await quest_session.turn_in(actor, quest.id, timeout=25)
                    await close_interaction()
                    report(f'Quest {quest.id} turned in through its authored NPC.', flush=True)
                    local_chat.event('done')
                    last_quest = quest
                    continue
                context.quest = quest
                if REPORTER:
                    REPORTER.update(quest=quest.id,task=f'Quest {quest.id}: working on objectives')
                report(f'Quest {quest.id} active: {quest.title}', flush=True)
                await objectives.run(quest, context)
                report(f'Quest {quest.id} objectives reported ready by the server.', flush=True)
                if REPORTER: REPORTER.update(last_failure='')
                continue
            quest = next_offer(table, quest_session.states, level, weapon, reachable, last_quest, node)
            if quest is None:
                if intro:
                    raise ProtocolError('Companion starter funding paused: no supported introductory quest available')
                report('No supported authored quest remains on this map.', flush=True)
                if NORMAL_WORLD and '--continuous' in sys.argv and not background:
                    await fallback_worker(context, 'No supported quest is currently available')
                break
            if intro and quest.id >= 1008:
                return
            actor = await quest_talk(quest.accept_npc)
            if REPORTER:
                REPORTER.update(quest=quest.id,task=f'Quest {quest.id}: accepting')
            await quest_session.accept(actor, quest.id, timeout=25)
            report(f'Quest {quest.id} accepted: {quest.title}', flush=True)
            last_quest = quest
        if not intro and not background:
            await logout()

    signal_loop = asyncio.get_running_loop() if NORMAL_WORLD else None
    if signal_loop is not None:
        signal_loop.add_signal_handler(signal.SIGTERM,
            lambda: tasks.append(asyncio.create_task(shutdown())))
    try:
        await conn.handshake()
        tasks.append(asyncio.create_task(heartbeat()))
        if learning_store is not None:
            tasks.append(asyncio.create_task(learning_worker()))
        if shared_activity:
            tasks.append(asyncio.create_task(party_target_worker()))
        await conn.send(protocol['CNE_CZ_ZoneServerReceiveTicket'], ticket)
        deadline = (float('inf') if '--continuous' in sys.argv else time.monotonic() +
                    (720 if any(a in sys.argv for a in ('--quest-only', '--quests')) else
                     180 if any(a in sys.argv for a in ('--tutorial', '--combat-probe')) else 90))
        while time.monotonic() < deadline:
            ncid, payload = await conn.receive()
            if ncid == protocol['CNC_CZ_ClientHello']:
                # Hello is also the server's liveness challenge. A periodic
                # client Hello alone does not acknowledge CEventPingAlive.
                await conn.send(protocol['CNE_CZ_ZoneServerEcho'])
            packet_name = reverse.get(ncid)
            if tutorial:
                tutorial.observe(ncid, payload)
            for event in quest_combat.observe(ncid, payload):
                report(event, flush=True)
            if packet_name:
                short = packet_name.removeprefix('CNC_CZ_Client')
                if battle_controller is not None:
                    try:
                        battle_controller.observe(short, payload)
                    except ProtocolError as error:
                        battle_controller.learned.clear()
                        if REPORTER: REPORTER.emit('warning', 'Battle snapshot unavailable: ' + str(error))
                quest_session.observe(short, payload)
                if quest_combat.evasion is not None:
                    quest_combat.evasion.observe(short, payload)
                quest_inventory.observe(short, payload)
            if (shared_activity or '--companion' in sys.argv) and packet_name:
                await observe_party(short, payload)
            if packet_name == 'CNC_CZ_ClientSay' and '--chat' in sys.argv:
                try:
                    speech = Reader(payload)
                    speaker = speech.number('I')
                    channel = speech.number('b')
                    # Native Say carries the text here, not a sender name.
                    message = speech.text()
                    length = speech.number('I')
                    if length > 2048:
                        raise ProtocolError('Oversized chat payload')
                    speech.take(length)
                    if speaker == player_id and REPORTER:
                        REPORTER.emit('info', f'Own chat confirmed by server: {message}')
                    elif channel == 0 and speaker not in (50000002, 50000003):
                        local_chat.hear(str(speaker), message)
                except ProtocolError:
                    pass
            for task in list(tasks):
                if task.done() and not task.cancelled() and task.exception() is not None:
                    if NORMAL_WORLD and '--continuous' in sys.argv and task.get_coro().__name__ in ('quest_worker','fallback_worker','companion_worker'):
                        detail = 'Questing paused: ' + str(task.exception())
                        if REPORTER:
                            REPORTER.emit('error', detail)
                        tasks.remove(task)
                        await close_interaction()
                        if fallback_context is not None and not fallback_started and '--companion' not in sys.argv:
                            tasks.append(asyncio.create_task(fallback_worker(fallback_context, detail)))
                        elif REPORTER:
                            REPORTER.update(phase='paused', task='Activity paused after repeated failures; character remains online')
                        continue
                    report(''.join(traceback.format_exception(
                        type(task.exception()), task.exception(), task.exception().__traceback__)),
                        flush=True)
                    raise ProtocolError('Pilot activity failed: ' + str(task.exception()))
            if ncid not in seen:
                report(f'Zone response: {reverse.get(ncid, ncid)}, payload_length={len(payload)}', flush=True)
                seen.add(ncid)
            if packet_name in {'CNC_CZ_ClientSpellCast', 'CNC_CZ_ClientSpellCastOK',
                               'CNC_CZ_ClientSpellBlastToLife', 'CNC_CZ_ClientSpellHitToLife',
                               'CNC_CZ_ClientRevive', 'CNC_CZ_ClientReviveInfo'} \
                    and spell_logs < 80:
                spell_logs += 1
                report(f'Spell evidence {packet_name}: {payload.hex()}', flush=True)
            if ncid == protocol['CNC_CZ_ClientEnterNodeNodeData']:
                map_ready.clear()
                mobs.clear()
                quest_combat.reset()
                companion_assist.intent = None
                companion_assist.pending_query = None
                loaded.clear()
                migration_done = False
                node, dynamic, auto_pvp, x, y, facing, sync, tower, fairy, times = struct.unpack('<hhbfffIHHh', payload)
                if learning_tracker is not None:
                    learning_tracker.finish('migration')
                    learning_tracker.map_id = node if dynamic == 0 else None
                    learning_tracker.level = None
                    learning_tracker.capability = None
                report(f'Native map entry: node={node}, instance={dynamic}, x={x:.2f}, y={y:.2f}, sync={sync}.', flush=True)
                (STATE / 'map.json').write_text(json.dumps({'node': node, 'dynamic': dynamic, 'x': x, 'y': y, 'sync': sync}))
                map_state = (x, y, sync)
                native_position = (x, y)
                position_observed_at = time.time()
                movement_sync.adopt(sync)
                scene_path = Path('/opt/ak-bot-prototype/maps', f'S{node:03}.ini')
                scene = Scene(scene_path) if scene_path.exists() else None
                entered_gateways.clear()
                if REPORTER:
                    REPORTER.update(map=node, task='Loading the map')
                for request in ('EnterNodePlayerData', 'EnterNodeEquipAndSpell', 'EnterNodeInventory',
                                'EnterNodeShortcut', 'EnterNodeElfInfo', 'EnterNodeCoinsData'):
                    await conn.send(protocol['CNE_CZ_ZoneServer' + request])
            if ncid == protocol['CNC_CZ_ClientEnterNodePlayerData']:
                data = Reader(payload)
                player_id = data.number('I')
                name, ps4, family, group = [data.text() for _ in range(4)]
                movement = data.number('f')
                melee_speed = data.number('B')
                flags = data.take(4)
                level, hp, secondary_resource = data.number('H'), data.number('i'), data.number('i')
                quest_combat.player_id = player_id
                login_hp = hp
                if learning_tracker is not None:
                    learning_tracker.level = level
                if hp > 0:
                    alive_event.set()
                if REPORTER:
                    REPORTER.update(level=level, character_id=player_id, name=name)
                report(f'Native player state: id={player_id}, level={level}, HP={hp}, movement={movement}.', flush=True)
            if ncid in {protocol['CNC_CZ_ClientEnterNodeEquipAndSpell'], protocol['CNC_CZ_ClientEnterNodeInventory']}:
                Path(STATE, 'equipment.bin' if ncid == protocol['CNC_CZ_ClientEnterNodeEquipAndSpell'] else 'inventory.bin').write_bytes(payload)
                if learning_tracker is not None and ncid == protocol['CNC_CZ_ClientEnterNodeEquipAndSpell']:
                    try:
                        from item_stream import equipment
                        gear, _ = equipment(payload)
                        if any(page != 0 for page,slot in gear):
                            raise ProtocolError('Multiple equipment presets require active-preset decoding')
                        signature = [(slot,item.id,item.flags,item.fields) for (page,slot),item in sorted(gear.items())]
                        strategy = ('battle-v1' if battle_controller else
                                    sys.argv[sys.argv.index('--spell')+1] if '--spell' in sys.argv else 'melee')
                        learning_tracker.capability = hashlib.sha256(json.dumps(signature).encode()).hexdigest()[:24] + ':' + strategy
                    except (ProtocolError, ValueError, TypeError):
                        learning_tracker.capability = None
                if learning_tracker is not None and REPORTER:
                    REPORTER.update(learning='recording' if learning_tracker.capability else 'waiting for verified equipment')
                if ncid == protocol['CNC_CZ_ClientEnterNodeInventory']:
                    first = first_inventory_item(payload)
                    if first:
                        quest_inventory.add(first[0], first[1], first[2])
                    report('Native first inventory item: ' + str(first), flush=True)
                    if first and first[2] == 30275:
                        starter_slot = first[:2]
            if learning_tracker is not None and ncid == protocol.get('CNC_CZ_ClientLevelUp'):
                # Do not guess this packet's level offset. Refresh our native
                # player snapshot; recording abstains until it arrives.
                learning_tracker.finish('interrupted')
                learning_tracker.level = None
                await conn.send(protocol['CNE_CZ_ZoneServerEnterNodePlayerData'])
            if (learning_tracker is not None and packet_name == 'CNC_CZ_ClientSwitchItemLocationOK'
                    and len(payload) == 13 and payload[-1] == 1):
                learning_tracker.finish('interrupted')
                learning_tracker.capability = None
                await conn.send(protocol['CNE_CZ_ZoneServerEnterNodeEquipAndSpell'])
            if ncid in {protocol['CNC_CZ_Client' + request] for request in ('EnterNodePlayerData',
                        'EnterNodeEquipAndSpell', 'EnterNodeInventory', 'EnterNodeShortcut',
                        'EnterNodeElfInfo', 'EnterNodeCoinsData')}:
                loaded.add(ncid)
                if len(loaded) == 6 and not migration_done:
                    migration_done = True
                    await conn.send(protocol['CNE_CZ_ZoneServerMigrationDone'])
                    report('Native map-load completion sent.', flush=True)
                    if login_hp is not None and login_hp <= 0:
                        tasks.append(asyncio.create_task(request_revive('login at 0 HP')))
            if ncid == protocol['CNC_CZ_ClientSeeMob']:
                data = Reader(payload)
                mob_id, template, enchant = data.number('I'), data.number('H'), data.number('b')
                mx, my, mz, facing, speed = [data.number('f') for _ in range(5)]
                attack = data.number('b')
                flags = data.number('I')
                name = data.text()
                mobs[mob_id] = {'template': template, 'position': (mx, my)}
                report(f'Native nearby actor: id={mob_id}, template={template}, name={name}, position=({mx:.2f},{my:.2f}), flags={flags}.', flush=True)
            if ncid == protocol['CNC_CZ_ClientMigrationDone'] and any(arg in sys.argv for arg in ('--move', '--route')):
                await conn.send(protocol['CNE_CZ_ZoneServerQueryMissionStates'])
                if '--equip' in sys.argv:
                    if starter_slot is None and '--starter' not in sys.argv:
                        raise ProtocolError('Earned starter weapon not confirmed in current inventory')
                    if starter_slot is not None:
                        tasks.append(asyncio.create_task(equip_starter(*starter_slot)))
                        report('Requested normal equipment transfer of the earned starter weapon.', flush=True)
                tasks.append(asyncio.create_task(walk_and_quit()))
            if ncid == protocol['CNC_CZ_ClientMigrationDone'] and '--starter' in sys.argv:
                if '--recover-starter' in sys.argv:
                    await conn.send(protocol['CNE_CZ_ZoneServerMissionListOp'], struct.pack('<hiH', 5, 2001, 65535))
                    report('Requested ordinary abandonment of the pilot starter quest for reacceptance.', flush=True)
                await conn.send(protocol['CNE_CZ_ZoneServerTalkToNPC'], struct.pack('<i', 0))
                await conn.send(protocol['CNE_CZ_ZoneServerMissionListOp'], struct.pack('<hiH', 9, 2001, 65535))
                report('Requested the normal Sword-and-Shield starter quest screen.', flush=True)
            if ncid == protocol['CNC_CZ_ClientMigrationDone'] and '--abandon-mission' in sys.argv:
                if node != 610:
                    raise ProtocolError('Mission abandonment probe requires the authored starter map')
                tasks.append(asyncio.create_task(abandon_mission()))
            if ncid == protocol['CNC_CZ_ClientMigrationDone'] and '--node-event' in sys.argv:
                if node != 610:
                    raise ProtocolError('Barrier experiment requires the authored starter map')
                tasks.append(asyncio.create_task(node_event()))
            if ncid == protocol['CNC_CZ_ClientMigrationDone'] and '--cross-wall' in sys.argv:
                if node != 610:
                    raise ProtocolError('Barrier experiment requires the authored starter map')
                tasks.append(asyncio.create_task(cross_wall()))
            if ncid == protocol['CNC_CZ_ClientMigrationDone'] and '--break-wall' in sys.argv:
                if node != 610:
                    raise ProtocolError('Barrier experiment requires the authored starter map')
                tasks.append(asyncio.create_task(break_wall()))
            if ncid == protocol['CNC_CZ_ClientMigrationDone'] and '--quests' in sys.argv and not shared_activity:
                if node not in (610, 2):
                    raise ProtocolError('Quest follower currently supports the tutorial and Port Skandia')
                tasks.append(asyncio.create_task(quest_worker()))
            if ncid == protocol['CNC_CZ_ClientMigrationDone'] and '--verify-arrival' in sys.argv:
                tasks.append(asyncio.create_task(verify_arrival()))
            if ncid == protocol['CNC_CZ_ClientMigrationDone'] and '--chat' in sys.argv:
                if not social_started:
                    social_started = True
                    tasks.append(asyncio.create_task(social_worker()))
            if ncid == protocol['CNC_CZ_ClientMigrationDone'] and '--exit-tutorial' in sys.argv and node == 610:
                tasks.append(asyncio.create_task(exit_finished_tutorial()))
            if ncid == protocol['CNC_CZ_ClientMigrationDone'] and '--outfit-only' in sys.argv:
                tasks.append(asyncio.create_task(outfit_only()))
            if ncid == protocol['CNC_CZ_ClientMigrationDone'] and (shared_activity or '--companion' in sys.argv) and not companion_started:
                companion_started=True
                tasks.append(asyncio.create_task(companion_worker()))
            if ncid == protocol['CNC_CZ_ClientMigrationDone'] and any(a in sys.argv for a in ('--tutorial','--quest-only')):
                if node != 610:
                    raise ProtocolError('Tutorial driver requires the authored starter map')
                tutorial = Tutorial(conn, protocol, mobs, walk, logout, report, combat_probe if '--quest-only' in sys.argv else None)
                tasks.append(asyncio.create_task(tutorial.run()))
            if ncid == protocol['CNC_CZ_ClientMigrationDone']:
                map_ready.set()
            if ncid == protocol['CNC_CZ_ClientMigrationDone'] and REPORTER:
                REPORTER.update(phase='online', task='Ready in the normal world' if NORMAL_WORLD else 'Ready in the isolated test world')
            if ncid == protocol['CNC_CZ_ClientMigrationDone'] and '--combat-probe' in sys.argv:
                tasks.append(asyncio.create_task(combat_probe()))
            if ncid == protocol['CNC_CZ_ClientMigrationDone'] and '--spell-test' in sys.argv:
                if node != 610:
                    raise ProtocolError('Spell experiment requires the authored starter map')
                tasks.append(asyncio.create_task(spell_test()))
            if ncid == protocol['CNC_CZ_ClientMigrationDone'] and '--gateways' in sys.argv:
                await check_gateways(map_state[:2])
            if ncid == protocol['CNC_CZ_ClientSpellCastOK'] and len(payload) == 12:
                spell, casting, victim, ok, effect = struct.unpack('<HiiBB', payload)
                report(f'Native skill acknowledgement: spell={spell}, target={victim}, accepted={bool(ok)}, casting_ms={casting}.', flush=True)
                if not ok and '--spell-test' not in sys.argv and not (
                        (battle_controller and spell in (51401, 51402)) or
                        (shared_activity and spell in (62033, 62034))):
                    raise ProtocolError('Native server rejected the pilot skill cast')
                combat_result.set()
            if ncid == protocol['CNC_CZ_ClientCommandFailReturn'] and len(payload) == 8:
                command_id, error_code = struct.unpack('<ii', payload)
                if '--spell-test' in sys.argv or (battle_controller and command_id == 74):
                    report(f'Native command rejected: command={command_id}, error={error_code}', flush=True)
                else:
                    raise ProtocolError(f'Native command rejected: command={command_id}, error={error_code}')
            if ncid == protocol['CNC_CZ_ClientTextOutputIndex'] and len(payload) >= 3:
                text_id, message_type = struct.unpack_from('<hB', payload)
                report(f'Native system message: text_id={text_id}, type={message_type}.', flush=True)
            if ncid == protocol['CNC_CZ_ClientMoveChar']:
                who, mx, my = struct.unpack('<iff', payload)
                if who == player_id:
                    native_position = (mx, my)
                    position_observed_at = time.time()
                    self_move_reports += 1
            if ncid == protocol['CNC_CZ_ClientResetCoord']:
                x, y, sync = struct.unpack('<ffI', payload)
                map_state, native_position = (x, y, sync), (x, y)
                position_observed_at = time.time()
                movement_sync.adopt(sync)
                correction_count += 1
                report(f'Native movement correction: position=({x:.2f},{y:.2f}), sync={sync}; replanning.', flush=True)
            if ncid == protocol['CNC_CZ_ClientSpellCast'] and len(payload) == 24:
                spell, caster, victim, ok, *_ = struct.unpack('<HiiBfffB', payload)
                if caster == player_id:
                    report(f'Native skill acknowledgement: spell={spell}, target={victim}, accepted={bool(ok)}.', flush=True)
                    if not ok and '--spell-test' not in sys.argv and not (
                            (battle_controller and spell in (51401, 51402)) or
                            (shared_activity and spell in (62033, 62034))):
                        raise ProtocolError('Native server rejected the pilot skill cast')
                    combat_result.set()
            if ncid == protocol['CNC_CZ_ClientCantSee'] and len(payload) == 4:
                actor, = struct.unpack('<I', payload)
                mobs.pop(actor, None)
                report(f'Native actor left visibility: id={actor}.', flush=True)
            if ncid == protocol['CNC_CZ_ClientDie'] and len(payload) == 11:
                victim, killer, flags, revive_kind = struct.unpack('<IIBH', payload)
                if victim == player_id:
                    position_observed_at = None
                    killer_mob = quest_combat.mobs.get(killer)
                    if killer_mob is not None:
                        hunting_exclusions[killer_mob.template] = time.monotonic() + 300
                    quest_combat.last_death = (killer_mob.template if killer_mob is not None
                                               else killer, time.monotonic())
                    alive_event.clear()
                    suspend_activity()
                    # The native client answers the death packet with its own
                    # revive request; without one the character stays at 0 HP
                    # across logins and can never act again.
                    tasks.append(asyncio.create_task(
                        request_revive('death packet from ' + str(killer))))
                mobs.pop(victim, None)
            if ncid == protocol.get('CNC_CZ_ClientRevive') and len(payload)>=4:
                if struct.unpack_from('<I',payload)[0] == player_id:
                    alive_event.set()
                    revive_pending = False
                    if REPORTER:
                        REPORTER.emit('info','Native respawn confirmed; character remains connected.')
                        REPORTER.update(phase='paused' if revives > 3 else 'online',
                                        task='Combat paused after repeated deaths' if revives > 3 else 'Recovering after native respawn')
                    if resume_after_revive is not None and revives <= 3:
                        factory, resume_after_revive = resume_after_revive, None
                        tasks.append(asyncio.create_task(resume_activity(factory)))
            if ncid == protocol['CNC_CZ_ClientSafeQuitResp']:
                count, = struct.unpack('<h', payload)
                report(f'Native logout countdown: {count} seconds.', flush=True)
                tasks.append(asyncio.create_task(finish_quit(count)))
            if ncid == protocol['CNC_CZ_ClientMissionStates']:
                data = Reader(payload)
                fms = [(data.number('H'), data.number('H')) for _ in range(data.number('h'))]
                mcn = [(data.number('H'), data.number('h')) for _ in range(data.number('h'))]
                pms = [(data.number('Q'), data.number('H')) for _ in range(data.number('h'))]
                report('Native quest-state prefix: ' + str({'final_nonzero': [(k,v) for k,v in fms if v], 'counts': mcn, 'personal': pms}), flush=True)
                (STATE / 'quests.bin').write_bytes(payload)
            if ncid == protocol['CNC_CZ_ClientEnterMissionList']:
                kind, quest, npc, complete = parse_mission_list(payload)
                report('Native quest UI: ' + str((kind, quest, npc, complete)) +
                       f' ({len(payload)} bytes)', flush=True)
                if '--turn-in-starter' in sys.argv and kind == 2 and quest == 2001:
                    await conn.send(protocol['CNE_CZ_ZoneServerMissionListOp'], struct.pack('<hiH', 2, 2001, 65535))
                    report('Requested ordinary starter quest reward claim; server checks its objective.', flush=True)
                if '--starter' in sys.argv and kind == 1 and quest == 2001 and not starter_requested:
                    starter_requested = True
                    await conn.send(protocol['CNE_CZ_ZoneServerMissionListOp'], struct.pack('<hiH', 1, 2001, 65535))
                    report('Accepted the native starter weapon quest.', flush=True)
            if ncid == protocol['CNC_CZ_ClientPutItemIntoInventory']:
                (STATE / 'last-item.bin').write_bytes(payload)
                report('Native earned item delivered; payload length=' + str(len(payload)), flush=True)
                if '--equip' in sys.argv and len(payload) >= 8:
                    bag, slot, item = struct.unpack_from('<hhI', payload)
                    if item == 30275 and 0 <= bag < 5 and 0 <= slot < 30:
                        tasks.append(asyncio.create_task(equip_starter(bag, slot)))
                        report('Requested normal equipment transfer of newly earned starter weapon.', flush=True)
            if ncid == protocol['CNC_CZ_ClientDisplayDialogView']:
                (STATE / 'dialogue.bin').write_bytes(payload)
                data = Reader(payload)
                dialogue_id = data.number('i')
                options = [(data.number('i'), data.text(), data.number('h')) for _ in range(data.number('h'))]
                kind, npc = data.number('b'), data.number('i')
                data.end()
                report('Native dialogue: ' + str({'id': dialogue_id, 'options': options, 'type': kind, 'npc': npc}), flush=True)
                if '--turn-in-starter' in sys.argv and npc == 10204:
                    matches = [i for i, option in enumerate(options) if option[1] == '2001']
                    if len(matches) == 1:
                        await conn.send(protocol['CNE_CZ_ZoneServerReplyDialog'], struct.pack('<h', matches[0]))
            if ncid == protocol['CNC_CZ_ClientUpdateMissionState']:
                kind, quest, state, *_ = struct.unpack('<bQHhhhh', payload)
                if NORMAL_WORLD and kind == 0 and state == 1:
                    # Cache only server-confirmed completion hints for reconnect
                    # planning. NPCs and native mission state remain authoritative.
                    history_path = STATE / 'quest-history.json'
                    try:
                        history = json.loads(history_path.read_text()) if history_path.exists() else {
                            'character_id': player_id, 'states': {}}
                        if history.get('character_id') != player_id:
                            raise ProtocolError('Quest history identity mismatch')
                        history['states'][str(quest)] = 1
                        temporary = history_path.with_suffix('.tmp')
                        temporary.write_text(json.dumps(history))
                        temporary.chmod(0o600)
                        temporary.replace(history_path)
                    except (OSError, ValueError) as error:
                        if REPORTER: REPORTER.emit('warning', 'Completion hint could not be saved: ' + type(error).__name__)
                if REPORTER and kind == 0:
                    REPORTER.update(quest=quest, task=f'Quest {quest}: ' + {1:'completed',3:'accepted',4:'ready to turn in'}.get(state, f'state {state}'))
                report('Native quest update: ' + str(struct.unpack('<bQHhhhh', payload)), flush=True)
            if ncid == protocol['CNC_CZ_ClientPotentialPointUpdate']:
                view = potential_module.decode_update(payload)
                if view is None:
                    report('Native potential snapshot in a foreign format; left untouched.', flush=True)
                else:
                    report('Native potential page ' + str(view['page']) + ': slots=' +
                           str(view['slots']) + ', free=' + str(view['free']) + '.', flush=True)
                    confirmed = potential_allocator.observe(view)
                    if confirmed:
                        report(f'Native potential allocation confirmed: page={view["page"]}, '
                               f'slots={view["slots"]}, free={view["free"]}.', flush=True)
                    if '--spend-potential' in sys.argv:
                        additions = potential_allocator.request(view)
                        if additions:
                            await conn.send(protocol['CNE_CZ_ZoneServerPotentialPointUpdate'],
                                            potential_module.build_allocation(view['page'], additions))
                            report(f'Native potential allocation requested: spending {sum(additions)} free '
                                   f'{"attack" if view["page"] == 0 else "defense"}-tree points '
                                   f'over slots {additions}.', flush=True)
                    if REPORTER:
                        REPORTER.update(potential=potential_allocator.summary())
            if ncid == protocol['CNC_CZ_ClientSwitchItemLocationOK']:
                transfer = struct.unpack('<hhhhhhB', payload)
                report('Native equipment transfer result: ' + str(transfer), flush=True)
                if transfer[-1] != 1 and battle_controller is None:
                    raise ProtocolError('Native server rejected equipment transfer')
                equipment_ready.set()
            if ncid == protocol['CNC_CZ_ClientTicketInvalid']:
                raise ProtocolError('Zone ticket rejected; reason=' + str(int.from_bytes(payload, 'little')))
    except ProtocolError as exc:
        if not (quitting and 'closed' in str(exc)):
            raise
        report('Native server closed the pilot session after logout.', flush=True)
    finally:
        if signal_loop is not None:
            signal_loop.remove_signal_handler(signal.SIGTERM)
        if learning_tracker is not None:
            learning_tracker.finish('disconnect')
        if learning_store is not None:
            learning_store.close()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        (STATE / 'last-observation.json').write_text(json.dumps({'moved': moved, 'quitting': quitting,
            'native_position': native_position, 'map': node if map_state else None, 'time': time.time()}))
        await conn.close()


async def world_session(ticket):
    protocol = json.loads((STATE / 'world-protocol.json').read_text())
    reverse = {v:k for k,v in protocol.items() if k.startswith('CNC_CW_') and isinstance(v, int)}
    reader, writer = await asyncio.open_connection(server_ip(), 5567, local_addr=('127.0.0.1', 0))
    conn = Connection(reader, writer)
    creating = False
    named = False
    keepalive = None
    try:
        await conn.handshake()
        await conn.send(protocol['CNC_CW_ServerReceiveTicket'], ticket + string('127.0.0.1'))
        for _ in range(64):
            ncid, payload = await conn.receive()
            report(f'World response: {reverse.get(ncid, ncid)}, payload_length={len(payload)}', flush=True)
            if ncid == protocol['CNC_CW_ClientGetCharacters']:
                data = Reader(payload)
                state, count = data.number('b'), data.number('B')
                report(f'Native character selection: state={state}, count={count}.', flush=True)
                if state == 0 and count == 0 and not creating:
                    creating = True
                    await conn.send(protocol['CNC_CW_ServerCreateCharacterName'],
                                    string(normal_config()['character_name'] if NORMAL_WORLD else 'AwanBotLab') + string('Merrilee') + struct.pack('<I', 0xffffffff))
                elif count:
                    char_id = data.number('I')
                    name = data.text()
                    if NORMAL_WORLD and name != normal_config()['character_name']:
                        raise ProtocolError('Refusing to control an unexpected normal-world character')
                    report(f'Native character present: id={char_id}, name={name}.', flush=True)
                    (STATE / 'character.json').write_text(json.dumps({'id': char_id, 'name': name}))
                    if '--create-only' in sys.argv:
                        break
                    if ((not creating) and
                        (('--discard-invalid-pilot' in sys.argv and char_id == 50000004) or
                         ('--recreate-pilot' in sys.argv and char_id in (50000003, 50000004, 50000005))) and name == 'AwanBotLab'):
                        await conn.send(protocol['CNC_CW_ServerRemoveCharacter'], struct.pack('<i', char_id) + string(''))
                    else:
                        await conn.send(protocol['CNC_CW_ServerLoginCharacter'],
                                        struct.pack('<I', char_id) + string('127.0.0.1') + b'\x01')
            if ncid == protocol['CNC_CW_ClientReceiveTicketToZoneServer']:
                if len(payload) != 22:
                    raise ProtocolError('Unexpected zone ticket length')
                (STATE / 'zone-ticket.bin').write_bytes(payload)
                report('Native zone ticket received; contents withheld.', flush=True)
                if '--create-only' not in sys.argv:
                    keepalive = asyncio.create_task(keep_session_alive(
                        conn, protocol['CNC_CW_ServerKeepAlive'], world_keepalive_payload()))
                    await zone_session(payload)
                break
            if ncid == protocol['CNC_CW_ClientVerifyCharacterName']:
                data = Reader(payload)
                result, kind = data.number('h'), data.number('b')
                data.end()
                report(f'Native name/creation validation: result={result}, type={kind}.', flush=True)
                if result != 0:
                    raise ProtocolError('Native creation rejected: ' + str(result))
                if creating and not named:
                    named = True
                    await asyncio.sleep(1)
                    # Sword-and-shield flag, normal race/class, standard starter.
                    appearance = struct.pack('<QQQQ', 0, 0, 0, sum(1 << shift for shift in (6, 12, 18, 24, 30)))
                    await conn.send(protocol['CNC_CW_ServerCreateCharacterData'],
                                    struct.pack('<IBBBHHH', 2, 0, 0, 2, 65535, 0, 0) + appearance + b'\x00')
            if ncid == protocol['CNC_CW_ClientTicketInvalid']:
                raise ProtocolError('World ticket rejected; reason=' + str(int.from_bytes(payload, 'little')))
            if ncid == protocol['CNC_CW_ClientException']:
                report('Native world exception fields: ' + str([int.from_bytes(payload[i:i+2], 'little') for i in range(0, len(payload), 2)]))
    finally:
        if keepalive is not None:
            keepalive.cancel()
            await asyncio.gather(keepalive, return_exceptions=True)
        await conn.close()


async def main():
    global REPORTER
    if '--learned-targets' in sys.argv and '--encounter-learning' not in sys.argv:
        raise SystemExit('--learned-targets requires --encounter-learning')
    if '--encounter-learning' in sys.argv and not NORMAL_WORLD:
        raise SystemExit('Encounter learning requires an explicitly authorized normal-world bot profile')
    marker = Path('/run/ak-bot-lab.json')
    if NORMAL_WORLD:
        config = normal_config()
        if any(x in sys.argv for x in ('--recreate-pilot','--discard-invalid-pilot','--recover-starter')):
            raise SystemExit('Destructive lab options are forbidden in the normal world')
        identity = json.loads((STATE / 'identity.json').read_text())
        if identity['username'] != config['username'] or identity['account_id'] != config['account_id']:
            raise SystemExit('Normal-world identity mismatch')
    elif not marker.is_file() or json.loads(marker.read_text())['netns'] != os.readlink('/proc/self/ns/net'):
        raise SystemExit('Probe requires isolated lab namespace')
    if os.geteuid() == 0:
        raise SystemExit('Run probe as unprivileged nobody user')
    REPORTER = Reporter(STATE, 'normal' if NORMAL_WORLD else 'isolated')
    REPORTER.update(world='normal' if NORMAL_WORLD else 'isolated')
    identity = json.loads((STATE / 'identity.json').read_text())
    protocol = json.loads((STATE / 'protocol.json').read_text())
    reader, writer = await asyncio.wait_for(asyncio.open_connection('127.0.0.1', 6543), 5)
    conn = Connection(reader, writer)
    keepalive = None
    try:
        bits = await conn.handshake()
        report(f'Native encrypted session established ({bits}-bit public key).', flush=True)
        await conn.send(protocol['CNC_CL_ServerLoginAccount'], string(identity['username']) +
                        string(hashlib.md5(identity['password'].encode()).hexdigest()) + string('015.001.01.16'))
        for _ in range(8):
            ncid, payload = await conn.receive()
            # Packet bytes may contain session tickets: metadata only.
            report(f'Native response: command={ncid}, payload_length={len(payload)}', flush=True)
            if ncid == protocol['CNC_CL_ClientLoginFail']:
                report('Login rejected; fail code=' + str(int.from_bytes(payload[:4], 'little')))
                break
            if ncid == protocol['CNC_CL_ClientGetWorldServers']:
                data = Reader(payload)
                count = data.number('h')
                if not 1 <= count <= 20:
                    raise ProtocolError('Unexpected world count')
                worlds = []
                for i in range(count):
                    world = {'id': data.number('h'), 'name': data.text(), 'ip_raw': data.number('I'),
                             'ip': data.text(), 'port': data.number('h'), 'online': data.number('i')}
                    world['flags'] = [data.number('h') for _ in range(7)]
                    worlds.append(world)
                data.number('h')  # last selected world
                data.number('b')  # population-block flag
                data.end()
                selected = worlds[0]
                report(f"Authenticated: {count} world(s); selected={selected}.")
                await conn.send(protocol['CNC_CL_ServerLoginWorld'], struct.pack('<h', selected['id']) +
                                string(identity['username']) + string(hashlib.md5(identity['password'].encode()).hexdigest()))
            if ncid == protocol['CNC_CL_ClientReceiveTicketToWorldServer']:
                if len(payload) != 22:
                    raise ProtocolError('Unexpected ticket size')
                (STATE / 'ticket.bin').write_bytes(payload)
                report('World ticket received and stored privately; contents withheld.')
                keepalive = asyncio.create_task(keep_session_alive(conn, protocol['CNC_CL_ServerHello'], string('')))
                await world_session(payload)
                break
    except ProtocolError as exc:
        report('Protocol probe stopped: ' + str(exc), flush=True)
    except Exception as exc:
        REPORTER.emit('error', 'Test stopped unexpectedly: ' + type(exc).__name__)
        raise
    finally:
        if keepalive is not None:
            keepalive.cancel()
            await asyncio.gather(keepalive, return_exceptions=True)
        await conn.close()
        if REPORTER.state['phase'] != 'failed':
            REPORTER.update(phase='stopped', task='Test session ended')
            REPORTER.emit('info', 'Test session ended')


if __name__ == '__main__':
    asyncio.run(main())
