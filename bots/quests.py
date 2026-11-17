"""Deterministic quest selection from the mission table plus live mission states.

The server is the authority on what an NPC offers. This module only decides
which NPC is worth visiting next and which of the *supported* objectives to
drive, so a rejected or hidden offer costs one dialog and no invented progress.

Conditions are evaluated conservatively:

    If_FMS <ids> done   at least one listed quest finished (weapon variants)
    If_CharLevel 1 <n>  character level >= n
    If_CharLevel 2 <n>  character level == n
    If_CheckWeapon <n>  n matches the character's weapon index

Anything else is treated as satisfied; if the server disagrees it simply will
not list the quest, and the next candidate is tried.
"""
from dataclasses import dataclass
from content import Quest
from npc import ACTIVE, FINISHED, READY


SUPPORTED = frozenset({'equip', 'talk', 'kill', 'collect_drop', 'collect',
                       'travel', 'buff', 'level', 'deliver', 'use_item'})
MAIN_LINE = '主線'


def _quest_ids(condition):
    result = []
    for arg in condition.args:
        for word in str(arg).split(';'):
            if word.lstrip('-').isdigit():
                result.append(int(word))
    return result


def condition_holds(condition, states, level, weapon):
    name, args = condition.name, condition.args
    if name == 'If_FMS':
        ids = _quest_ids(condition)
        return not ids or any(states.get(quest) == FINISHED for quest in ids)
    if name == 'If_CharLevel' and len(args) >= 2:
        operation, value = int(args[0]), int(args[1])
        if operation == 1:
            return level >= value
        if operation == 2:
            return level == value
        return True
    if name == 'If_CharLevelExp' and len(args) >= 2:
        # Authored as `op level exp`; only `op 1` exists and means level >= value.
        return level >= int(args[1])
    if name == 'If_CheckWeapon' and args:
        return weapon is None or int(args[0]) == weapon
    if name == 'If_CheckNotWeapon' and args:
        return weapon is None or weapon not in _quest_ids(condition)
    return True


def unlocked(quest, states, level=1, weapon=None):
    return all(condition_holds(condition, states, level, weapon)
               for condition in quest.conditions)


def supported(quest):
    return all(objective.kind in SUPPORTED for objective in quest.objectives)


def finishable(quest, states, level=1, weapon=None, node=None):
    """Unlocked, has drivers for every objective, and is not in flight/finished.

    `accept_npc == 0` means the quest is started through the map's mission
    board, so it only counts as an offer on the map named in the table.
    """
    if node is not None and quest.accept_npc == 0 and quest.node != node:
        return False
    return (unlocked(quest, states, level, weapon) and supported(quest)
            and states.get(quest.id) not in (ACTIVE, READY, FINISHED))


def priority(quest):
    """Main line before side quests, then authored id; ties are impossible."""
    return (quest.category != MAIN_LINE, quest.id)


def offers(quests, states, level=1, weapon=None, npcs=None, node=None):
    """Every quest this character could accept from a reachable NPC right now."""
    result = [quest for quest in quests.values()
              if quest.accept_npc is not None
              and (npcs is None or quest.accept_npc in npcs)
              and finishable(quest, states, level, weapon, node)]
    return sorted(result, key=priority)


def offer_at(quests, npc, states, level=1, weapon=None, node=None):
    """The next quest the given NPC should be offering, if any."""
    result = [quest for quest in quests.values()
              if quest.accept_npc == npc
              and finishable(quest, states, level, weapon, node)]
    return sorted(result, key=priority)


def next_offer(quests, states, level=1, weapon=None, npcs=None, after=None, node=None):
    """The canonical next offer, preferring the chain that follows `after`."""
    if after is not None:
        chained = offer_at(quests, after.return_npc, states, level, weapon, node)
        if chained:
            return chained[0]
    candidates = offers(quests, states, level, weapon, npcs, node)
    return candidates[0] if candidates else None


def turn_in_npc(quest):
    return quest.return_npc or quest.accept_npc


def active(quests, states):
    """Quests in flight, ready-to-turn-in first, then by id."""
    result = [quests[quest] for quest, state in states.items()
              if quest in quests and state in (ACTIVE, READY)]
    return sorted(result, key=lambda quest: (states[quest.id] != READY, quest.id))


@dataclass(frozen=True)
class Objective:
    """One authored objective plus the quest it belongs to."""
    quest: int
    index: int
    kind: str
    args: tuple
    command: str


def objective_plan(quest):
    return tuple(Objective(quest.id, index, objective.kind, objective.args, objective.command)
                 for index, objective in enumerate(quest.objectives))


def progress_by_kind(quest):
    """Authored totals per objective kind, useful for logging a quest's shape."""
    totals = {}
    for objective in quest.objectives:
        totals[objective.kind] = totals.get(objective.kind, 0) + 1
    return totals
