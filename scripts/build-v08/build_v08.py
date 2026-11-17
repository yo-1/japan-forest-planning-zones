# v0.8: apply the prefectural-plan-confirmed memberships (2026-11-17, Forestry Agency guidance)
# on top of the verified v0.7 candidate. Surgical: only the 13 municipalities and their
# districts/basins change; all other geometries are carried over untouched.
import geopandas as gpd, shapely, json, os
V7 = '/home/hatch/workspace/forest-planning-zones/v07-candidate'
OUT = '/home/hatch/workspace/forest-planning-zones/v08-candidate'
ASSIGN = {  # municipality_code -> (district_code, forest_source_url)
 '01699': ('012', 'https://www.e-stat.go.jp/stat-search/file-download?statInfId=000001203360&fileKind=2'),
 '03216': ('021', 'https://www3.pref.iwate.jp/webdb/view/outside/s19Kenpo/kenpoFile.download?fileId=s19Kenpo-1SjTBD.18OYJ.1ENHAp'),
 '12239': ('046', 'https://www.pref.chiba.lg.jp/shinrin/keikaku/nourinsuisan/shinrinkeikaku.html'),
 '13363': ('049', 'https://www.e-stat.go.jp/stat-search/file-download?statInfId=000001203360&fileKind=2'),
 '17212': ('058', 'https://www.rinya.maff.go.jp/kinki/keikaku/shinrin_keikaku/system_summary/keikakusyo/pdf/PDF/058kaga_01kokushin_R3_jyuritsu.pdf'),
 '17461': ('057', 'https://www-pref-ishikawa-lg-jp.cache.yimg.jp/shinrin/documents/r1_document.pdf'),
 '17463': ('057', 'https://www-pref-ishikawa-lg-jp.cache.yimg.jp/shinrin/documents/r1_document.pdf'),
 '21221': ('072', 'https://www.pref.gifu.lg.jp/uploaded/attachment/41730.pdf'),
 '23237': ('078', 'https://www.pref.aichi.jp/uploaded/life/621855_2859480_misc.pdf'),
 '23238': ('078', 'https://www.pref.aichi.jp/uploaded/life/621855_2859480_misc.pdf'),
 '28221': ('089', 'https://web.pref.hyogo.lg.jp/nk14/r8keikakujuran2.html'),
 '39212': ('126', 'https://www.pref.kochi.lg.jp/doc/chiikikeikaku/file_contents/file_2026184184713_1.pdf'),
 '40231': ('129', 'https://www.pref.fukuoka.lg.jp/uploaded/life/764782_62448402_misc.pdf'),
}
FG = f'{V7}/forest_planning_zones_2026_provisional_labeled.gpkg'
MG = f'{V7}/municipality_forest_zones_2026_candidate.gpkg'
dist = gpd.read_file(FG, layer='forest_plan_districts_provisional')
basin = gpd.read_file(FG, layer='forest_wide_basins_provisional')
un = gpd.read_file(FG, layer='forest_unassigned_review')
res = gpd.read_file(FG, layer='gap_residual_review')
muni = gpd.read_file(MG, layer='plane_rectangular_municipalities_2026')
dmap = {r.district_code: r for r in dist.itertuples()}
log = {'assigned': {}, 'districts_changed': {}, 'basins_changed': []}

for code, (dcode, url) in ASSIGN.items():
    rows = muni[muni['N03_007'] == code]
    assert len(rows) == 1, (code, len(rows))
    d = dmap[dcode]
    i = rows.index[0]
    muni.loc[i, 'forest_district_code'] = dcode
    muni.loc[i, 'forest_district_name'] = d.district_name
    muni.loc[i, 'wide_basin_code'] = str(d.basin_code)
    muni.loc[i, 'wide_basin_name'] = d.basin_name
    muni.loc[i, 'forest_status'] = '所属計画区を県資料で照合・境界未確認'
    muni.loc[i, 'forest_source_date'] = '2026-11-17'
    muni.loc[i, 'forest_source_url'] = url
    log['assigned'][code] = {'municipality': rows.iloc[0]['N03_004'], 'district': dcode,
                             'district_name': d.district_name, 'basin': str(d.basin_code), 'basin_name': d.basin_name}
    print('assign', code, rows.iloc[0]['N03_004'], '->', dcode, d.district_name, '/ basin', d.basin_code, d.basin_name, flush=True)

# districts: union in the new municipalities
from collections import defaultdict
by_district = defaultdict(list)
for code, (dcode, _) in ASSIGN.items():
    by_district[dcode].append(muni.loc[muni['N03_007'] == code, 'geometry'].iloc[0])
for dcode, geoms in by_district.items():
    i = dist.index[dist['district_code'] == dcode][0]
    dist.loc[i, 'geometry'] = shapely.union_all([dist.loc[i, 'geometry']] + geoms)
    dist.loc[i, 'source_features'] = int(dist.loc[i, 'source_features']) + len(geoms)
    log['districts_changed'][dcode] = len(geoms)
# basins: union in the new municipalities by basin
by_basin = defaultdict(list)
for code, (dcode, _) in ASSIGN.items():
    by_basin[str(dmap[dcode].basin_code)].append(muni.loc[muni['N03_007'] == code, 'geometry'].iloc[0])
print('basin columns:', list(basin.columns))
bcode_col = 'basin_code' if 'basin_code' in basin.columns else basin.columns[0]
for bcode, geoms in by_basin.items():
    i = basin.index[basin[bcode_col].astype(str) == bcode][0]
    basin.loc[i, 'geometry'] = shapely.union_all([basin.loc[i, 'geometry']] + geoms)
    log['basins_changed'].append(bcode)
# unassigned: drop the 13
un = un[~un['municipality_code'].isin(ASSIGN.keys())].copy()
# residual: drop the 3 unassigned holes (058 Nonoichi, 078 Nagakute, 078 Ama)
drop = ((res['district_code'] == '058') & (res['area_m2'] > 1e7)) | ((res['district_code'] == '078') & (res['area_m2'] > 1e7))
res = res[~drop].copy()
print('unassigned rows now', len(un), '| residual rows now', len(res))
for p in [f'{OUT}/forest_planning_zones_2026_provisional_labeled.gpkg', f'{OUT}/municipality_forest_zones_2026_candidate.gpkg']:
    if os.path.exists(p): os.remove(p)
dist.to_file(f'{OUT}/forest_planning_zones_2026_provisional_labeled.gpkg', layer='forest_plan_districts_provisional', driver='GPKG')
basin.to_file(f'{OUT}/forest_planning_zones_2026_provisional_labeled.gpkg', layer='forest_wide_basins_provisional', driver='GPKG', mode='a')
un.to_file(f'{OUT}/forest_planning_zones_2026_provisional_labeled.gpkg', layer='forest_unassigned_review', driver='GPKG', mode='a')
res.to_file(f'{OUT}/forest_planning_zones_2026_provisional_labeled.gpkg', layer='gap_residual_review', driver='GPKG', mode='a')
muni.to_file(f'{OUT}/municipality_forest_zones_2026_candidate.gpkg', layer='plane_rectangular_municipalities_2026', driver='GPKG')
json.dump(log, open(f'{OUT}/build_log.json', 'w'), ensure_ascii=False, indent=1)
print('BUILD V08 DONE')
