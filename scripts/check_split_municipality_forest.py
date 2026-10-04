"""Count target-forest polygons overlapping each coordinate-zone municipality part.

This tests forest presence on each part, not the whole-area planning boundary.
Usage: python check_split_municipality_forest.py CANDIDATE.gpkg TOKYO.gpkg KAGOSHIMA.gpkg OUTPUT.csv
"""
import csv
import sqlite3
import struct
import sys

from shapely import wkb


def geom(blob):
    flags = blob[3]
    if blob[:2] != b'GP':
        raise ValueError('Not a GeoPackage geometry')
    size = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(flags >> 1) & 7]
    _srid = struct.unpack(('<' if flags & 1 else '>') + 'i', blob[4:8])[0]
    return wkb.loads(blob[8 + size:])


def main(candidate_path, tokyo_path, kagoshima_path, output):
    src = sqlite3.connect(f'file:{candidate_path}?mode=ro', uri=True)
    table = src.execute('SELECT table_name FROM gpkg_geometry_columns').fetchone()[0]
    codes = ('13421', '46215', '46220', '46303', '46304')
    parts = {}
    for code, zone, blob in src.execute(
        f'SELECT N03_007,ZONE,geom FROM "{table}" WHERE N03_007 IN (?,?,?,?,?)', codes
    ):
        parts[(code, zone)] = geom(blob)
    src.close()
    counts = {key: 0 for key in parts}
    forest_total = {code: 0 for code in codes}
    for path, code_set in ((tokyo_path, {'13421'}), (kagoshima_path, set(codes[1:]))):
        db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        table = db.execute('SELECT table_name FROM gpkg_geometry_columns').fetchone()[0]
        for code, blob in db.execute(
            f'SELECT "市町村コード5桁",geom FROM "{table}" WHERE "市町村コード5桁" IN '
            '(' + ','.join('?' for _ in code_set) + ')', tuple(sorted(code_set))
        ):
            shape = geom(blob)
            forest_total[code] += 1
            for key, part in parts.items():
                if key[0] == code and shape.bounds[0] <= part.bounds[2] and shape.bounds[2] >= part.bounds[0] and shape.bounds[1] <= part.bounds[3] and shape.bounds[3] >= part.bounds[1] and shape.intersection(part).area > 0:
                    counts[key] += 1
        db.close()
    with open(output, 'w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['municipality_code', 'coordinate_zone', 'forest_features_intersecting_part',
                         'forest_features_in_municipality', 'meaning'])
        for (code, zone), n in sorted(counts.items()):
            writer.writerow([code, zone, n, forest_total[code], '森林所在のみ・行政上の区域全体は未確認'])
    print(sorted((code, zone, n, forest_total[code]) for (code, zone), n in counts.items()))


if __name__ == '__main__':
    main(*sys.argv[1:])
