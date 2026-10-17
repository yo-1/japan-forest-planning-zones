"""Read-only inventory of three uploaded projects and their accessible GDB layers."""
import argparse
import hashlib
import json
import platform
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pyogrio
import shapely


def digest(data):
    return hashlib.sha256(data).hexdigest()


def members(path):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        return {i.filename:digest(z.read(i)) for i in z.infolist() if not i.is_dir()}


def scalar(x):
    return x.item() if isinstance(x,np.generic) else x


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('project1',type=Path)
    p.add_argument('project3',type=Path)
    p.add_argument('project4',type=Path)
    p.add_argument('previous_project4',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists(): p.error('output exists')
    paths=[a.project1,a.project3,a.project4,a.previous_project4]
    before=[digest(x.read_bytes()) for x in paths]
    result=dict(python=platform.python_version(),shapely=shapely.__version__,geos=shapely.geos_version_string,
                pyogrio=pyogrio.__version__,gdal=pyogrio.__gdal_version__,numpy=np.__version__,projects={})
    geometries={}
    with tempfile.TemporaryDirectory(prefix='forest-batch-') as tmp:
        root=Path(tmp)
        hashes={}
        for label,path in zip(('project1','project3','project4'),paths):
            out=root/label
            record=dict(bytes=path.stat().st_size,sha256=digest(path.read_bytes()),gpkg_members=[],gdbs={})
            with zipfile.ZipFile(path) as z:
                assert z.testzip() is None
                record['crc_ok']=True
                record['gpkg_members']=[n for n in z.namelist() if n.lower().endswith('.gpkg')]
                for i in z.infolist():
                    if i.is_dir() or '.gdb/' not in i.filename: continue
                    dest=(out/i.filename).resolve()
                    assert dest.is_relative_to(out)
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    data=z.read(i);dest.write_bytes(data);hashes[dest]=digest(data)
            for gdb in out.rglob('*.gdb'):
                layers={}
                try: listing=pyogrio.list_layers(gdb)
                except pyogrio.errors.DataSourceError:
                    record['gdbs'][gdb.name]=dict(openfilegdb_readable=False,
                        note='No user layer confirmed; inability to open alone does not establish corruption')
                    continue
                for layer,kind in listing:
                    meta,fids,wkb,attrs=pyogrio.raw.read(gdb,layer=layer,return_fids=True)
                    info=dict(feature_count=len(fids),crs=meta['crs'],geometry_type=kind,fields=meta['fields'].tolist())
                    if kind is None:
                        info['rows']=[dict(zip(meta['fields'],[scalar(v[i]) for v in attrs])) for i in range(len(fids))]
                    else:
                        geoms=shapely.from_wkb(wkb)
                        dc=list(meta['fields']).index('district_code')
                        info['features']=[dict(fid=int(fids[i]),district_code=str(attrs[dc][i]),valid=bool(g.is_valid),
                            coordinate_count=int(shapely.get_num_coordinates(g)),polygon_count=len(g.geoms),
                            interior_ring_count=sum(len(x.interiors) for x in g.geoms)) for i,g in enumerate(geoms)]
                        for i,g in enumerate(geoms): geometries[(label,layer,str(attrs[dc][i]))]=g
                    layers[str(layer)]=info
                record['gdbs'][gdb.name]=dict(openfilegdb_readable=True,layers=layers)
            result['projects'][label]=record
        left=geometries[('project3','main_ExportFeatures','025')]
        right=geometries[('project4','district025_unchanged','025')]
        assert len(left.geoms)==len(right.geoms)==2384
        exact=all(len(x.interiors)==len(y.interiors)==0 and
                  np.array_equal(np.asarray(x.exterior.coords),np.asarray(y.exterior.coords))
                  for x,y in zip(left.geoms,right.geoms))
        result['project3_025_vs_project4_unchanged']=dict(exact_ordered_all_ring_xy_match=exact,
            note='Check table CLASS is districts_trial21, while stored feature class is main_ExportFeatures. FID4 maps to 025 in the stored class; original validation-input provenance is not established by that mapping alone.')
        assert exact
        old,new=members(a.previous_project4),members(a.project4)
        result['project4_archive_comparison']=dict(previous_sha256=before[3],new_sha256=before[2],
            member_names_equal=old.keys()==new.keys(),changed_content_members=sorted(k for k in old.keys()&new.keys() if old[k]!=new[k]),
            previous_file_count=len(old),new_file_count=len(new),
            note='Archive SHA differs but all member names and decompressed file bytes match; do not label ZIP binaries identical')
        result['extracted_gdb_files_unchanged']=all(digest(x.read_bytes())==h for x,h in hashes.items())
    result['input_archives_unchanged']=before==[digest(x.read_bytes()) for x in paths]
    assert result['extracted_gdb_files_unchanged'] and result['input_archives_unchanged']
    result['project2']=dict(status='not inspected',reason='Sediment transfer exceeds executor limit of 32 MiB',
                            source='user uploaded project2 ZIP; no hash or inventory inferred')
    result['limits']=['No void_candidates_gdb or check_void_candidates layer found in readable GDBs of projects1/3/4.',
        'No source comparison GPKG present in those three archives.',
        'No geometry repaired, no ArcGIS rerun, no cause inferred from GEOS validity.',
        'Project2 and project5 contents are unknown; screenshot showed project5.']
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__': main()
