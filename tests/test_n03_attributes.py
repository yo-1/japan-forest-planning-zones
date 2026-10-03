"""判定ルールを、元データ（N03 2026年版）の属性と突き合わせるテスト。

元データはリポジトリに入れていないので、環境変数 N03_DBF に N03-20260101.dbf のパスを
指定したときだけ実行する（指定しなければスキップ＝未実行）。

    N03_DBF=/path/to/N03-20260101.dbf python -m unittest discover -s tests -v
"""

import collections
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import n03_dbf  # noqa: E402
import zone_rules  # noqa: E402

# 経緯度で系が分かれる都県。属性だけでは判定できない。
COORDINATE_PREFECTURES = {"東京都", "鹿児島県", "沖縄県"}


@unittest.skipUnless(os.environ.get("N03_DBF"), "N03_DBF が未指定のため元データとの突き合わせは未実行")
class N03AttributesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = n03_dbf.read_dbf(os.environ["N03_DBF"])
        cls.rules = zone_rules.load_rules()
        cls.keys = {
            (r["N03_001"], r["N03_002"], r["N03_003"], r["N03_004"], r["N03_007"]) for r in cls.rows
        }

    def test_every_rule_condition_exists_in_data(self):
        # ルールの書き方（例：「後志総合振興局」）が元データと違うと、そのルールは一度も当たらない。
        for rule in self.rules:
            with self.subTest(rule_id=rule.rule_id):
                found = any(
                    key[0] == rule.prefecture
                    and (not rule.subprefecture or key[1] == rule.subprefecture)
                    and (not rule.county or key[2] == rule.county)
                    and (not rule.municipality or key[3] == rule.municipality)
                    and (not rule.code or key[4] == rule.code)
                    for key in self.keys
                )
                self.assertTrue(found, "元データに一致する行がない（名前かコードが違う）")

    def test_every_row_gets_zone_by_attributes(self):
        unmatched = []
        for row in self.rows:
            if row["N03_001"] in COORDINATE_PREFECTURES:
                continue
            rule = zone_rules.find_rule(self.rules, n03_dbf.to_rule_attributes(row))
            if rule is None:
                unmatched.append(row)
        self.assertEqual(unmatched, [])

    def test_hokkaido_named_cities_belong_to_expected_subprefecture(self):
        expected = {
            "小樽市": "後志総合振興局",
            "函館市": "渡島総合振興局",
            "北斗市": "渡島総合振興局",
            "伊達市": "胆振総合振興局",
            "北見市": "オホーツク総合振興局",
            "網走市": "オホーツク総合振興局",
            "帯広市": "十勝総合振興局",
            "釧路市": "釧路総合振興局",
            "根室市": "根室振興局",
        }
        for city, subprefecture in expected.items():
            with self.subTest(city=city):
                actual = {k[1] for k in self.keys if k[0] == "北海道" and k[3] == city}
                self.assertEqual(actual, {subprefecture})

    def test_amami_is_oshima_county_and_amami_city(self):
        # 奄美群島を「大島郡と奄美市」とみなす仮定で、取りこぼしや余計な町村がないことを確かめる。
        oshima = {k[3] for k in self.keys if k[0] == "鹿児島県" and k[2] == "大島郡"}
        self.assertEqual(
            oshima,
            {"龍郷町", "大和村", "宇検村", "瀬戸内町", "喜界町", "徳之島町",
             "天城町", "伊仙町", "和泊町", "知名町", "与論町"},
        )
        self.assertIn(("鹿児島県", "", "", "奄美市", "46222"), self.keys)

    def test_codes_are_not_empty_and_one_name_per_code(self):
        names_by_code = collections.defaultdict(set)
        for row in self.rows:
            self.assertTrue(row["N03_007"], row)
            names_by_code[row["N03_007"]].add((row["N03_001"], row["N03_004"], row["N03_005"]))
        duplicated = {code: names for code, names in names_by_code.items() if len(names) > 1}
        self.assertEqual(duplicated, {})


if __name__ == "__main__":
    unittest.main()
