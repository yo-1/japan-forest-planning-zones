"""Apply explicit, evidence-backed municipality patches to a separate copy.

GeoJSON must declare EPSG:6668. Each feature needs source_fid,
municipality_code, approved=true and a nonempty evidence string. Municipality
membership is never inferred from the longest shared border or nearest point.
"""
import json
import shutil
import sqlite3
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

from build_provisional_aggregates import decode, encode
from drop_tiny_rings import register_spatial_functions
from repair_narrow_gaps import metre_frame


def apply_reviewed_patches(src, dst, patch_file):
    src, dst = Path(src), Path(dst)
    if dst.exists() or src.resolve() == dst.resolve():
        raise FileExistsError(dst)
    data = json.loads(Path(patch_file).read_text(encoding='utf-8'))
    if data.get('type') != 'FeatureCollection' or data.get('crs', {}).get('properties', {}).get('name') != 'EPSG:6668':
        raise ValueError('Reviewed patches must declare EPSG:6668')
    conn = sqlite3.connect(src.resolve().as_uri() + '?mode=ro', uri=True)
    table, col, srid = conn.execute('SELECT table_name,column_name,srs_id FROM gpkg_geometry_columns').fetchone()
    if srid != 6668:
        raise ValueError('Municipality patches require EPSG:6668')
    records = conn.execute(f'SELECT fid,N03_007,"{col}" FROM "{table}"').fetchall()
    conn.close()
    ids = [r[0] for r in records]
    codes = {r[0]: r[1] for r in records}
    geoms = [decode(r[2])[1] for r in records]
    original = dict(zip(ids, geoms))
    tree = STRtree(geoms)
    changes = {}
    report = []
    additions = []
    for feature in data['features']:
        props = feature['properties']
        fid = props.get('source_fid')
        evidence = props.get('evidence')
        if props.get('approved') is not True or not isinstance(evidence, str) or not evidence.strip():
            raise ValueError('Patch lacks explicit approval or evidence')
        if type(fid) is not int or fid not in original or props.get('municipality_code') != codes[fid]:
            raise ValueError('Patch source_fid / municipality_code mismatch')
        patch = shape(feature['geometry'])
        if patch.geom_type not in ('Polygon', 'MultiPolygon') or not patch.is_valid or patch.is_empty:
            raise ValueError('Invalid reviewed patch')
        patch = patch.difference(original[fid])
        if patch.is_empty:
            raise ValueError('Reviewed patch adds no area')
        if not patch.intersects(original[fid]):
            raise ValueError('Patch does not touch the assigned municipality')
        if any(ids[i] != fid and patch.intersection(geoms[i]).area > 0 for i in tree.query(patch)):
            raise ValueError('Reviewed patch overlaps another municipality')
        if any(patch.intersection(p).area > 0 for p in additions):
            raise ValueError('Reviewed patches overlap each other')
        repaired = unary_union([changes.get(fid, original[fid]), patch])
        if not repaired.is_valid or original[fid].difference(repaired).area > 1e-18:
            raise ValueError('Reviewed patch failed additive geometry validation')
        changes[fid] = repaired
        additions.append(patch)
        forward, _ = metre_frame(patch)
        report.append(dict(source_fid=fid, municipality_code=codes[fid],
                           evidence=props['evidence'], added_area_m2=forward(patch).area))
    shutil.copyfile(src, dst)
    conn = sqlite3.connect(dst)
    register_spatial_functions(conn)
    try:
        for fid, geom in changes.items():
            conn.execute(f'UPDATE "{table}" SET "{col}"=? WHERE fid=?', (encode(geom, srid), fid))
        # Update bounds after additions, including RTree triggers via ST_* above.
        all_bounds = [changes.get(fid, g).bounds for fid, g in original.items()]
        bounds = (min(b[0] for b in all_bounds), min(b[1] for b in all_bounds),
                  max(b[2] for b in all_bounds), max(b[3] for b in all_bounds))
        conn.execute('UPDATE gpkg_contents SET min_x=?,min_y=?,max_x=?,max_y=? WHERE table_name=?', (*bounds, table))
        conn.commit()
    finally:
        conn.close()
    dst.with_suffix('.patches.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report
