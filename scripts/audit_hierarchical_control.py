"""Read-only proximity control for raw districts reaggregated to basins."""
import argparse
import collections
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import shapely
from shapely.ops import unary_union
from audit_close_vertices import close_pairs
from build_provisional_aggregates import decode


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def audit(path):
    before = digest(path)
    groups = collections.defaultdict(list)
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        for code, blob in db.execute('SELECT basin_code,geom FROM forest_plan_districts_provisional ORDER BY district_code'):
            srid, geometry = decode(blob)
            if srid != 6668:
                raise ValueError('Expected EPSG:6668')
            groups[code].append(geometry)
    rows = []
    for code, geometries in groups.items():
        geometry = unary_union(geometries)
        pairs = close_pairs([ring.coords for part in shapely.get_parts(geometry)
                             for ring in [part.exterior, *part.interiors]], 9e-9)
        rows.append(dict(basin_code=code, valid=bool(geometry.is_valid),
            zero_pairs=sum(p['distance_degree'] == 0 for p in pairs),
            numerical_pairs=sum(0 < p['distance_degree'] <= 1e-12 for p in pairs),
            positive_pairs=[p for p in pairs if p['distance_degree'] > 1e-12]))
    return dict(scope='Unrepaired raw municipality unions -> raw districts -> basins, not v0.3 final output',
        input_sha256=before, input_unchanged=before == digest(path), shapely=shapely.__version__,
        geos=shapely.geos_version_string, threshold_degree=9e-9, basins=rows,
        totals=dict(zero_pairs=sum(r['zero_pairs'] for r in rows),
                    numerical_pairs=sum(r['numerical_pairs'] for r in rows),
                    positive_pairs=sum(len(r['positive_pairs']) for r in rows)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists')
    report = audit(args.source)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report['totals']))
    if not report['input_unchanged'] or not all(r['valid'] for r in report['basins']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
