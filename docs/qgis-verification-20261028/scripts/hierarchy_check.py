"""Verification B step 4: hierarchy consistency of the v0.3 files themselves.

The geometry re-aggregation audit already exists for v0.2
(docs/geometry-audit-20261013) and carries over to the v0.3 forest layers
through the all-columns hash equality confirmed in Verification A.
What had not been checked on the v0.3 files directly is the attribute-level
hierarchy and a point-level geometric containment sanity check:

H1 candidate district codes (non-null) == district layer codes
H2 candidate basin codes (non-null) == basin layer codes
H3 every district maps to exactly one basin, identically in the candidate
   table and in the district layer (code and name)
H4 unassigned layer municipality codes == candidate rows with NULL codes
H5 source_features in the aggregate layers == candidate row counts
H6 representative point of each assigned candidate lies within its
   district and basin geometry; unassigned points lie within no district

Run in the main geo env (geopandas / shapely / GEOS 3.14.1).
Output: results/hierarchy_check.json
"""
import json
from pathlib import Path

import geopandas as gpd
from shapely.strtree import STRtree

BASE = Path.home() / "workspace/forest-planning-zones"
WORK = BASE / "verification-v04" / "work"
OUT = BASE / "verification-v04/results/hierarchy_check.json"

districts = gpd.read_file(WORK / "forest_planning_zones_2026_provisional_labeled.gpkg",
                          layer="forest_plan_districts_provisional")
basins = gpd.read_file(WORK / "forest_planning_zones_2026_provisional_labeled.gpkg",
                       layer="forest_wide_basins_provisional")
unassigned = gpd.read_file(WORK / "forest_planning_zones_2026_provisional_labeled.gpkg",
                           layer="forest_unassigned_review")
cand = gpd.read_file(WORK / "municipality_forest_zones_2026_candidate.gpkg",
                     layer="plane_rectangular_municipalities_2026")

res = {}

cand_d = cand[cand["forest_district_code"].notna()]
cand_b = cand[cand["wide_basin_code"].notna()]
res["H1_candidate_district_codes_eq_district_layer"] = {
    "candidate_unique": int(cand_d["forest_district_code"].nunique()),
    "district_layer_unique": int(districts["district_code"].nunique()),
    "equal": set(cand_d["forest_district_code"]) == set(districts["district_code"]),
}
res["H2_candidate_basin_codes_eq_basin_layer"] = {
    "candidate_unique": int(cand_b["wide_basin_code"].nunique()),
    "basin_layer_unique": int(basins["basin_code"].nunique()),
    "equal": set(cand_b["wide_basin_code"]) == set(basins["basin_code"]),
}

pair_cand = cand_d.groupby("forest_district_code")["wide_basin_code"].nunique()
pair_name = cand_d.groupby("forest_district_code")["wide_basin_name"].nunique()
dmap = districts.set_index("district_code")
mismatch = []
for code, row in dmap.iterrows():
    sub = cand_d[cand_d["forest_district_code"] == code]
    if len(sub) == 0:
        mismatch.append({"district_code": code, "issue": "no candidate rows"})
        continue
    if set(sub["wide_basin_code"]) != {row["basin_code"]}:
        mismatch.append({"district_code": code, "issue": "basin_code differs",
                         "candidate": sorted(set(sub["wide_basin_code"])),
                         "district_layer": row["basin_code"]})
    if set(sub["wide_basin_name"]) != {row["basin_name"]}:
        mismatch.append({"district_code": code, "issue": "basin_name differs"})
    if set(sub["forest_district_name"]) != {row["district_name"]}:
        mismatch.append({"district_code": code, "issue": "district_name differs"})
res["H3_district_basin_mapping"] = {
    "districts_with_multiple_basin_codes_in_candidates": int((pair_cand > 1).sum()),
    "districts_with_multiple_basin_names_in_candidates": int((pair_name > 1).sum()),
    "district_layer_basin_codes_unique": int(districts["basin_code"].nunique()),
    "mismatches": mismatch,
}

null_rows = cand[cand["forest_district_code"].isna() & cand["wide_basin_code"].isna()]
partial_null = cand[cand["forest_district_code"].isna() ^ cand["wide_basin_code"].isna()]
res["H4_unassigned_codes"] = {
    "candidate_null_both": int(len(null_rows)),
    "candidate_partial_null": int(len(partial_null)),
    "unassigned_layer_rows": int(len(unassigned)),
    "codes_equal": set(null_rows["N03_007"]) == set(unassigned["municipality_code"]),
    "null_codes_sorted": sorted(null_rows["N03_007"]),
}

sf_d = cand_d.groupby("forest_district_code").size()
sf_b = cand_b.groupby("wide_basin_code").size()
bad_d = [c for c, row in dmap.iterrows() if int(sf_d.get(c, 0)) != int(row["source_features"])]
bmap = basins.set_index("basin_code")
bad_b = [c for c, row in bmap.iterrows() if int(sf_b.get(c, 0)) != int(row["source_features"])]
res["H5_source_features"] = {
    "district_mismatches": bad_d, "basin_mismatches": bad_b,
    "sum_districts": int(districts["source_features"].sum()),
    "sum_basins": int(basins["source_features"].sum()),
    "assigned_candidate_rows": int(len(cand_d)),
}

# H6: point-level geometric containment using representative points
d_geom = districts.set_index("district_code")["geometry"]
b_geom = basins.set_index("basin_code")["geometry"]
outside_d, outside_b = [], []
for _, row in cand_d.iterrows():
    pt = row.geometry.representative_point()
    if not d_geom[row["forest_district_code"]].covers(pt):
        outside_d.append(row["N03_007"])
    if not b_geom[row["wide_basin_code"]].covers(pt):
        outside_b.append(row["N03_007"])
tree = STRtree(districts.geometry.values)
inside_any = []
for _, row in unassigned.iterrows():
    pt = row.geometry.representative_point()
    hits = tree.query(pt, predicate="covers")
    if len(hits) > 0:
        inside_any.append(row["municipality_code"])
res["H6_representative_point_containment"] = {
    "assigned_checked": int(len(cand_d)),
    "outside_own_district": outside_d,
    "outside_own_basin": outside_b,
    "unassigned_checked": int(len(unassigned)),
    "unassigned_points_inside_a_district": inside_any,
    "note": "Point-level sanity check only; full polygon overlap/gap audit is the "
            "existing geometry-audit-20261013 result carried over from v0.2.",
}

OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: (v if not isinstance(v, dict) else
                      {kk: vv for kk, vv in v.items() if kk != "null_codes_sorted"})
                  for k, v in res.items()}, ensure_ascii=False, indent=2))
print("wrote", OUT)
