"""scripts/build_zone_data.py と data/municipality_zones.csv のテスト。"""

import contextlib
import csv
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

import build_zone_data  # noqa: E402
import n03_dbf  # noqa: E402
import zone_rules  # noqa: E402
from test_check_coordinate_zones import write_dbf, write_shp  # noqa: E402

TABLE_CSV = REPO_ROOT / "data" / "municipality_zones.csv"

SAMPLE = [
    ({"N03_001": "北海道", "N03_002": "後志総合振興局", "N03_003": "古宇郡", "N03_004": "泊村", "N03_007": "01403"},
     (140.4, 43.0, 140.5, 43.1)),
    ({"N03_001": "北海道", "N03_002": "根室振興局", "N03_003": "国後郡", "N03_004": "泊村", "N03_007": "01696"},
     (145.5, 43.9, 145.6, 44.0)),
    ({"N03_001": "東京都", "N03_004": "小笠原村", "N03_007": "13421"}, (142.1, 27.0, 142.3, 27.1)),
    ({"N03_001": "東京都", "N03_004": "小笠原村", "N03_007": "13421"}, (153.9, 24.2, 154.0, 24.3)),
    ({"N03_001": "鹿児島県", "N03_004": "鹿児島市", "N03_007": "46201"}, (130.4, 31.5, 130.6, 31.7)),
]


class BuildZoneDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = zone_rules.load_rules()
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.source = Path(cls.tempdir.name) / "source"
        cls.source.mkdir()
        cls.shp = cls.source / "sample.shp"
        write_dbf(cls.shp.with_suffix(".dbf"), [row for row, _ in SAMPLE])
        write_shp(cls.shp, [box for _, box in SAMPLE])
        # .shx と .prj は写すだけなので、中身はテストに関係しない。
        cls.shp.with_suffix(".shx").write_bytes(b"shx")
        cls.shp.with_suffix(".prj").write_text("prj", encoding="ascii")
        cls.rows = n03_dbf.read_dbf(cls.shp.with_suffix(".dbf"), skip_deleted=False)
        cls.boxes = [box + (1,) for _, box in SAMPLE]

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def test_assign_zones(self):
        zones = build_zone_data.assign_zones(self.rows, self.boxes, self.rules)
        self.assertEqual(zones, [11, 13, 14, 19, 2])

    def test_rows_decided_by_attributes_do_not_need_boxes(self):
        boxes = [None, None] + self.boxes[2:]
        zones = build_zone_data.assign_zones(self.rows, boxes, self.rules)
        self.assertEqual(zones[:2], [11, 13])

    def test_coordinate_rows_need_boxes(self):
        boxes = list(self.boxes)
        boxes[2] = None
        with self.assertRaises(build_zone_data.ZoneAssignmentError):
            build_zone_data.assign_zones(self.rows, boxes, self.rules)

    def test_crossing_raises(self):
        boxes = list(self.boxes)
        boxes[2] = (142.0, 27.9, 142.1, 28.1, 1)
        with self.assertRaises(build_zone_data.ZoneAssignmentError):
            build_zone_data.assign_zones(self.rows, boxes, self.rules)

    def test_municipality_table(self):
        zones = build_zone_data.assign_zones(self.rows, self.boxes, self.rules)
        table = {t["code"]: t for t in build_zone_data.municipality_table(self.rows, zones)}
        self.assertEqual(table["13421"]["zones"], "14;19")
        self.assertEqual(table["13421"]["polygons"], 2)
        self.assertEqual(table["01403"]["zones"], "11")
        self.assertEqual(table["01696"]["zones"], "13")

    def test_main_writes_table_and_shapefile(self):
        output = Path(self.tempdir.name) / "output"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = build_zone_data.main([str(self.shp), str(output)])
        self.assertEqual(status, 0)
        self.assertIn("系が分かれる市町村: 1件", stdout.getvalue())
        for suffix in (".shp", ".shx", ".dbf", ".prj"):
            self.assertTrue((output / f"sample_zone{suffix}").is_file(), suffix)
        self.assertEqual((output / "sample_zone.shp").read_bytes(), self.shp.read_bytes())
        written = n03_dbf.read_dbf(output / "sample_zone.dbf")
        self.assertEqual([r["ZONE"] for r in written], ["11", "13", "14", "19", "2"])
        self.assertEqual([r["ZONE_ROMAN"] for r in written], ["XI", "XIII", "XIV", "XIX", "II"])
        self.assertEqual([r["EPSG"] for r in written], ["6679", "6681", "6682", "6687", "6670"])
        self.assertEqual(written[0]["N03_004"], "泊村")
        with (output / "municipality_zones.csv").open(encoding="utf-8", newline="") as f:
            self.assertEqual(len(list(csv.DictReader(f))), 4)

    def test_main_refuses_source_folder(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            status = build_zone_data.main([str(self.shp), str(self.source)])
        self.assertEqual(status, 1)
        self.assertIn("同じフォルダには書き出せません", stderr.getvalue())


class MunicipalityZonesCsvTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with TABLE_CSV.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            cls.fieldnames = reader.fieldnames
            cls.table = list(reader)

    def test_format(self):
        raw = TABLE_CSV.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), "BOM を付けない")
        self.assertNotIn(b"\r\n", raw, "改行は LF にする")
        self.assertEqual(self.fieldnames, build_zone_data.TABLE_COLUMNS)

    def test_codes_are_unique_and_five_digits(self):
        codes = [t["code"] for t in self.table]
        self.assertEqual(len(codes), len(set(codes)))
        for code in codes:
            self.assertRegex(code, r"^\d{5}$")

    def test_zones_are_valid(self):
        for t in self.table:
            with self.subTest(code=t["code"]):
                zones = [int(z) for z in t["zones"].split(";")]
                self.assertEqual(zones, sorted(set(zones)))
                for zone in zones:
                    self.assertTrue(1 <= zone <= 19)

    def test_known_values(self):
        table = {t["code"]: t for t in self.table}
        self.assertEqual(table["13421"]["zones"], "14;18;19")  # 小笠原村
        self.assertEqual(table["01403"]["zones"], "11")        # 後志の泊村
        self.assertEqual(table["01696"]["zones"], "13")        # 根室の泊村
        self.assertEqual(table["01233"]["zones"], "11")        # 北海道伊達市
        self.assertEqual(table["07213"]["zones"], "9")         # 福島県伊達市
        self.assertEqual(table["46222"]["zones"], "1")         # 奄美市
        self.assertEqual(table["47201"]["zones"], "15")        # 那覇市

    def test_split_municipalities(self):
        split = {t["code"] for t in self.table if ";" in t["zones"]}
        self.assertEqual(split, {"13421", "46215", "46220", "46303", "46304"})

    def test_attribute_only_rows_follow_rules(self):
        # 経緯度を使わない道府県は、ルールだけで同じ結果になるはず。
        rules = zone_rules.load_rules()
        for t in self.table:
            if t["prefecture"] in ("東京都", "鹿児島県", "沖縄県"):
                continue
            with self.subTest(code=t["code"]):
                attributes = {
                    "prefecture": t["prefecture"], "subprefecture": t["subprefecture"],
                    "county": t["county"], "municipality": t["municipality"], "code": t["code"],
                }
                self.assertEqual(str(zone_rules.find_rule(rules, attributes).zone), t["zones"])

    @unittest.skipUnless(os.environ.get("N03_DBF"), "N03_DBF が未指定のため元データとの突き合わせは未実行")
    def test_codes_match_source_data(self):
        rows = n03_dbf.read_dbf(os.environ["N03_DBF"])
        self.assertEqual({t["code"] for t in self.table}, {r["N03_007"] for r in rows})
        self.assertEqual(sum(int(t["polygons"]) for t in self.table), len(rows))


if __name__ == "__main__":
    unittest.main()
