"""Read-only, input-specific comparison of the two district025 GDB geometries."""
import argparse
import hashlib
import json
import math
import platform
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy as np
import pyogrio
import shapely


def sha(data):
    return hashlib.sha256(data).hexdigest()


def close_pairs(geom):
    coords, refs, sizes = [], [], {}
    for ri, poly in enumerate(geom.geoms):
        assert not poly.interiors
        ring = list(poly.exterior.coords)
        assert ring[0] == ring[-1]
        sizes[ri] = len(ring) - 1
        for pos, xy in enumerate(ring[:-1]):
            coords.append(xy)
            refs.append((ri, pos))
    points = shapely.points(np.asarray(coords))
    tree = shapely.STRtree(points)
    pairs, zeros, adjacent = [], 0, 0
    for start in range(0, len(points), 10000):
        a, b = tree.query(points[start:start+10000], predicate='dwithin', distance=9e-9)
        for i,j in zip(a,b):
            i,j=int(i)+start,int(j)
            if i>=j:
                continue
            ra,pa=refs[i]; rb,pb=refs[j]
            if ra==rb and abs(pa-pb) in (1,sizes[ra]-1):
                adjacent+=1
                continue
            d=math.dist(coords[i],coords[j])
            if d==0:
                zeros+=1
            else:
                pairs.append(dict(ring_a_0based=ra,pos_a_0based=pa,ring_b_0based=rb,pos_b_0based=pb,
                                  coordinate_a=coords[i],coordinate_b=coords[j],distance_degree=d))
    return dict(threshold_degree=9e-9,positive_nonadjacent_pairs=pairs,
                zero_distance_nonadjacent_pair_count=zeros,excluded_adjacent_pair_count=adjacent)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():
        p.error('output exists')
    raw=a.archive.read_bytes()
    assert sha(raw)=='63b42259484b2e3d9e22a99e05416a68f8ec0a766187b274797991c799240f6a'
    result=dict(archive_bytes=len(raw),archive_sha256=sha(raw),python=platform.python_version(),
                shapely=shapely.__version__,geos=shapely.geos_version_string,numpy=np.__version__,
                pyogrio=pyogrio.__version__,gdal=pyogrio.__gdal_version__,index_base=0,
                scope='GDB pair comparison; not comparison to missing distributed GPKG and not an ArcGIS rerun')
    with tempfile.TemporaryDirectory(prefix='district025-gdb-') as tmp:
        root=Path(tmp)
        with zipfile.ZipFile(a.archive) as z:
            assert z.testzip() is None
            files=[i for i in z.infolist() if not i.is_dir()]
            result['zip_crc_ok']=True
            result['file_count']=len(files)
            result['gpkg_members']=[i.filename for i in files if i.filename.lower().endswith('.gpkg')]
            result['void_candidate_members']=[i.filename for i in files if 'void_candidate' in i.filename.lower()]
            expected={}
            for i in files:
                if '.gdb/' not in i.filename:
                    continue
                dest=(root/i.filename).resolve()
                assert dest.is_relative_to(root)
                dest.parent.mkdir(parents=True,exist_ok=True)
                data=z.read(i)
                dest.write_bytes(data)
                expected[dest]=sha(data)
            result['check_messages']={}
            for name in ('118764669915700','118923566476100'):
                entry=next(i.filename for i in files if i.filename.endswith('/GpMessages/'+name))
                result['check_messages'][name]=[dict(code=m.get('code'),type=m.get('type'),text=m.text)
                                               for m in ET.fromstring(z.read(entry)).findall('msg')]
        geoms,attrs={},{}
        result['layers']={}
        for tag in ('unchanged','candidate'):
            gdb=next(root.rglob(tag+'.gdb'))
            layer='district025_'+tag
            meta,fids,wkbs,fields=pyogrio.raw.read(gdb,layer=layer,return_fids=True)
            assert len(fids)==1 and meta['crs']=='EPSG:6668'
            geom=shapely.from_wkb(wkbs[0])
            assert geom.geom_type=='MultiPolygon' and not geom.has_z and not geom.has_m
            geoms[tag]=geom
            attrs[tag]={str(k):v[0].item() if isinstance(v[0],np.generic) else v[0]
                        for k,v in zip(meta['fields'],fields)}
            cm,cf,_,ca=pyogrio.raw.read(gdb,layer='check_'+tag,return_fids=True)
            checks=[{str(k):v[i].item() if isinstance(v[i],np.generic) else v[i]
                     for k,v in zip(cm['fields'],ca)} for i in range(len(cf))]
            result['layers'][tag]=dict(feature_fids=fids.tolist(),crs=meta['crs'],attributes=attrs[tag],
                polygon_count=len(geom.geoms),stored_coordinate_count=int(shapely.get_num_coordinates(geom)),
                interior_ring_count=sum(len(x.interiors) for x in geom.geoms),valid=bool(geom.is_valid),
                validity_reason=shapely.is_valid_reason(geom),wkb_sha256=sha(wkbs[0]),
                decoded_ordered_xy_sha256=sha(np.asarray(shapely.get_coordinates(geom),dtype='<f8').tobytes()),
                check_table_fields=cm['fields'].tolist(),check_rows=checks,close_vertices=close_pairs(geom))
        u,c=geoms['unchanged'],geoms['candidate']
        assert len(u.geoms)==len(c.geoms)==2384
        changed=[]
        for i,(left,right) in enumerate(zip(u.geoms,c.geoms)):
            assert len(left.interiors)==len(right.interiors)==0
            if not np.array_equal(np.asarray(left.exterior.coords),np.asarray(right.exterior.coords)):
                changed.append(i)
        assert changed==[2023]
        before=np.asarray(u.geoms[2023].exterior.coords)
        after=np.asarray(c.geoms[2023].exterior.coords)
        exact=np.array_equal(np.delete(before,[54179,54180],axis=0),after)
        assert exact
        changed_attrs={k:[attrs['unchanged'][k],attrs['candidate'][k]] for k in attrs['unchanged']
                       if attrs['unchanged'][k]!=attrs['candidate'][k]}
        assert set(changed_attrs)=={'Shape_Length','Shape_Area'}
        added=c.difference(u); lost=u.difference(c)
        result['comparison']=dict(changed_polygon_indices_0based=changed,
            changed_ring_0based=2023,removed_positions_0based=[54179,54180],
            removed_coordinates=before[[54179,54180]].tolist(),
            exact_ordered_xy_match_after_only_two_deletions=exact,
            unchanged_ring_count=2383,changed_attributes=changed_attrs,
            added_area_degree2=added.area,lost_area_degree2=lost.area,
            added_geometry=json.loads(shapely.to_geojson(added)))
        result['extracted_gdb_files_unchanged']=all(sha(f.read_bytes())==h for f,h in expected.items())
        assert result['extracted_gdb_files_unchanged']
    result['archive_unchanged']=sha(a.archive.read_bytes())==result['archive_sha256']
    assert result['archive_unchanged']
    result['limits']=['GDAL/OpenFileGDB decoded coordinates; raw FileGDB shape storage not compared to GPKG.',
        'Check tables contain CLASS, FEATURE_ID, PROBLEM only; no reported problem coordinates.',
        'Inherited original_esri_problem attribute is not the candidate Check Geometry result.',
        'No clustering mechanism inference; no national adoption or source/release changes.']
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
