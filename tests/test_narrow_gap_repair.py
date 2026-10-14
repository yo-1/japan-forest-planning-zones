import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
try:
    from shapely.geometry import box, Polygon, MultiPolygon
    from shapely.ops import unary_union
    from repair_narrow_gaps import repair_geometry
except ImportError:
    repair_geometry = None


@unittest.skipIf(repair_geometry is None, 'Shapely is required')
class NarrowGapTests(unittest.TestCase):
    def repair(self, geom, blockers=()):
        return repair_geometry(geom, .001, blockers, metric=False)

    def test_long_closed_gap_above_area_threshold(self):
        hole = box(49.9998, 1, 50.0002, 10001)
        g = box(0, 0, 100, 10002).difference(hole)
        self.assertGreater(hole.area, 1)
        r, audit = self.repair(g)
        self.assertAlmostEqual(r.area - g.area, hole.area, places=6)
        self.assertEqual([d for _, _, d in audit], ['accepted'])
        self.assertTrue(g.difference(r).is_empty)

    def test_open_gap_at_coast_joins_parts(self):
        a, b = box(0, 0, 50, 100), box(50.0002, 0, 100, 100)
        g = unary_union([a, b])
        r, _ = self.repair(g)
        self.assertEqual(r.geom_type, 'Polygon')
        self.assertAlmostEqual(r.area, 10000)
        self.assertEqual(r.bounds, g.bounds)

    def test_broad_water_and_island_retained(self):
        water = box(20, 20, 80, 80)
        island = box(40, 40, 45, 45)
        g = unary_union([box(0, 0, 100, 100).difference(water), island])
        r, _ = self.repair(g)
        self.assertTrue(r.equals(g))

    def test_other_district_is_not_filled(self):
        slit = box(49.9998, 1, 50.0002, 99)
        g = box(0, 0, 100, 100).difference(slit)
        r, audit = self.repair(g, [slit])
        self.assertTrue(r.equals(g))
        self.assertIn('review_other_area', [d for _, _, d in audit])

    def test_repeated_repair_is_idempotent(self):
        g = box(0, 0, 100, 100).difference(box(49.9998, -1, 50.0002, 80))
        r, _ = self.repair(g)
        twice, _ = self.repair(r)
        self.assertTrue(r.equals(twice))

    def test_invalid_width_rejected(self):
        for width in (0, -1, math.inf, math.nan):
            with self.assertRaises(ValueError):
                repair_geometry(box(0, 0, 1, 1), width, metric=False)

    def test_disconnected_island_coordinates_preserved(self):
        mainland = box(140, 36, 140.01, 36.01).difference(box(140.004, 36, 140.004000001, 36.009))
        island = box(140.02, 36, 140.02000001, 36.00000001)
        g = MultiPolygon([mainland, island])
        r, _ = repair_geometry(g, .001)
        self.assertTrue(any(p.equals_exact(island, 0) for p in r.geoms))

    def test_nanometre_closed_ring_is_not_lost_by_overlay(self):
        hole = box(140.002, 36.001, 140.00200000000004, 36.009)
        g = Polygon(box(140, 36, 140.01, 36.01).exterior.coords, [hole.exterior.coords])
        r, audit = repair_geometry(g, .001)
        self.assertEqual(len(r.interiors), 0)
        self.assertEqual(list(g.exterior.coords), list(r.exterior.coords))
        self.assertTrue(any(m['method'] == 'closed_ring' and d == 'accepted' for _, m, d in audit))

    def test_part_inside_filled_hole_is_retained_as_covered_area(self):
        hole = box(49.9998, 1, 50.0002, 99)
        mainland = Polygon(box(0, 0, 100, 100).exterior.coords, [hole.exterior.coords])
        fragment = box(49.9999, 10, 50.0001, 90)
        g = MultiPolygon([mainland, fragment])
        r, _ = self.repair(g)
        self.assertTrue(r.is_valid)
        self.assertTrue(r.covers(fragment))
        self.assertAlmostEqual(r.area, 10000)

    def test_geographic_frame_preserves_original_area(self):
        g = box(140, 36, 140.01, 36.01).difference(box(140.004, 36, 140.004000001, 36.009))
        r, audit = repair_geometry(g, .001)
        self.assertTrue(r.is_valid)
        self.assertLess(g.difference(r).area, 1e-18)
        self.assertGreater(r.area, g.area)
        self.assertTrue(any(d == 'accepted' for _, _, d in audit))


if __name__ == '__main__':
    unittest.main()
