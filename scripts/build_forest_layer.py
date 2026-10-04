"""Join provisional forest planning attributes without changing source geometry."""
import argparse,csv,hashlib,json,sqlite3,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
root=Path(__file__).resolve().parents[1]
rows=list(csv.DictReader((root/'data/forest/municipality_forest_districts.csv').open(encoding='utf-8-sig')))
m={r['municipality_code']:r for r in rows};assert len(m)==len(rows)
fields={'forest_district_code':'district_code','forest_district_name':'district_name','wide_basin_code':'basin_code','wide_basin_name':'basin_name','forest_status':'verification_status','forest_coverage':'coverage','forest_source_date':'source_date','forest_source_url':'source_url','basin_source_date':'basin_source_date','basin_source_url':'basin_source_url','forest_final_usable':'usable_for_final_polygon'}
assert a.input.resolve()!=a.output.resolve();a.output.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(a.input,a.output)
c=sqlite3.connect(a.output);t=c.execute("select table_name from gpkg_contents where data_type='features'").fetchone()[0]
def digest():
 h=hashlib.sha256()
 for row in c.execute(f'SELECT * FROM "{t}" ORDER BY fid'):
  for v in row[:11]:
   b=v if isinstance(v,bytes) else str(v).encode();h.update(len(b).to_bytes(8,'big'));h.update(b)
 return h.hexdigest()
before=digest();codes=c.execute(f'SELECT fid,N03_007 FROM "{t}"').fetchall();assert all(code in m for _,code in codes)
for f in fields:c.execute(f'ALTER TABLE "{t}" ADD COLUMN "{f}" TEXT')
# Spatial extension supplies functions used by GeoPackage update triggers.
try:
 c.enable_load_extension(True);c.load_extension('mod_spatialite')
except sqlite3.OperationalError:
 def geometry_function_called(*args):
  raise RuntimeError('Unexpected geometry update during attribute join')
 for name in ['ST_IsEmpty','ST_MinX','ST_MaxX','ST_MinY','ST_MaxY']:
  c.create_function(name,1,geometry_function_called)
sql=f'UPDATE "{t}" SET '+','.join(f'"{f}"=?' for f in fields)+' WHERE fid=?'
c.executemany(sql,[tuple(m[code].get(key) or None for key in fields.values())+(fid,) for fid,code in codes]);c.commit()
after=digest();assert before==after
summary={'features':len(codes),'municipality_codes':len(set(code for _,code in codes)),'original_attributes_and_geometry_unchanged':before==after,'source_feature_digest':before,'missing_mapping_codes':0,'unassigned_features':sum(not m[code]['district_code'] for _,code in codes),'final_usable_features':sum(m[code]['usable_for_final_polygon']=='true' for _,code in codes),'geometry_crs':c.execute('select srs_id from gpkg_geometry_columns').fetchall(),'sqlite_integrity':c.execute('pragma integrity_check').fetchone()[0]}
assert summary['sqlite_integrity']=='ok';c.close()
(a.output.parent/'validation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(summary,ensure_ascii=False))
source=list(csv.DictReader((root/'data/municipality_zones.csv').open(encoding='utf-8')))
with (root/'data/municipality_coordinate_forest_zones.csv').open('w',encoding='utf-8',newline='') as out:
 w=csv.DictWriter(out,fieldnames=list(source[0])+list(fields),lineterminator='\n');w.writeheader()
 for r in source:w.writerow(dict(r,**{f:m[r['code']].get(k,'') for f,k in fields.items()}))
