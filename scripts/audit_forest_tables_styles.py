"""Audit candidate tables and QML; optionally verify downloaded release ZIPs.

Uses the standard library. This checks internal consistency, not official boundaries.
"""
import argparse
import collections
import csv
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def audit(root, release_dir=None):
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(message)

    base = rows(root / 'data/municipality_zones.csv')
    joined = rows(root / 'data/municipality_coordinate_forest_zones.csv')
    mapping = rows(root / 'data/forest/municipality_forest_districts.csv')
    districts = rows(root / 'data/forest/forest_plan_districts.csv')
    basins = rows(root / 'data/forest/forest_wide_basins.csv')
    dictionaries = {}
    for name, table, key, width, count in [
        ('municipalities', mapping, 'municipality_code', 5, 1905),
        ('districts', districts, 'district_code', 3, 158),
        ('basins', basins, 'basin_code', 2, 44),
    ]:
        dictionary = {r[key]: r for r in table}
        check(len(table) == count, name + ': unexpected row count')
        check(len(dictionary) == len(table), name + ': duplicate identifiers')
        check(all(re.fullmatch(r'[0-9]{%d}' % width, r[key]) for r in table), name + ': invalid identifier width')
        dictionaries[name] = dictionary
    m, d, b = (dictionaries[n] for n in ['municipalities', 'districts', 'basins'])
    for row in districts:
        basin = b.get(row['basin_code'])
        check(basin is not None and basin['basin_name'] == row['basin_name'], 'district basin mismatch: ' + row['district_code'])
    for row in mapping:
        code = row['municipality_code']
        if row['district_code']:
            district = d.get(row['district_code'])
            check(district is not None, 'unknown district: ' + code)
            if district:
                check(all(row[k] == district[k] for k in ['district_name', 'basin_code', 'basin_name']), 'membership mismatch: ' + code)
        else:
            check(not any(row[k] for k in ['district_name', 'basin_code', 'basin_name']), 'partial unassigned row: ' + code)
        check(row['usable_for_final_polygon'] == 'false', 'unexpected certification: ' + code)
    source = {r['code']: r for r in base}
    output = {r['code']: r for r in joined}
    check(len(source) == len(base) == 1905 and len(output) == len(joined) == 1905, 'coordinate tables: duplicate or wrong count')
    check(set(source) == set(output) == set(m), 'municipality key coverage mismatch')
    fields = {'forest_district_code': 'district_code', 'forest_district_name': 'district_name', 'wide_basin_code': 'basin_code', 'wide_basin_name': 'basin_name', 'forest_status': 'verification_status', 'forest_coverage': 'coverage', 'forest_source_date': 'source_date', 'forest_source_url': 'source_url', 'basin_source_date': 'basin_source_date', 'basin_source_url': 'basin_source_url', 'forest_final_usable': 'usable_for_final_polygon'}
    for code in set(source) & set(output) & set(m):
        check(all(output[code].get(k) == v for k, v in source[code].items()), 'source attribute changed: ' + code)
        check(all(output[code].get(k) == m[code][v] for k, v in fields.items()), 'joined attribute mismatch: ' + code)
    feature_count = sum(len(r['zones'].split(';')) for r in base)
    split = [{'code': r['code'], 'zones': r['zones'], 'expected_features': len(r['zones'].split(';'))} for r in base if ';' in r['zones']]
    check(feature_count == 1911 and len(split) == 5, 'source feature or split municipality count mismatch')
    unassigned = sorted(r['municipality_code'] for r in mapping if not r['district_code'])
    check(len(unassigned) == 20, 'unexpected unassigned count')
    styles = {}
    for layer, dictionary, code_field, name_field in [
        ('forest_plan_districts_provisional', d, 'district_code', 'district_name'),
        ('forest_wide_basins_provisional', b, 'basin_code', 'basin_name'),
    ]:
        xml = ET.parse(root / 'styles' / (layer + '.qml')).getroot()
        categories = xml.findall('./renderer-v2/categories/category')
        values = [c.get('value') for c in categories]
        check(len(values) == len(set(values)) == len(dictionary) and set(values) == set(dictionary), layer + ': category coverage mismatch')
        check(xml.find('./renderer-v2').get('attr') == code_field, layer + ': wrong classification field')
        check(xml.get('labelsEnabled') == '1', layer + ': disabled labels')
        label = xml.find('./labeling/settings/text-style')
        expected = '"' + code_field + '" || \'_\' || "' + name_field + '"'
        check(label is not None and label.get('fieldName') == expected and label.get('isExpression') == '1', layer + ': label expression mismatch')
        symbols = {s.get('name') for s in xml.findall('./renderer-v2/symbols/symbol')}
        check(all(c.get('symbol') in symbols for c in categories), layer + ': undefined symbol')
        check(all(c.get('label') in [c.get('value') + sep + dictionary[c.get('value')][name_field] for sep in [' ', '_']] for c in categories if c.get('value') in dictionary), layer + ': category label mismatch')
        styles[layer] = {'categories': len(categories), 'labels_enabled': xml.get('labelsEnabled') == '1', 'label_expression': label.get('fieldName') if label is not None else None}
    for path in (root / 'styles').glob('*.qml'):
        ET.parse(path)
    release = {'checked': False}
    if release_dir:
        manifest = json.loads((release_dir / 'review_manifest.json').read_text(encoding='utf-8'))
        packages = []
        for entry in manifest['review_files']:
            path = release_dir / entry['name']
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            check(path.stat().st_size == entry['bytes'] and digest.hexdigest() == entry['sha256'], 'release digest mismatch: ' + path.name)
            with zipfile.ZipFile(path) as archive:
                check(archive.testzip() is None, 'ZIP CRC failure: ' + path.name)
                names = archive.namelist()
                expected_names = {'README.txt', 'municipality_forest_zones_2026_candidate.gpkg'}
                if path.name == 'forest_planning_zones_2026_review.zip':
                    expected_names = {'README.txt', 'forest_planning_zones_2026_provisional_labeled.gpkg', 'plane_rectangular_zones_2026.gpkg'}
                    expected_names.update('tables/' + n for n in ['municipality_forest_districts.csv', 'forest_plan_districts.csv', 'forest_wide_basins.csv'])
                    expected_names.update('styles/' + p.name for p in (root / 'styles').glob('*.qml'))
                check(len(names) == len(expected_names) and set(names) == expected_names, 'unexpected distribution file list: ' + path.name)
                for name in names:
                    if name.startswith('tables/') and name.endswith('.csv'):
                        local = root / 'data/forest' / Path(name).name
                        check(archive.read(name) == local.read_bytes(), 'packaged table differs: ' + name)
                gpkg_checks = []
                with tempfile.TemporaryDirectory(prefix='forest-release-audit-') as temporary:
                    for name in names:
                        if not name.endswith('.gpkg'):
                            continue
                        target = Path(temporary) / Path(name).name
                        with archive.open(name) as src, target.open('wb') as dst:
                            shutil.copyfileobj(src, dst)
                        conn = sqlite3.connect(target.as_uri() + '?mode=ro', uri=True)
                        try:
                            check(conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'GeoPackage integrity: ' + name)
                            tables = []
                            for table, geom, srid in conn.execute('SELECT table_name,column_name,srs_id FROM gpkg_geometry_columns'):
                                check(srid == 6668, 'GeoPackage CRS: ' + table)
                                quoted = '"' + table.replace('"', '""') + '"'
                                columns = {r[1] for r in conn.execute('PRAGMA table_info(' + quoted + ')')}
                                count = conn.execute('SELECT count(*) FROM ' + quoted).fetchone()[0]
                                expected = {'forest_plan_districts_provisional': 158, 'forest_wide_basins_provisional': 44, 'forest_unassigned_review': 20, 'plane_rectangular_zones_2026': 19, 'plane_rectangular_municipalities_2026': 1911}.get(table)
                                check(expected is not None and count == expected, 'GeoPackage feature count: ' + table)
                                if table == 'plane_rectangular_municipalities_2026':
                                    query = 'SELECT N03_007,' + ','.join('"' + f + '"' for f in fields) + ' FROM ' + quoted
                                    codes = set()
                                    for values in conn.execute(query):
                                        code = values[0]
                                        codes.add(code)
                                        check(code in m, 'GeoPackage unmapped code: ' + str(code))
                                        if code in m:
                                            check(all((actual or '') == m[code][key] for actual, key in zip(values[1:], fields.values())), 'GeoPackage membership mismatch: ' + code)
                                    check(codes == set(m), 'GeoPackage code coverage')
                                else:
                                    defaults = conn.execute('SELECT styleQML FROM layer_styles WHERE f_table_name=? AND useAsDefault=1', (table,)).fetchall()
                                    check(len(defaults) == 1, 'GeoPackage default style: ' + table)
                                    for qml, in defaults:
                                        xml = ET.fromstring(qml)
                                        renderer = xml.find('./renderer-v2')
                                        if renderer is not None and renderer.get('attr'):
                                            check(renderer.get('attr') in columns, 'GeoPackage style attribute: ' + table)
                                        label = xml.find('./labeling/settings/text-style')
                                        if xml.get('labelsEnabled') == '1' and label is not None:
                                            referenced = re.findall(r'"([^"]+)"', label.get('fieldName', '')) if label.get('isExpression') == '1' else [label.get('fieldName')]
                                            check(all(field in columns for field in referenced), 'GeoPackage label attribute: ' + table)
                                tables.append({'table': table, 'features': count, 'epsg': srid})
                            gpkg_checks.append({'name': name, 'tables': tables})
                        finally:
                            conn.close()
                        target.unlink()
                packages.append({'name': path.name, 'bytes': path.stat().st_size, 'sha256': digest.hexdigest(), 'entries': len(names), 'geopackages': gpkg_checks})
        release = {'checked': True, 'packages': packages}
    return {'status': 'pass' if not errors else 'fail', 'scope': 'internal consistency; official membership and boundaries unverified', 'municipality_codes': len(m), 'municipality_features_expected_from_zones': feature_count, 'districts': len(d), 'basins': len(b), 'unassigned_codes': unassigned, 'split_municipalities': split, 'verification_status_counts': dict(collections.Counter(r['verification_status'] for r in mapping)), 'styles': styles, 'release': release, 'qgis_gui_verified': False, 'errors': errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--release-dir', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = audit(args.root, args.release_dir)
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    print(text, end='')
    raise SystemExit(0 if result['status'] == 'pass' else 1)


if __name__ == '__main__':
    main()
