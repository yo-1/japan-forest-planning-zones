# Phase 2: rebuild all layers of the forest-zones dataset from the normalized source.
# Geometry is rebuilt; attributes are carried verbatim from the published v0.5 layers.
# The gap_repair_audit layer is NOT carried into the package (kept as work records only).
import geopandas as gpd, numpy as np, shapely, json, time
from shapely.ops import unary_union
B = '/home/hatch/workspace/forest-planning-zones'
OUT = f'{B}/v07-candidate'
log = {}
t0 = time.time()

def offdigit(geoms):
    c = shapely.get_coordinates(geoms)
    if len(c) == 0: return 0.0
    off = (c[:, 0] != np.round(c[:, 0], 9)) | (c[:, 1] != np.round(c[:, 1], 9))
    return float(off.mean())

# --- 1. dissolve normalized fragments into municipality geometries (1,905 codes)
src = gpd.read_file(f'{OUT}/source_normalized.gpkg', layer='admin_fragments_2026_normalized9')
muni_geom = {}
for code, grp in src.groupby('N03_007'):
    muni_geom[code] = unary_union(grp.geometry.values)
log['municipalities_dissolved'] = len(muni_geom)
del src
print('dissolved municipalities:', len(muni_geom), flush=True)

# --- 2. municipality layer rows (1,911): v0.5 attributes + rebuilt geometry
m5 = gpd.read_file(f'{B}/v05-published/extracted_muni/municipality_forest_zones_2026_candidate.gpkg',
                   layer='plane_rectangular_municipalities_2026')
zones = gpd.read_file(f'{B}/work/plane_rectangular_zones_2026.gpkg', layer='plane_rectangular_zones_2026')
zone_geom = {r.ZONE: r.geometry for _, r in zones.iterrows()}
counts = m5['N03_007'].value_counts()
geoms = []
for _, r in m5.iterrows():
    g = muni_geom[r['N03_007']]
    if counts[r['N03_007']] > 1:  # zone-split municipality: clip to the row's zone, then re-snap
        g = shapely.set_precision(g.intersection(zone_geom[r['ZONE']]), grid_size=1e-9, mode='valid_output')
    geoms.append(g)
m_new = m5.copy(); m_new['geometry'] = geoms
assert shapely.is_valid(m_new.geometry.values).all() and not shapely.is_empty(m_new.geometry.values).any()
log['municipality_rows'] = len(m_new)
log['municipality_offdigit'] = offdigit(m_new.geometry.values)
print('municipality rows built, offdigit:', log['municipality_offdigit'], flush=True)

# --- 3. districts (158): dissolve member municipalities by forest_district_code
d5 = gpd.read_file(f'{B}/v05-candidate/forest_planning_zones_2026_provisional_labeled.gpkg',
                   layer='forest_plan_districts_provisional')
code_of = {}  # municipality code -> district code (from v0.5 municipality attributes)
for _, r in m5.drop_duplicates('N03_007').iterrows():
    if isinstance(r['forest_district_code'], str) and r['forest_district_code']:
        code_of[r['N03_007']] = r['forest_district_code']
members = {}
for mc, dc in code_of.items():
    members.setdefault(dc, []).append(muni_geom[mc])
dist_geom = {dc: unary_union(gs) for dc, gs in members.items()}
d_new = d5.copy()
d_new['geometry'] = [dist_geom[c] for c in d_new['district_code']]
assert len(d_new) == 158 and shapely.is_valid(d_new.geometry.values).all()
log['districts'] = len(d_new); log['district_offdigit_raw'] = offdigit(d_new.geometry.values)
print('districts built, offdigit raw:', log['district_offdigit_raw'], flush=True)

# --- 3b. apply the v0.5 editorial decision (user, 2026-11-06): fill the 9 classified
# empty holes by removing the matching inner rings from the rebuilt districts.
# Site-restricted: only rings whose interior matches one of the 9 classified hole
# polygons (v0.4 gap_residual_review rows 0-4 and 12-15) are removed. Pure vertex
# surgery on existing coordinates, so the 9-digit property is preserved.
holes16 = gpd.read_file(f'{B}/v04-candidate/extracted/forest_planning_zones_2026_provisional_labeled.gpkg',
                        layer='gap_residual_review')
targets = [holes16.geometry.values[i] for i in [0, 1, 2, 3, 4, 12, 13, 14, 15]]
def fill_rings(geom, targets):
    from shapely.geometry import Polygon, MultiPolygon
    parts = list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [geom]
    out, filled = [], []
    for p in parts:
        keep = []
        for ring in p.interiors:
            rp = Polygon(ring)
            hit = None
            for t in targets:
                if rp.symmetric_difference(t).area / max(rp.area, t.area) < 0.02:
                    hit = t; break
            if hit is not None: filled.append(rp.area)
            else: keep.append(ring)
        out.append(Polygon(p.exterior, keep))
    g = out[0] if len(out) == 1 else MultiPolygon(out)
    return g, filled
new_geoms, fill_log = [], []
for _, r in d_new.iterrows():
    g, filled = fill_rings(r.geometry, targets)
    new_geoms.append(g); fill_log += [(r['district_code'], a) for a in filled]
d_new['geometry'] = new_geoms
assert shapely.is_valid(d_new.geometry.values).all() and not shapely.is_empty(d_new.geometry.values).any()
log['rings_filled'] = len(fill_log); log['rings_filled_detail'] = fill_log
log['district_offdigit_after_fill'] = offdigit(d_new.geometry.values)
print('rings filled:', len(fill_log), fill_log, flush=True)

# --- 4. basins (44): dissolve districts by basin_code
b5 = gpd.read_file(f'{B}/v05-candidate/forest_planning_zones_2026_provisional_labeled.gpkg',
                   layer='forest_wide_basins_provisional')
basin_members = {}
for _, r in d_new.iterrows():
    basin_members.setdefault(r['basin_code'], []).append(r.geometry)
b_new = b5.copy()
b_new['geometry'] = [unary_union(basin_members[c]) for c in b_new['basin_code']]
assert len(b_new) == 44 and shapely.is_valid(b_new.geometry.values).all()
log['basins'] = len(b_new); log['basin_offdigit_raw'] = offdigit(b_new.geometry.values)
print('basins built, offdigit raw:', log['basin_offdigit_raw'], flush=True)

# --- 5. unassigned (20): full municipality geometry, v0.5 attributes
u5 = gpd.read_file(f'{B}/v05-candidate/forest_planning_zones_2026_provisional_labeled.gpkg',
                   layer='forest_unassigned_review')
u_new = u5.copy()
u_new['geometry'] = [muni_geom[c] for c in u_new['municipality_code']]
assert len(u_new) == 20 and shapely.is_valid(u_new.geometry.values).all()
log['unassigned'] = len(u_new); log['unassigned_offdigit'] = offdigit(u_new.geometry.values)

# --- 6. residual review: carry the v0.6 candidate layer (already 100% on the 9-digit grid)
r6 = gpd.read_file(f'{B}/v06-candidate/forest_planning_zones_2026_provisional_labeled.gpkg',
                   layer='gap_residual_review')
log['residual_carried_from_v06'] = len(r6)

# --- 7. write outputs (no gap_repair_audit layer). Remove stale outputs first:
# append-mode layer writes would otherwise duplicate rows on a rebuild.
import os
for p in [f'{OUT}/forest_planning_zones_2026_provisional_labeled.gpkg',
          f'{OUT}/municipality_forest_zones_2026_candidate.gpkg']:
    if os.path.exists(p): os.remove(p)
FO = f'{OUT}/forest_planning_zones_2026_provisional_labeled.gpkg'
d_new.to_file(FO, driver='GPKG', layer='forest_plan_districts_provisional')
b_new.to_file(FO, driver='GPKG', layer='forest_wide_basins_provisional', mode='a')
u_new.to_file(FO, driver='GPKG', layer='forest_unassigned_review', mode='a')
r6.to_file(FO, driver='GPKG', layer='gap_residual_review', mode='a')
m_new.to_file(f'{OUT}/municipality_forest_zones_2026_candidate.gpkg', driver='GPKG',
              layer='plane_rectangular_municipalities_2026')
log['elapsed_sec'] = round(time.time() - t0, 1)
json.dump(log, open(f'{OUT}/build_log.json', 'w'), ensure_ascii=False, indent=1)
print('BUILD DONE', log)
