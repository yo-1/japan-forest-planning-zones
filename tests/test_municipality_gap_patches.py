import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
try:
    from shapely.geometry import box, mapping
    from build_provisional_aggregates import encode, decode
    from repair_municipality_gaps import apply_reviewed_patches
except ImportError:
    apply_reviewed_patches = None


@unittest.skipIf(apply_reviewed_patches is None, 'Shapely / NumPy are required')
class ReviewedMunicipalityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src, self.dst = self.root / 'src.gpkg', self.root / 'dst.gpkg'
        db = sqlite3.connect(self.src)
        db.executescript('CREATE TABLE gpkg_geometry_columns(table_name,column_name,srs_id);'
                         'INSERT INTO gpkg_geometry_columns VALUES("municipalities","geom",6668);'
                         'CREATE TABLE gpkg_contents(table_name,min_x,min_y,max_x,max_y);'
                         'INSERT INTO gpkg_contents VALUES("municipalities",140,36,141,37);'
                         'CREATE TABLE municipalities(fid INTEGER PRIMARY KEY,N03_007 TEXT,geom BLOB);')
        self.geoms = [box(140, 36, 140.4, 37), box(140.6, 36, 141, 37)]
        db.executemany('INSERT INTO municipalities VALUES(?,?,?)',
                       [(i + 1, f'{i + 1:05}', encode(g, 6668)) for i, g in enumerate(self.geoms)])
        db.commit(); db.close()
        self.source_bytes = self.src.read_bytes()

    def patch(self, **props):
        properties = dict(source_fid=1, municipality_code='00001', approved=True, evidence='review evidence 1')
        properties.update(props)
        path = self.root / 'patch.json'
        path.write_text(json.dumps(dict(type='FeatureCollection',
            crs=dict(type='name', properties=dict(name='EPSG:6668')),
            features=[dict(type='Feature', properties=properties,
                           geometry=mapping(box(140.4, 36, 140.5, 37)))])))
        return path

    def test_approved_patch_keeps_source_and_other_municipality(self):
        report = apply_reviewed_patches(self.src, self.dst, self.patch())
        self.assertEqual(self.src.read_bytes(), self.source_bytes)
        db = sqlite3.connect(self.dst)
        gs = [decode(r[0])[1] for r in db.execute('SELECT geom FROM municipalities ORDER BY fid')]
        db.close()
        self.assertTrue(gs[1].equals(self.geoms[1]))
        self.assertGreater(gs[0].area, self.geoms[0].area)
        self.assertEqual(report[0]['municipality_code'], '00001')

    def test_no_evidence_no_guess(self):
        for props in ({'approved': False}, {'evidence': ''}, {'evidence': None}, {'evidence': 0},
                      {'evidence': True}, {'source_fid': True}, {'source_fid': 1.0},
                      {'municipality_code': '00002'}):
            with self.assertRaises(ValueError):
                apply_reviewed_patches(self.src, self.dst, self.patch(**props))
            self.assertFalse(self.dst.exists())

    def test_overlap_with_other_municipality_rejected(self):
        path = self.patch()
        data = json.loads(path.read_text())
        data['features'][0]['geometry'] = mapping(box(140.4, 36, 140.7, 37))
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            apply_reviewed_patches(self.src, self.dst, path)


if __name__ == '__main__':
    unittest.main()
