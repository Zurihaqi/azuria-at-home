"""Data-driven grind target selection from the native biology table.

Nothing here hardcodes template identities. The catalog is derived from the
server's own S_Biology.ini (`catalog_from_biology`, invoked by the deploy
script because only root may read the data directory):

    {"<template>": {"level": L, "hp": H}, ...}   hostile class-2 rows only

Column evidence (Port Skandia rows):

  col6 == '2'  hostile actor class. assist.hostile_templates reads the same
               field, and it excludes everything a levelling bot should not
               attack: friendly objects (quest mound 40336, class 5), worried
               NPCs (class 1) and the stat-packed quest bosses (41165 is
               class 3, its kin 41071 class 4) whose attr far exceeds a bot.
  col8         the authored enemy level
  col11        behaviour bitmask; bit48 marks special staged actors
  col20        the HP baseline every instance of the template spawns with

Selection rules, verified against live ZoneServer behaviour:

  eligibility  the template has an authored spawn on the bot's current map and
               its level is at or below the bot's level
  elite filter bit48 actors and baseline HP above `ELITE_RATIO` times the
               median candidate HP are skipped (ordinary level bands sit
               within ~2.2x of one another, e.g. level 7's 301 vs 752; the
               staged outlier 44576 holds 3471 against 519-rated peers).
               With too few candidates to expose an outlier this sieve passes
               everything; the runtime death-based hunting_exclusions remain
               the authoritative guard
  ordering     strongest level first, then smaller template id, so grinding
               fights the most rewarding fodder the bot can survive
"""
import json
from pathlib import Path
import re
import statistics

BIT_SPECIAL = 1 << 48
ELITE_RATIO = 2.5
MIN_ENEMY_LEVEL = 1


def catalog_from_biology(path):
    """Template -> {level, hp, special} for every hostile class-2 row."""
    text = Path(path).read_bytes().decode('cp950', errors='surrogateescape')
    result = {}
    for block in re.split(r'(?m)(?=^\d+\|)', text)[1:]:
        fields = block.rstrip().split('|')
        if len(fields) <= 20 or fields[6] != '2':
            continue
        try:
            template, level, hp, mask = int(fields[0]), int(fields[8]), int(fields[20]), int(fields[11])
        except ValueError:
            continue
        if level >= MIN_ENEMY_LEVEL and hp > 0:
            result[template] = dict(level=level, hp=hp, special=bool(mask & BIT_SPECIAL))
    return result


def load_catalog(path):
    """Load the prebuilt catalog; missing or malformed data disables grinding."""
    try:
        raw = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    result = {}
    for template, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        level, hp = entry.get('level'), entry.get('hp')
        if (str(template).isdigit() and isinstance(level, int) and isinstance(hp, int)
                and level >= MIN_ENEMY_LEVEL and hp > 0):
            special = entry.get('special')
            result[int(template)] = dict(level=level, hp=hp, special=special is True)
    return result


def targets(catalog, level, present):
    """Ordinary, level-appropriate templates available on the current map.

    `present` is the set of templates with an authored spawn on the bot's
    current map (scene.spawns). Returned templates are ordered by descending
    enemy level, ascending id.
    """
    candidates = [(template, entry) for template, entry in catalog.items()
                  if template in present and entry['level'] <= level]
    if not candidates:
        return []
    median = statistics.median(entry['hp'] for _, entry in candidates)
    ordinary = [(template, entry) for template, entry in candidates
                if not entry['special'] and entry['hp'] <= median * ELITE_RATIO]
    return [template for template, _ in
            sorted(ordinary, key=lambda pair: (-pair[1]['level'], pair[0]))]
