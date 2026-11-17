# Phase 1: normalize the KSJ 2026 admin-boundary source to a uniform 1e-9 degree grid.
# Input : admin-boundary-check-2026/data/*/N03-20260101_*.geojson (47 prefectures)
# Output: v07-candidate/source_normalized.gpkg (all fragments, snapped) + normalization_log.json
import geopandas as gpd, numpy as np, shapely, json, glob, os, time
SRC = sorted(p for p in glob.glob('/home/hatch/workspace/admin-boundary-check-2026/data/pref*/N03-20260101_*.geojson')
             if 'subprefectures' not in p)
OUT = '/home/hatch/workspace/forest-planning-zones/v07-candidate'
assert len(SRC) == 47, f'expected 47 prefecture files, got {len(SRC)}'

def offdigit_frac(geoms):
    c = shapely.get_coordinates(geoms)
    if len(c) == 0: return 0.0
    off = (c[:, 0] != np.round(c[:, 0], 9)) | (c[:, 1] != np.round(c[:, 1], 9))
    return float(off.mean())

frames, log = [], {'files': [], 'total_features': 0, 'total_changed_features': 0}
t0 = time.time()
for path in SRC:
    pref = os.path.basename(path).replace('N03-20260101_', '').replace('.geojson', '')
    g = gpd.read_file(path)
    before = offdigit_frac(g.geometry.values)
    snapped = shapely.set_precision(g.geometry.values, grid_size=1e-9, mode='valid_output')
    assert len(snapped) == len(g)
    assert shapely.is_valid(snapped).all(), pref
    assert not shapely.is_empty(snapped).any(), pref
    after = offdigit_frac(snapped)
    assert after == 0.0, (pref, after)
    changed = int(sum(1 for a, b in zip(g.geometry.values, snapped) if not shapely.equals_exact(a, b, 0.0)))
    keep = [c for c in ['N03_001', 'N03_002', 'N03_003', 'N03_004', 'N03_005', 'N03_007'] if c in g.columns]
    gg = g[keep].copy(); gg['geometry'] = snapped; gg['pref_file'] = pref
    frames.append(gg)
    log['files'].append({'pref': pref, 'features': len(g), 'changed_features': changed,
                         'offdigit_before': before, 'offdigit_after': after})
    log['total_features'] += len(g); log['total_changed_features'] += changed
    print(pref, len(g), 'changed', changed, 'offdigit', round(before, 4), '-> 0.0', flush=True)
    del g, gg
allf = gpd.GeoDataFrame(pd_concat := __import__('pandas').concat(frames, ignore_index=True), crs='EPSG:6668')
allf.to_file(f'{OUT}/source_normalized.gpkg', driver='GPKG', layer='admin_fragments_2026_normalized9')
log['elapsed_sec'] = round(time.time() - t0, 1)
log['unique_municipality_codes'] = int(allf['N03_007'].nunique())
json.dump(log, open(f'{OUT}/normalization_log.json', 'w'), ensure_ascii=False, indent=1)
print('TOTAL features', log['total_features'], '| changed', log['total_changed_features'],
      '| municipality codes', log['unique_municipality_codes'], '| elapsed', log['elapsed_sec'], 's')
