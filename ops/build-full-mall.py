"""Build the full F2P item-mall catalog (marker codex:mall-f2p:v1).

Reads server S_Item.ini/S_ItemMall.ini and client C_Item.ini/C_ItemMall.ini,
filters debug/dev/GM stock, categorizes every remaining purchasable item into
the 43 client label slots (ids 61001-61043), and prices each row with the
approved quality+level curve.  Output: docs/mall-f2p-catalog.json (staging only;
deploy with ops/install-full-mall.py).
"""
from pathlib import Path
import collections, json, re

root = Path(__file__).resolve().parent.parent
MARKER = 'codex:mall-f2p:v1'
GROUP = 6
MAX_SLOTS = 43
PRICE_CAP = 10000

# ---------------------------------------------------------------- slots/labels
SLOTS = {
    1: 'Dual Blades', 2: 'Sword and Shield', 3: 'Axes', 4: 'Staves',
    5: 'Dual Pistols', 6: 'Cannons', 7: 'Grimoires', 8: 'Harps', 9: 'Katars',
    10: 'Bows', 11: 'Tachi', 12: 'Scythes', 13: 'Holy Swords',
    14: 'Shurikens', 15: 'Lances', 16: 'Guitars', 17: 'Dragon Puppets',
    18: 'Whips',
    19: 'Helmets', 20: 'Body Armor', 21: 'Waistguards', 22: 'Gloves',
    23: 'Boots', 24: 'Cloaks',
    25: 'Mounts', 26: 'Pets & Hatchlings', 27: 'Consumables',
    28: 'Materials', 29: 'Secret Stones', 30: 'Enchant & Fortification',
    31: 'Eidolon Keys', 32: 'Eidolon Treasures', 33: 'Duel Cards',
    34: 'Crafting Recipes', 35: 'Cores', 36: 'Legendary Gear Bags',
    37: 'Crates & Bags', 38: 'Furniture & Garden', 39: 'Fashion, Gifts & Wings',
    40: 'Head Costumes', 41: 'Body Costumes', 42: 'Prize Gear',
    43: 'Fishing & Cooking Gear',
}
assert len(SLOTS) == MAX_SLOTS == max(SLOTS)

WEAPON_TYPES = list(range(7, 25))
TYPE_MAP = {typ: slot for slot, typ in enumerate(WEAPON_TYPES, start=1)}
TYPE_MAP.update({typ: slot for slot, typ in enumerate(range(1, 7), start=19)})
TYPE_MAP.update({
    41: 25,                          # mounts
    42: 26, 92: 26,                  # pet feed, hatchlings
    57: 27, 69: 27, 87: 27, 97: 27, 98: 27, 109: 27,   # consumables (silver)
    58: 28, 61: 28, 71: 28, 72: 28, 73: 28, 74: 28, 77: 28,  # materials
    59: 29,                          # secret stones
    60: 30, 64: 30, 68: 30, 79: 30,  # enchant & fortification
    63: 31, 70: 31,                  # eidolon keys / fragments
    78: 32, 99: 32, 95: 32,          # eidolon treasures + formulas
    81: 33, 100: 33,                 # duel cards + breakthrough devices
    67: 34, 75: 34, 76: 34,          # crafting recipes / fusion formulas
    65: 35, 66: 35,                  # cores
    62: 36,                          # unidentified legendary gear
    91: 37, 104: 37, 56: 37, 43: 37, # crates / boxes / bags
    89: 38, 90: 38, 96: 38,          # furniture / blueprints / saplings
    94: 39, 33: 39, 35: 39,          # fashion accessories, back display, wings
    32: 40,                          # head costumes
    34: 41,                          # body costumes
    31: 42,                          # prize gear (Torian's sets etc.)
    7001: 43, 7002: 43, 7003: 43, 7004: 43, 7005: 43, 7006: 43,
    7007: 43, 7008: 43,              # fishing gear + cooking tools
})
MISC = 43
SILVER_SLOTS = {27}                  # consumables -> silver (bind gold) wallet
GEAR_TYPES = set(range(1, 7)) | set(range(7, 25)) | {31, 32, 33, 34, 35, 37, 38, 39, 40}

# ---------------------------------------------------------------- records
def records(path, fields=None):
    out = {}
    for chunk in re.split(r'(?m)(?=^\d+\|)', path.read_bytes().decode('cp950', errors='replace'))[1:]:
        row = chunk.rstrip().split('|')
        if fields is None or len(row) == fields:
            try:
                out[int(row[0])] = row
            except ValueError:
                pass
    return out


def item_records(paths):
    data = {}
    for path in paths:
        for ident, row in records(path, 67).items():
            if ident in data and data[ident][8] != row[8]:
                raise RuntimeError('Conflicting item type for %d' % ident)
            data[ident] = row
    return data

# ---------------------------------------------------------------- pricing
BASE_BY_SLOT = {
    **{s: 12 for s in range(1, 19)},     # weapons
    **{s: 8 for s in range(19, 25)},     # armor
    25: 100, 26: 30, 27: 2, 28: 3, 29: 8, 30: 20, 31: 40,
    32: 60, 33: 5, 34: 15, 35: 25, 36: 200, 37: 50, 38: 25,
    39: 80, 40: 60, 41: 80, 42: 400, 43: 12,
}
CONSUMABLE_TIERS = [
    (r'(?i)\bsuper(?:ior)?\b', 20), (r'(?i)\badvanced\b', 16),
    (r'(?i)\brefined\b', 12), (r'(?i)\blarge\b', 10),
    (r'(?i)\bmedium\b', 5), (r'(?i)\bsmall\b', 2), (r'(?i)\btiny\b', 1),
    (r'(?i)\b(?:fragment|dust)\b', 2), (r'(?i)\bcrystal\b', 10),
]
# Slot 31 covers fragments (63) and full Keys of Gaia (70); the keys price
# higher than slot base 40 per the approved 100-1,000 curve.
TYPE_BASE = {63: 40, 70: 150}
RARE_KEYWORDS = [
    (r'(?i)\blegendary\b', 6.0), (r'(?i)\bmythical\b', 5.0),
    (r'(?i)\bexotic\b', 2.5), (r'(?i)\bdivine\b', 2.5), (r'(?i)\brare\b', 2.0),
]
DEBUG_FILTER = re.compile(
    r'(?i)\btest(?:ing|er)?\b|undefined|reserved|occupied|japanese|dev only'
    r'|do not use|\[gm\]|test field|\bdummy\b|\bsubtest\b')


def level_of(row, title):
    """Required level from the item row, else 'Lv.' in the title, else 0."""
    if row[13].strip().isdigit():
        value = int(row[13])
        return value if value <= 150 else min(value, 150)
    match = re.search(r'(?i)lv\.?\s*(\d{1,3})', title)
    if match:
        return min(int(match.group(1)), 150)
    return 0


def price_of(slot, level, title, typ=None):
    base = TYPE_BASE.get(typ) if typ is not None else None
    if base is None:
        base = BASE_BY_SLOT.get(slot, 3)
    band = 1.0 + level / 25.0
    factor = band
    if slot == 27:                       # consumables: tier over level
        factor = 1.0
        for pattern, value in CONSUMABLE_TIERS:
            if re.search(pattern, title):
                factor = value
                break
        factor *= (1.0 + level / 50.0)
    else:
        for pattern, value in RARE_KEYWORDS:
            if re.search(pattern, title):
                factor *= value
                break
    price = int(round(base * factor))
    return min(max(price, 1), PRICE_CAP)


def main():
    server = item_records([
        root / 'staging/ultimate/hxsy/Data/db/S_Item.ini',
        root / 'staging/ultimate/hxsy/Data/db/S_ItemMall.ini'])
    client = item_records([
        root / 'client/Requiem Aurakingdom/data/db/C_Item.ini',
        root / 'client/Requiem Aurakingdom/data/db/C_ItemMall.ini'])
    names = {}
    for ident, row in records(root / 'client/Requiem Aurakingdom/data/db/T_Item.ini').items():
        if len(row) > 1:
            names.setdefault(ident, row[1].strip())

    dropped_debug = 0
    catalog = []
    for ident, row in sorted(server.items()):
        other = client.get(ident)
        title = names.get(ident, '')
        if not title or not other or row[8] != other[8] or not 1 <= ident <= 65535:
            continue
        if not row[1] or not row[1].strip():
            continue
        if DEBUG_FILTER.search(title) or DEBUG_FILTER.search(row[1]):
            dropped_debug += 1
            continue
        typ = row[8]
        if not typ.isdigit():
            continue
        level = level_of(row, title)
        slot = TYPE_MAP.get(int(typ), MISC)
        catalog.append({
            'id': ident, 'type': int(typ), 'title': title, 'level': level,
            'detail_type': slot, 'money_unit': 2 if slot in SILVER_SLOTS else 1,
            'price': price_of(slot, level, title, int(typ)),
        })
    catalog.sort(key=lambda r: (r['detail_type'], r['type'], r['level'], r['id']))
    counts = collections.Counter(r['detail_type'] for r in catalog)
    for slot in sorted(counts):
        assert counts[slot] < 32767
    indexes = collections.Counter()
    for row in catalog:
        indexes[row['detail_type']] += 1
        row['index'] = indexes[row['detail_type']]

    used = sorted(counts)
    output = {
        'marker': MARKER, 'item_group': GROUP,
        'label_ids': {str(k): (61000 + k) for k in used},
        'slots': {str(k): SLOTS[k] for k in used},
        'counts': {str(k): counts[k] for k in used},
        'silver_slots': sorted(SILVER_SLOTS & set(counts)),
        'items': [{k: row[k] for k in
                   ('id', 'type', 'title', 'level', 'detail_type', 'index',
                    'money_unit', 'price')} for row in catalog],
    }
    (root / 'docs/mall-f2p-catalog.json').write_text(json.dumps(output, indent=1))
    silver = sum(r['price'] for r in catalog if r['money_unit'] == 2)
    print(json.dumps({
        'items': len(catalog), 'types_total': len(server),
        'dropped_debug': dropped_debug, 'slots_used': {str(k): counts[k] for k in used},
        'unused_slots': sorted(set(SLOTS) - set(counts)),
        'silver_items': sum(1 for r in catalog if r['money_unit'] == 2),
        'silver_total': silver,
        'min_price': min(r['price'] for r in catalog),
        'max_price': max(r['price'] for r in catalog),
    }, indent=1))


if __name__ == '__main__':
    main()
