"""data/zones.csv の整合性テスト。

標準ライブラリだけで動く検査を基本とし、pyproj がある環境では EPSG の定義との照合も行う。
"""

import csv
import re
import unittest
from pathlib import Path

ZONES_CSV = Path(__file__).resolve().parent.parent / "data" / "zones.csv"
EXPECTED_COLUMNS = [
    "zone",
    "zone_roman",
    "origin_lon_dms",
    "origin_lat_dms",
    "origin_lon",
    "origin_lat",
    "epsg_jgd2011",
    "area_text",
]
ROMAN = [
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
    "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX",
]
DMS_PATTERN = re.compile(r"^(\d+)°(\d{2})′(\d{2})″$")


def dms_to_degrees(text):
    match = DMS_PATTERN.match(text)
    if match is None:
        raise ValueError(f"度分秒の形式ではありません: {text!r}")
    degrees, minutes, seconds = (int(part) for part in match.groups())
    return degrees + minutes / 60 + seconds / 3600


def load_rows():
    # BOM 付きで保存し直されても列名がずれないよう utf-8-sig で読む。
    with ZONES_CSV.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


class ZonesCsvTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fieldnames, cls.rows = load_rows()

    def test_file_is_utf8_without_bom_and_lf(self):
        raw = ZONES_CSV.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), "BOM を付けない")
        self.assertNotIn(b"\r\n", raw, "改行は LF にする")
        raw.decode("utf-8")

    def test_columns(self):
        self.assertEqual(self.fieldnames, EXPECTED_COLUMNS)

    def test_nineteen_zones_in_order(self):
        self.assertEqual([int(r["zone"]) for r in self.rows], list(range(1, 20)))
        self.assertEqual([r["zone_roman"] for r in self.rows], ROMAN)

    def test_decimal_origin_matches_dms(self):
        for row in self.rows:
            with self.subTest(zone=row["zone"]):
                self.assertAlmostEqual(
                    float(row["origin_lon"]), dms_to_degrees(row["origin_lon_dms"]), places=9
                )
                self.assertAlmostEqual(
                    float(row["origin_lat"]), dms_to_degrees(row["origin_lat_dms"]), places=9
                )

    def test_epsg_codes_are_sequential(self):
        # JGD2011 の平面直角座標系は EPSG:6669（I系）から 6687（XIX系）まで連番。
        for row in self.rows:
            with self.subTest(zone=row["zone"]):
                self.assertEqual(int(row["epsg_jgd2011"]), 6668 + int(row["zone"]))

    def test_area_text_not_empty(self):
        for row in self.rows:
            with self.subTest(zone=row["zone"]):
                self.assertTrue(row["area_text"].strip())


class ZonesCsvEpsgTest(unittest.TestCase):
    """pyproj の EPSG データベースと原点・縮尺係数を照合する。"""

    @classmethod
    def setUpClass(cls):
        try:
            from pyproj import CRS
        except ImportError:
            raise unittest.SkipTest("pyproj がないため EPSG との照合は未実行")
        cls.CRS = CRS
        _, cls.rows = load_rows()

    def test_origin_and_scale_match_epsg(self):
        for row in self.rows:
            with self.subTest(zone=row["zone"]):
                crs = self.CRS.from_epsg(int(row["epsg_jgd2011"]))
                params = {p.name: p.value for p in crs.coordinate_operation.params}
                self.assertIn("JGD2011", crs.name)
                self.assertAlmostEqual(
                    params["Longitude of natural origin"], float(row["origin_lon"]), places=9
                )
                self.assertAlmostEqual(
                    params["Latitude of natural origin"], float(row["origin_lat"]), places=9
                )
                self.assertEqual(params["Scale factor at natural origin"], 0.9999)


if __name__ == "__main__":
    unittest.main()
