"""Finish a review build by directly testing its retained interior rings.

This also upgrades earlier narrow-gap review builds that used closing alone.
Input is kept; write to a new output and regenerate basins from districts.
"""
import argparse
import collections
import json
import sqlite3
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

from build_provisional_aggregates import decode, encode
from drop_tiny_rings import register_spatial_functions
from repair_narrow_gaps import polygons, repair_closed_holes, metre_frame


def finalize(src, dst, width=.001):
    src, dst = Path(src), Path(dst)
    if dst.exists() or src.resolve() == dst.resolve():
        raise FileExistsError(dst)
    db = sqlite3.connect(dst)
    inp = sqlite3.connect(src.resolve().as_uri() + '?mode=ro', uri=True)
    inp.backup(db)
    inp.close()
    register_spatial_functions(db)
    districts = {code: (bc, decode(blob)[1]) for code, bc, blob in db.execute(
        'SELECT district_code,basin_code,geom FROM forest_plan_districts_provisional ORDER BY district_code')}
    codes = list(districts)
    obstacles = [districts[c][1] for c in codes]
    obstacles += [decode(blob)[1] for blob, in db.execute('SELECT geom FROM forest_unassigned_review')]
    codes += [None] * (len(obstacles) - len(codes))
    tree = STRtree(obstacles)
    if 'method' not in [r[1] for r in db.execute('PRAGMA table_info(gap_repair_audit)')]:
        db.execute('ALTER TABLE gap_repair_audit ADD COLUMN method TEXT DEFAULT "closing"')
    db.execute('DELETE FROM gap_residual_review')
    basin_groups = collections.defaultdict(list)
    for code, (bc, g) in districts.items():
        blockers = [obstacles[i] for i in tree.query(g) if codes[i] != code]
        r, audit = repair_closed_holes(g, width, blockers)
        for hole, m, decision in audit:
            db.execute('INSERT INTO gap_repair_audit VALUES(NULL,?,?,?,?,?,?,?,?)',
                       (encode(hole, 6668), code, decision, m['area_m2'], m['perimeter_m'],
                        m['mean_width_proxy_m'], m['boundary_support'], m['method']))
        db.execute('UPDATE forest_plan_districts_provisional SET geom=? WHERE district_code=?', (encode(r, 6668), code))
        basin_groups[bc].append(r)
        forward, _ = metre_frame(r)
        for part in polygons(r):
            for ring in part.interiors:
                hole = Polygon(ring); hm = forward(hole)
                db.execute('INSERT INTO gap_residual_review VALUES(NULL,?,?,?,?,?)',
                           (encode(hole, 6668), code, '未補修の穴・水域等との区別は要確認',
                            hm.area, 2 * hm.area / hm.length))
    for code, gs in basin_groups.items():
        db.execute('UPDATE forest_wide_basins_provisional SET geom=? WHERE basin_code=?',
                   (encode(unary_union(gs), 6668), code))
    for table in ['gap_repair_audit', 'gap_residual_review']:
        bounds = [decode(blob)[1].bounds for blob, in db.execute(f'SELECT geom FROM {table}')]
        extent = (min(b[0] for b in bounds), min(b[1] for b in bounds), max(b[2] for b in bounds), max(b[3] for b in bounds)) if bounds else (None,) * 4
        db.execute('UPDATE gpkg_contents SET min_x=?,min_y=?,max_x=?,max_y=? WHERE table_name=?', (*extent, table))
    counts = dict(db.execute('SELECT decision,count(*) FROM gap_repair_audit GROUP BY decision'))
    residual = db.execute('SELECT count(*) FROM gap_residual_review').fetchone()[0]
    db.commit()
    result = dict(source_features=1911, districts=len(districts), basins=len(basin_groups), unassigned=20,
                  gap_width_m=width, gap_audit_counts=counts, remaining_closed_holes=residual,
                  basins_derived_from_repaired_districts=True,
                  sqlite_integrity=db.execute('PRAGMA integrity_check').fetchone()[0])
    db.close()
    dst.with_suffix('.validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source'); p.add_argument('destination')
    p.add_argument('--gap-width-m', type=float, default=.001)
    a = p.parse_args()
    finalize(a.source, a.destination, a.gap_width_m)
