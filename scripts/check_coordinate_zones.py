"""経緯度で系が分かれる都県（東京都・鹿児島県・沖縄県）のポリゴンが、系の境目をまたいでいないかを調べる。

元データ（N03）のシェープファイル（.shp と、同じ名前の .dbf）を読み、ポリゴンごとの範囲（最小・最大の
経度と緯度）を CSV に書き出す。GDAL や QGIS がなくても動くよう、標準ライブラリだけで .shp を読む。

考え方:
    判定ルールの経緯度の境目（例：北緯28度、東経126度）は、どれも経線か緯線である。ポリゴンの範囲を
    その境目の線で区切ると、区切られた各部分の中ではどのルールの条件も変わらないので、系も1つに決まる。
    各部分の中心で系を求め、すべて同じ系ならポリゴン全体がその系に入る。違う系が混ざるポリゴンは
    「またぐ候補」として印を付ける（範囲がまたいでいても、ポリゴンそのものはまたいでいないこともある）。
    線が範囲の中を通っても、ルールの評価順のために系が変わらない場合（例：奄美群島の東経130度）は
    またがないと判定する。

使い方（Python 3.9 以降。リポジトリのルートで実行）:
    python scripts/check_coordinate_zones.py N03-20260101.shp coordinate_zones.csv
"""

import argparse
import collections
import csv
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import n03_dbf  # noqa: E402
import zone_rules  # noqa: E402

COORDINATE_PREFECTURES = ("東京都", "鹿児島県", "沖縄県")
NULL_SHAPE = 0
POLYGON_SHAPES = {5, 15, 25}  # Polygon, PolygonZ, PolygonM

OUTPUT_COLUMNS = [
    "record", "N03_001", "N03_002", "N03_003", "N03_004", "N03_005", "N03_007",
    "xmin", "ymin", "xmax", "ymax", "num_parts",
    "zone", "crosses_boundary", "zones_in_box", "crossed_lines",
]


def read_shp_bounding_boxes(path):
    """.shp のレコードごとに (xmin, ymin, xmax, ymax, num_parts) を返す。空の形は None。

    形の座標そのものは読まず、各レコードの先頭にある範囲だけを読む（大きなファイルでも速く読めるため）。
    """
    boxes = []
    with Path(path).open("rb") as f:
        header = f.read(100)
        if len(header) < 100 or struct.unpack(">i", header[:4])[0] != 9994:
            raise ValueError(f"シェープファイル（.shp）ではありません: {path}")
        while True:
            record_header = f.read(8)
            if not record_header:
                break
            if len(record_header) < 8:
                raise ValueError(f"レコードの見出しが途中で切れています: {path}")
            _, content_words = struct.unpack(">ii", record_header)
            content = f.read(content_words * 2)
            if len(content) < content_words * 2:
                raise ValueError(f"レコードが途中で切れています: {path}")
            shape_type = struct.unpack("<i", content[:4])[0]
            if shape_type == NULL_SHAPE:
                boxes.append(None)
                continue
            if shape_type not in POLYGON_SHAPES:
                raise ValueError(f"ポリゴン以外の形（種類 {shape_type}）が入っています: {path}")
            xmin, ymin, xmax, ymax = struct.unpack("<4d", content[4:36])
            num_parts = struct.unpack("<i", content[36:40])[0]
            boxes.append((xmin, ymin, xmax, ymax, num_parts))
    return boxes


def boundary_lines(rules, attributes):
    """この属性の行に関係するルールの境目を、('lon', 値) と ('lat', 値) の集合で返す。"""
    lines = set()
    for rule in rules:
        if not rule.uses_coordinates or not rule.matches_attributes(attributes):
            continue
        for value in (rule.lon_min, rule.lon_max):
            if value is not None:
                lines.add(("lon", value))
        for value in (rule.lat_min, rule.lat_max):
            if value is not None:
                lines.add(("lat", value))
    return lines


def zones_in_box(rules, attributes, lines, box):
    """範囲を境目の線で区切り、各部分の中心で求めた系の集合と、範囲の中を通る線を返す。"""
    xmin, ymin, xmax, ymax = box[:4]
    inner_lons = sorted(v for axis, v in lines if axis == "lon" and xmin < v < xmax)
    inner_lats = sorted(v for axis, v in lines if axis == "lat" and ymin < v < ymax)
    xs = [xmin] + inner_lons + [xmax]
    ys = [ymin] + inner_lats + [ymax]
    zones = set()
    for x0, x1 in zip(xs, xs[1:]):
        for y0, y1 in zip(ys, ys[1:]):
            rule = zone_rules.find_rule(rules, attributes, (x0 + x1) / 2, (y0 + y1) / 2)
            zones.add(rule.zone if rule else None)
    inner = [f"lon={v:g}" for v in inner_lons] + [f"lat={v:g}" for v in inner_lats]
    return zones, inner


def check(shp_path, rules, prefectures=COORDINATE_PREFECTURES):
    dbf_path = Path(shp_path).with_suffix(".dbf")
    rows = n03_dbf.read_dbf(dbf_path, skip_deleted=False)
    boxes = read_shp_bounding_boxes(shp_path)
    if len(rows) != len(boxes):
        raise ValueError(f".dbf（{len(rows)}行）と .shp（{len(boxes)}件）の件数が合いません")

    results = []
    for index, (row, box) in enumerate(zip(rows, boxes)):
        if row is None or box is None or row["N03_001"] not in prefectures:
            continue
        attributes = n03_dbf.to_rule_attributes(row)
        zones, inner = zones_in_box(rules, attributes, boundary_lines(rules, attributes), box)
        crosses = len(zones) > 1
        zone = "" if crosses else (next(iter(zones)) or "")
        result = {name: row.get(name, "") for name in OUTPUT_COLUMNS[1:7]}
        result.update(
            record=index,
            xmin=box[0], ymin=box[1], xmax=box[2], ymax=box[3], num_parts=box[4],
            zone=zone,
            crosses_boundary="yes" if crosses else "no",
            zones_in_box=" ".join(str(z) for z in sorted(zones, key=lambda z: (z is None, z or 0))),
            crossed_lines=" ".join(inner) if crosses else "",
        )
        results.append(result)
    return results


def write_csv(results, path):
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)


def summarize(results):
    lines = []
    by_prefecture = collections.defaultdict(collections.Counter)
    for r in results:
        key = r["zone"] if r["crosses_boundary"] == "no" else "またぐ候補"
        by_prefecture[r["N03_001"]][key] += 1
    for prefecture in COORDINATE_PREFECTURES:
        counts = by_prefecture.get(prefecture)
        if counts:
            detail = "、".join(f"{k}系 {v}件" if k != "またぐ候補" else f"{k} {v}件"
                              for k, v in sorted(counts.items(), key=lambda kv: str(kv[0])))
            lines.append(f"{prefecture}: {detail}")
    candidates = [r for r in results if r["crosses_boundary"] == "yes"]
    lines.append(f"境目をまたぐ候補: {len(candidates)}件")
    for r in candidates[:20]:
        lines.append(
            f"  record={r['record']} {r['N03_004']} {r['N03_007']} "
            f"範囲=({r['xmin']:.4f}, {r['ymin']:.4f})-({r['xmax']:.4f}, {r['ymax']:.4f}) "
            f"境目={r['crossed_lines']} 系={r['zones_in_box']}"
        )
    if len(candidates) > 20:
        lines.append(f"  ほか {len(candidates) - 20}件（CSV を見てください）")
    return "\n".join(lines)


def find_input_error(shp_path):
    """入力ファイルの指定に誤りがあれば、利用者向けの説明を返す。問題がなければ None。"""
    shp = Path(shp_path)
    if shp.suffix.lower() == ".dbf":
        return (f".dbf ではなく .shp を指定してください（同じフォルダの .dbf は自動で読みます）: {shp}\n"
                f"  例: {shp.with_suffix('.shp')}")
    if shp.suffix.lower() != ".shp":
        return f"シェープファイル（.shp）を指定してください: {shp}"
    if not shp.is_file():
        return (f"ファイルが見つかりません: {shp}\n"
                "  パスに「...」のような仮の文字が残っていないか、ZIP を展開したか確かめてください。")
    dbf = shp.with_suffix(".dbf")
    if not dbf.is_file():
        return f"同じフォルダに .dbf が見つかりません: {dbf}"
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("shp", help="N03 のシェープファイル（例：N03-20260101.shp）。同じ名前の .dbf も必要")
    parser.add_argument("output", help="書き出す CSV のパス（UTF-8、BOM なし）")
    args = parser.parse_args(argv)

    message = find_input_error(args.shp)
    if message:
        print(f"エラー: {message}", file=sys.stderr)
        return 1
    try:
        results = check(args.shp, zone_rules.load_rules())
        write_csv(results, args.output)
    except (OSError, ValueError) as error:
        # 長い Traceback ではなく、原因の1行だけを見せる。
        print(f"エラー: {error}", file=sys.stderr)
        return 1
    print(f"{len(results)}件を {args.output} に書き出しました")
    print(summarize(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
