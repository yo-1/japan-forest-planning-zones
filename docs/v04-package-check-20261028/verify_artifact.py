"""Independently inspect downloaded CI packages without modifying any input."""
from pathlib import Path
import hashlib, json, sqlite3, struct, zipfile
import shapely

ROOT=Path(__file__).resolve().parent/'v04-evidence-20261028'
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()
def unpack(path,dest):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        for name in z.namelist():
            assert not Path(name).is_absolute() and '..' not in Path(name).parts
        z.extractall(dest)
def decode(blob):
    assert blob[:2]==b'GP'
    flags=blob[3]; endian='<' if flags&1 else '>'
    srid=struct.unpack(endian+'i',blob[4:8])[0]
    n=(0,4,6,6,8)[(flags>>1)&7]
    return srid,shapely.from_wkb(blob[8+8*n:])
def qi(name): return '"'+name.replace('"','""')+'"'

archive=ROOT/'artifact.zip'
assert sha(archive)=='57097efa4e8eba9bb4d6815e29cfc0792b55bf7adf969ed564cc77fc0c843ed4'
unpack(archive,ROOT/'packages')
pkg=ROOT/'packages'
m=json.loads((pkg/'review_manifest.json').read_text())
v=json.loads((pkg/'gap_validation.json').read_text())
assert v['passed'] and not v['errors'] and not v['invalid']
assert v['basin_exact_matches']==v['basin_total']==44 and v['unassigned_preserved']
assert len(v['districts'])==158
result={'source_run':40543634341,'source_head':'2e88052c0495a96bd88dc73d3d99da3b1633da50','artifact_sha256':sha(archive),'environment':{'shapely':shapely.__version__,'geos':shapely.geos_version_string},'packages':[],'layers':{},'gpkg_files':[],'ci_gap_validation_readback':{'passed':v['passed'],'errors':v['errors'],'invalid':v['invalid'],'basin_exact_matches':v['basin_exact_matches'],'unassigned_preserved':v['unassigned_preserved'],'added_m2_total':v['added_m2_total'],'lost_m2_total':v['lost_m2_total']},'repair':m['narrow_gap_repair'],'qgis_candidate_verified':False,'qgis_gui_candidate_verified':False}
manifest={**m['candidate'],**m['aggregates'],**m['coordinate_zones']}
expected_counts={'forest_plan_districts_provisional':158,'forest_wide_basins_provisional':44,'forest_unassigned_review':20,'plane_rectangular_municipalities_2026':1911,'plane_rectangular_zones_2026':19}
for entry in m['review_files']:
    path=pkg/entry['name']; actual=sha(path)
    assert actual==entry['sha256'] and path.stat().st_size==entry['bytes']
    result['packages'].append({'name':path.name,'bytes':path.stat().st_size,'sha256':actual,'crc_ok':True})
    dest=ROOT/path.stem; unpack(path,dest)
    for gpkg in dest.glob('*.gpkg'):
        before=sha(gpkg)
        conn=sqlite3.connect(gpkg.resolve().as_uri()+'?mode=ro',uri=True)
        assert conn.execute('pragma integrity_check').fetchone()[0]=='ok'
        for table,col,kind,srid in conn.execute('select table_name,column_name,geometry_type_name,srs_id from gpkg_geometry_columns'):
            if table not in expected_counts: continue
            assert srid==6668 and kind=='MULTIPOLYGON'
            cols=conn.execute('pragma table_info('+qi(table)+')').fetchall()
            assert {r[1]:r[2].upper() for r in cols}[col]==kind
            digest=hashlib.sha256(); count=invalid=empty=0
            for fid,blob in conn.execute('select fid,'+qi(col)+' from '+qi(table)+' order by fid'):
                assert blob is not None
                actual_srid,g=decode(blob); assert actual_srid==srid
                invalid+=not g.is_valid; empty+=g.is_empty; count+=1; digest.update(blob)
            assert count==expected_counts[table] and invalid==empty==0
            assert digest.hexdigest()==manifest[table]['geometry_sha256']
            attr={}
            names={r[1] for r in cols}
            for name in ('status','final_usable','forest_final_usable'):
                if name in names: attr[name]=conn.execute('select '+qi(name)+',count(*) from '+qi(table)+' group by '+qi(name)).fetchall()
            result['layers'][table]={'features':count,'epsg':srid,'sql_geometry_type':kind,'invalid':invalid,'empty':empty,'geometry_sha256':digest.hexdigest(),'manifest_match':True,'status_values':attr}
        conn.close(); assert before==sha(gpkg)
        result['gpkg_files'].append({'name':gpkg.name,'bytes':gpkg.stat().st_size,'sha256':before,'sqlite_integrity':'ok','unchanged_after_verification':True})
assert set(result['layers'])==set(expected_counts)
assert result['layers']['plane_rectangular_municipalities_2026']['geometry_sha256']=='7e4c91ec0ffc7a3e69e7b77248d9a65b73080a3353f3a663a84cdeb13144e1aa'
assert result['layers']['plane_rectangular_zones_2026']['geometry_sha256']=='23fa2d62f395ce192857e2a69444e639e24d4f89c30f4da17d0976b0acb3a02b'
assert result['layers']['forest_unassigned_review']['geometry_sha256']=='a3193c944bd3f44f4ad7621a95c1865d930f26da4a379ef00640d2b1e6bf9d6f'
result['passed']=True
(ROOT/'independent_package_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
