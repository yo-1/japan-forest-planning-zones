"""Compare pinned v0.2 reference GPKG with the uploaded national GDB, without repair."""
import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path
import numpy as np
import pyogrio
import shapely


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def decode(b):
    return shapely.from_wkb(b[8+{0:0,1:32,2:48,3:48,4:64}[(b[3]>>1)&7]:])


def rings(g):
    for pi,p in enumerate(g.geoms):
        for hi,r in enumerate([p.exterior,*p.interiors]):yield pi,hi,np.asarray(r.coords)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('reference',type=Path);p.add_argument('gdb',type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    if a.output.exists():p.error('output exists')
    before=sha(a.reference)
    assert before=='fea638d8882a4c1581bb24d634854065d89b463701a1a74b40ad75c1c27d2bea'
    files={str(f.relative_to(a.gdb)):sha(f) for f in a.gdb.rglob('*') if f.is_file()}
    db=sqlite3.connect(a.reference.resolve().as_uri()+'?mode=ro',uri=True)
    pyogrio.set_gdal_config_options({'OGR_ORGANIZE_POLYGONS':'ONLY_CCW'})
    result=dict(reference_version='v0.2, not directly downloaded v0.3',reference_sha256=before,
        shapely=shapely.__version__,geos=shapely.geos_version_string,pyogrio=pyogrio.__version__,
        gdal=pyogrio.__gdal_version__,gdal_config={'OGR_ORGANIZE_POLYGONS':'ONLY_CCW'},layers={})
    for src,dst,key in [('forest_plan_districts_provisional','forest_plan_districts','district_code'),
                        ('forest_wide_basins_provisional','forest_wide_basins','basin_code'),
                        ('forest_unassigned_review','forest_unassigned','municipality_code')]:
        cols=[x[1] for x in db.execute('PRAGMA table_info('+src+')')]
        sources={str(r[cols.index(key)]):dict(zip(cols,r)) for r in db.execute('SELECT * FROM '+src)}
        meta,fids,wkbs,attrs=pyogrio.raw.read(a.gdb,layer=dst,return_fids=True)
        assert len(sources)==len(fids)
        records=[]
        for i,(fid,wkb) in enumerate(zip(fids,wkbs)):
            fields={str(k):v[i].item() if isinstance(v[i],np.generic) else v[i] for k,v in zip(meta['fields'],attrs)}
            code=str(fields[key]);s=sources.pop(code);g=shapely.from_wkb(wkb);original=decode(s['geom'])
            sr=list(rings(original));gr=list(rings(g))
            same=len(sr)==len(gr) and all(x[0:2]==y[0:2] and x[2].shape==y[2].shape for x,y in zip(sr,gr))
            assert same,(dst,code)
            attribute_diff={k:[v,fields.get(k)] for k,v in s.items() if k not in ('fid','geom') and v!=fields.get(k)}
            assert not attribute_diff,(dst,code,attribute_diff)
            max_component=0.;max_displacement=0.;zero_new=0;nonadj_new=0;samples=[];invalidrings=[]
            g_valid=bool(g.is_valid)
            for ri,((pi,hi,x),(_,_,y)) in enumerate(zip(sr,gr)):
                d=y-x;max_component=max(max_component,float(np.abs(d).max()))
                max_displacement=max(max_displacement,float(np.linalg.norm(d,axis=1).max()))
                edges_source=np.linalg.norm(np.diff(x,axis=0),axis=1)
                edges_dest=np.linalg.norm(np.diff(y,axis=0),axis=1)
                zero_new+=int(np.count_nonzero((edges_source>0)&(edges_dest==0)))
                if not g_valid:
                    ring=shapely.Polygon(y)
                    if not ring.is_valid:
                        invalidrings.append(dict(ring_0based=ri,polygon_0based=pi,local_ring_0based=hi,
                            reason=shapely.is_valid_reason(ring),source_ring_valid=bool(shapely.Polygon(x).is_valid)))
                # Closing coordinates excluded; only source-distinct pairs newly
                # collapsed to exact duplicate, nonadjacent GDB coordinates.
                _,inverse,counts=np.unique(y[:-1],axis=0,return_inverse=True,return_counts=True)
                for u in np.flatnonzero(counts>1):
                    positions=np.flatnonzero(inverse==u)
                    for k,pa in enumerate(positions):
                        for pb in positions[k+1:]:
                            pa,pb=int(pa),int(pb)
                            if abs(pa-pb) in (1,len(y)-2):continue
                            sd=float(np.linalg.norm(x[pa]-x[pb]))
                            if sd==0:continue
                            nonadj_new+=1
                            if len(samples)<40:samples.append(dict(ring_0based=ri,polygon_0based=pi,local_ring_0based=hi,
                                pos_a_0based=pa,pos_b_0based=pb,source_a=x[pa].tolist(),source_b=x[pb].tolist(),
                                source_distance_degree=sd,gdb_common_coordinate=y[pa].tolist()))
            records.append(dict(fid=int(fid),code=code,source_valid=bool(original.is_valid),gdb_valid=g_valid,
                gdb_validity_reason=shapely.is_valid_reason(g),source_coordinate_count=int(shapely.get_num_coordinates(original)),
                gdb_coordinate_count=int(shapely.get_num_coordinates(g)),same_ring_structure_and_order=True,
                attribute_differences=attribute_diff,max_component_delta_degree=max_component,max_displacement_degree=max_displacement,
                new_zero_length_edges=zero_new,new_nonadjacent_coincident_pairs=nonadj_new,
                new_coincident_pair_samples=samples,invalid_individual_rings=invalidrings))
        assert not sources
        result['layers'][dst]=dict(count=len(records),source_valid_count=sum(r['source_valid'] for r in records),
            gdb_invalid_codes=[r['code'] for r in records if not r['gdb_valid']],
            max_component_delta_degree=max(r['max_component_delta_degree'] for r in records),
            total_new_zero_length_edges=sum(r['new_zero_length_edges'] for r in records),
            total_new_nonadjacent_coincident_pairs=sum(r['new_nonadjacent_coincident_pairs'] for r in records),features=records)
        print(dst,'complete',len(records),flush=True)
    db.close()
    result['inputs_unchanged']=before==sha(a.reference) and files=={str(f.relative_to(a.gdb)):sha(f) for f in a.gdb.rglob('*') if f.is_file()}
    assert result['inputs_unchanged']
    result['limits']=['Pinned v0.2 is a direct comparison baseline; release text reports v0.3 geometry identity but the v0.3 binary was not obtained.',
        'No GDB repair, snapping or synthetic national candidate was created.',
        'New coordinate coincidences are measured facts, not proof of ArcGIS internal clustering.',
        'Invalid GDB features are not passed to national overlay/union as if valid.']
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
