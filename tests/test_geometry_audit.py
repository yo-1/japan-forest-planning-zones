import tempfile
import unittest
from pathlib import Path
import sys,importlib.util
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
AVAILABLE=all(importlib.util.find_spec(p) for p in ['shapely','pyproj','numpy'])
if AVAILABLE:
    from shapely.geometry import Polygon,box
    from geometry_audit import common as v

@unittest.skipUnless(AVAILABLE, "Optional geometry-audit libraries are not installed")
class GeometryAuditTests(unittest.TestCase):
    def test_hole_fill_is_addition_with_unchanged_exterior(self):
        outer=[(139,35),(139.01,35),(139.01,35.01),(139,35.01),(139,35)]
        hole=[(139.002,35.002),(139.003,35.002),(139.003,35.003),(139.002,35.003),(139.002,35.002)]
        before=Polygon(outer,[hole]);after=Polygon(outer)
        with tempfile.TemporaryDirectory() as d:
            audit=v.Audit(Path(d));r=audit.compare('synthetic','hole',before,after)
            self.assertTrue(r['lost_empty']);self.assertFalse(r['added_empty'])
            self.assertGreater(r['added_m2'],1000)
            self.assertEqual(v.exteriors(before),v.exteriors(after))
            self.assertEqual(sum((v.hole_signature(before)-v.hole_signature(after)).values()),1)

    def test_shared_border_is_not_overlap_but_true_overlap_is_detected(self):
        records=[dict(code='a',geometry=box(139,35,139.01,35.01)),
                 dict(code='b',geometry=box(139.01,35,139.02,35.01))]
        with tempfile.TemporaryDirectory() as d:
            audit=v.Audit(Path(d));self.assertEqual(audit.overlaps('synthetic',records,'code')['positive_area_pairs'],0)
            records[1]['geometry']=box(139.005,35,139.015,35.01)
            self.assertEqual(audit.overlaps('synthetic',records,'code')['positive_area_pairs'],1)

    def test_nonempty_sub_square_metre_difference_not_discarded(self):
        before=box(139,35,139.001,35.001);after=box(139,35,139.001000001,35.001)
        with tempfile.TemporaryDirectory() as d:
            r=v.Audit(Path(d)).compare('synthetic','tiny',before,after)
            self.assertFalse(r['added_empty']);self.assertGreater(r['added_m2'],0);self.assertLess(r['added_m2'],1)

    @unittest.skipUnless(importlib.util.find_spec('pyogrio'), 'pyogrio is not installed')
    def test_difference_geopackage_roundtrip(self):
        import pyogrio,shapely
        from pyogrio.raw import read
        with tempfile.TemporaryDirectory() as directory:
            audit=v.Audit(Path(directory))
            audit.compare('roundtrip','x',box(139,35,139.01,35.01),box(139,35,139.011,35.01))
            audit.write({'status':'synthetic validation'})
            meta,_,wkb,_=read(str(Path(directory)/'differences.gpkg'),layer='differences')
            self.assertEqual(meta['crs'],'EPSG:6668')
            self.assertEqual(len(wkb),1)
            self.assertTrue(bool(shapely.is_valid(shapely.from_wkb(wkb)).all()))

if __name__=='__main__':unittest.main()
