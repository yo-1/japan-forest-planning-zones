"""Compare selected forest-target GeoPackages with municipality candidates.

The result verifies membership only at forest locations. It cannot confirm
the administrative boundary of a planning district or wide basin.

Usage: python compare_forest_target_layer.py MAPPING.csv OUTPUT.csv INPUT.gpkg ...
"""
import collections
import csv
import json
import sqlite3
import sys
from pathlib import Path


def main(mapping, output, sources):
    with open(mapping, encoding='utf-8-sig', newline='') as stream:
        candidate = {r['municipality_code']: r for r in csv.DictReader(stream)}
    observations = collections.Counter()
    source_stats = []
    for path in sources:
        db = sqlite3.connect(f'file:{Path(path).resolve()}?mode=ro', uri=True)
        layer = db.execute('SELECT table_name FROM gpkg_geometry_columns').fetchone()[0]
        stats = db.execute(
            f'SELECT COUNT(*), COUNT(DISTINCT "市町村コード5桁"),'
            f' MIN("データ時点"), MAX("データ時点") FROM "{layer}"'
        ).fetchone()
        source_stats.append(dict(layer=layer, features=stats[0], municipality_codes=stats[1],
                                 date_min=stats[2], date_max=stats[3]))
        for code, district_code, district_name, basin_name, count in db.execute(
            f'SELECT "市町村コード5桁","森林計画区コード","森林計画区名称",'
            f'"広域流域名称",COUNT(*) FROM "{layer}" GROUP BY 1,2,3,4'
        ):
            observations[(layer, code, district_code, district_name, basin_name)] += count
        db.close()
    result = []
    for (pref, code, district_code, district_name, basin_name), count in sorted(
        observations.items(), key=lambda item: tuple(v or '' for v in item[0])
    ):
        row = candidate.get(code)
        if row is None:
            status = '対応表にコードなし'
        elif not district_name or not basin_name:
            status = '森林側属性空欄'
        elif not row['district_code']:
            status = '候補未割当・森林側に所属あり'
        elif row['district_name'] != district_name or row['basin_name'] != basin_name:
            status = '名称または広域流域の不一致・要照会'
        elif row['district_code'] != district_code:
            status = '名称一致・計画区コード体系相違'
        else:
            status = '所属とコード一致・森林存在地点のみ'
        result.append(dict(prefecture=pref, municipality_code=code or '',
                           candidate_name=row['municipality'] if row else '',
                           candidate_district_code=row['district_code'] if row else '',
                           candidate_district_name=row['district_name'] if row else '',
                           candidate_basin_name=row['basin_name'] if row else '',
                           forest_district_code=district_code or '',
                           forest_district_name=district_name or '',
                           forest_basin_name=basin_name or '',
                           forest_features=count, status=status))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(result[0]))
        writer.writeheader()
        writer.writerows(result)
    summary = dict(source_layers=source_stats, observed_codes=len({(k[0], k[1]) for k in observations}),
                   comparison_rows=len(result), status_rows=dict(collections.Counter(r['status'] for r in result)),
                   warning='Forest-target polygons do not establish administrative whole-area boundaries.')
    output.with_suffix('.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
