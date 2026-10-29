#!/bin/bash
# Verification B step 2: native:checkvalidity, METHOD=2 (GEOS),
# IGNORE_RING_SELF_INTERSECTION=0 (do not ignore ring self-intersections)
source ~/workspace/tools/geo-env.sh 2>/dev/null
micromamba activate ~/workspace/geo-env-qgis344 2>/dev/null
B=~/workspace/forest-planning-zones
W=$B/verification-v04/work
O=$B/verification-v04/results/validity
L=$B/verification-v04/logs
run() {
  local gpkg="$1" layer="$2"
  echo "=== $layer ==="
  local t0=$SECONDS
  qgis_process run native:checkvalidity \
    "INPUT_LAYER=${gpkg}|layername=${layer}" \
    METHOD=2 IGNORE_RING_SELF_INTERSECTION=0 \
    "VALID_OUTPUT=${O}/${layer}_valid.gpkg" \
    "INVALID_OUTPUT=${O}/${layer}_invalid.gpkg" \
    "ERROR_OUTPUT=${O}/${layer}_errors.gpkg" \
    > "${L}/checkvalidity_${layer}.log" 2>&1
  echo "exit=$? layer=$layer elapsed=$((SECONDS-t0))s"
  grep -v "PDAL Error" "${L}/checkvalidity_${layer}.log" | tail -n 5
}
run "$W/forest_planning_zones_2026_provisional_labeled.gpkg" forest_plan_districts_provisional
run "$W/forest_planning_zones_2026_provisional_labeled.gpkg" forest_wide_basins_provisional
run "$W/forest_planning_zones_2026_provisional_labeled.gpkg" forest_unassigned_review
run "$W/municipality_forest_zones_2026_candidate.gpkg" plane_rectangular_municipalities_2026
run "$W/plane_rectangular_zones_2026.gpkg" plane_rectangular_zones_2026
echo "ALL DONE"
