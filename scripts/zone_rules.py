"""data/zone_rules.csv を読み込み、行政区域の属性と代表点から平面直角座標系の系番号を決める。

ルールは rule_id の昇順に評価し、最初に条件をすべて満たしたルールの系番号を採用する。
空欄の条件は「指定なし」（どの値にも一致）として扱う。
code（全国地方公共団体コード）が書かれたルールは、名前に加えてコードも一致したときだけ当てはまる。
同じ名前の市町村（例：北海道の2つの泊村）の取り違えや、名前とコードの食い違いに気づけるようにするため。
経緯度の条件（lon_min / lon_max / lat_min / lat_max）は両端を含む。境界上の点で複数のルールが
一致する場合は、rule_id が小さいルールが優先される。

標準ライブラリだけで動くようにしている（GDAL などがない環境でもルールを検証できるようにするため）。
"""

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_RULES_CSV = Path(__file__).resolve().parent.parent / "data" / "zone_rules.csv"

ATTRIBUTE_COLUMNS = ("prefecture", "subprefecture", "county", "municipality")
BBOX_COLUMNS = ("lon_min", "lon_max", "lat_min", "lat_max")


@dataclass(frozen=True)
class ZoneRule:
    rule_id: int
    zone: int
    prefecture: str
    subprefecture: str
    county: str
    municipality: str
    code: str
    lon_min: Optional[float]
    lon_max: Optional[float]
    lat_min: Optional[float]
    lat_max: Optional[float]
    basis: str
    note: str

    @property
    def uses_coordinates(self):
        return any(getattr(self, name) is not None for name in BBOX_COLUMNS)

    def matches(self, attributes, lon=None, lat=None):
        if not self.matches_attributes(attributes):
            return False
        if not self.uses_coordinates:
            return True
        if lon is None or lat is None:
            # 経緯度で区分される都県で代表点がないのは呼び出し側の誤り。黙って次のルールへ
            # 進むと別の系に落ちるため、例外にして気づけるようにする。
            raise ValueError(
                f"rule_id={self.rule_id} は経緯度の条件を持つため、代表点の経度・緯度が必要です"
            )
        if self.lon_min is not None and lon < self.lon_min:
            return False
        if self.lon_max is not None and lon > self.lon_max:
            return False
        if self.lat_min is not None and lat < self.lat_min:
            return False
        if self.lat_max is not None and lat > self.lat_max:
            return False
        return True

    def matches_attributes(self, attributes):
        """経緯度を見ずに、属性（名前とコード）の条件だけを確かめる。"""
        for name in ATTRIBUTE_COLUMNS:
            expected = getattr(self, name)
            if expected and (attributes.get(name) or "") != expected:
                return False
        if self.code:
            actual_code = attributes.get("code") or ""
            if not actual_code:
                # 名前が一致したのにコードがないと、このルールを飛ばして別の系に落ちてしまう。
                # 経緯度と同じく、呼び出し側の誤りとして例外にする。
                raise ValueError(
                    f"rule_id={self.rule_id} はコードの条件を持つため、全国地方公共団体コードが必要です"
                )
            if actual_code != self.code:
                return False
        return True


def _optional_float(text):
    text = text.strip()
    return float(text) if text else None


def load_rules(path=DEFAULT_RULES_CSV):
    # Excel で保存し直されて BOM が付いても列名がずれないよう utf-8-sig で読む。
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        rules = [
            ZoneRule(
                rule_id=int(row["rule_id"]),
                zone=int(row["zone"]),
                prefecture=row["prefecture"].strip(),
                subprefecture=row["subprefecture"].strip(),
                county=row["county"].strip(),
                municipality=row["municipality"].strip(),
                code=row["code"].strip(),
                lon_min=_optional_float(row["lon_min"]),
                lon_max=_optional_float(row["lon_max"]),
                lat_min=_optional_float(row["lat_min"]),
                lat_max=_optional_float(row["lat_max"]),
                basis=row["basis"],
                note=row["note"],
            )
            for row in csv.DictReader(f)
        ]
    return sorted(rules, key=lambda rule: rule.rule_id)


def find_rule(rules, attributes, lon=None, lat=None):
    """一致した最初のルールを返す。一致するルールがなければ None。

    attributes には prefecture / subprefecture / county / municipality / code を渡す
    （それぞれ N03_001 / N03_002 / N03_003 / N03_004 / N03_007 に対応）。
    lon / lat はポリゴンの代表点（ポリゴン内部にある点）の経度・緯度（JGD2011、度）。
    """
    for rule in rules:
        if rule.matches(attributes, lon, lat):
            return rule
    return None
