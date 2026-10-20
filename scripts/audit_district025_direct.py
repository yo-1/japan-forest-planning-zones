"""Pinned, read-only comparison of the supplied district025 GPKG and project GDBs."""
import argparse
import hashlib
import json
import math
import platform
import sqlite3
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy as np
import pyogrio
import shapely


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def scalar(v):return v.item() if isinstance(v,np.generic) else v


def inspect_geometry(g):
    assert g.geom_type=='MultiPolygon' and len(g.geoms)==2384
    coords=[];refs=[];sizes={};starts=[];ends=[];edge_refs=[]
    for ri,poly in enumerate(g.geoms):
        assert not poly.interiors
        cs=list(poly.exterior.coords);assert cs[0]==cs[-1];sizes[ri]=len(cs)-1
        for pos,xy in enumerate(cs[:-1]):
            coords.append(xy);refs.append((ri,pos));starts.append(xy);ends.append(cs[pos+1]);edge_refs.append((ri,pos))
    points=shapely.points(np.asarray(coords))
    segments=shapely.linestrings(np.stack([starts,ends],axis=1))
    ptree=shapely.STRtree(points);stree=shapely.STRtree(segments)
    vpairs=[];vertex_edge=[];intersections=[]
    for start in range(0,len(points),10000):
        aa,bb=ptree.query(points[start:start+10000],predicate='dwithin',distance=9e-9)
        for a,b in zip(aa,bb):
            a,b=int(a)+start,int(b)
            if a>=b:continue
            ra,pa=refs[a];rb,pb=refs[b]
            if ra==rb and abs(pa-pb) in (1,sizes[ra]-1):continue
            vpairs.append(dict(ring_a_0based=ra,pos_a_0based=pa,ring_b_0based=rb,pos_b_0based=pb,
                coordinate_a=coords[a],coordinate_b=coords[b],distance_degree=math.dist(coords[a],coords[b])))
        aa,bb=stree.query(points[start:start+10000],predicate='dwithin',distance=9e-9)
        for a,b in zip(aa,bb):
            a,b=int(a)+start,int(b);rv,pv=refs[a];re,pe=edge_refs[b]
            if rv==re and pv in (pe,(pe+1)%sizes[re]):continue
            vertex_edge.append(dict(vertex_ring_0based=rv,vertex_pos_0based=pv,
                edge_ring_0based=re,edge_start_pos_0based=pe,edge_end_pos_0based=(pe+1)%sizes[re],
                vertex=coords[a],edge_start=starts[b],edge_end=ends[b],distance_degree=float(points[a].distance(segments[b]))))
        aa,bb=stree.query(segments[start:start+10000],predicate='intersects')
        for a,b in zip(aa,bb):
            a,b=int(a)+start,int(b)
            if a>=b:continue
            ra,pa=edge_refs[a];rb,pb=edge_refs[b]
            if ra==rb and abs(pa-pb) in (1,sizes[ra]-1):continue
            intersections.append(dict(ring_a_0based=ra,edge_a_start_0based=pa,ring_b_0based=rb,edge_b_start_0based=pb,
                geometry=json.loads(shapely.to_geojson(segments[a].intersection(segments[b])))))
    return dict(valid=bool(g.is_valid),validity_reason=shapely.is_valid_reason(g),polygon_count=len(g.geoms),
        stored_coordinate_count=int(shapely.get_num_coordinates(g)),holes=0,search_threshold_degree=9e-9,
        nonadjacent_vertex_pairs=vpairs,nonincident_vertex_edge_pairs=vertex_edge,
        exact_nonadjacent_segment_intersections=intersections)


def extract_checked(path,dest,allowed):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        inventory=[]
        for i in z.infolist():
            if i.is_dir():continue
            data=z.read(i);inventory.append(dict(name=i.filename,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
            if allowed(i.filename):
                target=(dest/i.filename).resolve();assert target.is_relative_to(dest.resolve())
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    return inventory


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('comparison_zip',type=Path);p.add_argument('project_zip',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--full-ring-deltas',action='store_true',help='Include all nonzero per-ring deltas in addition to summary')
    a=p.parse_args()
    if a.output.exists():p.error('output exists')
    before={str(x):sha(x) for x in [a.comparison_zip,a.project_zip]}
    assert before[str(a.comparison_zip)]=='442806d09fe9f2512d33e7e4091983efa146b4913166ee8ad0fbc880aa239a70'
    assert before[str(a.project_zip)]=='63b42259484b2e3d9e22a99e05416a68f8ec0a766187b274797991c799240f6a'
    result=dict(python=platform.python_version(),shapely=shapely.__version__,geos=shapely.geos_version_string,
        numpy=np.__version__,pyogrio=pyogrio.__version__,gdal=pyogrio.__gdal_version__,input_sha256=before,index_base=0,layers={})
    with tempfile.TemporaryDirectory(prefix='district025-direct-') as tmp:
        root=Path(tmp)
        result['comparison_zip_inventory']=extract_checked(a.comparison_zip,root/'comparison',lambda n:n.endswith('.gpkg'))
        # Avoid publishing project files or unrelated local-path-bearing messages.
        extract_checked(a.project_zip,root/'project',lambda n:('/unchanged.gdb/' in n or '/candidate.gdb/' in n))
        gpkg=next((root/'comparison').rglob('*.gpkg'))
        assert sha(gpkg)=='b93f906489e5cd670be95f934d8c96fd8e98a7a079a9be666440e13c44efb4cf'
        files={str(x.relative_to(root)):sha(x) for x in root.rglob('*') if x.is_file()}
        with sqlite3.connect(gpkg.resolve().as_uri()+'?mode=ro',uri=True) as c:
            assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
            assert not c.execute('pragma foreign_key_check').fetchall()
            result['gpkg_geometry_registration']=c.execute('select table_name,geometry_type_name,srs_id from gpkg_geometry_columns').fetchall()
        geoms={}
        for tag,source_table in [('unchanged','trial_025_unchanged'),('candidate','candidate_025')]:
            gdb=next((root/'project').rglob(tag+'.gdb'));dest_table='district025_'+tag
            sm,sf,sw,sa=pyogrio.raw.read(gpkg,layer=source_table,return_fids=True)
            gm,gf,gw,ga=pyogrio.raw.read(gdb,layer=dest_table,return_fids=True)
            assert len(sf)==len(gf)==1 and sm['crs']==gm['crs']=='EPSG:6668'
            source=shapely.from_wkb(sw[0]);dest=shapely.from_wkb(gw[0]);geoms[tag]=(source,dest)
            sfields={str(k):scalar(v[0]) for k,v in zip(sm['fields'],sa)}
            dfields={str(k):scalar(v[0]) for k,v in zip(gm['fields'],ga)}
            assert sfields['district_code']==dfields['district_code']=='025'
            assert sfields['source_district_fid']==dfields['source_district_fid']==25
            attrdiff={k:[v,dfields.get(k)] for k,v in sfields.items() if v!=dfields.get(k)}
            assert not attrdiff
            rows=[];maxdelta=0.;maxnorm=0.
            assert len(source.geoms)==len(dest.geoms)==2384
            for ri,(left,right) in enumerate(zip(source.geoms,dest.geoms)):
                assert len(left.interiors)==len(right.interiors)==0
                x=np.asarray(left.exterior.coords);y=np.asarray(right.exterior.coords);assert x.shape==y.shape
                delta=y-x;component=float(np.abs(delta).max());norm=float(np.linalg.norm(delta,axis=1).max())
                maxdelta=max(maxdelta,component);maxnorm=max(maxnorm,norm)
                if component:rows.append(dict(ring_0based=ri,max_component_delta_degree=component,max_displacement_degree=norm))
            cm,cf,_,ca=pyogrio.raw.read(gdb,layer='check_'+tag,return_fids=True)
            checks=[dict(zip(cm['fields'],[scalar(v[i]) for v in ca])) for i in range(len(cf))]
            _,_,_,xml=pyogrio.raw.read(gdb,sql='GetLayerDefinition '+dest_table)
            settings={e.tag.rsplit('}',1)[-1]:e.text for e in ET.fromstring(xml[0][0]).iter()
                if e.tag.rsplit('}',1)[-1] in {'XOrigin','YOrigin','XYScale','XYTolerance','WKID','LatestWKID'}}
            result['layers'][tag]=dict(gpkg_layer=source_table,gdb_layer=dest_table,gpkg_fid=int(sf[0]),gdb_fid=int(gf[0]),
                source_attributes=sfields,gdb_only_attributes={k:v for k,v in dfields.items() if k not in sfields},
                source_attribute_differences=attrdiff,same_ring_counts_vertex_counts_and_order=True,
                maximum_component_delta_degree=maxdelta,maximum_displacement_degree=maxnorm,
                compared_ring_count=2384,rings_with_nonzero_coordinate_delta=len(rows),
                largest_ring_deltas=sorted(rows,key=lambda r:r['max_component_delta_degree'],reverse=True)[:10],
                notch_ring_delta=next((r for r in rows if r['ring_0based']==2023),None),
                gpkg_ordered_xy_sha256=hashlib.sha256(np.asarray(shapely.get_coordinates(source),dtype='<f8').tobytes()).hexdigest(),
                gdb_ordered_xy_sha256=hashlib.sha256(np.asarray(shapely.get_coordinates(dest),dtype='<f8').tobytes()).hexdigest(),
                gdb_settings=settings,check_fields=cm['fields'].tolist(),saved_esri_rows=checks,
                gpkg_inspection=inspect_geometry(source),gdb_inspection=inspect_geometry(dest))
            if a.full_ring_deltas:result['layers'][tag]['full_ring_deltas']=rows
            print(tag,'direct comparison complete',flush=True)
        u,c=[geoms[k][0] for k in ('unchanged','candidate')]
        changed=[]
        for ri,(x,y) in enumerate(zip(u.geoms,c.geoms)):
            if not np.array_equal(np.asarray(x.exterior.coords),np.asarray(y.exterior.coords)):changed.append(ri)
        assert changed==[2023]
        original=np.asarray(u.geoms[2023].exterior.coords);candidate=np.asarray(c.geoms[2023].exterior.coords)
        assert np.array_equal(np.delete(original,[54179,54180],axis=0),candidate)
        gu,gc=[geoms[k][1] for k in ('unchanged','candidate')]
        assert all(np.array_equal(np.asarray(x.exterior.coords),np.asarray(y.exterior.coords))
                   for i,(x,y) in enumerate(zip(gu.geoms,gc.geoms)) if i!=2023)
        assert np.array_equal(np.delete(np.asarray(gu.geoms[2023].exterior.coords),[54179,54180],axis=0),
                              np.asarray(gc.geoms[2023].exterior.coords))
        assert result['layers']['unchanged']['source_attributes']==result['layers']['candidate']['source_attributes']
        result['within_gdb_comparison']=dict(only_two_vertex_deletions=True,changed_ring_0based=2023,
            removed_positions_0based=[54179,54180],unchanged_other_rings=2383)
        result['within_gpkg_comparison']=dict(changed_ring_indices_0based=changed,removed_positions_0based=[54179,54180],
            only_two_vertex_deletions=True,unchanged_other_rings=2383,added_area_degree2=c.difference(u).area,lost_area_degree2=u.difference(c).area)
        result['notch_location']=dict(crs='EPSG:6668',ring_0based=2023,
            mouth_a_pos_0based=54178,mouth_b_pos_0based=54180,tip_pos_0based=54179,
            source_mouth_a=original[54178].tolist(),source_tip=original[54179].tolist(),source_mouth_b=original[54180].tolist(),
            gdb_mouth_a=list(gu.geoms[2023].exterior.coords)[54178],gdb_tip=list(gu.geoms[2023].exterior.coords)[54179],gdb_mouth_b=list(gu.geoms[2023].exterior.coords)[54180],
            evidence='Independent near-vertex/near-edge locus and exactly localized candidate edit, not an Esri-reported problem coordinate')
        result['extracted_inputs_unchanged']=files=={str(x.relative_to(root)):sha(x) for x in root.rglob('*') if x.is_file()}
        assert result['extracted_inputs_unchanged']
    result['original_archives_unchanged']=before=={str(x):sha(x) for x in [a.comparison_zip,a.project_zip]}
    assert result['original_archives_unchanged']
    result['limits']=['GPKG/GDB compare native decoded double coordinates; no rounding, snapping, repair or reprojection.',
        'Degree-distance searches and GEOS validity do not reproduce Esri tolerance/clustering/geometry checks.',
        'Saved check tables identify FEATURE_ID, not error coordinates; direct Esri-reported point remains unavailable.',
        'ZIP README/manifest describe the earlier build, not newly executed instructions or a new ArcGIS run.',
        'No new ArcGIS run, national repair rule, original data change or Release update.']
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
