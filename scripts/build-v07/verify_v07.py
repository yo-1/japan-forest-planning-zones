import geopandas as gpd, numpy as np, shapely, json, hashlib, sys
from shapely.ops import unary_union
B = '/home/hatch/workspace/forest-planning-zones'
V5F = f'{B}/v05-candidate/forest_planning_zones_2026_provisional_labeled.gpkg'
V7F = f'{B}/v07-candidate/forest_planning_zones_2026_provisional_labeled.gpkg'
V5M = f'{B}/v05-published/extracted_muni/municipality_forest_zones_2026_candidate.gpkg'
V7M = f'{B}/v07-candidate/municipality_forest_zones_2026_candidate.gpkg'
stage = sys.argv[1]
res = {}
if stage == 'attrs':
    import fiona
    res['v07_forest_layers'] = fiona.listlayers(V7F)
    def attrhash(df):
        d = df.drop(columns='geometry').astype(str)
        return hashlib.sha256(d.to_csv(index=False).encode()).hexdigest()
    for layer in ['forest_plan_districts_provisional', 'forest_wide_basins_provisional',
                  'forest_unassigned_review', 'gap_residual_review']:
        a = gpd.read_file(V5F if layer != 'gap_residual_review' else f'{B}/v06-candidate/forest_planning_zones_2026_provisional_labeled.gpkg', layer=layer)
        b = gpd.read_file(V7F, layer=layer)
        res[layer] = {'rows': len(b), 'valid': bool(shapely.is_valid(b.geometry.values).all()),
                      'empty': int(shapely.is_empty(b.geometry.values).sum()),
                      'attr_equal': attrhash(a) == attrhash(b)}
        print(layer, res[layer], flush=True)
        del a, b
    a = gpd.read_file(V5M, layer='plane_rectangular_municipalities_2026')
    b = gpd.read_file(V7M, layer='plane_rectangular_municipalities_2026')
    res['municipalities'] = {'rows': len(b), 'valid': bool(shapely.is_valid(b.geometry.values).all()),
                             'attr_equal': attrhash(a) == attrhash(b)}
    ap = a.to_crs(6933); bp = b.to_crs(6933)
    res['municipalities']['area_total_delta_m2'] = float(bp.geometry.area.sum() - ap.geometry.area.sum())
    sd = [x.symmetric_difference(y).area for x, y in zip(ap.geometry.values, bp.geometry.values)]
    res['municipalities']['symdiff_total_m2'] = float(np.sum(sd)); res['municipalities']['symdiff_max_m2'] = float(np.max(sd))
    print('municipalities', res['municipalities'], flush=True)
elif stage == 'districts':
    d5 = gpd.read_file(V5F, layer='forest_plan_districts_provisional')
    d7 = gpd.read_file(V7F, layer='forest_plan_districts_provisional')
    assert (d5.district_code.values == d7.district_code.values).all()
    d5p = d5.to_crs(6933); d7p = d7.to_crs(6933)
    deltas = d7p.geometry.area.values - d5p.geometry.area.values
    res['district_area_max_abs_delta_m2'] = float(np.abs(deltas).max())
    res['district_area_total_delta_m2'] = float(deltas.sum())
    sd = [x.symmetric_difference(y).area for x, y in zip(d5p.geometry.values, d7p.geometry.values)]
    res['district_symdiff_total_m2'] = float(np.sum(sd)); res['district_symdiff_max_m2'] = float(np.max(sd))
    i = int(np.argmax(sd)); res['district_symdiff_worst'] = f"{d5.district_code.iloc[i]} {d5.district_name.iloc[i]}"
    print('area/symdiff', {k: res[k] for k in list(res)}, flush=True)
    sidx = d7p.sindex; geoms = d7p.geometry.values; tot = 0.0; pairs = []
    for i2 in range(len(geoms)):
        for j in sidx.query(geoms[i2], predicate='intersects'):
            if j <= i2: continue
            inter = geoms[i2].intersection(geoms[j])
            if not inter.is_empty and inter.area > 0:
                tot += inter.area; pairs.append([d7p.district_code.iloc[i2], d7p.district_code.iloc[j], round(float(inter.area), 6)])
    res['district_overlap_total_m2'] = float(tot); res['district_overlap_pairs'] = pairs
    print('overlap', tot, pairs, flush=True)
elif stage == 'holes':
    d7 = gpd.read_file(V7F, layer='forest_plan_districts_provisional')
    u7 = gpd.GeoSeries([unary_union(d7.geometry.values)], crs=6668).to_crs(6933).iloc[0]
    del d7
    holes = gpd.read_file(f'{B}/v04-candidate/extracted/forest_planning_zones_2026_provisional_labeled.gpkg',
                          layer='gap_residual_review').to_crs(6933)
    res['hole16_coverage_v07'] = [round(float(h.geometry.intersection(u7).area / h.geometry.area), 4) for _, h in holes.iterrows()]
    print('hole16 coverage v0.7:', res['hole16_coverage_v07'], flush=True)
json.dump(res, open(f'{B}/v07-candidate/verify_{stage}.json', 'w'), ensure_ascii=False, indent=1)
print('SAVED', stage)
