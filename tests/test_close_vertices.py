"""Verify adjacency exclusions and cross-ring contacts for proximity audit."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
try:
    from audit_close_vertices import close_pairs
except ImportError:
    close_pairs = None


@unittest.skipIf(close_pairs is None, 'optional geometry audit dependencies not installed')
class CloseVerticesTests(unittest.TestCase):
    def test_cyclic_neighbours_excluded(self):
        pairs = close_pairs([[(0, 0), (1e-10, 0), (1, 1), (0, 1e-10), (0, 0)]], 1e-9)
        self.assertEqual(len(pairs), 1)
        self.assertEqual((pairs[0]['vertex_a'], pairs[0]['vertex_b']), (1, 3))
        self.assertAlmostEqual(pairs[0]['distance_degree'] / 1e-10, 2 ** .5)

    def test_returning_notch_detected(self):
        pairs = close_pairs([[(0, 0), (1, 1), (1e-10, 0), (2, 0), (2, 2), (0, 0)]], 1e-9)
        self.assertEqual([(p['vertex_a'], p['vertex_b']) for p in pairs], [(0, 2)])

    def test_cross_ring_contact_retained(self):
        pairs = close_pairs([[(0, 0), (1, 0), (0, 1), (0, 0)],
                             [(0, 0), (-1, 0), (0, -1), (0, 0)]], 1e-9)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]['distance_degree'], 0)
