"""森林計画区 v0.3 レビュー用データを実機 QGIS に読み込み、件数・CRS を照合する。

使い方: このファイルを Dev Probe の recipe_dir に置き、
  run_recipe(name="load_forest_zones_review", args={
      "forest_gpkg": "C:/.../forest_planning_zones_2026_provisional_labeled.gpkg",
      "municipality_gpkg": "C:/.../municipality_forest_zones_2026_candidate.gpkg",
      "zones_gpkg": "C:/.../plane_rectangular_zones_2026.gpkg",
  })

期待値は検証B（QGIS 3.44 ヘッドレス）の layer_inspection.json と同じ。
読み込みだけを行い、データファイルは変更しない。
"""

EXPECTED = [
    ("forest_gpkg", "forest_plan_districts_provisional", 158),
    ("forest_gpkg", "forest_wide_basins_provisional", 44),
    ("forest_gpkg", "forest_unassigned_review", 20),
    ("municipality_gpkg", "plane_rectangular_municipalities_2026", 1911),
    ("zones_gpkg", "plane_rectangular_zones_2026", 19),
]
EXPECTED_CRS = "EPSG:6668"


def run(ctx, args):
    results = []
    problems = []
    for key, layer_name, expected_count in EXPECTED:
        path = args.get(key)
        if not isinstance(path, str) or not path:
            raise ValueError(f"args.{key}（GeoPackage のパス）が必要です")
        uri = f"{path}|layername={layer_name}"
        brief = ctx.call("add_layer", path=uri, name=layer_name)
        info = ctx.call("inspect_layer", layer=brief["id"], sample=1)
        count = info.get("feature_count")
        crs = info.get("crs")
        entry = {
            "layer": layer_name,
            "id": brief["id"],
            "valid": bool(brief.get("valid")),
            "feature_count": count,
            "expected_count": expected_count,
            "crs": crs,
        }
        results.append(entry)
        if not entry["valid"]:
            problems.append(f"{layer_name}: layer is not valid")
        if count != expected_count:
            problems.append(f"{layer_name}: feature_count {count} != expected {expected_count}")
        if crs != EXPECTED_CRS:
            problems.append(f"{layer_name}: crs {crs} != {EXPECTED_CRS}")
        ctx.log(f"loaded {layer_name}: count={count} crs={crs}")
    return {"layers": results, "problems": problems}
