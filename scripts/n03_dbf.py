"""行政区域データ（N03）のシェープファイルに付いている .dbf から属性だけを読み込む。

形（ポリゴン）を読まずに属性を確かめたいときに使う。GDAL などを入れなくても動くよう、
標準ライブラリだけで dBASE III 形式を読む。文字コードは N03 2026年版の .cpg に合わせて UTF-8 とする。
"""

import struct
from pathlib import Path

N03_TO_RULE_ATTRIBUTES = {
    "N03_001": "prefecture",
    "N03_002": "subprefecture",
    "N03_003": "county",
    "N03_004": "municipality",
    "N03_007": "code",
}


def read_dbf(path, encoding="utf-8", skip_deleted=True):
    """各行を {列名: 文字列} の dict で返す。

    skip_deleted が True なら削除フラグの付いた行は返さない。.shp と行の順番を合わせて読むときは
    False にする（削除された行は None になる）。
    """
    with Path(path).open("rb") as f:
        header = f.read(32)
        if len(header) < 32:
            raise ValueError(f"dBASE のヘッダーが短すぎます: {path}")
        record_count, header_length, record_length = struct.unpack("<4xIHH20x", header)

        fields = []
        while True:
            descriptor = f.read(32)
            if not descriptor or descriptor[0] == 0x0D:
                break
            name = descriptor[:11].split(b"\0", 1)[0].decode("ascii")
            fields.append((name, descriptor[16]))

        f.seek(header_length)
        rows = []
        for _ in range(record_count):
            record = f.read(record_length)
            if len(record) < record_length:
                raise ValueError(f"レコードが途中で切れています: {path}")
            if record[:1] == b"*":
                if not skip_deleted:
                    rows.append(None)
                continue
            position = 1
            row = {}
            for name, length in fields:
                row[name] = record[position:position + length].decode(encoding).strip()
                position += length
            rows.append(row)
    return rows


def to_rule_attributes(row):
    """N03 の1行を zone_rules.find_rule() に渡す形に変える。"""
    return {key: row.get(column, "") for column, key in N03_TO_RULE_ATTRIBUTES.items()}
