"""Verification B step 3: reconcile manifest geometry_sha256.

Definition (from scripts/build_review_release.py, inspect_gpkg):
SHA-256 over the concatenation of the raw GeoPackage geometry BLOBs
as stored in the table, in ORDER BY fid order, per layer.
Also records the extracted GPKG file SHA-256 values.
Output: results/geometry_hash_reconciliation.json
"""
import hashlib
import json
import sqlite3
from pathlib import Path

BASE = Path.home() / "workspace/forest-planning-zones"
WORK = BASE / "work"
MANIFEST = json.loads((BASE / "inputs/review_manifest.json").read_text(encoding="utf-8"))
OUT = BASE / "verification-b/results/geometry_hash_reconciliation.json"

TARGETS = [
    ("forest_planning_zones_2026_provisional_labeled.gpkg", "forest_plan_districts_provisional",
     MANIFEST["aggregates"]["forest_plan_districts_provisional"]["geometry_sha256"]),
    ("forest_planning_zones_2026_provisional_labeled.gpkg", "forest_wide_basins_provisional",
     MANIFEST["aggregates"]["forest_wide_basins_provisional"]["geometry_sha256"]),
    ("forest_planning_zones_2026_provisional_labeled.gpkg", "forest_unassigned_review",
     MANIFEST["aggregates"]["forest_unassigned_review"]["geometry_sha256"]),
    ("municipality_forest_zones_2026_candidate.gpkg", "plane_rectangular_municipalities_2026",
     MANIFEST["candidate"]["plane_rectangular_municipalities_2026"]["geometry_sha256"]),
    ("plane_rectangular_zones_2026.gpkg", "plane_rectangular_zones_2026",
     MANIFEST["coordinate_zones"]["plane_rectangular_zones_2026"]["geometry_sha256"]),
]


def file_sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    result = {"definition": "SHA-256 of concatenated raw geometry BLOBs in ORDER BY fid order "
                            "(scripts/build_review_release.py inspect_gpkg)",
              "gpkg_files": {}, "layers": {}}
    for gpkg_name in sorted({t[0] for t in TARGETS}):
        p = WORK / gpkg_name
        result["gpkg_files"][gpkg_name] = {"bytes": p.stat().st_size, "sha256": file_sha256(p)}
    for gpkg_name, layer, expected in TARGETS:
        path = WORK / gpkg_name
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        col = conn.execute(
            "SELECT column_name FROM gpkg_geometry_columns WHERE table_name=?", (layer,)
        ).fetchone()[0]
        h = hashlib.sha256()
        n = 0
        for (blob,) in conn.execute(f'SELECT "{col}" FROM "{layer}" ORDER BY fid'):
            h.update(blob)
            n += 1
        conn.close()
        measured = h.hexdigest()
        result["layers"][layer] = {
            "source": gpkg_name, "features": n,
            "manifest_geometry_sha256": expected,
            "measured_geometry_sha256": measured,
            "match": measured == expected,
        }
        print(f"{layer}: n={n} match={measured == expected}")
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
