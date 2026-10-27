"""Read-only near-vertex audit. No snapping, repair or Esri-validity claims."""
import argparse
import hashlib
import json
import math
import sqlite3
import struct
from pathlib import Path

import numpy as np
import shapely
from scipy.spatial import cKDTree


def close_pairs(rings, threshold):
    """Exclude duplicated closing coordinate and cyclic same-ring neighbours."""
    coordinates, ring_ids, indices, counts = [], [], [], []
    for rid, ring in enumerate(rings):
        a = np.asarray(ring, dtype=float)[:, :2]
        if len(a) > 1 and np.array_equal(a[0], a[-1]):
            a = a[:-1]
        counts.append(len(a))
        coordinates.extend(a)
        ring_ids.extend([rid] * len(a))
        indices.extend(range(len(a)))
    if not coordinates:
        return []
    a = np.asarray(coordinates)
    result = []
    for i, j in sorted(cKDTree(a).query_pairs(threshold)):
        ri, rj = ring_ids[i], ring_ids[j]
        ii, ij = indices[i], indices[j]
        if ri == rj and (abs(ii - ij) == 1 or abs(ii - ij) == counts[ri] - 1):
            continue
        result.append(dict(ring_a=ri, vertex_a=ii, ring_b=rj, vertex_b=ij,
                           distance_degree=float(np.linalg.norm(a[i] - a[j])),
                           coordinate_a=a[i].tolist(), coordinate_b=a[j].tolist()))
    return result


def decode(blob):
    if blob[:2] != b'GP':
        raise ValueError('Not GeoPackage geometry')
    envelope = (blob[3] >> 1) & 7
    offset = 8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[envelope]
    srid = struct.unpack('<i' if blob[3] & 1 else '>i', blob[4:8])[0]
    if srid != 6668:
        raise ValueError(f'Expected EPSG:6668, got {srid}')
    return shapely.from_wkb(blob[offset:])


def audit(path, threshold, layers=None):
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("threshold must be finite and positive")
    with path.open('rb') as f:
        before = hashlib.file_digest(f, 'sha256').hexdigest()
    output = dict(input_sha256=before, crs='EPSG:6668', threshold_degree=threshold,
                  shapely=shapely.__version__, geos=shapely.geos_version_string,
                  scope='Euclidean degree distance; not an Esri Check Geometry substitute', layers={})
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('SQLite integrity failure')
    tables = list(db.execute('SELECT table_name,column_name FROM gpkg_geometry_columns'))
    if layers is not None:
        missing = set(layers) - {t for t, _ in tables}
        if missing:
            db.close()
            raise ValueError('Unknown layers: ' + ', '.join(sorted(missing)))
        tables = [(t, c) for t, c in tables if t in layers]
    for table, geomcol in tables:
        quote = lambda x: '"' + x.replace('"', '""') + '"'
        cur = db.execute('SELECT * FROM ' + quote(table))
        names = [x[0] for x in cur.description]
        rows = []
        for record in cur:
            row = dict(zip(names, record))
            g = decode(row[geomcol])
            rings = [r for p in shapely.get_parts(g) for r in [p.exterior, *p.interiors]]
            pairs = close_pairs([r.coords for r in rings], threshold)
            attributes = {k: row[k] for k in ('fid', 'district_code', 'district_name',
                          'basin_code', 'basin_name', 'municipality_code') if k in row}
            rows.append(dict(attributes=attributes, district_code=row.get('district_code'), valid=bool(g.is_valid),
                             reason=shapely.is_valid_reason(g), vertices=int(shapely.get_num_coordinates(g)),
                             zero_pairs=sum(p['distance_degree'] == 0 for p in pairs),
                             numerical_pairs=sum(0 < p['distance_degree'] <= 1e-12 for p in pairs),
                             positive_pairs=[p for p in pairs if p['distance_degree'] > 1e-12]))
        output['layers'][table] = rows
    db.close()
    with path.open('rb') as f:
        output['input_unchanged'] = before == hashlib.file_digest(f, 'sha256').hexdigest()
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gpkg', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--threshold-degree', type=float, default=9e-9)
    parser.add_argument('--layer', action='append', help='Audit only these layers (repeatable)')
    args = parser.parse_args()
    if not math.isfinite(args.threshold_degree) or args.threshold_degree <= 0:
        parser.error('threshold must be finite and positive')
    if args.output.exists():
        parser.error('output exists; use a new path')
    result = audit(args.gpkg, args.threshold_degree, args.layer)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
