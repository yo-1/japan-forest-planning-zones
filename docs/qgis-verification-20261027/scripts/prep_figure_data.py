"""Prepare figure inputs (Verification B step 5).

Overview figures use topology-preserving simplified copies
(shapely simplify, tolerance 0.0015 degrees) because rendering the
original nationwide geometries exceeded this VM's memory (7.7 GB).
The zoom figure uses the ORIGINAL geometries clipped to the
district 025 extent plus a margin.
Output: figures/work/*.gpkg
"""
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

BASE = Path.home() / "workspace/forest-planning-zones"
WORK = BASE / "work"
OUT = BASE / "verification-b/figures/work"
OUT.mkdir(parents=True, exist_ok=True)
FOREST = WORK / "forest_planning_zones_2026_provisional_labeled.gpkg"
TOL = 0.0015

districts = gpd.read_file(FOREST, layer="forest_plan_districts_provisional")
basins = gpd.read_file(FOREST, layer="forest_wide_basins_provisional")
unassigned = gpd.read_file(FOREST, layer="forest_unassigned_review")
muni = gpd.read_file(WORK / "municipality_forest_zones_2026_candidate.gpkg",
                     layer="plane_rectangular_municipalities_2026")

for name, gdf in (("districts", districts), ("basins", basins), ("unassigned", unassigned)):
    s = gdf[["geometry"]].copy()
    s["geometry"] = s.geometry.simplify(TOL, preserve_topology=True)
    s = s[~s.geometry.is_empty]
    s.to_file(OUT / f"fig_{name}.gpkg", layer=name, driver="GPKG")
    print(name, "simplified rows:", len(s))

row = districts[districts.district_code == "025"].iloc[0]
minx, miny, maxx, maxy = row.geometry.bounds
margin = 0.15
clip_box = box(minx - margin, miny - margin, maxx + margin, maxy + margin)
print("025", row.district_name, row.basin_name, "bounds", (minx, miny, maxx, maxy))
for name, gdf in (("districts", districts), ("basins", basins), ("muni", muni)):
    c = gpd.clip(gdf[["geometry"]], clip_box)
    c = c[~c.geometry.is_empty]
    c.to_file(OUT / f"zoom_{name}.gpkg", layer=name, driver="GPKG")
    print("zoom", name, "rows:", len(c))
