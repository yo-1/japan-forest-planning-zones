"""ArcGIS Pro runtime only: copy to a new GDB and record ESRI Check Geometry.

Never runs Repair Geometry. Sources are read-only; exported geometries and
actual spatial-reference settings are retained for investigation.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

DEFAULT_LAYERS = {
    'forest_plan_districts_provisional', 'forest_wide_basins_provisional',
    'forest_unassigned_review', 'districts_upstream_trial', 'districts_v03_control',
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def spatial_reference(arcpy, dataset):
    sr = arcpy.Describe(dataset).spatialReference
    return dict(name=sr.name, factory_code=sr.factoryCode,
                xy_resolution=sr.XYResolution, xy_tolerance=sr.XYTolerance,
                wkt_with_domain=sr.exportToString())


def run(sources, output, layers=None, xy_resolution=None, xy_tolerance=None):
    # Deferred import permits syntax/help checks without an ArcGIS installation.
    import arcpy
    output.mkdir(parents=True, exist_ok=False)
    gdb = output / 'comparison.gdb'
    arcpy.management.CreateFileGDB(str(output), gdb.name)
    report = dict(scope='Actual ArcGIS ESRI check; no repair; not boundary certification',
                  arcgis=arcpy.GetInstallInfo(), python=sys.version, sources=[],
                  requested_xy_resolution=xy_resolution, requested_xy_tolerance=xy_tolerance)
    environment = dict(overwriteOutput=False, outputCoordinateSystem=arcpy.SpatialReference(6668))
    if xy_resolution is not None:
        environment['XYResolution'] = xy_resolution
    if xy_tolerance is not None:
        environment['XYTolerance'] = xy_tolerance
    with arcpy.EnvManager(**environment):
        for label, path in sources:
            before = digest(path)
            source_result = dict(label=label, name=path.name, input_sha256=before, layers=[])
            report['sources'].append(source_result)
            with arcpy.EnvManager(workspace=str(path)):
                available = arcpy.ListFeatureClasses() or []
            wanted = set(layers) if layers else DEFAULT_LAYERS
            selected = [name for name in available if name.split('.')[-1] in wanted]
            if not selected:
                raise ValueError('No requested feature classes found: ' + label)
            if layers and set(layers) - {name.split('.')[-1] for name in selected}:
                raise ValueError('Requested layer missing: ' + label)
            for index, name in enumerate(selected):
                layer = name.split('.')[-1]
                source = str(path / name)
                target = str(gdb / (label + '_' + str(index)))
                original_settings = spatial_reference(arcpy, source)
                source_count = int(arcpy.management.GetCount(source)[0])
                arcpy.management.CopyFeatures(source, target)
                count = int(arcpy.management.GetCount(target)[0])
                if count != source_count:
                    raise ValueError('Export changed feature count: ' + label + '/' + layer)
                table = str(gdb / (label + '_' + str(index) + '_check'))
                arcpy.management.CheckGeometry(target, table, 'ESRI')
                fields = [field.name for field in arcpy.ListFields(table) if field.type != 'Geometry']
                problems = [dict(zip(fields, row)) for row in arcpy.da.SearchCursor(table, fields)]
                issue_rows = [row for row in problems if
                    str(row.get('PROBLEM', '')).replace('_', ' ').strip().lower() != 'no problems found']
                issue_ids = {row.get('FEATURE_ID') for row in issue_rows}
                names = {field.name for field in arcpy.ListFields(target)}
                identities = [field for field in ('district_code', 'district_name', 'basin_code',
                    'basin_name', 'source_district_fid', 'source_fid', 'municipality_code') if field in names]
                features = []
                for row in arcpy.da.SearchCursor(target, ['OID@', *identities, 'SHAPE@JSON']):
                    attributes = dict(zip(identities, row[1:-1]))
                    diagnostic = attributes.get('district_code') == '025' or attributes.get('basin_code') == '43'
                    if row[0] in issue_ids or diagnostic:
                        features.append(dict(objectid=row[0], attributes=attributes,
                                             geometry=json.loads(row[-1]) if row[-1] else None))
                geometry_file = label + '_' + layer + '_geometry.json'
                (output / geometry_file).write_text(json.dumps(features, ensure_ascii=False) + '\n', encoding='utf-8')
                source_result['layers'].append(dict(layer=layer, features=count, source_settings=original_settings,
                    gdb_settings=spatial_reference(arcpy, target), check_rows=problems,
                    issue_rows=len(issue_rows), diagnostic_geometry=geometry_file,
                    geometry_sha256=digest(output / geometry_file)))
            source_result['input_unchanged'] = before == digest(path)
            if not source_result['input_unchanged']:
                raise ValueError('Source file changed during ArcGIS check: ' + label)
    settings = [layer['gdb_settings'] for source in report['sources'] for layer in source['layers']]
    report['same_gdb_settings'] = all(settings[0] == value for value in settings[1:])
    report['issue_rows_total'] = sum(layer['issue_rows'] for source in report['sources'] for layer in source['layers'])
    report['comparison_ready'] = report['same_gdb_settings']
    (output / 'arcgis_check_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', action='append', required=True, help='Unique ASCII label=absolute GeoPackage path; repeatable')
    parser.add_argument('--output', required=True, type=Path, help='New output directory')
    parser.add_argument('--layer', action='append', help='Exact unqualified layer name; repeatable')
    parser.add_argument('--xy-resolution', help='Optional ArcGIS environment value, including unit')
    parser.add_argument('--xy-tolerance', help='Optional ArcGIS environment value, including unit')
    args = parser.parse_args()
    sources = []
    for source in args.source:
        label, separator, filename = source.partition('=')
        path = Path(filename).resolve()
        if not separator or not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,19}', label) or not path.is_file():
            parser.error('Each source must be label=existing GeoPackage path')
        if label in {name for name, _ in sources}:
            parser.error('Duplicate source label')
        sources.append((label, path))
    if args.output.exists():
        parser.error('Output already exists; use a new directory')
    result = run(sources, args.output, args.layer, args.xy_resolution, args.xy_tolerance)
    print(json.dumps({'issue_rows_total': result['issue_rows_total'],
                      'comparison_ready': result['comparison_ready']}, ensure_ascii=False))
    if not result['comparison_ready'] or result['issue_rows_total']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
