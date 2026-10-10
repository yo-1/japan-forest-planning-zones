"""Build review-only download packages; never certify forestry boundaries."""
import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from build_provisional_aggregates import decode
from drop_tiny_rings import drop_tiny_rings, rewrite_geometry

ROOT = Path(__file__).resolve().parents[1]
SOURCE_BASE = 'https://github.com/yo-1/japan-plane-rectangular-cs-zones/releases/download/v2026.1/'
MUNICIPALITY_ZIP_SHA256 = '091606c6a0c84f62ee3611a01e93913c9fb343add9a5201cc5a7dff90da30b20'
# 19系区域は、派生元Release v2026.2 の系ごと版（面積1㎡未満の内部リングを除いた版）を使う。
ZONES_SOURCE_BASE = 'https://github.com/yo-1/japan-plane-rectangular-cs-zones/releases/download/v2026.2/'
ZONES_ZIP_SHA256 = 'c32ac8417ee604436e0a20280a6f2d3a1e73a3247c5a8db10230209daf9e3fbd'
ZONE_GEOMETRY_SHA256 = '23fa2d62f395ce192857e2a69444e639e24d4f89c30f4da17d0976b0acb3a02b'
# 集約レイヤの内部リングのうち、等積面積がこの値（㎡）未満のものを削除する（v2026.2 と同じ基準）。
TINY_RING_AREA_M2 = 1.0
AGGREGATE_COUNTS = {'forest_plan_districts_provisional': 158, 'forest_wide_basins_provisional': 44, 'forest_unassigned_review': 20}


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def download_gpkg(asset, work, expected_sha=None, base=SOURCE_BASE):
    archive = work / asset
    with urllib.request.urlopen(base + asset, timeout=120) as src, archive.open('wb') as dst:
        shutil.copyfileobj(src, dst)
    if expected_sha and sha256(archive) != expected_sha:
        raise ValueError('Upstream ZIP SHA-256 mismatch: ' + asset)
    with zipfile.ZipFile(archive) as z:
        matches = [n for n in z.namelist() if n.lower().endswith('.gpkg')]
        if len(matches) != 1:
            raise ValueError('Expected one GeoPackage in ' + asset)
        output = work / Path(matches[0]).name
        with z.open(matches[0]) as src, output.open('wb') as dst:
            shutil.copyfileobj(src, dst)
    return output


def inspect_gpkg(path, counts):
    conn = sqlite3.connect(path)
    if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('SQLite integrity check failed')
    info = {}
    for table, expected in counts.items():
        col, srid = conn.execute('SELECT column_name,srs_id FROM gpkg_geometry_columns WHERE table_name=?', (table,)).fetchone()
        h = hashlib.sha256()
        n = 0
        for blob, in conn.execute(f'SELECT "{col}" FROM "{table}" ORDER BY fid'):
            actual_srid, geom = decode(blob)
            if actual_srid != 6668 or srid != 6668 or geom.is_empty or not geom.is_valid:
                raise ValueError('Invalid geometry in ' + table)
            h.update(blob)
            n += 1
        if n != expected:
            raise ValueError(f'Unexpected count for {table}: {n}')
        info[table] = {'features': n, 'geometry_sha256': h.hexdigest(), 'epsg': srid, 'invalid': 0, 'empty': 0}
    conn.close()
    return info


def remove_tiny_interior_rings(source, destination, tables):
    """集約レイヤから面積1㎡未満の内部リングを削除する。外環と1㎡以上の穴の座標は、バイト列のまま残る。

    削除したあとに、1㎡未満の内部リングが残っていないことを確かめる。確かめられなければ、公開せずに止める。
    """
    results = drop_tiny_rings(source, destination, list(tables), TINY_RING_AREA_M2)
    conn = sqlite3.connect(destination)
    try:
        for table in tables:
            col = conn.execute('SELECT column_name FROM gpkg_geometry_columns WHERE table_name=?', (table,)).fetchone()[0]
            for fid, blob in conn.execute(f'SELECT fid,"{col}" FROM "{table}"'):
                _, leftover = rewrite_geometry(bytes(blob), TINY_RING_AREA_M2)
                if leftover:
                    raise ValueError(f'Tiny interior rings remain in {table} fid={fid}')
    finally:
        conn.close()
    return {table: {'features_changed': changed, 'rings_dropped': len(areas), 'dropped_area_m2_total': round(sum(areas), 6),
                    'dropped_area_m2_max': round(max(areas, default=0.0), 6)}
            for table, (changed, areas) in results.items()}


def add_styles(path, style_specs):
    conn = sqlite3.connect(path)
    if not conn.execute("SELECT name FROM sqlite_master WHERE name='layer_styles'").fetchone():
        conn.execute("CREATE TABLE layer_styles (id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,f_table_catalog TEXT,f_table_schema TEXT,f_table_name TEXT,f_geometry_column TEXT,styleName TEXT,styleQML TEXT,styleSLD TEXT,useAsDefault BOOLEAN,description TEXT,owner TEXT,ui TEXT,update_time DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))")
    conn.execute('DELETE FROM layer_styles')
    for table, filename, name, default in style_specs:
        qml = (ROOT / 'styles' / filename).read_text(encoding='utf-8')
        q = ET.fromstring(qml)
        if table in AGGREGATE_COUNTS and table != 'forest_unassigned_review':
            if len(q.findall('./renderer-v2/categories/category')) != AGGREGATE_COUNTS[table] or q.get('labelsEnabled') != '1':
                raise ValueError('Invalid review style for ' + table)
        conn.execute('INSERT INTO layer_styles(f_table_catalog,f_table_schema,f_table_name,f_geometry_column,styleName,styleQML,styleSLD,useAsDefault,description,owner,ui) VALUES(?,?,?,?,?,?,?,?,?,?,?)', ('','',table,'geom',name,qml,'',default,'確認用の表示設定。公式境界ではない。','Yoichi Wada',''))
    conn.commit()
    conn.close()


def zip_files(path, files):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for src, target in files:
            z.write(src, target)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, default=ROOT / 'release_output')
    p.add_argument('--candidate', type=Path, help='Local already-joined candidate, for independent packaging check')
    p.add_argument('--zones', type=Path, help='Local user-provided plane coordinate zones')
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    work = a.output / 'work'
    work.mkdir()
    candidate = work / 'municipality_forest_zones_2026_candidate.gpkg'
    if a.candidate:
        shutil.copyfile(a.candidate, candidate)
    else:
        municipality = download_gpkg('plane_rectangular_municipalities_2026.zip', work, MUNICIPALITY_ZIP_SHA256)
        subprocess.run([sys.executable, str(ROOT / 'scripts/build_forest_layer.py'), str(municipality), str(candidate)], check=True)
    candidate_db = sqlite3.connect(candidate)
    t = candidate_db.execute('SELECT table_name FROM gpkg_geometry_columns').fetchone()[0]
    counts = candidate_db.execute(f'SELECT count(*),count(DISTINCT N03_007),sum(forest_district_code IS NULL),sum(forest_final_usable="true") FROM "{t}"').fetchone()
    candidate_db.close()
    if counts != (1911, 1905, 20, 0):
        raise ValueError('Unexpected candidate memberships: ' + str(counts))
    candidate_info = inspect_gpkg(candidate, {t: 1911})
    aggregate_raw = work / 'forest_planning_zones_2026_provisional_raw.gpkg'
    aggregate = work / 'forest_planning_zones_2026_provisional_labeled.gpkg'
    subprocess.run([sys.executable, str(ROOT / 'scripts/build_provisional_aggregates.py'), str(candidate), str(aggregate_raw)], check=True)
    tiny_ring_report = remove_tiny_interior_rings(aggregate_raw, aggregate, AGGREGATE_COUNTS)
    before = inspect_gpkg(aggregate, AGGREGATE_COUNTS)
    add_styles(aggregate, [(table, table + '.qml', '確認用色分け・ラベル', 1) for table in AGGREGATE_COUNTS])
    after = inspect_gpkg(aggregate, AGGREGATE_COUNTS)
    if before != after:
        raise ValueError('Styling changed aggregate geometry')
    zones = work / 'plane_rectangular_zones_2026.gpkg'
    if a.zones:
        shutil.copyfile(a.zones, zones)
    else:
        upstream_zones = download_gpkg('plane_rectangular_zones_2026.zip', work, ZONES_ZIP_SHA256, ZONES_SOURCE_BASE)
        if upstream_zones != zones:
            shutil.copyfile(upstream_zones, zones)
    zone_info = inspect_gpkg(zones, {'plane_rectangular_zones_2026': 19})
    if zone_info['plane_rectangular_zones_2026']['geometry_sha256'] != ZONE_GEOMETRY_SHA256:
        raise ValueError('Coordinate-zone geometry differs from the expected v2026.2 GeoPackage; stop rather than substitute')
    add_styles(zones, [('plane_rectangular_zones_2026','plane_rectangular_zones_2026.qml','layer',1),('plane_rectangular_zones_2026','plane_rectangular_zones_2026_default.qml','default',0)])
    if zone_info != inspect_gpkg(zones, {'plane_rectangular_zones_2026': 19}):
        raise ValueError('Styling changed coordinate-zone geometry')
    readme = ROOT / 'docs/REVIEW_PACKAGE_README.txt'
    files = [(aggregate, aggregate.name),(zones,zones.name),(readme,'README.txt')]
    for name in ('municipality_forest_districts.csv','forest_plan_districts.csv','forest_wide_basins.csv'):
        files.append((ROOT / 'data/forest' / name,'tables/' + name))
    for qml in sorted((ROOT / 'styles').glob('*.qml')):
        files.append((qml,'styles/' + qml.name))
    overview_zip = a.output / 'forest_planning_zones_2026_review.zip'
    zip_files(overview_zip, files)
    municipality_zip = a.output / 'municipality_forest_zones_2026_candidate.zip'
    zip_files(municipality_zip, [(candidate,candidate.name),(readme,'README.txt')])
    manifest = {'status':'provisional; official membership and boundaries not certified','source_municipality_zip_sha256':MUNICIPALITY_ZIP_SHA256,'coordinate_zones_source':'japan-plane-rectangular-cs-zones v2026.2','coordinate_zones_zip_sha256':ZONES_ZIP_SHA256,'coordinate_zones_geometry_sha256':ZONE_GEOMETRY_SHA256,'tiny_interior_rings_removed':{'threshold_m2':TINY_RING_AREA_M2,'layers':tiny_ring_report},'candidate':candidate_info,'aggregates':after,'coordinate_zones':zone_info,'qgis_gui_verified':False,'review_files':[{ 'name': f.name,'bytes':f.stat().st_size,'sha256':sha256(f)} for f in (overview_zip,municipality_zip)]}
    (a.output/'review_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (a.output/'SHA256SUMS.txt').write_text(''.join(f"{entry['sha256']}  {entry['name']}\n" for entry in manifest['review_files']),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
