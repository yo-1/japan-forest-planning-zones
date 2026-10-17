"""Read-only, ordered-coordinate GPKG -> GDB -> Esri JSON comparison."""
import argparse
import hashlib
import json
import math
import platform
import sqlite3
from pathlib import Path

import numpy as np
import pyogrio
import shapely
from pyproj import CRS, Transformer
from shapely.ops import transform


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def scalar(x):return x.item() if isinstance(x,np.generic) else x


def short_pairs(coords,threshold):
    # All 13 candidates have one shell and no holes. Closing point is excluded.
    points=shapely.points(coords[:-1]);tree=shapely.STRtree(points)
    aa,bb=tree.query(points,predicate='dwithin',distance=threshold)
    rows=[];n=len(points)
    for a,b in zip(aa,bb):
        a,b=int(a),int(b)
        if a>=b or abs(a-b) in (1,n-1):continue
        rows.append(dict(pos_a_0based=a,pos_b_0based=b,distance_degree=math.dist(coords[a],coords[b])))
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('gpkg',type=Path);p.add_argument('gdb',type=Path);p.add_argument('esri_json',type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    if a.output.exists():p.error('output exists')
    before={str(f):sha(f) for f in [a.gpkg,a.esri_json]}
    gdbhash={f.relative_to(a.gdb).as_posix():sha(f) for f in a.gdb.rglob('*') if f.is_file()}
    with sqlite3.connect(a.gpkg.resolve().as_uri()+'?mode=ro',uri=True) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        declarations=db.execute('SELECT table_name,column_name,geometry_type_name,srs_id FROM gpkg_geometry_columns').fetchall()
    sm,sf,sw,sa=pyogrio.raw.read(a.gpkg,layer='void_candidates',return_fids=True)
    gm,gf,gw,ga=pyogrio.raw.read(a.gdb,layer='void_candidates_gdb',return_fids=True)
    assert sm['crs']==gm['crs']=='EPSG:6668' and len(sf)==len(gf)==13
    src={str(sa[list(sm['fields']).index('candidate_id')][i]):i for i in range(len(sf))}
    assert len(src)==13
    jd=json.loads(a.esri_json.read_bytes());js={int(f['attributes']['OBJECTID']):f for f in jd['features']}
    assert jd['spatialReference']=={'wkid':104020,'latestWkid':6668} and len(js)==13
    _,_,_,checks=pyogrio.raw.read(a.gdb,layer='check_void_candidates')
    cm,_,_,ca=pyogrio.raw.read(a.gdb,layer='check_void_candidates')
    checkrows=[dict(zip(cm['fields'],[scalar(v[i]) for v in ca])) for i in range(len(ca[0]))]
    reported={int(r['FEATURE_ID']) for r in checkrows}
    threshold=8.983152841195215e-9
    result=dict(python=platform.python_version(),shapely=shapely.__version__,geos=shapely.geos_version_string,
        pyogrio=pyogrio.__version__,gdal=pyogrio.__gdal_version__,input_sha256=before,
        source_gpkg_registration=declarations,source_gpkg_integrity='ok',features=[])
    for i,(fid,wkb) in enumerate(zip(gf,gw)):
        fields={str(k):scalar(v[i]) for k,v in zip(gm['fields'],ga)}
        key=fields['candidate_id'];si=src[key]
        source=shapely.from_wkb(sw[si]);gdb=shapely.from_wkb(wkb)
        assert source.geom_type=='Polygon' and not source.interiors
        assert len(gdb.geoms)==1 and not gdb.geoms[0].interiors
        x=np.asarray(source.exterior.coords);y=np.asarray(gdb.geoms[0].exterior.coords)
        assert x.shape==y.shape
        assert np.array_equal(y,np.asarray(js[int(fid)]['geometry']['rings'][0]))
        sourcefields={str(k):scalar(v[si]) for k,v in zip(sm['fields'],sa)}
        attrdiff=[k for k,v in sourcefields.items() if v!=fields.get(k)]
        assert not attrdiff
        delta=y-x;rp=source.representative_point()
        laea=CRS.from_proj4(f'+proj=laea +lat_0={rp.y} +lon_0={rp.x} +ellps=GRS80 +units=m +no_defs')
        project=Transformer.from_crs('EPSG:6668',laea,always_xy=True).transform
        added=gdb.difference(source);lost=source.difference(gdb)
        rows=dict(gdb_fid=int(fid),candidate_id=key,reported_by_esri=int(fid) in reported,
            source_valid=bool(source.is_valid),gdb_valid=bool(gdb.is_valid),coordinate_count=len(x),
            same_coordinate_count_and_order=True,exact_gpkg_gdb_coordinates=bool(np.array_equal(x,y)),
            exact_gdb_json_coordinates=True,source_attribute_differences=attrdiff,source_attribute_count=len(sourcefields),
            maximum_absolute_component_delta_degree=float(np.abs(delta).max()),
            maximum_vertex_displacement_degree=float(np.linalg.norm(delta,axis=1).max()),
            original_nonadjacent_pairs_within_gdb_xy_tolerance=short_pairs(x,threshold),
            exported_nonadjacent_pairs_within_gdb_xy_tolerance=short_pairs(y,threshold),
            source_minimum_clearance_degree=source.minimum_clearance,gdb_minimum_clearance_degree=gdb.minimum_clearance,
            source_local_laea_area_m2=transform(project,source).area,gdb_local_laea_area_m2=transform(project,gdb).area,
            added_area_m2=transform(project,added).area,lost_area_m2=transform(project,lost).area,
            source_geometry= json.loads(shapely.to_geojson(source)) if int(fid) in reported else None)
        result['features'].append(rows)
    result['summary']=dict(matched_candidates=13,total_coordinate_count=sum(f['coordinate_count'] for f in result['features']),
        source_valid_count=sum(f['source_valid'] for f in result['features']),gdb_valid_count=sum(f['gdb_valid'] for f in result['features']),
        maximum_absolute_component_delta_degree=max(f['maximum_absolute_component_delta_degree'] for f in result['features']),
        source_ids_with_near_nonadjacent_vertices=[f['gdb_fid'] for f in result['features'] if f['original_nonadjacent_pairs_within_gdb_xy_tolerance']],
        exported_ids_with_near_nonadjacent_vertices=[f['gdb_fid'] for f in result['features'] if f['exported_nonadjacent_pairs_within_gdb_xy_tolerance']],
        esri_reported_ids=sorted(reported))
    result['inputs_unchanged']=before=={str(f):sha(f) for f in [a.gpkg,a.esri_json]} and gdbhash=={f.relative_to(a.gdb).as_posix():sha(f) for f in a.gdb.rglob('*') if f.is_file()}
    assert result['inputs_unchanged']
    result['limits']=['Ring correspondence is by the supplied order with identical counts; no snapping, rotation, repair or precision grid is used.',
        'Polygon to single-part MultiPolygon wrapper and automatic GDB fields differ; source 29 attributes match.',
        'Metric differences are overlay-first then projected to local GRS80 LAEA, sensitive to double precision for very thin shapes.',
        'No source GPKG ArcGIS run, internal clustering inference or direct error-location evidence.',
        'Origin means uploaded candidates GPKG, not independent N03 lineage validation.',
        'This input is void review data, not the missing district025 comparison GPKG or national forest GPKG.']
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
