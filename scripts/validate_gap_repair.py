"""Independently validate additive patches and district/basin consistency."""
import argparse
import collections
import hashlib
import json
import sqlite3
from pathlib import Path

from shapely.ops import unary_union
from shapely.strtree import STRtree

from build_provisional_aggregates import decode
from repair_narrow_gaps import metre_frame


def area_m2(g, reference):
    if g.is_empty:
        return 0.0
    forward, _ = metre_frame(reference)
    return forward(g).area


def validate(source, output):
    db = sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True)
    table, col, srid = db.execute('SELECT table_name,column_name,srs_id FROM gpkg_geometry_columns').fetchone()
    groups = collections.defaultdict(list)
    unassigned = []
    unassigned_by_fid = {}
    memberships = {}
    district_attributes = {}
    basin_attributes = {}
    for fid, code, dc, dn, bc, bn, blob in db.execute(f'SELECT fid,N03_007,forest_district_code,forest_district_name,wide_basin_code,wide_basin_name,"{col}" FROM "{table}"'):
        actual, geom = decode(blob)
        if srid != 6668 or actual != srid:
            raise ValueError('Wrong source CRS')
        if dc and bc:
            groups[dc].append(geom)
            if dc in memberships and memberships[dc] != bc:
                raise ValueError('Inconsistent source basin membership: ' + dc)
            memberships[dc] = bc
            district_attributes[dc] = (dn, bc, bn)
            basin_attributes[bc] = bn
        else:
            unassigned.append(geom)
            unassigned_by_fid[fid] = (code, geom)
    db.close()
    raw = {k: unary_union(gs) for k, gs in groups.items()}
    db = sqlite3.connect(Path(output).resolve().as_uri() + '?mode=ro', uri=True)
    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('SQLite integrity failure')
    districts, basins = {}, {}
    basin_groups = collections.defaultdict(list)
    errors = []
    for code, dn, bc, bn, n, blob in db.execute('SELECT district_code,district_name,basin_code,basin_name,source_features,geom FROM forest_plan_districts_provisional ORDER BY district_code'):
        if memberships.get(code) != bc:
            errors.append('District basin membership changed: ' + code)
        if district_attributes.get(code) != (dn, bc, bn) or n != len(groups.get(code, [])):
            errors.append('District attributes changed: ' + code)
        districts[code] = decode(blob)[1]
        basin_groups[bc].append(districts[code])
    for code, name, n, blob in db.execute('SELECT basin_code,basin_name,source_features,geom FROM forest_wide_basins_provisional'):
        expected_n = sum(len(groups[dc]) for dc in memberships if memberships[dc] == code)
        if basin_attributes.get(code) != name or n != expected_n:
            errors.append('Basin attributes changed: ' + code)
        basins[code] = decode(blob)[1]
    seen_unassigned = set()
    for fid, code, blob in db.execute('SELECT source_fid,municipality_code,geom FROM forest_unassigned_review'):
        expected = unassigned_by_fid.get(fid)
        if fid in seen_unassigned or expected is None or expected[0] != code or not decode(blob)[1].equals_exact(expected[1], 0):
            errors.append('Unassigned source feature changed: ' + str(fid))
        seen_unassigned.add(fid)
    if seen_unassigned != set(unassigned_by_fid):
        errors.append('Unassigned source features missing or added')
    for table in ('forest_plan_districts_provisional', 'forest_wide_basins_provisional'):
        if db.execute(f'SELECT count(*) FROM "{table}" WHERE final_usable IS NULL OR final_usable != "false"').fetchone()[0]:
            errors.append('Unexpected final_usable in ' + table)
    patches = collections.defaultdict(list)
    for code, blob in db.execute('SELECT district_code,geom FROM gap_repair_audit WHERE decision="accepted"'):
        if code not in raw:
            errors.append('Unknown district in accepted patch ledger: ' + str(code))
        patches[code].append(decode(blob)[1])
    invalid = []
    for table, col in db.execute('SELECT table_name,column_name FROM gpkg_geometry_columns'):
        for fid, blob in db.execute(f'SELECT fid,"{col}" FROM "{table}"'):
            actual, geom = decode(blob)
            if actual != 6668 or geom.is_empty or not geom.is_valid:
                invalid.append((table, fid))
    db.close()
    if set(districts) != set(raw) or len(districts) != 158 or len(basins) != 44:
        raise ValueError('Unexpected district/basin membership')
    report = []
    obstacles = list(raw.values()) + unassigned
    obstacle_codes = list(raw) + [None] * len(unassigned)
    tree = STRtree(obstacles)
    additions, codes = [], []
    for code, geom in districts.items():
        added = geom.difference(raw[code])
        lost = raw[code].difference(geom)
        ledger = unary_union(patches[code])
        # Rebuilding a global union would repeat the collapse of untouched
        # tiny parts that the repair deliberately avoids. Check additions and
        # ledger coverage independently of source preservation instead.
        discrepancy = (area_m2(added.difference(ledger), raw[code])
                       + area_m2(ledger.difference(geom), raw[code]))
        lost_m2 = area_m2(lost, raw[code])
        report.append(dict(district_code=code, added_m2=area_m2(added, raw[code]),
                           lost_m2=lost_m2, ledger_discrepancy_m2=discrepancy))
        if lost_m2 > 1e-4 or discrepancy > 1e-4:
            errors.append('Non-additive or unlogged district change: ' + code)
        if not added.is_empty:
            for i in tree.query(added):
                if obstacle_codes[i] != code and area_m2(added.intersection(obstacles[i]), raw[code]) > 1e-4:
                    errors.append('New overlap with source area: ' + code)
            additions.append(added); codes.append(code)
    tree = STRtree(additions)
    for i, added in enumerate(additions):
        for j in tree.query(added):
            if j > i and area_m2(added.intersection(additions[j]), raw[codes[i]]) > 1e-4:
                errors.append(f'New patch overlap: {codes[i]} / {codes[j]}')
    basin_equal = {}
    for code, gs in basin_groups.items():
        expected = unary_union(gs)
        basin_equal[code] = expected.equals_exact(basins[code], 0, normalize=True)
        if not basin_equal[code]:
            errors.append('Basin differs from repaired districts: ' + code)
    if invalid:
        errors.append('Invalid / empty geometry or wrong CRS')
    with Path(source).open('rb') as f:
        digest = hashlib.sha256()
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    return dict(source_sha256=digest.hexdigest(), districts=report,
                added_m2_total=sum(r['added_m2'] for r in report),
                lost_m2_total=sum(r['lost_m2'] for r in report),
                basin_exact_matches=sum(basin_equal.values()), basin_total=len(basins),
                unassigned_preserved=seen_unassigned == set(unassigned_by_fid) and not any('Unassigned' in e for e in errors),
                invalid=invalid, errors=errors, passed=not errors)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path); p.add_argument('output', type=Path)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    result = validate(a.source, a.output)
    a.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'districts'}, ensure_ascii=False))
    if not result['passed']:
        raise SystemExit(1)
