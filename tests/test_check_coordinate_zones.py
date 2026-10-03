"""scripts/check_coordinate_zones.py のテスト。

小さなシェープファイル（.shp と .dbf）をテストの中で作り、境目をまたぐかどうかの判定を確かめる。
"""

import csv
import struct
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_coordinate_zones  # noqa: E402
import zone_rules  # noqa: E402

DBF_FIELDS = [("N03_001", 20), ("N03_002", 40), ("N03_003", 40), ("N03_004", 40), ("N03_005", 40), ("N03_007", 5)]


def write_dbf(path, rows):
    header_length = 32 + 32 * len(DBF_FIELDS) + 1
    record_length = 1 + sum(length for _, length in DBF_FIELDS)
    with open(path, "wb") as f:
        f.write(struct.pack("<BBBBIHH20x", 3, 126, 1, 1, len(rows), header_length, record_length))
        for name, length in DBF_FIELDS:
            f.write(struct.pack("<11sc4xBB14x", name.encode("ascii"), b"C", length, 0))
        f.write(b"\r")
        for row in rows:
            f.write(b" ")
            for name, length in DBF_FIELDS:
                f.write(row.get(name, "").encode("utf-8").ljust(length, b" ")[:length])
        f.write(b"\x1a")


def write_shp(path, boxes):
    """範囲 (xmin, ymin, xmax, ymax) ごとに、長方形のポリゴンを1件ずつ書く。"""
    records = []
    for xmin, ymin, xmax, ymax in boxes:
        points = [(xmin, ymin), (xmin, ymax), (xmax, ymax), (xmax, ymin), (xmin, ymin)]
        content = struct.pack("<i4dii", 5, xmin, ymin, xmax, ymax, 1, len(points))
        content += struct.pack("<i", 0)
        content += b"".join(struct.pack("<2d", x, y) for x, y in points)
        records.append(content)
    file_length = 100 + sum(8 + len(c) for c in records)
    all_x = [b[0] for b in boxes] + [b[2] for b in boxes]
    all_y = [b[1] for b in boxes] + [b[3] for b in boxes]
    with open(path, "wb") as f:
        f.write(struct.pack(">i5ii", 9994, 0, 0, 0, 0, 0, file_length // 2))
        f.write(struct.pack("<ii4d4d", 1000, 5, min(all_x), min(all_y), max(all_x), max(all_y), 0, 0, 0, 0))
        for number, content in enumerate(records, 1):
            f.write(struct.pack(">ii", number, len(content) // 2))
            f.write(content)


class CheckCoordinateZonesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = zone_rules.load_rules()
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.shp = Path(cls.tempdir.name) / "sample.shp"
        rows_and_boxes = [
            # 父島付近の小さな島：またがない（XIV系）
            ({"N03_001": "東京都", "N03_004": "小笠原村", "N03_007": "13421"}, (142.1, 27.0, 142.3, 27.1)),
            # 北緯28度をまたぐ架空の島
            ({"N03_001": "東京都", "N03_004": "小笠原村", "N03_007": "13421"}, (142.0, 27.9, 142.1, 28.1)),
            # 東京都区部：境目はすべて北緯28度より南の範囲なので、経度の線にはかからない
            ({"N03_001": "東京都", "N03_004": "千代田区", "N03_007": "13101"}, (139.7, 35.6, 139.8, 35.7)),
            # 東経126度をまたぐ架空の島（沖縄県）
            ({"N03_001": "沖縄県", "N03_004": "久米島町", "N03_003": "島尻郡", "N03_007": "47361"}, (125.9, 26.3, 126.1, 26.4)),
            # 喜界島付近：大島郡なので東経130度は境目にならず、130度13分より西なので I系
            ({"N03_001": "鹿児島県", "N03_004": "喜界町", "N03_003": "大島郡", "N03_007": "46529"}, (129.9, 28.25, 130.05, 28.35)),
            # 対象外の道県は書き出さない
            ({"N03_001": "北海道", "N03_002": "石狩振興局", "N03_004": "札幌市", "N03_005": "中央区", "N03_007": "01101"}, (141.3, 43.0, 141.4, 43.1)),
        ]
        write_dbf(cls.shp.with_suffix(".dbf"), [r for r, _ in rows_and_boxes])
        write_shp(cls.shp, [b for _, b in rows_and_boxes])
        cls.results = check_coordinate_zones.check(cls.shp, cls.rules)

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def test_only_coordinate_prefectures_are_written(self):
        self.assertEqual([r["record"] for r in self.results], [0, 1, 2, 3, 4])

    def test_not_crossing_gets_zone(self):
        self.assertEqual(self.results[0]["crosses_boundary"], "no")
        self.assertEqual(self.results[0]["zone"], 14)
        self.assertEqual(self.results[2]["zone"], 9)

    def test_crossing_is_marked_without_zone(self):
        self.assertEqual(self.results[1]["crosses_boundary"], "yes")
        self.assertEqual(self.results[1]["crossed_lines"], "lat=28")
        self.assertEqual(self.results[1]["zone"], "")
        self.assertEqual(self.results[1]["zones_in_box"], "9 14")
        self.assertEqual(self.results[3]["crossed_lines"], "lon=126")
        self.assertEqual(self.results[3]["zones_in_box"], "15 16")

    def test_tokyo_mainland_does_not_cross_longitude_lines(self):
        # 経度の線（東経140度30分など）は北緯28度より南だけの境目だが、範囲の判定では
        # 線の位置だけを見る。東京都区部は東経140度30分より西にあるので、またがない。
        self.assertEqual(self.results[2]["crosses_boundary"], "no")

    def test_amami_uses_extended_longitude(self):
        self.assertEqual(self.results[4]["crosses_boundary"], "no")
        self.assertEqual(self.results[4]["zone"], 1)

    def test_csv_output(self):
        output = Path(self.tempdir.name) / "out.csv"
        check_coordinate_zones.write_csv(self.results, output)
        raw = output.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        with output.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["N03_004"], "小笠原村")

    def test_summary_mentions_candidates(self):
        summary = check_coordinate_zones.summarize(self.results)
        self.assertIn("境目をまたぐ候補: 2件", summary)

    def test_rejects_non_shapefile(self):
        bad = Path(self.tempdir.name) / "bad.shp"
        bad.write_bytes(b"\0" * 100)
        with self.assertRaises(ValueError):
            check_coordinate_zones.read_shp_bounding_boxes(bad)


if __name__ == "__main__":
    unittest.main()
