"""Reject invalid experimental settings before downloading or writing files."""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HAS_DEPS = all(importlib.util.find_spec(name) for name in ('shapely', 'numpy'))


@unittest.skipUnless(HAS_DEPS, 'shapely and numpy are required')
class ReviewGapOptionsTests(unittest.TestCase):
    def test_invalid_width_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'uncreated'
            for width in ('nan', 'inf', '0', '-0.001'):
                with self.subTest(width=width):
                    result = subprocess.run([sys.executable, str(ROOT / 'scripts/build_review_release.py'),
                        '--gap-width-m', width, '--output', str(output)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn('finite and positive', result.stderr)
                    self.assertFalse(output.exists())

    def test_municipality_patch_requires_experimental_opt_in(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'uncreated'
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/build_review_release.py'),
                '--municipality-patches', 'patches.geojson', '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('explicit experimental', result.stderr)
            self.assertFalse(output.exists())
