"""scripts/drop_tiny_rings.py のテスト。小さな GeoPackage をテストの中で作って動かす。numpy がない環境ではスキップする。"""

import sqlite3
import struct
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

try:
    import numpy  # noqa: F401
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

if HAS_NUMPY:
    import drop_tiny_rings as dtr

LON, LAT = 139.0, 36.0


def square(size_deg, lon=LON, lat=LAT):
    return [(lon, lat), (lon + size_deg, lat), (lon + size_deg, lat + size_deg),
            (lon, lat + size_deg), (lon, lat)]


def wkb_polygon(rings, endian="<"):
    out = struct.pack(endian + "BI", 1 if endian == "<" else 0, 3) + struct.pack(endian + "I", len(rings))
    for ring in rings:
        out += struct.pack(endian + "I", len(ring)) + b"".join(struct.pack(endian + "2d", *p) for p in ring)
    return out


def gpkg_blob(wkb):
    # 'GP'、版0、フラグ1（リトルエンディアン・包絡線なし）、SRS 6668
    return b"GP" + bytes([0, 1]) + struct.pack("<i", 6668) + wkb


def wkb_multipolygon(polygons):
    return (struct.pack("<BII", 1, 6, len(polygons))
            + b"".join(wkb_polygon(p) for p in polygons))


@unittest.skipUnless(HAS_NUMPY, "numpy がないためスキップ")
class DropTinyRingsTest(unittest.TestCase):
    BIG_HOLE = square(0.001, LON + 0.01, LAT + 0.01)    # 約8,900㎡
    TINY_HOLE = square(0.000001, LON + 0.05, LAT + 0.05)  # 約0.009㎡
    OUTER = square(0.1)

    def make_gpkg(self, folder):
        path = str(Path(folder) / "in.gpkg")
        con = sqlite3.connect(path)
        con.execute("create table gpkg_geometry_columns (table_name text, column_name text)")
        con.execute("insert into gpkg_geometry_columns values ('layer','geom')")
        con.execute("create table layer (fid integer primary key, name text, geom blob)")
        rows = [
            (1, "poly", gpkg_blob(wkb_polygon([self.OUTER, self.BIG_HOLE, self.TINY_HOLE]))),
            (2, "multi", gpkg_blob(wkb_multipolygon([[self.OUTER, self.TINY_HOLE], [self.OUTER]]))),
            (3, "clean", gpkg_blob(wkb_polygon([self.OUTER, self.BIG_HOLE]))),
            (4, "null", None),
        ]
        con.executemany("insert into layer values (?,?,?)", rows)
        con.commit()
        con.close()
        return path

    def fetch_geom(self, path, fid):
        """図形の BLOB を読む。Windows では開いたままの SQLite ファイルを消せないので、必ず閉じる。"""
        con = sqlite3.connect(path)
        try:
            value = con.execute("select geom from layer where fid=?", (fid,)).fetchone()[0]
        finally:
            con.close()
        return None if value is None else bytes(value)

    def rings_of(self, path, fid):
        blob = self.fetch_geom(path, fid)
        _, rings = dtr._read_polygon(blob, 8 + 5, "<")
        return rings

    def test_ring_area_is_small_for_tiny_hole_and_large_for_big_hole(self):
        import numpy as np
        self.assertLess(dtr.ring_area_m2(np.array(self.TINY_HOLE)), 1.0)
        self.assertGreater(dtr.ring_area_m2(np.array(self.BIG_HOLE)), 1000.0)

    def test_removes_only_tiny_holes_and_keeps_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            src = self.make_gpkg(folder)
            dst = str(Path(folder) / "out.gpkg")
            before = Path(src).read_bytes()
            results = dtr.drop_tiny_rings(src, dst, ["layer"], 1.0)
            self.assertEqual(Path(src).read_bytes(), before, "入力を書き換えてはいけない")
            changed, areas = results["layer"]
            self.assertEqual(changed, 2)
            self.assertEqual(len(areas), 2)
            rings = self.rings_of(dst, 1)
            self.assertEqual(len(rings), 2)  # 外環 + 大きな穴
            self.assertEqual(self.fetch_geom(src, 3), self.fetch_geom(dst, 3), "穴を削らない地物は変えない")
            self.assertIsNone(self.fetch_geom(dst, 4))

    def test_multipolygon_keeps_polygon_count(self):
        with tempfile.TemporaryDirectory() as folder:
            src = self.make_gpkg(folder)
            dst = str(Path(folder) / "out.gpkg")
            dtr.drop_tiny_rings(src, dst, ["layer"], 1.0)
            blob = self.fetch_geom(dst, 2)
            self.assertEqual(struct.unpack_from("<I", blob, 8 + 5)[0], 2)
            new_blob, dropped = dtr.rewrite_geometry(blob, 1.0)
            self.assertEqual(dropped, [])
            self.assertEqual(new_blob, blob)

    def test_threshold_zero_removes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            src = self.make_gpkg(folder)
            dst = str(Path(folder) / "out.gpkg")
            results = dtr.drop_tiny_rings(src, dst, ["layer"], 0.0)
            self.assertEqual(results["layer"][0], 0)

    def test_unknown_layer_and_unsupported_type(self):
        with tempfile.TemporaryDirectory() as folder:
            src = self.make_gpkg(folder)
            with self.assertRaises(ValueError):
                dtr.drop_tiny_rings(src, str(Path(folder) / "o.gpkg"), ["nothing"], 1.0)
        point = gpkg_blob(struct.pack("<BIdd", 1, 1, 1.0, 2.0))
        with self.assertRaises(AssertionError):
            dtr.rewrite_geometry(point, 1.0)


if __name__ == "__main__":
    unittest.main()
