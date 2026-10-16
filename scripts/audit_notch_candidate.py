"""Measure an explicit diagnostic two-vertex removal; never writes a GeoPackage."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

import shapely
from pyproj import CRS, Transformer
from shapely.ops import transform
from audit_close_vertices import decode


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('trial', type=Path)
    p.add_argument('national', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        p.error('output already exists')
    db = sqlite3.connect(args.trial.resolve().as_uri() + '?mode=ro', uri=True)
    original = decode(db.execute("SELECT geom FROM districts_upstream_trial WHERE district_code='025'").fetchone()[0])
    db.close()
    parts = list(original.geoms)
    # Explicit reproduction of the published diagnostic hypothesis; no national rule.
    polygon = parts[2023]
    coordinates = list(polygon.exterior.coords)
    assert coordinates[54178][:2] == (139.967886278, 39.879999685)
    assert coordinates[54180][:2] == (139.967886272, 39.87999969)
    parts[2023] = shapely.Polygon(coordinates[:54179] + coordinates[54181:],
                                 [r.coords for r in polygon.interiors])
    candidate = shapely.MultiPolygon(parts)
    added, lost = candidate.difference(original), original.difference(candidate)
    local = CRS.from_proj4('+proj=laea +lat_0=39.88 +lon_0=139.968 +ellps=GRS80 +units=m')
    project = Transformer.from_crs(6668, local, always_xy=True).transform
    area = lambda g: transform(project, g).area
    result = dict(scope='Diagnostic only; not an Esri test or a production repair',
                  shapely=shapely.__version__, geos=shapely.geos_version_string,
                  input_sha256={str(path.name): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in (args.trial, args.national)},
                  district='025', removed_vertices=[54179, 54180], ring=2023,
                  valid=bool(candidate.is_valid), vertices_before=int(shapely.get_num_coordinates(original)),
                  vertices_after=int(shapely.get_num_coordinates(candidate)),
                  added_m2=area(added), lost_m2=area(lost),
                  added_geojson=shapely.geometry.mapping(added), intersections=[])
    db = sqlite3.connect(args.national.resolve().as_uri() + '?mode=ro', uri=True)
    for table, key in [('forest_plan_districts_provisional', 'district_code'),
                       ('forest_wide_basins_provisional', 'basin_code'),
                       ('forest_unassigned_review', 'municipality_code')]:
        for code, blob in db.execute(f'SELECT {key},geom FROM {table}'):
            geometry = decode(blob)
            if added.intersects(geometry):
                intersection = added.intersection(geometry)
                result['intersections'].append(dict(layer=table, code=code,
                    area_m2=area(intersection), geometry_type=intersection.geom_type))
    db.close()
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
