"""Read-only trace of the 025 notch to the exact original N03 SHP."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import shapely
from pyogrio.raw import read
from pyproj import CRS, Transformer
from shapely.ops import transform, unary_union

EXPECTED_SHP_SHA256 = '6325d7f08c9374198e27b2cffd01bd420411be8b3cf3528da0587c6cea35538d'
TARGETS = np.array([[139.967886278, 39.879999685],
                    [139.968179805, 39.880223054],
                    [139.967886272, 39.879999690]])


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def audit(source):
    components = [source.with_suffix(suffix) for suffix in ('.shp', '.shx', '.prj', '.dbf', '.cpg')]
    before = {path.name: digest(path) for path in components}
    if before[source.name] != EXPECTED_SHP_SHA256:
        raise ValueError('SHP does not match the input used by the 21-district trial')
    metadata, fids, blobs, fields = read(source, return_fids=True,
        bbox=(139.9678, 39.8799, 139.9683, 39.8803))
    records, geometries, endpoints = [], [], {}
    rules_path = Path(__file__).resolve().parents[1] / 'data/forest/municipality_forest_districts.csv'
    with rules_path.open(encoding='utf-8', newline='') as stream:
        memberships = {row['municipality_code']: row for row in csv.DictReader(stream)}
    for index, fid in enumerate(fids):
        properties = {str(name): values[index] for name, values in zip(metadata['fields'], fields)}
        geometry = shapely.from_wkb(blobs[index])
        code = properties['N03_007']
        matches = []
        for part_index, part in enumerate(shapely.get_parts(geometry)):
            for ring_index, ring in enumerate([part.exterior, *part.interiors]):
                coordinates = np.asarray(ring.coords)
                nearest = []
                for target_index, point in enumerate(TARGETS):
                    distances = np.linalg.norm(coordinates - point, axis=1)
                    vertex = int(np.argmin(distances))
                    if distances[vertex] < 1e-7:
                        nearest.append(dict(target=target_index, vertex=vertex,
                            distance_degree=float(distances[vertex]), coordinate=coordinates[vertex].tolist()))
                if len(nearest) == 3:
                    matches.append(dict(part=part_index, ring=ring_index, nearest=nearest))
                    endpoints[code] = nearest
        rule = memberships.get(code, {})
        records.append(dict(ogr_fid=int(fid), attributes=properties, valid=bool(geometry.is_valid),
            matching_rings=matches, existing_mapping={key: rule.get(key) for key in
            ('district_code', 'district_name', 'basin_code', 'verification_status', 'usable_for_final_polygon')}))
        geometries.append(geometry)
    if set(endpoints) != {'05206', '05211'}:
        raise ValueError('Unexpected source features around the diagnostic notch')
    # Trace the two original boundaries; do not assign the gap to either city.
    oga, katagami = endpoints['05206'], endpoints['05211']
    polygon = shapely.Polygon([katagami[0]['coordinate'], katagami[1]['coordinate'],
                               oga[1]['coordinate'], oga[2]['coordinate']])
    if not polygon.is_valid:
        raise ValueError('Original diagnostic envelope is invalid')
    project = Transformer.from_crs(6668, CRS.from_proj4(
        '+proj=laea +lat_0=39.88 +lon_0=139.968 +ellps=GRS80 +units=m'), always_xy=True).transform
    area = lambda geometry: transform(project, geometry).area
    union = unary_union(geometries)
    after = {path.name: digest(path) for path in components}
    return dict(scope='Source coordinate trace only; no municipal assignment or geometry repair',
        shapely=shapely.__version__, geos=shapely.geos_version_string, source_components_sha256=before,
        source_unchanged=before == after, exact_trial_shp_match=True, crs=metadata['crs'],
        mapping_csv_sha256=digest(rules_path), source_features=records,
        diagnostic_envelope=dict(valid=True, area_m2=area(polygon),
            outside_source_union_m2=area(polygon.difference(union)),
            overlap_source_union_m2=area(polygon.intersection(union)),
            geometry=shapely.geometry.mapping(polygon)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists')
    result = audit(args.source)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('source_unchanged', 'exact_trial_shp_match')}, ensure_ascii=False))
    if not result['source_unchanged']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
