import argparse,json,hashlib,math,platform
from pathlib import Path
import numpy as np
import shapely
from shapely.geometry import Polygon,MultiPolygon
parser=argparse.ArgumentParser(description="Read-only district025 Esri JSON vertex audit; no Esri tolerance simulation.")
parser.add_argument('input', type=Path)
parser.add_argument('--output', type=Path, required=True)
args=parser.parse_args()
p=args.input
if args.output.exists(): parser.error('output exists; choose a new path')
if shapely.__version__ != '2.1.2' or shapely.geos_version_string != '3.13.1':
    parser.error('requires actual Shapely 2.1.2 / GEOS 3.13.1')
raw=p.read_bytes()
if hashlib.sha256(raw).hexdigest() != '433432955571410679a9792a0abedbb9fdb1c852636c9eafe1ffefbe594fe94b':
    parser.error('input SHA-256 differs from recorded district025 JSON')
d=json.loads(raw); rings=d['features'][0]['geometry']['rings']; threshold=9e-9
assert len(d['features']) == 1 and d['geometryType'] == 'esriGeometryPolygon'
assert all(not shapely.LinearRing(r).is_ccw and r[0] == r[-1] for r in rings), 'This input-specific script expects closed clockwise shells without holes'
coords=[]; refs=[]; sizes={}
for ri,r in enumerate(rings):
 closed=r[0]==r[-1]; unique=r[:-1] if closed else r; sizes[ri]=len(unique)
 for pi,c in enumerate(unique): coords.append(c); refs.append((ri,pi))
points=shapely.points(np.array(coords)); tree=shapely.STRtree(points)
pairs=[]; zero=0; adjacent=0
for start in range(0,len(points),10000):
 q=tree.query(points[start:start+10000],predicate='dwithin',distance=threshold)
 for a,b in zip(q[0],q[1]):
  a=int(a)+start; b=int(b)
  if a>=b: continue
  ra,pa=refs[a]; rb,pb=refs[b]
  if ra==rb and (abs(pa-pb)==1 or abs(pa-pb)==sizes[ra]-1): adjacent+=1; continue
  dx=coords[b][0]-coords[a][0]; dy=coords[b][1]-coords[a][1]; dist=math.hypot(dx,dy)
  if dist==0: zero+=1; continue
  if dist<=threshold: pairs.append({'ring_a_0based':ra,'pos_a_0based':pa,'ring_b_0based':rb,'pos_b_0based':pb,'coordinate_a':coords[a],'coordinate_b':coords[b],'delta_longitude_degrees':dx,'delta_latitude_degrees':dy,'distance_degrees':dist})
g=MultiPolygon([Polygon(r) for r in rings])
result={'input_file':p.name,'sha256':hashlib.sha256(raw).hexdigest(),'python':platform.python_version(),'shapely':shapely.__version__,'geos':shapely.geos_version_string,'index_convention':'ring and pos are 0-based indices into original JSON features[0].geometry.rings. For 1-based indexing add 1. Closing coordinate retained for geometry validity; removed from vertex search when identical to first coordinate. First and last distinct vertices are cyclic neighbors and excluded. Adjacent pairs excluded only within the same ring; cross-ring pairs searched as well. Positive planar Euclidean distance in input longitude/latitude degrees, not geodesic distance.','ring_count':len(rings),'stored_coordinate_count':sum(map(len,rings)),'closed_ring_count':sum(r[0]==r[-1] for r in rings),'searched_vertex_count':len(points),'threshold_degrees':threshold,'positive_nonadjacent_pair_count':len(pairs),'same_ring_positive_pair_count':sum(x['ring_a_0based']==x['ring_b_0based'] for x in pairs),'cross_ring_positive_pair_count':sum(x['ring_a_0based']!=x['ring_b_0based'] for x in pairs),'excluded_zero_distance_nonadjacent_pairs':zero,'excluded_adjacent_pairs_within_threshold':adjacent,'pairs':pairs,'geometry_type':g.geom_type,'geometry_is_valid':bool(g.is_valid),'geometry_validity_reason':shapely.is_valid_reason(g),'invalid_individual_rings':sum(not Polygon(r).is_valid for r in rings),'arcgis_limitation':'This is GEOS validity and a degree-distance vertex search. It does not reproduce ArcGIS XY tolerance, resolution, clustering, or ArcGIS geometry validation.','source_unchanged':hashlib.sha256(p.read_bytes()).hexdigest()==hashlib.sha256(raw).hexdigest()}
args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
assert result['source_unchanged']
print(args.output)
