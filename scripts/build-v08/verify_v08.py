import geopandas as gpd, shapely, numpy as np, json, hashlib
V7 = '/home/hatch/workspace/forest-planning-zones/v07-candidate'
V8 = '/home/hatch/workspace/forest-planning-zones/v08-candidate'
F7 = f'{V7}/forest_planning_zones_2026_provisional_labeled.gpkg'; F8 = f'{V8}/forest_planning_zones_2026_provisional_labeled.gpkg'
M7 = f'{V7}/municipality_forest_zones_2026_candidate.gpkg'; M8 = f'{V8}/municipality_forest_zones_2026_candidate.gpkg'
def offdigit(geoms):
    bad = tot = 0
    for g in geoms:
        a = shapely.get_coordinates(g); tot += len(a)
        bad += int((np.abs(a * 1e9 - np.round(a * 1e9)) > 1e-3).any(axis=1).sum())
    return bad / tot if tot else 0.0
def gh(s): return [hashlib.sha256(shapely.to_wkb(g)).hexdigest() for g in s]
out = {}
EXP_D = {'012','021','046','049','057','058','072','078','089','126','129'}
EXP_B = {'04','10','17','22','23','29','36','39'}
for layer, key in [('forest_plan_districts_provisional','district_code'), ('forest_wide_basins_provisional','basin_code')]:
    a = gpd.read_file(F7, layer=layer); b = gpd.read_file(F8, layer=layer)
    a = a.sort_values(key).reset_index(drop=True); b = b.sort_values(key).reset_index(drop=True)
    changed = set()
    for i in range(len(a)):
        if gh([a.geometry.iloc[i]])[0] != gh([b.geometry.iloc[i]])[0]: changed.add(str(a[key].iloc[i]))
    out[layer] = {'n7': len(a), 'n8': len(b), 'invalid8': int((~shapely.is_valid(b.geometry.values)).sum()),
                  'offdigit8': offdigit(b.geometry.values), 'changed': sorted(changed)}
    print(layer, out[layer], flush=True)
    if layer.startswith('forest_plan'):
        out['district_changed_ok'] = changed == EXP_D
        d8 = b
    else:
        out['basin_changed_ok'] = changed == EXP_B
        out['basin_source_features_23'] = int(b.loc[b['basin_code'].astype(str) == '23', 'source_features'].iloc[0])
un7 = gpd.read_file(F7, layer='forest_unassigned_review'); un8 = gpd.read_file(F8, layer='forest_unassigned_review')
out['unassigned'] = {'n8': len(un8), 'codes8': sorted(un8['municipality_code'].tolist()),
                     'invalid8': int((~shapely.is_valid(un8.geometry.values)).sum()), 'offdigit8': offdigit(un8.geometry.values)}
res7 = gpd.read_file(F7, layer='gap_residual_review'); res8 = gpd.read_file(F8, layer='gap_residual_review')
out['residual'] = {'n8': len(res8), 'districts8': sorted(res8['district_code'].tolist()),
                   'same_geoms_as_v7_enclaves': sorted(gh(res8.geometry.values)) == sorted(gh(res7[res7['district_code'].isin(['040','043','048','050'])].geometry.values))}
m7 = gpd.read_file(M7, layer='plane_rectangular_municipalities_2026'); m8 = gpd.read_file(M8, layer='plane_rectangular_municipalities_2026')
out['muni'] = {'n8': len(m8), 'invalid8': int((~shapely.is_valid(m8.geometry.values)).sum()), 'offdigit8': offdigit(m8.geometry.values),
               'geom_identical_to_v7': gh(m7.sort_values('N03_007').geometry.values) == gh(m8.sort_values('N03_007').geometry.values)}
a7 = m7.sort_values('N03_007').reset_index(drop=True); a8 = m8.sort_values('N03_007').reset_index(drop=True)
diff_rows = {}
for c in a7.columns:
    if c == 'geometry': continue
    neq = (a7[c].astype(str) != a8[c].astype(str))
    if neq.any(): diff_rows[c] = sorted(a7.loc[neq, 'N03_007'].tolist())
out['muni_attr_diff'] = diff_rows
print('muni', out['muni']); print('attr diff', diff_rows, flush=True)
# overlaps among districts (EPSG:6933)
dg = d8.to_crs(6933); geoms = dg.geometry.values; codes = dg['district_code'].tolist()
sidx = shapely.STRtree(geoms); pairs = []
for i, g in enumerate(geoms):
    for j in sidx.query(g, predicate='intersects'):
        if j > i:
            inter = shapely.intersection(g, geoms[j])
            ar = shapely.area(inter) if not shapely.is_empty(inter) else 0.0
            if ar > 1e-9: pairs.append((codes[i], codes[j], float(ar)))
out['district_overlaps'] = pairs
print('overlaps', pairs, flush=True)
# area deltas of changed districts == municipality areas (EPSG:6933)
blog = json.load(open(f'{V8}/build_log.json'))
mg = m8.to_crs(6933); d7 = gpd.read_file(F7, layer='forest_plan_districts_provisional').to_crs(6933)
deltas = {}
for code, info in blog['assigned'].items():
    pass
for dcode in EXP_D:
    a_new = float(shapely.area(d8.loc[d8['district_code'] == dcode, 'geometry'].to_crs(6933).iloc[0]))
    a_old = float(shapely.area(d7.loc[d7['district_code'] == dcode, 'geometry'].iloc[0]))
    msum = sum(float(shapely.area(mg.loc[mg['N03_007'] == c, 'geometry'].iloc[0]))
               for c, v in blog['assigned'].items() if v['district'] == dcode)
    deltas[dcode] = {'delta': a_new - a_old, 'muni_sum': msum, 'diff': (a_new - a_old) - msum}
out['area_deltas'] = deltas
print('area deltas ok:', all(abs(v['diff']) < 0.01 for v in deltas.values()))
json.dump(out, open(f'{V8}/verify_results.json', 'w'), ensure_ascii=False, indent=1, default=str)
print('VERIFY V08 DONE')
