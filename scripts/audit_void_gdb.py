"""Read-only measurement of all 13 exported void candidates and saved Esri results."""
import argparse
import hashlib
import json
import math
import platform
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pyogrio
import shapely
from pyproj import CRS, Transformer
from shapely.ops import transform


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def scalar(v):
    return v.item() if isinstance(v,np.generic) else v


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('gdb',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists(): p.error('output exists')
    files={x.relative_to(a.gdb).as_posix():digest(x) for x in a.gdb.rglob('*') if x.is_file()}
    _,_,_,xml=pyogrio.raw.read(a.gdb,sql='GetLayerDefinition void_candidates_gdb')
    definition=ET.fromstring(xml[0][0])
    wanted={'XOrigin','YOrigin','XYScale','XYTolerance','WKID','LatestWKID'}
    settings={e.tag.rsplit('}',1)[-1]:e.text for e in definition.iter() if e.tag.rsplit('}',1)[-1] in wanted}
    tolerance=float(settings['XYTolerance'])
    m,cf,_,ca=pyogrio.raw.read(a.gdb,layer='check_void_candidates',return_fids=True)
    checks=[dict(zip(m['fields'],[scalar(x[i]) for x in ca])) for i in range(len(cf))]
    reported={int(x['FEATURE_ID']) for x in checks}
    m,fids,wkbs,attrs=pyogrio.raw.read(a.gdb,layer='void_candidates_gdb',return_fids=True)
    assert len(fids)==13 and m['crs']=='EPSG:6668'
    result=dict(python=platform.python_version(),shapely=shapely.__version__,geos=shapely.geos_version_string,
        numpy=np.__version__,pyogrio=pyogrio.__version__,gdal=pyogrio.__gdal_version__,
        coordinate_units='longitude/latitude degrees',index_base=0,input_file_sha256=files,
        native_gdb_settings=settings,check_table_rows=checks,check_fields=m['fields'].tolist(),features=[])
    # Keep check-table fields separate from feature fields.
    result['check_fields']=['CLASS','FEATURE_ID','PROBLEM']
    for i,(fid,wkb) in enumerate(zip(fids,wkbs)):
        g=shapely.from_wkb(wkb)
        fields={str(k):scalar(v[i]) for k,v in zip(m['fields'],attrs)}
        coords=[];refs=[];sizes={};rid=0
        for poly in g.geoms:
            for ring in [poly.exterior,*poly.interiors]:
                cs=list(ring.coords);assert cs[0]==cs[-1];sizes[rid]=len(cs)-1
                for pos,xy in enumerate(cs[:-1]): coords.append(xy);refs.append((rid,pos))
                rid+=1
        points=shapely.points(np.asarray(coords));tree=shapely.STRtree(points)
        x,y=tree.query(points,predicate='dwithin',distance=tolerance)
        close=[]
        for u,v in zip(x,y):
            u,v=int(u),int(v)
            if u>=v: continue
            ra,pa=refs[u];rb,pb=refs[v]
            if ra==rb and abs(pa-pb) in (1,sizes[ra]-1):continue
            close.append(dict(ring_a=ra,pos_a=pa,ring_b=rb,pos_b=pb,coordinate_a=coords[u],coordinate_b=coords[v],
                distance_degree=math.dist(coords[u],coords[v])))
        point=g.representative_point()
        laea=CRS.from_proj4(f'+proj=laea +lat_0={point.y} +lon_0={point.x} +ellps=GRS80 +units=m +no_defs')
        projected=transform(Transformer.from_crs('EPSG:6668',laea,always_xy=True).transform,g)
        rectangle=np.asarray(projected.minimum_rotated_rectangle.exterior.coords)
        lengths=np.linalg.norm(np.diff(rectangle,axis=0),axis=1)
        result['features'].append(dict(fid=int(fid),candidate_id=fields['candidate_id'],
            reported_by_esri=int(fid) in reported,geometry_type=g.geom_type,valid=bool(g.is_valid),
            validity_reason=shapely.is_valid_reason(g),polygon_count=len(g.geoms),
            stored_coordinate_count=int(shapely.get_num_coordinates(g)),
            minimum_clearance_degree=float(g.minimum_clearance),nonadjacent_vertex_pairs_within_xy_tolerance=close,
            representative_point=[point.x,point.y],local_laea_area_m2=projected.area,
            local_laea_obb_width_m=float(min(lengths)),local_laea_obb_length_m=float(max(lengths)),
            inherited_attributes=fields,
            geometry=json.loads(shapely.to_geojson(g)) if int(fid) in reported else None))
    result['summary']=dict(total=len(fids),geos_valid=sum(x['valid'] for x in result['features']),
        esri_reported_ids=sorted(reported),
        ids_with_nonadjacent_vertices_within_xy_tolerance=[x['fid'] for x in result['features'] if x['nonadjacent_vertex_pairs_within_xy_tolerance']])
    result['input_files_unchanged']=files=={x.relative_to(a.gdb).as_posix():digest(x) for x in a.gdb.rglob('*') if x.is_file()}
    assert result['input_files_unchanged']
    result['limits']=['Saved Esri Check Geometry rows, not an AI ArcGIS rerun.',
        'Native XY tolerance is compared to a circular degree-distance search; this does not reproduce Esri validation or clustering.',
        'Inherited cause/decision/area/hash attributes are not independently verified source facts.',
        'Local LAEA metric measurements use decoded GDB coordinates; tiny-shape measurements can be numerically sensitive.',
        'No source GPKG comparison; error table has no problem coordinates.',
        'Zone and candidate_id attributes identify void-review candidates; do not map FEATURE_ID to forest district codes.',
        'No geometry changes or national repair rule.']
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__': main()
