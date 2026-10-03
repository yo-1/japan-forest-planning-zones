"""元データ（N03）のすべてのポリゴンに系番号を割り当て、対応表と、系番号の列を足したシェープファイルを作る。

作るもの（出力フォルダの中）:
    municipality_zones.csv
        全国地方公共団体コードごとの対応表。1つの市町村の中で系が分かれる場合は、zones 列に
        「1;2」のように複数の系を書く。
    <元の名前>_zone.shp / .shx / .dbf / .prj / .cpg
        元データのシェープファイルに、次の5列を足したもの。形は元のまま。
          ZONE        系番号
          ZONE_ROMAN  系番号のローマ数字（I〜XIX）
          EPSG        その系の平面直角座標系の EPSG コード（JGD2011）
          UNIT_CODE   都道府県ごとにまとめるときの単位のコード
          UNIT_NAME   その単位の名前
        UNIT_CODE と UNIT_NAME は、ふつうの府県では府県（コードは府県コード＋000）、北海道・東京都・
        鹿児島県・沖縄県では市区町村（元データの N03_007）。この4都道県は1つの都道府県の中で系が
        分かれるため、市区町村のまま残す。
        系ごとにまとめたポリゴン（ディゾルブ）は、これを QGIS や ogr2ogr でまとめて作る（README を参照）。

GDAL や QGIS がなくても動くよう、標準ライブラリだけで読み書きする。

使い方（Python 3.9 以降。リポジトリのルートで実行）:
    python scripts/build_zone_data.py N03-20260101.shp output
"""

import argparse
import collections
import csv
import shutil
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_coordinate_zones  # noqa: E402
import n03_dbf  # noqa: E402
import zone_rules  # noqa: E402

TABLE_COLUMNS = [
    "code", "prefecture", "subprefecture", "county", "municipality", "ward", "zones", "polygons",
]
ZONES_CSV = Path(__file__).resolve().parent.parent / "data" / "zones.csv"
# 都道府県ごとにまとめるとき、市区町村のまま残す都道県（1つの都道府県の中で系が分かれるもの）。
MUNICIPALITY_UNIT_PREFECTURES = ("北海道", "東京都", "鹿児島県", "沖縄県")
# 足す列：(名前, 型, 長さ)。長さは dBASE のバイト数（文字列は UTF-8）。
ADDED_FIELDS = [
    (b"ZONE", b"N", 2),
    (b"ZONE_ROMAN", b"C", 5),
    (b"EPSG", b"N", 4),
    (b"UNIT_CODE", b"C", 5),
    (b"UNIT_NAME", b"C", 120),
]


class ZoneAssignmentError(ValueError):
    """系番号を1つに決められないポリゴンがあったときの例外。"""


def assign_zones(rows, boxes, rules):
    """行ごとの系番号のリストを返す（削除された行は None）。

    boxes は .shp の範囲（read_shp_bounding_boxes の戻り値）。属性だけで決まる行では使わないので、
    None が入っていてもよい。経緯度が必要な行で範囲がない、または境目をまたぐときは例外にする。
    """
    if len(rows) != len(boxes):
        raise ValueError(f".dbf（{len(rows)}行）と .shp（{len(boxes)}件）の件数が合いません")
    zones = []
    for index, (row, box) in enumerate(zip(rows, boxes)):
        if row is None:
            zones.append(None)
            continue
        attributes = n03_dbf.to_rule_attributes(row)
        lines = check_coordinate_zones.boundary_lines(rules, attributes)
        if not lines:
            rule = zone_rules.find_rule(rules, attributes)
            found = {rule.zone if rule else None}
        elif box is None:
            raise ZoneAssignmentError(f"record={index} は経緯度で系を決める行ですが、形（範囲）がありません: {row}")
        else:
            found, _ = check_coordinate_zones.zones_in_box(rules, attributes, lines, box)
        if None in found:
            raise ZoneAssignmentError(f"record={index} に当てはまるルールがありません: {row}")
        if len(found) > 1:
            raise ZoneAssignmentError(
                f"record={index} は系の境目をまたぐ可能性があります（系 {sorted(found)}）: {row}"
            )
        zones.append(found.pop())
    return zones


def municipality_table(rows, zones):
    """全国地方公共団体コードごとに、名前・系番号・ポリゴンの数をまとめる。"""
    names = {}
    zone_counts = collections.defaultdict(collections.Counter)
    for row, zone in zip(rows, zones):
        if row is None:
            continue
        code = row["N03_007"]
        name = (row["N03_001"], row["N03_002"], row["N03_003"], row["N03_004"], row["N03_005"])
        if names.setdefault(code, name) != name:
            raise ValueError(f"同じコード {code} に別の名前があります: {names[code]} / {name}")
        zone_counts[code][zone] += 1
    table = []
    for code in sorted(names):
        prefecture, subprefecture, county, municipality, ward = names[code]
        counts = zone_counts[code]
        table.append({
            "code": code,
            "prefecture": prefecture,
            "subprefecture": subprefecture,
            "county": county,
            "municipality": municipality,
            "ward": ward,
            "zones": ";".join(str(z) for z in sorted(counts)),
            "polygons": sum(counts.values()),
        })
    return table


def write_table(table, path):
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TABLE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(table)


def load_zone_definitions(path=ZONES_CSV):
    """系番号から zones.csv の1行（dict）を引けるようにする。"""
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return {int(row["zone"]): row for row in csv.DictReader(f)}


def prefecture_unit(row):
    """都道府県ごとにまとめるときの単位（コード、名前）を返す。"""
    if row["N03_001"] in MUNICIPALITY_UNIT_PREFECTURES:
        return row["N03_007"], row["N03_004"] + row["N03_005"]
    return row["N03_007"][:2] + "000", row["N03_001"]


def added_field_texts(row, zone, definitions):
    """足す列の値を、ADDED_FIELDS の順に文字列で返す。削除された行は空にする。"""
    if row is None or zone is None:
        return [""] * len(ADDED_FIELDS)
    definition = definitions[zone]
    unit_code, unit_name = prefecture_unit(row)
    return [str(zone), definition["zone_roman"], definition["epsg_jgd2011"], unit_code, unit_name]


def added_values(row, zone, definitions):
    """足す列の値を、各列の長さにそろえた bytes で返す。数値は右寄せ、文字は左寄せ。"""
    parts = []
    for (name, field_type, length), text in zip(ADDED_FIELDS, added_field_texts(row, zone, definitions)):
        value = text.encode("utf-8")
        if len(value) > length:
            raise ValueError(f"{name.decode()} の値「{text}」が列の長さ（{length}バイト）を超えます")
        parts.append(value.rjust(length, b" ") if field_type == b"N" else value.ljust(length, b" "))
    return b"".join(parts)


def write_dbf_with_zone(source_dbf, rows, zones, target_dbf, definitions=None):
    """元の .dbf の列と値をそのまま写し、最後に ADDED_FIELDS の列を足す。

    rows は同じ .dbf を read_dbf(skip_deleted=False) で読んだもの（足す列の値を決めるのに使う）。
    """
    if definitions is None:
        definitions = load_zone_definitions()
    if len(rows) != len(zones):
        raise ValueError(f"行（{len(rows)}件）と系番号（{len(zones)}件）の件数が合いません")
    with Path(source_dbf).open("rb") as src:
        header = bytearray(src.read(32))
        record_count, header_length, record_length = struct.unpack("<4xIHH20x", header)
        if record_count != len(zones):
            raise ValueError(f".dbf（{record_count}行）と系番号（{len(zones)}件）の件数が合いません")
        descriptors = src.read(header_length - 32)
        terminator = descriptors.index(b"\r")
        fields = descriptors[:terminator]
        if len(fields) % 32:
            raise ValueError(f".dbf の列の定義が読めません: {source_dbf}")
        added_descriptors = b"".join(
            struct.pack("<11sc4xBB14x", name, field_type, length, 0)
            for name, field_type, length in ADDED_FIELDS
        )
        new_header_length = 32 + len(fields) + len(added_descriptors) + 1
        new_record_length = record_length + sum(length for _, _, length in ADDED_FIELDS)
        struct.pack_into("<HH", header, 8, new_header_length, new_record_length)

        src.seek(header_length)
        with Path(target_dbf).open("wb") as dst:
            dst.write(header)
            dst.write(fields)
            dst.write(added_descriptors)
            dst.write(b"\r")
            for row, zone in zip(rows, zones):
                record = src.read(record_length)
                if len(record) < record_length:
                    raise ValueError(f"レコードが途中で切れています: {source_dbf}")
                dst.write(record + added_values(row, zone, definitions))
            dst.write(b"\x1a")


def write_shapefile_with_zone(shp_path, rows, zones, output_dir):
    """形のファイル（.shp/.shx/.prj/.cpg）を写し、ZONE 列を足した .dbf を書く。書いた .shp のパスを返す。"""
    shp = Path(shp_path)
    target = Path(output_dir) / f"{shp.stem}_zone.shp"
    for suffix in (".shp", ".shx", ".prj", ".cpg"):
        source = shp.with_suffix(suffix)
        if source.is_file():
            shutil.copyfile(source, target.with_suffix(suffix))
        elif suffix in (".shp", ".shx"):
            raise FileNotFoundError(f"{suffix} が見つかりません: {source}")
    write_dbf_with_zone(shp.with_suffix(".dbf"), rows, zones, target.with_suffix(".dbf"))
    return target


def summarize(rows, zones, table):
    per_zone = collections.Counter(z for r, z in zip(rows, zones) if r is not None)
    split = [t for t in table if ";" in t["zones"]]
    lines = [
        f"ポリゴン {sum(per_zone.values())}件、市区町村など {len(table)}件",
        "系ごとのポリゴンの数: " + "、".join(f"{z}系 {n}件" for z, n in sorted(per_zone.items())),
        f"系が分かれる市町村: {len(split)}件",
    ]
    lines += [f"  {t['code']} {t['prefecture']}{t['municipality']}：{t['zones']}" for t in split]
    lines.append(
        "ディゾルブ後の地物の数（予想）: "
        f"系ごと {len(per_zone)}件、"
        f"都道府県ごと {len(dissolve_keys(rows, zones, 'unit'))}件、"
        f"市区町村ごと {len(dissolve_keys(rows, zones, 'municipality'))}件"
    )
    return "\n".join(lines)


def dissolve_keys(rows, zones, level):
    """ディゾルブしたときにできる地物のキーの集合を返す（件数の確かめ用）。"""
    keys = set()
    for row, zone in zip(rows, zones):
        if row is None:
            continue
        if level == "unit":
            keys.add((prefecture_unit(row)[0], zone))
        elif level == "municipality":
            keys.add((row["N03_007"], zone))
        else:
            raise ValueError(level)
    return keys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("shp", help="N03 のシェープファイル（例：N03-20260101.shp）。同じ名前の .dbf と .shx も必要")
    parser.add_argument("output_dir", help="書き出すフォルダ（なければ作る）")
    args = parser.parse_args(argv)

    message = check_coordinate_zones.find_input_error(args.shp)
    if message:
        print(f"エラー: {message}", file=sys.stderr)
        return 1
    output_dir = Path(args.output_dir)
    if output_dir.resolve() == Path(args.shp).resolve().parent:
        print("エラー: 元データと同じフォルダには書き出せません。別のフォルダを指定してください。", file=sys.stderr)
        return 1
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        rows = n03_dbf.read_dbf(Path(args.shp).with_suffix(".dbf"), skip_deleted=False)
        boxes = check_coordinate_zones.read_shp_bounding_boxes(args.shp)
        zones = assign_zones(rows, boxes, zone_rules.load_rules())
        table = municipality_table(rows, zones)
        write_table(table, output_dir / "municipality_zones.csv")
        written = write_shapefile_with_zone(args.shp, rows, zones, output_dir)
    except (OSError, ValueError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1
    print(f"{output_dir / 'municipality_zones.csv'} と {written} を書き出しました")
    print(summarize(rows, zones, table))
    return 0


if __name__ == "__main__":
    sys.exit(main())
