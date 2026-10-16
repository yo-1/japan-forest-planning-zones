"""Read-only national context checks; explicit diagnostic candidate in memory only."""
import argparse
import collections
import hashlib
import json
import platform
import sqlite3
from pathlib import Path

import shapely


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def decode(blob):
    assert blob[:2] == b'GP'
    offset = 8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(blob[3] >> 1) & 7]
    return shapely.from_wkb(blob[offset:])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('national', type=Path)
    p.add_argument('input_json', type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    if a.output.exists():
        p.error('output exists')
    hashes = {x.name: digest(x) for x in (a.national, a.input_json)}
    assert hashes[a.national.name] == 'ed4df025f6b078a7b1378adddee1eac86f277894d9dd755318963ac34acf2da7'
    assert hashes[a.input_json.name] == '433432955571410679a9792a0abedbb9fdb1c852636c9eafe1ffefbe594fe94b'
    assert shapely.__version__ == '2.1.2' and shapely.geos_version_string == '3.13.1'
    db = sqlite3.connect(a.national.resolve().as_uri() + '?mode=ro', uri=True)
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert db.execute('SELECT DISTINCT srs_id FROM gpkg_geometry_columns').fetchall() == [(6668,)]
    layers = {}
    for table, key in [('forest_plan_districts_provisional', 'district_code'),
                       ('forest_unassigned_review', 'municipality_code'),
                       ('forest_wide_basins_provisional', 'basin_code')]:
        layers[table] = [(str(code), decode(blob)) for code, blob in db.execute(f'SELECT {key},geom FROM {table}')]
    db.close()
    result = dict(python=platform.python_version(), shapely=shapely.__version__, geos=shapely.geos_version_string,
                  input_sha256=hashes, index_base=0, units='degree; area degree squared',
                  scope='GEOS only, not ArcGIS XY tolerance or clustering; no production repair', contacts={})
    districts = layers['forest_plan_districts_provisional']
    assert len(districts) == 158 and len(layers['forest_unassigned_review']) == 20
    for code in ('023', '140'):
        g = next(g for c, g in districts if c == code)
        parts = list(g.geoms)
        vertices = collections.defaultdict(list)
        rid = 0
        for pi, poly in enumerate(parts):
            for local, ring in enumerate([poly.exterior, *poly.interiors]):
                for pos, xy in enumerate(list(ring.coords)[:-1]):
                    vertices[tuple(xy)].append(dict(polygon=pi, ring=rid, local_ring=local, pos=pos))
                rid += 1
        contacts = []
        for xy, refs in vertices.items():
            for i, left in enumerate(refs):
                for right in refs[i + 1:]:
                    if left['ring'] == right['ring']:
                        continue
                    x, y = parts[left['polygon']], parts[right['polygon']]
                    intersection = x.intersection(y)
                    contacts.append(dict(coordinate=xy, a=left, b=right, distance_degree=0.0,
                                         intersection_type=intersection.geom_type,
                                         intersection_area=intersection.area,
                                         shared_boundary_length=x.boundary.intersection(y.boundary).length,
                                         polygon_areas=[x.area, y.area]))
        result['contacts'][code] = dict(valid=bool(g.is_valid), reason=shapely.is_valid_reason(g),
                                       exact_cross_ring_vertex_pairs=contacts)
    rings = json.loads(a.input_json.read_text())['features'][0]['geometry']['rings']
    original = shapely.MultiPolygon([shapely.Polygon(r) for r in rings])
    parts = list(original.geoms)
    assert rings[2023][54179] == [139.9681798050001, 39.880223054000055]
    parts[2023] = shapely.Polygon(rings[2023][:54179] + rings[2023][54181:])
    candidate = shapely.MultiPolygon(parts)
    added, lost = candidate.difference(original), original.difference(candidate)
    result['diagnostic'] = dict(input='attached JSON; not identical to national v0.3 geometry',
                                ring=2023, removed_positions=[54179, 54180], candidate_valid=bool(candidate.is_valid),
                                added_area=added.area, lost_area=lost.area,
                                added_geometry=json.loads(shapely.to_geojson(added)),
                                layer_checks={})
    for table, rows in layers.items():
        checks = []
        for code, geom in rows:
            checks.append(dict(code=code, intersects=bool(added.intersects(geom)),
                               intersection_area=added.intersection(geom).area,
                               distance_degree=added.distance(geom)))
        other = [x for x in checks if not (table == 'forest_plan_districts_provisional' and x['code'] == '025')]
        result['diagnostic']['layer_checks'][table] = dict(feature_count=len(rows),
            invalid_features=sum(not g.is_valid for _, g in rows),
            intersections=[x for x in checks if x['intersects']],
            nearest_other=min(other, key=lambda x: x['distance_degree']),
            other_within_1e_7_degree=[x for x in other if x['distance_degree'] <= 1e-7])
    result['inputs_unchanged'] = all(digest(x) == hashes[x.name] for x in (a.national, a.input_json))
    assert result['inputs_unchanged']
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
