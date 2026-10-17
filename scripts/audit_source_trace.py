"""Read-only N03 local trace and attribute coverage; no repair or precision grid."""
import argparse
import csv
import hashlib
import json
import platform
from pathlib import Path

import numpy as np
import pyogrio
import shapely


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('mapping', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error('output exists')
    files = [a.source.with_suffix(s) for s in ('.shp', '.shx', '.dbf', '.prj', '.cpg')] + [a.mapping]
    hashes = {str(f): digest(f) for f in files}
    assert hashes[str(a.source)] == '6325d7f08c9374198e27b2cffd01bd420411be8b3cf3528da0587c6cea35538d'
    mapping = {r['municipality_code']: r for r in csv.DictReader(a.mapping.open(encoding='utf-8'))}
    meta, fids, _, fields = pyogrio.raw.read(a.source, return_fids=True, read_geometry=False)
    code_index = list(meta['fields']).index('N03_007')
    codes = {str(c) for c in fields[code_index]}
    result = dict(python=platform.python_version(), shapely=shapely.__version__, geos=shapely.geos_version_string,
                  numpy=np.__version__, pyogrio=pyogrio.__version__, gdal=pyogrio.__gdal_version__,
                  input_sha256=hashes, crs=meta['crs'], source_features=len(fids), source_codes=len(codes),
                  mapping_codes=len(mapping), source_only_codes=sorted(codes-set(mapping)),
                  mapping_only_codes=sorted(set(mapping)-codes),
                  mapped_districts=len({r['district_code'] for r in mapping.values()}-{''}),
                  mapped_basins=len({r['basin_code'] for r in mapping.values()}-{''}),
                  unassigned_codes=sorted(c for c,r in mapping.items() if not r['district_code']), local_traces=[])
    points = [('025 mouth A', [139.96788627800004,39.87999968500003]),
              ('025 mouth B', [139.9678862720001,39.879999690000034]),
              ('025 notch tip', [139.9681798050001,39.880223054000055]),
              ('023 contact 1', [141.57436528014892,38.269476273794524]),
              ('023 contact 2', [141.58515358649998,38.2764484635]),
              ('140 contact', [130.4557579575,32.5891687165])]
    for label, xy in points:
        x,y=xy
        meta, fids, wkbs, attrs = pyogrio.raw.read(a.source, bbox=(x-.001,y-.001,x+.001,y+.001), return_fids=True)
        assert meta['crs']=='EPSG:6668'
        rows=[]
        exact_geoms=[]
        for i,(fid,wkb) in enumerate(zip(fids,wkbs)):
            g=shapely.from_wkb(wkb)
            coords=shapely.get_coordinates(g)
            distances=np.linalg.norm(coords-np.array(xy),axis=1)
            ix=int(distances.argmin())
            if float(distances[ix]) == 0:
                exact_geoms.append((int(fid),g))
            props={str(k):attrs[j][i] for j,k in enumerate(meta['fields'])}
            code=str(props['N03_007'])
            ring_refs=[]
            for pi,poly in enumerate(g.geoms if g.geom_type=='MultiPolygon' else [g]):
                for ri,ring in enumerate([poly.exterior,*poly.interiors]):
                    cs=np.asarray(ring.coords)
                    k=int(np.linalg.norm(cs-np.array(xy),axis=1).argmin())
                    if np.linalg.norm(cs[k]-np.array(xy)) <= 1e-8:
                        ring_refs.append(dict(polygon_0based=pi,local_ring_0based=ri,pos_0based=k,
                            previous=cs[(k-1)%(len(cs)-1)].tolist(),vertex=cs[k].tolist(),
                            next=cs[(k+1)%(len(cs)-1)].tolist()))
            rows.append(dict(ogr_fid_0based=int(fid), attributes=props, nearest_ring_refs=ring_refs,
                             district_code=mapping.get(code,{}).get('district_code'),
                             basin_code=mapping.get(code,{}).get('basin_code'), valid=bool(g.is_valid),
                             nearest_vertex=coords[ix].tolist(),nearest_vertex_distance_degree=float(distances[ix]),
                             boundary_distance_degree=g.boundary.distance(shapely.Point(xy)),
                             covers_point=bool(g.covers(shapely.Point(xy)))))
        pairs=[]
        for i,(fa,ga) in enumerate(exact_geoms):
            for fb,gb in exact_geoms[i+1:]:
                inter=ga.intersection(gb)
                pairs.append(dict(source_fids_0based=[fa,fb],intersection_type=inter.geom_type,
                    intersection_area_degree2=inter.area,shared_boundary_length_degree=ga.boundary.intersection(gb.boundary).length))
        result['local_traces'].append(dict(label=label,point=xy,bbox_margin_degree=.001,
            source_features=rows,exact_vertex_source_pair_classification=pairs))
    # Geometry of the PR #6 diagnostic addition; never written back to any input.
    added=shapely.Polygon([[139.96784775600008,39.88002055900006],
        [139.9678862720001,39.879999690000034],[139.9681798050001,39.880223054000055],
        [139.96788627800004,39.87999968500003],[139.96784775600008,39.88002055900006]])
    _,fids,wkbs,_=pyogrio.raw.read(a.source,bbox=(139.967,39.879,139.969,39.881),return_fids=True)
    local_union=shapely.union_all(shapely.from_wkb(wkbs))
    inside=added.intersection(local_union)
    outside=added.difference(local_union)
    rp=outside.representative_point()
    result['notch_diagnostic_source_overlay']=dict(source_fids_0based=fids.tolist(),
        diagnostic_added_area_degree2=added.area,source_covered_area_degree2=inside.area,
        outside_source_area_degree2=outside.area,outside_representative_point=list(rp.coords)[0],
        outside_point_covered_by_any_local_source=bool(local_union.covers(rp)),
        note='Local bbox covers entire diagnostic polygon. Overlay in double precision can have residuals; no physical/legal gap inference. Missing GDB/GPKG coordinates not independently compared.')
    result['inputs_unchanged']=all(digest(f)==hashes[str(f)] for f in files)
    assert result['inputs_unchanged']
    result['limits']='Local source vertex/boundary trace plus nationwide attribute coverage only. No equivalence to missing v0.3, GDB or trial GPKG is assumed. Coordinates from PR #6 context-result.json/README at 1f84a78. No ArcGIS validation or causal clustering inference. Distances are planar degrees.'
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
