"""data/zone_rules.csv と scripts/zone_rules.py のテスト。

地点ごとの期待値は告示の適用区域から導いたもの。代表点の経緯度は島などのおおよその位置で、
測量上の正確な値ではない（ルールの評価順と境界の判定を確かめるための値）。
"""

import csv
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import zone_rules  # noqa: E402

RULES_CSV = REPO_ROOT / "data" / "zone_rules.csv"
ZONES_CSV = REPO_ROOT / "data" / "zones.csv"

PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]
# 全域を経度だけで区分していて、条件なしのルール（その都道府県の残り全部）がない県。
PREFECTURES_WITHOUT_FALLBACK = {"沖縄県"}


class ZoneRulesCsvTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = zone_rules.load_rules(RULES_CSV)

    def test_file_is_utf8_without_bom_and_lf(self):
        raw = RULES_CSV.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), "BOM を付けない")
        self.assertNotIn(b"\r\n", raw, "改行は LF にする")
        raw.decode("utf-8")

    def test_rule_ids_are_unique(self):
        ids = [rule.rule_id for rule in self.rules]
        self.assertEqual(len(ids), len(set(ids)))

    def test_zones_exist_and_all_used(self):
        with ZONES_CSV.open(encoding="utf-8-sig", newline="") as f:
            defined = {int(row["zone"]) for row in csv.DictReader(f)}
        used = {rule.zone for rule in self.rules}
        self.assertEqual(used, defined)

    def test_prefecture_names_are_valid(self):
        for rule in self.rules:
            with self.subTest(rule_id=rule.rule_id):
                self.assertIn(rule.prefecture, PREFECTURES)

    def test_every_prefecture_has_rules(self):
        self.assertEqual({rule.prefecture for rule in self.rules}, set(PREFECTURES))

    def test_fallback_rule_is_last_in_prefecture(self):
        # 条件なしのルールより後に同じ都道府県のルールがあると、そのルールは評価されない。
        for prefecture in PREFECTURES:
            with self.subTest(prefecture=prefecture):
                rules = [r for r in self.rules if r.prefecture == prefecture]
                fallbacks = [
                    r for r in rules
                    if not (r.subprefecture or r.county or r.municipality or r.uses_coordinates)
                ]
                if prefecture in PREFECTURES_WITHOUT_FALLBACK:
                    self.assertEqual(fallbacks, [])
                else:
                    self.assertEqual(len(fallbacks), 1)
                    self.assertIs(rules[-1], fallbacks[0])

    def test_bbox_values_are_ordered(self):
        for rule in self.rules:
            with self.subTest(rule_id=rule.rule_id):
                if rule.lon_min is not None and rule.lon_max is not None:
                    self.assertLess(rule.lon_min, rule.lon_max)
                if rule.lat_min is not None and rule.lat_max is not None:
                    self.assertLess(rule.lat_min, rule.lat_max)

    def test_basis_not_empty(self):
        for rule in self.rules:
            with self.subTest(rule_id=rule.rule_id):
                self.assertTrue(rule.basis.strip())


class FindRuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = zone_rules.load_rules(RULES_CSV)

    def assertZone(self, expected, prefecture, municipality="", subprefecture="",
                   county="", lon=None, lat=None, code=""):
        attributes = {
            "prefecture": prefecture,
            "subprefecture": subprefecture,
            "county": county,
            "municipality": municipality,
            "code": code,
        }
        rule = zone_rules.find_rule(self.rules, attributes, lon, lat)
        self.assertIsNotNone(rule, f"一致するルールがない: {attributes} ({lon}, {lat})")
        self.assertEqual(rule.zone, expected, f"{attributes} ({lon}, {lat}) rule_id={rule.rule_id}")

    def test_prefecture_level(self):
        self.assertZone(1, "長崎県", "長崎市")
        self.assertZone(2, "福岡県", "福岡市")
        self.assertZone(6, "京都府", "京都市")
        self.assertZone(9, "神奈川県", "横浜市")
        self.assertZone(10, "宮城県", "仙台市")

    def test_hokkaido(self):
        # コードは元データ（N03 2026年版）の N03_007 の値。
        self.assertZone(11, "北海道", "小樽市", "後志総合振興局", code="01203")
        self.assertZone(11, "北海道", "伊達市", "胆振総合振興局", code="01233")
        self.assertZone(11, "北海道", "豊浦町", "胆振総合振興局", "虻田郡", code="01571")
        self.assertZone(12, "北海道", "室蘭市", "胆振総合振興局", code="01205")
        self.assertZone(11, "北海道", "江差町", "檜山振興局", "檜山郡", code="01361")
        self.assertZone(12, "北海道", "札幌市", "石狩振興局", code="01101")
        self.assertZone(13, "北海道", "北見市", "オホーツク総合振興局", code="01208")
        self.assertZone(13, "北海道", "美幌町", "オホーツク総合振興局", "網走郡", code="01543")
        self.assertZone(12, "北海道", "遠軽町", "オホーツク総合振興局", "紋別郡", code="01555")
        self.assertZone(13, "北海道", "音更町", "十勝総合振興局", "河東郡", code="01631")
        self.assertZone(13, "北海道", "別海町", "根室振興局", "野付郡", code="01691")

    def test_hokkaido_city_rules(self):
        # 告示で名前が挙がっている市のうち、所属する振興局が全域同じ系のものは、
        # 市のルールがなくても同じ結果になる。振興局の一部だけがその系のものは、
        # 市のルールがないと XII系になってしまう。
        city_subprefectures = {
            "小樽市": ("後志総合振興局", "01203", False),
            "函館市": ("渡島総合振興局", "01202", False),
            "北斗市": ("渡島総合振興局", "01236", False),
            "帯広市": ("十勝総合振興局", "01207", False),
            "釧路市": ("釧路総合振興局", "01206", False),
            "根室市": ("根室振興局", "01223", False),
            "伊達市": ("胆振総合振興局", "01233", True),
            "北見市": ("オホーツク総合振興局", "01208", True),
            "網走市": ("オホーツク総合振興局", "01211", True),
        }
        for city, (subprefecture, code, required) in city_subprefectures.items():
            with self.subTest(city=city):
                attributes = {
                    "prefecture": "北海道",
                    "subprefecture": subprefecture,
                    "municipality": city,
                    "code": code,
                }
                with_city_rule = zone_rules.find_rule(self.rules, attributes)
                without_city_rule = zone_rules.find_rule(
                    [r for r in self.rules if r.municipality != city], attributes
                )
                if required:
                    self.assertEqual(without_city_rule.zone, 12)
                    self.assertNotEqual(with_city_rule.zone, 12)
                else:
                    self.assertEqual(without_city_rule.zone, with_city_rule.zone)

    def test_same_village_name_in_two_subprefectures(self):
        # 北海道には泊村が2つある（後志総合振興局と、根室振興局の北方領土）。振興局で区別できること。
        self.assertZone(11, "北海道", "泊村", "後志総合振興局", "古宇郡", code="01403")
        self.assertZone(13, "北海道", "泊村", "根室振興局", "国後郡", code="01696")

    def test_unassigned_area_follows_prefecture_rules(self):
        # 元データには市区町村が決まっていない「所属未定地」があり、都道府県の単位のルールで判定する。
        self.assertZone(9, "東京都", "所属未定地", lon=140.30, lat=30.48)
        self.assertZone(2, "福岡県", "所属未定地")

    def test_same_city_name_in_other_prefecture(self):
        # 伊達市は北海道と福島県にある。北海道の XI系の規定が福島県に及ばないこと。
        self.assertZone(9, "福島県", "伊達市")

    def test_tokyo(self):
        self.assertZone(9, "東京都", "千代田区", lon=139.75, lat=35.69)
        self.assertZone(9, "東京都", "八丈町", lon=139.80, lat=33.10)
        self.assertZone(14, "東京都", "小笠原村", lon=142.20, lat=27.07)   # 父島付近
        self.assertZone(18, "東京都", "小笠原村", lon=136.08, lat=20.42)   # 沖ノ鳥島付近
        self.assertZone(19, "東京都", "小笠原村", lon=153.98, lat=24.28)   # 南鳥島付近

    def test_okinawa(self):
        self.assertZone(15, "沖縄県", "那覇市", lon=127.68, lat=26.21)
        self.assertZone(16, "沖縄県", "石垣市", lon=124.16, lat=24.34)
        self.assertZone(17, "沖縄県", "南大東村", county="島尻郡", lon=131.23, lat=25.85)

    def test_kagoshima(self):
        self.assertZone(2, "鹿児島県", "鹿児島市", lon=130.55, lat=31.60)
        self.assertZone(1, "鹿児島県", "薩摩川内市", lon=129.80, lat=31.75)  # 甑島付近
        self.assertZone(1, "鹿児島県", "十島村", county="鹿児島郡", lon=129.60, lat=29.50)
        self.assertZone(2, "鹿児島県", "屋久島町", county="熊毛郡", lon=130.50, lat=30.35)
        self.assertZone(2, "鹿児島県", "三島村", county="鹿児島郡", lon=130.22, lat=30.79)  # 硫黄島付近
        self.assertZone(1, "鹿児島県", "奄美市", lon=129.49, lat=28.38, code="46222")
        # 東経130度より東でも、奄美群島（ここでは大島郡）は東経130度13分までI系。
        self.assertZone(1, "鹿児島県", "喜界町", county="大島郡", lon=130.03, lat=28.32)

    def test_boundary_is_inclusive_and_first_rule_wins(self):
        # 北緯28度ちょうどは「北緯28度から南」に含まれる。
        self.assertZone(14, "東京都", "小笠原村", lon=142.0, lat=28.0)
        # 東経143度ちょうどは XIV系（「東経143度から西」）と XIX系（「東経143度から東」）の
        # 両方に当たる。rule_id が小さい XIV系を採る。
        self.assertZone(14, "東京都", "小笠原村", lon=143.0, lat=25.0)

    def test_code_must_also_match(self):
        # 名前が合っていてもコードが違えば、そのルールには当たらない（伊達市のルールが外れて XII系になる）。
        self.assertZone(12, "北海道", "伊達市", "胆振総合振興局", code="07213")

    def test_missing_code_raises_for_code_rules(self):
        attributes = {"prefecture": "北海道", "subprefecture": "胆振総合振興局", "municipality": "伊達市"}
        with self.assertRaises(ValueError):
            zone_rules.find_rule(self.rules, attributes)

    def test_codes_are_five_digits(self):
        for rule in self.rules:
            with self.subTest(rule_id=rule.rule_id):
                if rule.code:
                    self.assertRegex(rule.code, r"^\d{5}$")
                    self.assertTrue(rule.municipality, "コードは市町村単位のルールにだけ書く")

    def test_missing_point_raises_for_coordinate_rules(self):
        attributes = {"prefecture": "東京都", "municipality": "小笠原村"}
        with self.assertRaises(ValueError):
            zone_rules.find_rule(self.rules, attributes)

    def test_unknown_prefecture_returns_none(self):
        self.assertIsNone(zone_rules.find_rule(self.rules, {"prefecture": "所属未定地"}))


if __name__ == "__main__":
    unittest.main()
