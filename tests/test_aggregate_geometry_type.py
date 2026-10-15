"""Prevent geometry columns from being exported as plain BLOB tables."""
import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
HAS_DEPS = all(importlib.util.find_spec(name) for name in ('shapely', 'numpy'))


@unittest.skipUnless(HAS_DEPS, 'shapely and numpy are required')
class AggregateGeometryTypeTest(unittest.TestCase):
    def test_generated_layer_type_and_release_guard(self):
        from build_provisional_aggregates import encode, layer
        from build_review_release import inspect_gpkg
        from shapely.geometry import Polygon

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.gpkg'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE gpkg_contents(table_name TEXT,data_type TEXT,identifier TEXT,description TEXT,last_change TEXT,srs_id INTEGER)')
                db.execute('CREATE TABLE gpkg_geometry_columns(table_name TEXT,column_name TEXT,geometry_type_name TEXT,srs_id INTEGER,z INTEGER,m INTEGER)')
                layer(db, 'sample', 'label TEXT', 6668)
                blob = encode(Polygon([(139, 36), (140, 36), (140, 37), (139, 36)]), 6668)
                db.execute('INSERT INTO sample VALUES (1,?,?)', (blob, '確認用'))
            self.assertEqual(inspect_gpkg(path, {'sample': 1})['sample']['features'], 1)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT geom,label FROM sample').fetchone(), (blob, '確認用'))
                db.execute('ALTER TABLE sample RENAME TO old_sample')
                db.execute('CREATE TABLE sample(fid INTEGER PRIMARY KEY,geom BLOB NOT NULL,label TEXT)')
                db.execute('INSERT INTO sample SELECT * FROM old_sample')
                db.execute('DROP TABLE old_sample')
            with self.assertRaisesRegex(ValueError, 'Geometry SQL type'):
                inspect_gpkg(path, {'sample': 1})
