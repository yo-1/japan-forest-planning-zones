import collections
import json
import sqlite3
import struct
import sys

from shapely import wkb
from shapely.validation import explain_validity

path = sys.argv[1]
con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
table, col, srid = con.execute(
    "SELECT table_name, column_name, srs_id FROM gpkg_geometry_columns"
).fetchone()
rows = con.execute(
    f'SELECT fid, "N03_007", "ZONE", "{col}" FROM "{table}" ORDER BY fid'
)
summary = collections.Counter()
errors = []
types = collections.Counter()
bounds = [float("inf"), float("inf"), float("-inf"), float("-inf")]

for fid, code, zone, blob in rows:
    summary["features"] += 1
    if blob is None or len(blob) < 8 or blob[:2] != b"GP":
        errors.append({"fid": fid, "code": code, "error": "invalid GeoPackage header"})
        continue
    flags = blob[3]
    order = "<" if flags & 1 else ">"
    envelope_size = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get((flags >> 1) & 7)
    if envelope_size is None:
        errors.append({"fid": fid, "code": code, "error": "invalid envelope indicator"})
        continue
    geo_srid = struct.unpack(order + "i", blob[4:8])[0]
    if geo_srid != srid:
        errors.append({"fid": fid, "code": code, "error": f"SRID {geo_srid}"})
    try:
        geom = wkb.loads(blob[8 + envelope_size :])
    except Exception as exc:
        errors.append({"fid": fid, "code": code, "error": f"WKB: {exc}"})
        continue
    types[geom.geom_type] += 1
    if geom.is_empty:
        summary["empty"] += 1
    else:
        a, b, c, d = geom.bounds
        bounds[0] = min(bounds[0], a)
        bounds[1] = min(bounds[1], b)
        bounds[2] = max(bounds[2], c)
        bounds[3] = max(bounds[3], d)
        if not (-180 <= a <= 180 and -180 <= c <= 180 and -90 <= b <= 90 and -90 <= d <= 90):
            summary["outside_lonlat"] += 1
            errors.append({"fid": fid, "code": code, "error": "bounds outside lon/lat"})
    if not geom.is_valid:
        summary["invalid"] += 1
        errors.append({"fid": fid, "code": code, "zone": zone, "error": explain_validity(geom)})
    if summary["features"] % 300 == 0:
        print(f"checked {summary['features']}", flush=True)

result = {"source": path, "geometry_column": col, "srid": srid,
          "summary": dict(summary), "geometry_types": dict(types),
          "bounds": bounds, "errors": errors}
print(json.dumps(result, ensure_ascii=False, indent=2))
