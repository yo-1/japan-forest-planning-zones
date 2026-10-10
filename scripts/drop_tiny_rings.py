"""GeoPackage の Polygon / MultiPolygon から、面積が小さい内部リング（ポリゴンの中の微小な穴）だけを削除する。

背景
  市区町村のポリゴンを結合（dissolve）すると、元データ（N03）の隣り合うポリゴンの
  サブミリ（約1e-9度）のずれが、面積1㎡未満の穴として残ることがあります
  （派生元 japan-plane-rectangular-cs-zones の VALIDATION.txt の 2026-10-10 の記録。このファイルはそこから持ってきました）。

やること
  - 内部リングのうち、等積面積が閾値（既定 1㎡）未満のものだけを削除します。
  - 外環と、閾値以上の穴（N03 由来の実在の穴など）は、座標のバイト列をそのままコピーします。
    座標の再計算や丸めはしません。
  - 入力ファイルは読み取りだけです。出力は別ファイルに書きます。元に戻すときは出力を削除します。

使い方（numpy が必要。QGIS 3.44 付属の Python には入っています）
  python -I scripts/drop_tiny_rings.py <入力gpkg> <出力gpkg> <レイヤ名>[,<レイヤ名>...] [閾値㎡=1.0]

対応する図形は Polygon と MultiPolygon の2次元だけです。それ以外（Z・M 付きなど）は、
黙って壊さないよう AssertionError で止めます。
"""

import shutil
import sqlite3
import struct
import sys

import numpy as np

EARTH_RADIUS_M = 6371008.8  # 円筒等積による面積の計算に使う球の半径
# GeoPackage のヘッダにある包絡線（envelope）の種類ごとのバイト数
ENVELOPE_BYTES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}


def ring_area_m2(coords):
    """経緯度（度）の閉じたリングの面積（㎡）。円筒等積で出す。

    平面座標の引き算で出すと、小さな面積は桁落ちで丸まってしまうため、
    経度差と緯度の正弦の和から計算する。
    """
    lam = np.radians(coords[:, 0])
    sin_phi = np.sin(np.radians(coords[:, 1]))
    return abs(0.5 * EARTH_RADIUS_M ** 2 * np.sum((lam[1:] - lam[:-1]) * (sin_phi[:-1] + sin_phi[1:])))


def _read_polygon(blob, pos, endian):
    ring_count = struct.unpack_from(endian + "I", blob, pos)[0]
    pos += 4
    rings = []
    for _ in range(ring_count):
        point_count = struct.unpack_from(endian + "I", blob, pos)[0]
        start = pos
        pos += 4
        coords = np.frombuffer(blob, endian + "f8", 2 * point_count, pos).reshape(-1, 2)
        pos += 16 * point_count
        rings.append((blob[start:pos], coords))
    return pos, rings


def _keep_rings(rings, threshold_m2):
    """外環（先頭）と、閾値以上の穴を残す。削除した穴の面積も返す。"""
    kept = [rings[0]]
    dropped = []
    for ring in rings[1:]:
        area = ring_area_m2(ring[1])
        if area >= threshold_m2:
            kept.append(ring)
        else:
            dropped.append(area)
    return kept, dropped


def rewrite_geometry(blob, threshold_m2=1.0):
    """GeoPackage の図形 BLOB から微小な穴を除いた BLOB と、削除した穴の面積リストを返す。"""
    flags = blob[3]
    offset = 8 + ENVELOPE_BYTES[(flags >> 1) & 7]
    header = blob[:offset]
    endian = "<" if blob[offset] == 1 else ">"
    geometry_type = struct.unpack_from(endian + "I", blob, offset + 1)[0]
    assert geometry_type in (3, 6), f"未対応の図形の種類です: {geometry_type}"

    if geometry_type == 3:
        _, rings = _read_polygon(blob, offset + 5, endian)
        kept, dropped = _keep_rings(rings, threshold_m2)
        body = (blob[offset:offset + 5] + struct.pack(endian + "I", len(kept))
                + b"".join(r[0] for r in kept))
        return header + body, dropped

    polygon_count = struct.unpack_from(endian + "I", blob, offset + 5)[0]
    pos = offset + 9
    parts = [blob[offset:offset + 9]]
    dropped = []
    for _ in range(polygon_count):
        poly_endian = "<" if blob[pos] == 1 else ">"
        poly_header = blob[pos:pos + 5]
        pos, rings = _read_polygon(blob, pos + 5, poly_endian)
        kept, part_dropped = _keep_rings(rings, threshold_m2)
        dropped += part_dropped
        parts += [poly_header, struct.pack(poly_endian + "I", len(kept))] + [r[0] for r in kept]
    return header + b"".join(parts), dropped


def _envelope(blob):
    if blob is None or ((blob[3] >> 1) & 7) == 0:
        return None
    endian = "<" if (blob[3] & 1) else ">"
    return struct.unpack_from(endian + "4d", blob, 8)


def register_spatial_functions(connection):
    """GeoPackage の空間インデックス（rtree）のトリガが呼ぶ ST_* 関数を登録する。

    外環は変えないので、ヘッダの包絡線の値がそのまま使える。
    """
    def pick(index):
        return lambda blob: (_envelope(blob) or (None,) * 4)[index]

    connection.create_function(
        "ST_IsEmpty", 1, lambda blob: None if blob is None else int(bool((blob[3] >> 4) & 1)))
    for name, index in (("ST_MinX", 0), ("ST_MaxX", 1), ("ST_MinY", 2), ("ST_MaxY", 3)):
        connection.create_function(name, 1, pick(index))


def drop_tiny_rings(src, dst, layers, threshold_m2=1.0):
    """src を dst にコピーし、dst の各レイヤから微小な穴を削除する。レイヤごとの結果の dict を返す。"""
    shutil.copyfile(src, dst)
    connection = sqlite3.connect(dst)
    register_spatial_functions(connection)
    results = {}
    try:
        for layer in layers:
            row = connection.execute(
                "select column_name from gpkg_geometry_columns where table_name=?", (layer,)).fetchone()
            if row is None:
                raise ValueError(f"レイヤが見つかりません: {layer}")
            geometry_column = row[0]
            primary_key = connection.execute(
                'select name from pragma_table_info(?) where pk=1', (layer,)).fetchone()[0]
            changed = 0
            dropped_areas = []
            rows = connection.execute(f'select "{primary_key}","{geometry_column}" from "{layer}"').fetchall()
            for fid, blob in rows:
                if blob is None:
                    continue
                new_blob, dropped = rewrite_geometry(bytes(blob), threshold_m2)
                if dropped:
                    connection.execute(
                        f'update "{layer}" set "{geometry_column}"=? where "{primary_key}"=?', (new_blob, fid))
                    changed += 1
                    dropped_areas += dropped
            results[layer] = (changed, dropped_areas)
        connection.commit()
        connection.execute("vacuum")
    finally:
        connection.close()
    return results


def main(argv):
    if len(argv) < 4:
        print(__doc__)
        return 2
    threshold = float(argv[4]) if len(argv) > 4 else 1.0
    results = drop_tiny_rings(argv[1], argv[2], argv[3].split(","), threshold)
    for layer, (changed, areas) in results.items():
        print(f"{layer}: 変更した地物 {changed}、削除した穴 {len(areas)}、"
              f"面積の合計 {sum(areas):.6f} ㎡、最大 {max(areas, default=0):.6f} ㎡")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
