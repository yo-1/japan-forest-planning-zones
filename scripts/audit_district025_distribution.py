"""Compare the received distribution to GDB-derived JSON and saved GDB hashes.

Read-only diagnostics. Saved hashes are historical evidence, not a fresh GDB read.
"""
import argparse
import hashlib
import json
import math
import sqlite3
import zipfile
from pathlib import Path

import numpy as np
import shapely
from audit_project_gdb import close_pairs


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ordered(rings):
    return sha(np.asarray([p for ring in rings for p in ring], dtype='<f8').tobytes())


def run(archive, esri_json, prior, output):
    if output.exists():
        raise ValueError('Use a new output directory')
    raw, eraw = archive.read_bytes(), esri_json.read_bytes()
    if sha(raw) != '442806d09fe9f2512d33e7e4091983efa146b4913166ee8ad0fbc880aa239a70':
        raise ValueError('Unexpected comparison ZIP')
    if sha(eraw) != '433432955571410679a9792a0abedbb9fdb1c852636c9eafe1ffefbe594fe94b':
        raise ValueError('Unexpected GDB-derived JSON')
    source = json.loads(eraw)
    feature = source['features'][0] if 'features' in source else source
    rings = feature['geometry']['rings']
    saved = json.loads(prior.read_text())
    expected_candidate = [r[:] for r in rings]
    expected_candidate[2023] = rings[2023][:54179] + rings[2023][54181:]
    report = dict(zip_sha256=sha(raw), zip_bytes=len(raw), esri_json_sha256=sha(eraw),
                  prior_gdb_report_sha256=sha(prior.read_bytes()), index_base=0,
                  shapely=shapely.__version__, geos=shapely.geos_version_string,
                  provenance='README explicitly identifies a 2026-10-17 reconstruction; not the old Claude binary',
                  fresh_raw_gdb_read=False, arcgis_rerun=False, layers={})
    diagnostics = []
    geometries = {}
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError('ZIP CRC failure')
        data = z.read('district025_arcgis_comparison_20261017.gpkg')
        manifest = json.loads(z.read('district025_arcgis_comparison_20261017.json'))
        report['members'] = [dict(name=i.filename, bytes=i.file_size, sha256=sha(z.read(i))) for i in z.infolist()]
        report['gpkg_sha256'] = sha(data)
        if sha(data) != manifest['output_gpkg_sha256'] or sha(data) != 'b93f906489e5cd670be95f934d8c96fd8e98a7a079a9be666440e13c44efb4cf':
            raise ValueError('GPKG hash mismatch')
        conn = sqlite3.connect(':memory:')
        conn.deserialize(data)
        if conn.execute('pragma integrity_check').fetchall() != [('ok',)] or conn.execute('pragma foreign_key_check').fetchall():
            raise ValueError('SQLite integrity failure')
        for tag, table, reference in [('unchanged', 'trial_025_unchanged', rings),
                                       ('candidate', 'candidate_025', expected_candidate)]:
            columns = [r[1] for r in conn.execute('pragma table_info('+table+')')]
            rows = conn.execute('select * from '+table).fetchall()
            if len(rows) != 1:
                raise ValueError('Expected one feature')
            attrs = dict(zip(columns, rows[0]))
            blob = attrs.pop('geom')
            offset = 8 + {0:0, 1:32, 2:48, 3:48, 4:64}[(blob[3] >> 1) & 7]
            geom = shapely.from_wkb(blob[offset:])
            geometries[tag] = geom
            actual = [list(p.exterior.coords) for p in geom.geoms]
            if len(actual) != len(reference) or any(p.interiors for p in geom.geoms):
                raise ValueError('Ring structure differs')
            if any(len(a) != len(b) for a,b in zip(actual, reference)):
                raise ValueError('Ring coordinate counts differ')
            a, b = np.asarray([p for r in actual for p in r]), np.asarray([p for r in reference for p in r])
            delta = a-b
            refhash = ordered(reference)
            if refhash != saved['layers'][tag]['decoded_ordered_xy_sha256']:
                raise ValueError('Recovered coordinates do not match saved GDB hash: '+tag)
            common = {k:v for k,v in attrs.items() if k in saved['layers'][tag]['attributes']}
            attrdiff = {k:[v,saved['layers'][tag]['attributes'][k]] for k,v in common.items()
                        if v != saved['layers'][tag]['attributes'][k]}
            if attrdiff:
                raise ValueError('Common attributes differ: '+repr(attrdiff))
            report['layers'][tag] = dict(table=table, polygons=len(actual), coordinates=len(a),
                valid=bool(geom.is_valid), ordered_gpkg_xy_sha256=ordered(actual),
                reference_gdb_xy_sha256=refhash, reference_matches_saved_gdb_hash=True,
                max_abs_coordinate_component_delta_degree=float(np.abs(delta).max()),
                unequal_coordinate_pairs=int(np.count_nonzero(np.any(delta != 0, axis=1))),
                max_vertex_distance_degree=float(np.linalg.norm(delta, axis=1).max()),
                common_attributes_checked=len(common), common_attributes_different=attrdiff,
                close_vertices=close_pairs(geom))
        conn.close()
    u,c = geometries['unchanged'],geometries['candidate']
    before = list(u.geoms[2023].exterior.coords)
    after = list(c.geoms[2023].exterior.coords)
    if before[:54179]+before[54181:] != after:
        raise ValueError('Candidate is not exactly the stated two deletions')
    if any(list(a.exterior.coords) != list(b.exterior.coords) for i,(a,b) in enumerate(zip(u.geoms,c.geoms)) if i != 2023):
        raise ValueError('Unstated changes in other rings')
    report['local_change'] = dict(ring=2023, removed_positions=[54179,54180],
        removed_gpkg_coordinates=[before[54179],before[54180]],
        gpkg_entrance_distance_degree=math.dist(before[54178],before[54180]),
        added_area_degree2=float(c.difference(u).area), lost_area_degree2=float(u.difference(c).area))
    for pos in (54178,54179,54180,54181):
        diagnostics.append(dict(type='Feature', properties=dict(role='diagnostic vertex; not an Esri-reported error location',
            ring=2023, position=pos, gdb_json_coordinate=rings[2023][pos]),
            geometry=dict(type='Point', coordinates=before[pos])))
    diagnostics.append(dict(type='Feature', properties=dict(role='two-vertex-deletion added area; diagnostic only'),
                            geometry=json.loads(shapely.to_geojson(c.difference(u)))))
    report['limits'] = ['Fresh GPKG versus recovered GDB-derived JSON comparison; raw GDB unavailable in this run.',
        'Candidate GDB coordinates independently bridged by saved SHA-256 after the recorded two deletions.',
        'No Esri error position is present in the saved CLASS/FEATURE_ID/PROBLEM tables.',
        'Coordinates identify the changed notch, not the Esri internal mechanism or legal ownership.']
    if archive.read_bytes()!=raw or esri_json.read_bytes()!=eraw:
        raise ValueError('Input changed')
    report['inputs_unchanged'] = True
    output.mkdir(parents=True)
    (output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (output/'diagnostic-locations.geojson').write_text(json.dumps(dict(type='FeatureCollection',features=diagnostics),ensure_ascii=False,indent=2)+'\n')
    return report


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive', type=Path)
    p.add_argument('esri_json', type=Path)
    p.add_argument('--prior', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a=p.parse_args()
    print(json.dumps(run(a.archive,a.esri_json,a.prior,a.output),ensure_ascii=False,indent=2))
