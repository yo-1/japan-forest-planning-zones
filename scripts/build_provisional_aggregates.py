"""Dissolve 2026 municipality candidates into review-only forest zones.

Usage: python build_provisional_aggregates.py INPUT.gpkg OUTPUT.gpkg
Requires Shapely 2. Output is provisional, not a legal boundary.
"""
import collections
import datetime
import json
import sqlite3
import struct
import sys
import argparse
import tempfile
import os
from pathlib import Path

from shapely import wkb
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree
from repair_narrow_gaps import repair_geometry, polygons, metre_frame


def decode(blob):
    if blob[:2] != b"GP":
        raise ValueError("Invalid geometry")
    flags = blob[3]
    size = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(flags >> 1) & 7]
    byteorder = "<" if flags & 1 else ">"
    srid = struct.unpack(byteorder + "i", blob[4:8])[0]
    return srid, wkb.loads(blob[8 + size:])


def encode(geom, srid):
    if geom.geom_type == "Polygon":
        geom = MultiPolygon([geom])
    if geom.geom_type != "MultiPolygon" or geom.is_empty or not geom.is_valid:
        raise ValueError("Invalid dissolved geometry")
    x1, y1, x2, y2 = geom.bounds
    return b"GP\x00\x03" + struct.pack("<i4d", srid, x1, x2, y1, y2) + wkb.dumps(geom, byte_order=1)


def layer(db, name, fields, srid):
    db.execute(f'CREATE TABLE "{name}" (fid INTEGER PRIMARY KEY, geom BLOB NOT NULL, {fields})')
    db.execute('INSERT INTO gpkg_contents(table_name,data_type,identifier,description,last_change,srs_id) VALUES (?,?,?,?,?,?)',
               (name, 'features', name, '市町村界の集約による確認用。公式境界ではない。',
                datetime.datetime.now(datetime.timezone.utc).isoformat(), srid))
    db.execute('INSERT INTO gpkg_geometry_columns VALUES (?,"geom","MULTIPOLYGON",?,0,0)', (name, srid))


def main(src, dst, gap_width_m=None):
    src, dst = Path(src), Path(dst)
    if dst.exists():
        raise FileExistsError(dst)
    inp = sqlite3.connect(f'file:{src.resolve()}?mode=ro', uri=True)
    table, geom_col, srid = inp.execute('SELECT table_name,column_name,srs_id FROM gpkg_geometry_columns').fetchone()
    groups = [collections.defaultdict(list), collections.defaultdict(list)]
    unassigned = []
    count = 0
    for fid, code, pref, city, ward, dc, dn, bc, bn, blob in inp.execute(
        f'SELECT fid,N03_007,N03_001,N03_004,N03_005,forest_district_code,forest_district_name,wide_basin_code,wide_basin_name,"{geom_col}" FROM "{table}"'
    ):
        actual_srid, geom = decode(blob)
        if actual_srid != srid or geom.is_empty or not geom.is_valid:
            raise ValueError(f'Invalid source fid={fid}')
        count += 1
        record = (fid, code, pref, city, ward, dc, dn, bc, bn, geom)
        if not dc or not bc:
            unassigned.append(record)
        else:
            groups[0][dc].append(record)
            groups[1][bc].append(record)
    inp.close()
    if (count, len(groups[0]), len(groups[1]), len(unassigned)) != (1911, 158, 44, 20):
        raise ValueError('Unexpected source counts')
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=dst.name + '.', suffix='.building', dir=dst.parent)
    os.close(fd)
    db = sqlite3.connect(temporary_name)
    db.execute('ATTACH DATABASE ? AS src', (str(src.resolve()),))
    for n in ('gpkg_spatial_ref_sys', 'gpkg_contents', 'gpkg_geometry_columns'):
        db.execute(db.execute('SELECT sql FROM src.sqlite_master WHERE name=?', (n,)).fetchone()[0])
    db.execute('INSERT INTO gpkg_spatial_ref_sys SELECT * FROM src.gpkg_spatial_ref_sys')
    db.execute('PRAGMA application_id=1196444487')
    db.execute('PRAGMA user_version=10400')
    layer(db, 'forest_plan_districts_provisional',
          'district_code TEXT UNIQUE,district_name TEXT,basin_code TEXT,basin_name TEXT,source_features INTEGER,status TEXT,final_usable TEXT', srid)
    layer(db, 'forest_wide_basins_provisional',
          'basin_code TEXT UNIQUE,basin_name TEXT,source_features INTEGER,status TEXT,final_usable TEXT', srid)
    layer(db, 'forest_unassigned_review',
          'source_fid INTEGER UNIQUE,municipality_code TEXT,prefecture TEXT,municipality TEXT,status TEXT', srid)
    if gap_width_m is not None:
        if srid != 6668:
            raise ValueError('Narrow-gap repair requires EPSG:6668')
        layer(db, 'gap_repair_audit',
              'district_code TEXT,decision TEXT,area_m2 REAL,perimeter_m REAL,mean_width_proxy_m REAL,boundary_support REAL', srid)
        layer(db, 'gap_residual_review',
              'district_code TEXT,status TEXT,area_m2 REAL,mean_width_proxy_m REAL', srid)
    districts = {}
    basin_districts = collections.defaultdict(list)
    audit_counts = collections.Counter()
    audit_bounds = []
    residual_count = 0
    residual_bounds = []
    raw_districts = {key: unary_union([r[9] for r in records]) for key, records in sorted(groups[0].items())}
    obstacle_keys = list(raw_districts) + [f'unassigned:{r[0]}' for r in unassigned]
    obstacle_geoms = list(raw_districts.values()) + [r[9] for r in unassigned]
    tree = STRtree(obstacle_geoms)
    for key, raw in raw_districts.items():
        print('district ' + key, flush=True)
        geom = raw
        if gap_width_m is not None:
            nearby = tree.query(raw.buffer(gap_width_m / 50000))
            blockers = [obstacle_geoms[i] for i in nearby if obstacle_keys[i] != key]
            geom, audit = repair_geometry(raw, gap_width_m, blockers)
            for patch, measurements, decision in audit:
                audit_counts[decision] += 1
                patch = MultiPolygon(list(polygons(patch)))
                audit_bounds.append(patch.bounds)
                db.execute('INSERT INTO gap_repair_audit VALUES(NULL,?,?,?,?,?,?,?)',
                           (encode(patch, srid), key, decision, measurements['area_m2'],
                            measurements['perimeter_m'], measurements['mean_width_proxy_m'], measurements['boundary_support']))
        districts[key] = geom
        if gap_width_m is not None:
            forward, _ = metre_frame(geom)
            for part in polygons(geom):
                for ring in part.interiors:
                    hole = Polygon(ring)
                    hm = forward(hole)
                    residual_count += 1
                    residual_bounds.append(hole.bounds)
                    db.execute('INSERT INTO gap_residual_review VALUES(NULL,?,?,?,?,?)',
                               (encode(hole, srid), key, '未補修の穴・水域等との区別は要確認',
                                hm.area, 2 * hm.area / hm.length))
        basin_districts[groups[0][key][0][7]].append(geom)
    if audit_bounds:
        db.execute('UPDATE gpkg_contents SET min_x=?,min_y=?,max_x=?,max_y=? WHERE table_name="gap_repair_audit"',
                   (min(b[0] for b in audit_bounds), min(b[1] for b in audit_bounds),
                    max(b[2] for b in audit_bounds), max(b[3] for b in audit_bounds)))
    if residual_bounds:
        db.execute('UPDATE gpkg_contents SET min_x=?,min_y=?,max_x=?,max_y=? WHERE table_name="gap_residual_review"',
                   (min(b[0] for b in residual_bounds), min(b[1] for b in residual_bounds),
                    max(b[2] for b in residual_bounds), max(b[3] for b in residual_bounds)))
    for i, name in enumerate(('forest_plan_districts_provisional', 'forest_wide_basins_provisional')):
        bounds = []
        for key, records in sorted(groups[i].items()):
            if len({(r[5], r[6], r[7], r[8]) if i == 0 else (r[7], r[8]) for r in records}) != 1:
                raise ValueError('Inconsistent names: ' + key)
            # Always derive basins from the exact district output, not independently
            # repaired municipality unions.
            geom = districts[key] if i == 0 else unary_union(basin_districts[key])
            bounds.append(geom.bounds)
            attrs = ((key, records[0][6], records[0][7], records[0][8]) if i == 0
                     else (key, records[0][8])) + (len(records), '確認用・区域未確定', 'false')
            db.execute(f'INSERT INTO "{name}" VALUES (NULL,?,' + ','.join('?' for _ in attrs) + ')',
                       (encode(geom, srid), *attrs))
        db.execute('UPDATE gpkg_contents SET min_x=?,min_y=?,max_x=?,max_y=? WHERE table_name=?',
                   (min(x[0] for x in bounds), min(x[1] for x in bounds),
                    max(x[2] for x in bounds), max(x[3] for x in bounds), name))
        db.commit()
    bounds = []
    for fid, code, pref, city, ward, *_extra, geom in unassigned:
        bounds.append(geom.bounds)
        db.execute('INSERT INTO forest_unassigned_review VALUES (NULL,?,?,?,?,?,?)',
                   (encode(geom, srid), fid, code, pref, (city or '') + (ward or ''), '未割当・要照会'))
    name = 'forest_unassigned_review'
    db.execute('UPDATE gpkg_contents SET min_x=?,min_y=?,max_x=?,max_y=? WHERE table_name=?',
               (min(x[0] for x in bounds), min(x[1] for x in bounds),
                max(x[2] for x in bounds), max(x[3] for x in bounds), name))
    db.commit()
    result = {'source_features': count, 'districts': len(groups[0]), 'basins': len(groups[1]),
              'unassigned': len(unassigned), 'epsg': srid, 'sqlite_integrity': db.execute('PRAGMA integrity_check').fetchone()[0],
              'gap_width_m': gap_width_m, 'gap_audit_counts': dict(audit_counts),
              'remaining_closed_holes': residual_count,
              'basins_derived_from_repaired_districts': True}
    db.close()
    Path(temporary_name).replace(dst)
    dst.with_suffix('.validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('destination')
    parser.add_argument('--gap-width-m', type=float)
    args = parser.parse_args()
    main(args.source, args.destination, args.gap_width_m)
