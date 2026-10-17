"""Read-only national GDB validity and saved Esri check-table inventory."""
import argparse
import collections
import hashlib
import json
import platform
import xml.etree.ElementTree as ET
from pathlib import Path
import pyogrio
import shapely


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('gdb',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('output exists')
    hashes={x.relative_to(a.gdb).as_posix():sha(x) for x in a.gdb.rglob('*') if x.is_file()}
    # FileGDB shell/hole orientation allows faster organization. A prior default
    # GDAL read independently returned the same invalid FID sets (recorded below).
    pyogrio.set_gdal_config_options({'OGR_ORGANIZE_POLYGONS':'ONLY_CCW'})
    result=dict(python=platform.python_version(),shapely=shapely.__version__,geos=shapely.geos_version_string,
        pyogrio=pyogrio.__version__,gdal=pyogrio.__gdal_version__,gdal_config={'OGR_ORGANIZE_POLYGONS':'ONLY_CCW'},
        input_file_sha256=hashes,layers={})
    expected={'forest_plan_districts':[20,23,25,31,36,37,48,50,78,79,102,118,138,140,141,153],
              'forest_wide_basins':[10,11,13,15,16,17,18,23,32,33,43], 'forest_unassigned':[]}
    for layer,key in [('forest_plan_districts','district_code'),('forest_wide_basins','basin_code'),('forest_unassigned','municipality_code')]:
        meta,fids,wkbs,fields=pyogrio.raw.read(a.gdb,layer=layer,return_fids=True)
        idx=list(meta['fields']).index(key)
        geoms=shapely.from_wkb(wkbs)
        rows=[dict(fid=int(fid),code=str(fields[idx][i]),valid=bool(g.is_valid),
            validity_reason=shapely.is_valid_reason(g),stored_coordinate_count=int(shapely.get_num_coordinates(g)))
            for i,(fid,g) in enumerate(zip(fids,geoms))]
        invalid=[r['fid'] for r in rows if not r['valid']]
        assert invalid==expected[layer],(layer,invalid)
        _,_,_,xml=pyogrio.raw.read(a.gdb,sql='GetLayerDefinition '+layer)
        settings={e.tag.rsplit('}',1)[-1]:e.text for e in ET.fromstring(xml[0][0]).iter()
                  if e.tag.rsplit('}',1)[-1] in {'XYTolerance','XYScale','XOrigin','YOrigin','WKID','LatestWKID'}}
        result['layers'][layer]=dict(count=len(rows),crs=meta['crs'],invalid_fids=invalid,features=rows,
            native_gdb_settings=settings,matches_prior_default_gdal_read_invalid_fids=True)
    meta,fids,_,fields=pyogrio.raw.read(a.gdb,layer='check_districts_esri',return_fids=True)
    checks=[{str(k):v[i].item() if hasattr(v[i],'item') else v[i] for k,v in zip(meta['fields'],fields)} for i in range(len(fids))]
    mapping={r['fid']:r['code'] for r in result['layers']['forest_plan_districts']['features']}
    for r in checks:r['district_code_by_stored_fid']=mapping.get(int(r['FEATURE_ID']))
    result['saved_esri_check']=dict(row_count=len(checks),problem_counts=dict(collections.Counter(x['PROBLEM'] for x in checks)),rows=checks)
    result['input_files_unchanged']=hashes=={x.relative_to(a.gdb).as_posix():sha(x) for x in a.gdb.rglob('*') if x.is_file()}
    assert result['input_files_unchanged']
    result['limits']=['This is uploaded GDB validity, not validity of the released GPKG.',
        'Saved Esri district checks are not a new ArcGIS execution, and do not cover basin/unassigned validation.',
        'No direct original GPKG coordinate comparison; export/quantization as cause is not established.',
        'No geometry repair or source/release changes.']
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
