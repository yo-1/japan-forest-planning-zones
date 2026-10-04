import csv, json, re, struct, pathlib, collections, pdfplumber, argparse
parser=argparse.ArgumentParser(description='森林計画区・広域流域の確認用対応CSVを生成します')
parser.add_argument('--source-pdf',type=pathlib.Path,required=True)
parser.add_argument('--n03-dbf',type=pathlib.Path,required=True)
parser.add_argument('--output',type=pathlib.Path,required=True)
args=parser.parse_args();OUT=args.output;OUT.mkdir(parents=True,exist_ok=True)
URL='https://www.e-stat.go.jp/SG1/estat/Pdfdl.do?sinfid=000012449985'
def clean(s):return re.sub(r'\s+','',s or '')
districts=[];basins={};bn=bc=pref=''
with pdfplumber.open(args.source_pdf) as pdf:
 for page,pg in enumerate(pdf.pages,1):
  for r in pg.extract_tables()[0]:
   if not r[3] or not re.match(r'^\d{3}',r[3]):continue
   if r[0]:
    m=re.match(r'(\d{2})\s*(.*)',clean(r[0]));bc,bn=m.groups();basins[bc]=dict(basin_code=bc,basin_name=bn,main_rivers=clean(r[2]),source_date='2010-02-01',source_url=URL)
   if r[6]:pref=clean(r[6])
   m=re.match(r'(\d{3})\s*(.*)',clean(r[3]));dc,dn=m.groups()
   districts.append(dict(district_code=dc,district_name=dn,prefecture_source=pref,basin_code=bc,basin_name=bn,area_text=clean(r[5]),source_date='2010-02-01',source_page=page,source_url=URL,current_verification='未確認'))
assert len(districts)==158 and len(basins)==44
assert len({d['district_code'] for d in districts})==158
dbf=args.n03_dbf
areas=set();blank=0
with dbf.open('rb') as f:
 h=f.read(32);n=struct.unpack('<I',h[4:8])[0];hl,rl=struct.unpack('<HH',h[8:12]);fields=[]
 for i in range((hl-33)//32):
  d=f.read(32);fields.append((d[:11].split(b'\0')[0].decode(),d[16]))
 f.seek(hl)
 for i in range(n):
  b=f.read(rl)
  if b[0:1]==b'*':continue
  o=1;row={}
  for name,l in fields:row[name]=b[o:o+l].decode('utf-8').strip();o+=l
  if not row['N03_007']:blank+=1
  areas.add(tuple(row[k] for k in ['N03_007','N03_001','N03_002','N03_003','N03_004','N03_005']))
def tokens(text):
 text=re.sub(r'＜[^＞]*＞','、',text).strip('、');depth=0;start=0;out=[]
 for i,ch in enumerate(text):
  if ch=='（':depth+=1
  elif ch=='）':depth-=1
  elif ch=='、' and depth==0:out.append(text[start:i]);start=i+1
 out.append(text[start:]);return out
def match(d,a):
 code,p,sub,county,city,ward=a
 if (p[:-1] if p[-1:] in ['県','府','都'] else p)!=d['prefecture_source'] and p!=d['prefecture_source']:return []
 if city=='所属未定地':return []
 matched=[]
 for token in tokens(d['area_text']):
  token=token.replace('塩竃市','塩竈市').replace('駒ケ根市','駒ヶ根市').replace('芦北郡','葦北郡')
  m=re.fullmatch(r'([^（]+)（(.*)）',token)
  if m:
   base,condition=m.groups()
   if county!=base:continue
   exclude=condition.endswith('を除く');names=condition.removesuffix('を除く').split('、')
   if (city not in names if exclude else city in names):matched.append(token)
  elif token in [city,county,p] and token:matched.append(token)
  elif token=='東京都特別区' and p=='東京都' and city.endswith('区'):matched.append(token)
 return matched
modern=[]
def modern_add(pref,dc,names,date,url):
 for name in names.split('、'):modern.append(dict(prefecture=pref,district_code=dc,municipality=name,source_date=date,source_url=url))
toyama='https://www.pref.toyama.jp/1603/5jou/plan.html'
modern_add('富山県','055','富山市、魚津市、滑川市、黒部市、上市町、立山町、入善町、朝日町','2024-03-13',toyama)
modern_add('富山県','056','高岡市、氷見市、砺波市、小矢部市、南砺市、射水市','2024-03-13',toyama)
miyagi='https://www.pref.miyagi.jp/soshiki/ringyo-sk/chiikishinrinkeikaku.html'
modern_add('宮城県','023','富谷市、大和町、大郷町、大衡村、大崎市、色麻町、加美町、涌谷町、美里町、栗原市、石巻市、東松島市、女川町、登米市、気仙沼市、南三陸町','2026-04-01',miyagi)
modern_add('宮城県','024','白石市、角田市、蔵王町、七ヶ宿町、大河原町、村田町、柴田町、川崎町、丸森町、仙台市、塩竈市、名取市、多賀城市、岩沼市、亘理町、山元町、松島町、七ヶ浜町、利府町','2026-04-01',miyagi)
kago='https://www.pref.kagoshima.jp/ad06/sangyo-rodo/rinsui/ringyo/keikaku/tiikisinnrinnkeikaku_40850.html'
for dc,names in [('150','薩摩川内市、阿久根市、出水市、伊佐市、薩摩郡、出水郡'),('151','霧島市、姶良市、姶良郡'),('152','鹿児島市、枕崎市、指宿市、日置市、いちき串木野市、南さつま市、南九州市、鹿児島郡'),('153','鹿屋市、垂水市、曽於市、志布志市、曽於郡、肝属郡'),('154','西之表市、熊毛郡'),('155','奄美市、大島郡')]:modern_add('鹿児島県',dc,names,'2026-04-01',kago)
rows=[]
for a in sorted(areas):
 matches=[(d,match(d,a)) for d in districts if match(d,a)]
 checks=[v for v in modern if v['prefecture']==a[1] and v['municipality'] in (a[3],a[4]) and a[4]!='所属未定地']
 if checks:
  assert len(checks)==1
  v=checks[0];d=next(d for d in districts if d['district_code']==v['district_code']);matches=[(d,[v['municipality']])]
 if not matches:matches=[(None,[])]
 for d,mt in matches:
  code,p,sub,county,city,ward=a
  rows.append(dict(municipality_code=code,prefecture=p,subprefecture=sub,county=county,municipality=city,ward=ward,district_code=d['district_code'] if d else '',district_name=d['district_name'] if d else '',basin_code=d['basin_code'] if d else '',basin_name=d['basin_name'] if d else '',coverage='未確認',match_method='県公式の区域一覧と名称一致' if checks else ('2010年包括区域の名称条件一致' if d else '名称一致なし'),matched_rule='／'.join(mt),verification_status='所属計画区を県資料で照合・境界未確認' if checks else ('要現行資料照合' if len(matches)==1 and d else ('複数候補・要区域確認' if d else '未対応・要調査')),source_date=checks[0]['source_date'] if checks else '2010-02-01',n03_date='2026-01-01',source_page='' if checks else (d['source_page'] if d else ''),source_url=checks[0]['source_url'] if checks else URL,basin_source_date='2010-02-01',basin_source_url=URL,checked_date='2026-10-03',usable_for_final_polygon='false'))
def write(name,rs):
 with (OUT/name).open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rs[0]),lineterminator='\n');w.writeheader();w.writerows(rs)
write('forest_wide_basins.csv',sorted(basins.values(),key=lambda d:d['basin_code']))
write('forest_plan_districts.csv',sorted(districts,key=lambda d:d['district_code']))
write('municipality_forest_districts.csv',rows)
issues=[r for r in rows if not r['district_code'] or '複数候補' in r['verification_status']]
if issues:write('municipality_mapping_issues.csv',issues)
write('current_prefecture_rules.csv',modern)
stats=dict(source_date='2010-02-01',n03_date='2026-01-01',districts=len(districts),basins=len(basins),n03_records=n,n03_unique_attribute_groups=len(areas),n03_codes=len({a[0] for a in areas if a[0]}),csv_rows=len(rows),statuses=dict(collections.Counter(r['verification_status'] for r in rows)),blank_code_polygon_records=blank,final_polygon_ready_rows=0)
(OUT/'validation_summary.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(stats,ensure_ascii=False,indent=2));print('ISSUES');print([(r['municipality_code'],r['prefecture'],r['municipality'],r['district_code']) for r in issues])
