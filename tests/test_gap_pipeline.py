import contextlib
import io
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
try:
    from shapely.geometry import box
    from build_provisional_aggregates import main, encode
    from validate_gap_repair import validate
except ImportError:
    validate = None


@unittest.skipIf(validate is None, 'Shapely is required')
class GapPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src, self.out = self.root / 'src.gpkg', self.root / 'out.gpkg'
        db = sqlite3.connect(self.src)
        db.executescript('''
          CREATE TABLE gpkg_spatial_ref_sys(srs_name,srs_id PRIMARY KEY,organization,organization_coordsys_id,definition,description);
          INSERT INTO gpkg_spatial_ref_sys VALUES('JGD2011',6668,'EPSG',6668,'test','');
          CREATE TABLE gpkg_contents(table_name PRIMARY KEY,data_type,identifier,description,last_change,min_x,min_y,max_x,max_y,srs_id);
          CREATE TABLE gpkg_geometry_columns(table_name,column_name,geometry_type_name,srs_id,z,m);
          INSERT INTO gpkg_geometry_columns VALUES('municipalities','geom','MULTIPOLYGON',6668,0,0);
          CREATE TABLE municipalities(fid INTEGER PRIMARY KEY,N03_007,N03_001,N03_004,N03_005,
          forest_district_code,forest_district_name,wide_basin_code,wide_basin_name,geom);
        ''')
        rows = []
        for i in range(1911):
            if i < 1891:
                district = i % 158
                dc, bc = f'{district + 1:03}', f'{district % 44 + 1:02}'
                x, y = 140 + (district % 20) * .01, 35 + (district // 20) * .01
            else:
                dc, bc = None, None
                x, y = 143 + (i - 1891) * .01, 35
            g = box(x, y, x + .004, y + .004)
            if dc == '001':
                g = g.difference(box(x + .002, y - .001, x + .002000001, y + .003))
            rows.append((i + 1, f'{i % 1905:05}', 'pref', 'city', '', dc, dc, bc, bc, encode(g, 6668)))
        db.executemany('INSERT INTO municipalities VALUES(?,?,?,?,?,?,?,?,?,?)', rows)
        db.commit(); db.close()
        self.original_bytes = self.src.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            main(self.src, self.out, .001)

    def test_hierarchy_audit_and_input_preservation(self):
        result = validate(self.src, self.out)
        self.assertTrue(result['passed'], result['errors'])
        self.assertEqual(result['basin_exact_matches'], 44)
        self.assertGreater(result['added_m2_total'], 0)
        self.assertEqual(self.src.read_bytes(), self.original_bytes)
        db = sqlite3.connect(self.out)
        self.assertGreater(db.execute('SELECT count(*) FROM gap_repair_audit WHERE decision="accepted"').fetchone()[0], 0)
        self.assertIsNotNone(db.execute('SELECT min_x FROM gpkg_contents WHERE table_name="gap_repair_audit"').fetchone()[0])
        self.assertEqual(db.execute('SELECT count(*) FROM forest_unassigned_review').fetchone()[0], 20)
        db.close()

    def test_independent_validation_detects_basin_change(self):
        db = sqlite3.connect(self.out)
        db.execute('UPDATE forest_wide_basins_provisional SET geom=? WHERE basin_code="01"',
                   (encode(box(139, 34, 139.1, 34.1), 6668),))
        db.commit(); db.close()
        result = validate(self.src, self.out)
        self.assertFalse(result['passed'])
        self.assertIn('Basin differs from repaired districts: 01', result['errors'])

    def test_independent_validation_detects_unlogged_change(self):
        db = sqlite3.connect(self.out)
        db.execute('DELETE FROM gap_repair_audit WHERE decision="accepted"')
        db.commit(); db.close()
        result = validate(self.src, self.out)
        self.assertFalse(result['passed'])
        self.assertTrue(any('unlogged' in error for error in result['errors']))


if __name__ == '__main__':
    unittest.main()
