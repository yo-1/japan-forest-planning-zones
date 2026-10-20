"""Trace all 13 review polygons to supplied N03 and published municipality geometry."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pyogrio
import shapely
from pyproj import CRS,Transformer
from shapely.ops import transform


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('candidates',type=Path);p.add_argument('source_shp',type=Path);p.add_argument('municipalities',type=Path)
    p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    files=[a.candidates,a.municipalities]+[a.source_shp.with_suffix(s) for s in ['.shp','.dbf','.shx','.prj','.cpg']]
    hashes={str(f):sha(f) for f in files}
    assert hashes[str(a.source_shp)]=='6325d7f08c9374198e27b2cffd01bd420411be8b3cf3528da0587c6cea35538d'
    m,f,w,attrs=pyogrio.raw.read(a.candidates,layer='void_candidates',return_fids=True)
    result=dict(input_sha256=hashes,shapely=shapely.__version__,geos=shapely.geos_version_string,
                pyogrio=pyogrio.__version__,gdal=pyogrio.__gdal_version__,features=[])
    for i,b in enumerate(w):
        g=shapely.from_wkb(b);rp=g.representative_point()
        key=str(attrs[list(m['fields']).index('candidate_id')][i])
        laea=CRS.from_proj4(f'+proj=laea +lat_0={rp.y} +lon_0={rp.x} +ellps=GRS80 +units=m +no_defs')
        project=Transformer.from_crs('EPSG:6668',laea,always_xy=True).transform
        row=dict(candidate_id=key,original_candidate_fid=int(f[i]),representative_point=[rp.x,rp.y],
                 original_area_m2=transform(project,g).area,contexts={})
        for label,path,layer in [('N03',a.source_shp,None),('published_municipalities',a.municipalities,'plane_rectangular_municipalities_2026')]:
            meta,ids,wkbs,fields=pyogrio.raw.read(path,layer=layer,bbox=g.bounds,return_fids=True)
            assert meta['crs']=='EPSG:6668'
            geoms=shapely.from_wkb(wkbs)
            assert all(x.is_valid for x in geoms)
            union=shapely.union_all(geoms)
            inside=g.intersection(union);outside=g.difference(union)
            inside_point=bool(union.covers(rp))
            constituents=[]
            for j,(fid,h) in enumerate(zip(ids,geoms)):
                inter=g.intersection(h)
                if not inter.is_empty or h.distance(g)<=1e-9:
                    props={str(k):v[j].item() if isinstance(v[j],np.generic) else v[j] for k,v in zip(meta['fields'],fields)
                           if str(k).startswith('N03_')}
                    constituents.append(dict(fid=int(fid),attributes=props,intersection_type=inter.geom_type,
                        intersection_empty=bool(inter.is_empty),intersection_area_degree2=inter.area,
                        distance_degree=h.distance(g),covers_representative_point=bool(h.covers(rp))))
            row['contexts'][label]=dict(bbox_feature_count=len(ids),covered_area_m2=transform(project,inside).area,
                outside_area_m2=transform(project,outside).area,covers_representative_point=inside_point,
                contributors_or_within_1e_9_degree=constituents,
                inside_empty=bool(inside.is_empty),outside_empty=bool(outside.is_empty))
        result['features'].append(row)
        print(key,'traced',flush=True)
    result['summary']=dict(candidate_count=len(result['features']),
        source_point_covered=[r['candidate_id'] for r in result['features'] if r['contexts']['N03']['covers_representative_point']],
        municipality_point_covered=[r['candidate_id'] for r in result['features'] if r['contexts']['published_municipalities']['covers_representative_point']])
    result['inputs_unchanged']=hashes=={str(f):sha(f) for f in files}
    assert result['inputs_unchanged']
    result['limits']=['Source N03 is the user-supplied pinned 2026 dataset; legal meaning and current forestry membership are not established.',
        'No water classification or authoritative lake boundary is available in N03 attributes.',
        'Representative-point coverage is local evidence, not whole-polygon equivalence; overlay areas are separately retained.',
        'Tiny overlays can have floating point residuals; no tolerance suppresses nonempty differences.',
        'No source geometry modification, filling, deletion or national repair rule.']
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
