"""data/zone_rules.csv を読み込み、行政区域の属性と代表点から平面直角座標系の系番号を決める。

ルールは rule_id の昇順に評価し、最初に条件をすべて満たしたルールの系番号を採用する。
空欄の条件は「指定なし」（どの値にも一致）として扱う。
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
        for name in ATTRIBUTE_COLUMNS:
            expected = getattr(self, name)
            if expected and (attributes.get(name) or "") != expected:
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

    attributes には prefecture / subprefecture / county / municipality を渡す
    （それぞれ N03_001 / N03_002 / N03_003 / N03_004 に対応）。
    lon / lat はポリゴンの代表点（ポリゴン内部にある点）の経度・緯度（JGD2011、度）。
    """
    for rule in rules:
        if rule.matches(attributes, lon, lat):
            return rule
    return None
