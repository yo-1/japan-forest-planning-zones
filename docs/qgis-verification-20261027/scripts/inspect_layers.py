"""Verification B step 1: load v0.3 layers in QGIS 3.44 and inspect them.

Records per layer: load validity, feature count, geometry type, CRS,
field definitions, code format / leading-zero preservation, Japanese
name attributes, distinct status values, empty/null geometry counts.
Output: results/layer_inspection.json
"""
import json
import re
import sys
from pathlib import Path

from PyQt5.QtCore import QVariant
from qgis.core import Qgis, QgsApplication, QgsVectorLayer


def is_null(v):
    return v is None or (isinstance(v, QVariant) and v.isNull())

BASE = Path.home() / "workspace/forest-planning-zones"
WORK = BASE / "work"
OUT = BASE / "verification-b/results/layer_inspection.json"

LAYERS = [
    ("forest_planning_zones_2026_provisional_labeled.gpkg", "forest_plan_districts_provisional"),
    ("forest_planning_zones_2026_provisional_labeled.gpkg", "forest_wide_basins_provisional"),
    ("forest_planning_zones_2026_provisional_labeled.gpkg", "forest_unassigned_review"),
    ("municipality_forest_zones_2026_candidate.gpkg", "plane_rectangular_municipalities_2026"),
    ("plane_rectangular_zones_2026.gpkg", "plane_rectangular_zones_2026"),
]

EXPECTED_COUNTS = {
    "forest_plan_districts_provisional": 158,
    "forest_wide_basins_provisional": 44,
    "forest_unassigned_review": 20,
    "plane_rectangular_municipalities_2026": 1911,
    "plane_rectangular_zones_2026": 19,
}

# field roles per layer: code fields with expected digit length, name fields
ROLES = {
    "forest_plan_districts_provisional": {
        "codes": {"district_code": 3, "basin_code": 2},
        "names": ["district_name", "basin_name"],
    },
    "forest_wide_basins_provisional": {
        "codes": {"basin_code": 2},
        "names": ["basin_name"],
    },
    "forest_unassigned_review": {
        "codes": {"municipality_code": 5},
        "names": ["prefecture", "municipality"],
    },
    "plane_rectangular_municipalities_2026": {
        "codes": {"N03_007": 5, "forest_district_code": 3, "wide_basin_code": 2},
        "names": ["N03_001", "N03_004", "N03_005", "forest_district_name", "wide_basin_name"],
    },
    "plane_rectangular_zones_2026": {
        "codes": {},
        "names": ["ZONE_ROMAN"],
    },
}

JP = re.compile(r"[぀-ヿ一-鿿]")


def main():
    app = QgsApplication([], False)
    app.initQgis()
    result = {"qgis_version": Qgis.version(), "layers": {}}
    for gpkg_name, layer_name in LAYERS:
        path = WORK / gpkg_name
        uri = f"{path}|layername={layer_name}"
        layer = QgsVectorLayer(uri, layer_name, "ogr")
        info = {"source": str(path), "load_valid": layer.isValid()}
        if not layer.isValid():
            result["layers"][layer_name] = info
            continue
        info["provider"] = layer.providerType()
        info["feature_count"] = layer.featureCount()
        info["expected_count"] = EXPECTED_COUNTS[layer_name]
        info["count_matches"] = layer.featureCount() == EXPECTED_COUNTS[layer_name]
        info["geometry_type"] = str(layer.geometryType())
        info["wkb_type"] = str(layer.wkbType())
        crs = layer.crs()
        info["crs_authid"] = crs.authid()
        info["crs_description"] = crs.description()
        info["extent"] = [layer.extent().xMinimum(), layer.extent().yMinimum(),
                          layer.extent().xMaximum(), layer.extent().yMaximum()]
        fields = [f.name() for f in layer.fields()]
        info["fields"] = [{"name": f.name(), "type": f.typeName()} for f in layer.fields()]

        roles = ROLES[layer_name]
        code_stats = {}
        for field, digits in roles["codes"].items():
            if field not in fields:
                code_stats[field] = {"missing_field": True}
                continue
            vals = []
            empty = 0
            for feat in layer.getFeatures():
                v = feat[field]
                if is_null(v) or (isinstance(v, str) and v.strip() == ""):
                    empty += 1
                else:
                    vals.append(str(v))
            pat = re.compile(rf"^\d{{{digits}}}$")
            code_stats[field] = {
                "non_empty": len(vals),
                "empty": empty,
                "unique": len(set(vals)),
                "all_match_digits": all(pat.match(v) for v in vals),
                "leading_zero_count": sum(1 for v in vals if v.startswith("0")),
                "samples": sorted(set(vals))[:5],
            }
        info["code_stats"] = code_stats

        name_stats = {}
        for field in roles["names"]:
            if field not in fields:
                continue
            vals = [str(feat[field]) for feat in layer.getFeatures()
                    if not is_null(feat[field]) and str(feat[field]).strip() != ""]
            name_stats[field] = {
                "non_empty": len(vals),
                "all_contain_japanese": all(JP.search(v) for v in vals) if vals else None,
                "samples": vals[:3],
            }
        info["name_stats"] = name_stats

        null_geom = empty_geom = 0
        for feat in layer.getFeatures():
            g = feat.geometry()
            if g is None or g.isNull():
                null_geom += 1
            elif g.isEmpty():
                empty_geom += 1
        info["null_geometry"] = null_geom
        info["empty_geometry"] = empty_geom

        for extra in ("status", "final_usable"):
            if extra in fields:
                info[f"distinct_{extra}"] = sorted(
                    {str(feat[extra]) for feat in layer.getFeatures()})
        if "source_features" in fields:
            info["source_features_sum"] = sum(
                int(feat["source_features"]) for feat in layer.getFeatures())

        sample = []
        for i, feat in enumerate(layer.getFeatures()):
            if i >= 2:
                break
            sample.append({f: (None if is_null(feat[f]) else str(feat[f])) for f in fields})
        info["sample_features"] = sample
        result["layers"][layer_name] = info
        print(f"{layer_name}: count={info['feature_count']} crs={info['crs_authid']} "
              f"null_geom={null_geom} empty_geom={empty_geom}", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)
    app.exitQgis()


if __name__ == "__main__":
    sys.exit(main())
