"""Compare user-exported Esri JSON to decoded GDB by OBJECTID and candidate_id."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pyogrio
import shapely


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('json',type=Path)
    p.add_argument('gdb',type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    if a.output.exists():p.error('output exists')
    before=sha(a.json)
    hashes={x.relative_to(a.gdb).as_posix():sha(x) for x in a.gdb.rglob('*') if x.is_file()}
    d=json.loads(a.json.read_bytes())
    assert d['geometryType']=='esriGeometryPolygon'
    assert d['spatialReference']=={'wkid':104020,'latestWkid':6668}
    src={int(f['attributes']['OBJECTID']):f for f in d['features']}
    assert len(src)==len(d['features'])==13
    m,fids,wkbs,attrs=pyogrio.raw.read(a.gdb,layer='void_candidates_gdb',return_fids=True)
    assert m['crs']=='EPSG:6668' and set(map(int,fids))==set(src)
    result=dict(json_bytes=a.json.stat().st_size,json_sha256=before,spatial_reference=d['spatialReference'],
                gdb_crs=m['crs'],shapely=shapely.__version__,geos=shapely.geos_version_string,
                pyogrio=pyogrio.__version__,gdal=pyogrio.__gdal_version__,features=[])
    for i,(fid,wkb) in enumerate(zip(fids,wkbs)):
        g=shapely.from_wkb(wkb);f=src[int(fid)]
        rings=[np.asarray(r.coords) for poly in g.geoms for r in [poly.exterior,*poly.interiors]]
        original=f['geometry']['rings']
        exact=len(rings)==len(original) and all(np.array_equal(r,np.asarray(s)) for r,s in zip(rings,original))
        field_differences=[str(k) for k,v in zip(m['fields'],attrs)
            if (v[i].item() if isinstance(v[i],np.generic) else v[i])!=f['attributes'].get(str(k))]
        result['features'].append(dict(objectid=int(fid),candidate_id=f['attributes']['candidate_id'],
            ring_count=len(rings),coordinate_count=sum(len(r) for r in rings),
            exact_all_ring_ordered_xy_match=exact,attribute_differences=field_differences))
        assert exact and not field_differences
    result['all_13_geometry_and_attribute_matches']=True
    result['total_coordinate_count']=sum(f['coordinate_count'] for f in result['features'])
    result['json_unchanged']=before==sha(a.json)
    result['gdb_files_unchanged']=hashes=={x.relative_to(a.gdb).as_posix():sha(x) for x in a.gdb.rglob('*') if x.is_file()}
    assert result['json_unchanged'] and result['gdb_files_unchanged']
    result['limits']='Confirms Esri JSON vs decoded GDB, not source GPKG equivalence. Geometry-bearing JSON is not a location-bearing Check Geometry report and does not prove error mechanism.'
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
