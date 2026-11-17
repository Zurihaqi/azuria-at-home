import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import grind

BIOLOGY_ROW = '{0}|E{1}|name|x|y|graph|{2}|flag|{3}|a|b|{4}|d|e|f|g|h|i|j|k|{5}|tail\n'
SPECIAL_BIT = 1 << 48


def catalog(entries):
    """Entries are (template, level, hp, special) tuples."""
    return {template: dict(level=level, hp=hp, special=special)
            for template, level, hp, special in entries}


def ordinary(template, level, hp):
    return (template, level, hp, False)


class CatalogTests(unittest.TestCase):
    def test_hostile_rows_are_indexed_from_the_biology_table(self):
        path = Path(__file__).resolve().parent / 'grind.tmp.ini'
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        path.write_text(
            BIOLOGY_ROW.format(40326, 'Fairy', 2, 6, 0, 248) +
            BIOLOGY_ROW.format(41165, 'Boss', 3, 7, SPECIAL_BIT, 3008) +
            BIOLOGY_ROW.format(41071, 'Kin', 4, 3, SPECIAL_BIT, 4149) +
            BIOLOGY_ROW.format(40336, 'Mound', 5, 1, SPECIAL_BIT, 1) +
            BIOLOGY_ROW.format(10210, 'NPC', 1, 1, 0, 5),
            encoding='cp950')
        table = grind.catalog_from_biology(str(path))
        self.assertEqual(table[40326], dict(level=6, hp=248, special=False))
        # Quest bosses (classes 3/4), friendly objects (class 5) and NPCs
        # (class 1) are never grind targets — the class column alone excludes
        # the stat-packed 41165 whose attr defeats an under-levelled bot.
        self.assertNotIn(41165, table)
        self.assertNotIn(41071, table)
        self.assertNotIn(40336, table)
        self.assertNotIn(10210, table)


class SelectorTests(unittest.TestCase):
    def test_ordinary_peers_rank_by_level_then_id(self):
        pool = grind.targets(catalog([(40323, 11, 5, False), (40329, 9, 4, False),
                                      (40328, 9, 4, False)]),
                             11, {40323, 40328, 40329})
        self.assertEqual(pool, [40323, 40328, 40329])

    def test_above_level_templates_never_rank(self):
        pool = grind.targets(catalog([ordinary(40331, 12, 3), ordinary(40325, 5, 3)]),
                             11, {40331, 40325})
        self.assertEqual(pool, [40325])

    def test_templates_without_an_authored_spawn_here_never_rank(self):
        self.assertEqual(grind.targets(catalog([ordinary(40329, 9, 3)]), 11, set()), [])

    def test_special_bit48_actors_are_skipped(self):
        pool = grind.targets(catalog([ordinary(40326, 6, 248), (44001, 6, 248, True)]),
                             11, {40326, 44001})
        self.assertEqual(pool, [40326])

    def test_hp_outlier_is_skipped_as_elite(self):
        # Staged 44576-style rows: 3471 hp against 519-rated ordinary peers.
        pool = grind.targets(catalog([ordinary(40326, 6, 248), ordinary(40327, 7, 301),
                                      ordinary(40329, 9, 519), (44576, 10, 3471, False)]),
                             11, {40326, 40327, 40329, 44576})
        self.assertEqual(pool, [40329, 40327, 40326])

    def test_legitimate_band_spread_survives(self):
        # Real level-7 variants hold 301, 376 and 752 hp in one scene; the
        # ratio bar (2.5x the pool median 752... choose peers so the spread
        # stays within it) must keep all of them.
        pool = grind.targets(catalog([ordinary(40327, 7, 301), ordinary(38713, 7, 376),
                                      ordinary(38507, 7, 752)]), 11, {40327, 38713, 38507})
        self.assertEqual(pool, [38507, 38713, 40327])

    def test_tiny_pools_pass_everything_ordinary(self):
        # Two candidates cannot expose an outlier through the median sieve;
        # runtime death-based exclusions remain the guard for that case.
        pool = grind.targets(catalog([ordinary(40326, 6, 248), ordinary(44576, 10, 3471)]),
                             11, {40326, 44576})
        self.assertEqual(pool, [44576, 40326])

    def test_empty_catalog_is_safe(self):
        self.assertEqual(grind.targets({}, 11, {40326}), [])
        self.assertEqual(grind.load_catalog(Path('Z:/definitely/missing.json')), {})
        self.assertEqual(grind.load_catalog(Path(__file__).resolve()), {})


if __name__ == '__main__':
    unittest.main()
