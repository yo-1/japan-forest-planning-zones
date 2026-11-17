# Package the verified v0.8 candidate into release staging (mirrors the v0.7 layout).
import geopandas as gpd, numpy as np, shapely, json, hashlib, os, shutil, zipfile, time, csv, io
B = '/home/hatch/workspace/forest-planning-zones'
C = f'{B}/v08-candidate'; R = f'{B}/v08-release'; R7 = f'{B}/v07-release'
t0 = time.time()
for d in [f'{R}/forest/styles', f'{R}/forest/tables', f'{R}/muni']:
    os.makedirs(d, exist_ok=True)

README = """森林計画区・広域流域 確認用データ v0.8

確認用データです。公式境界・所属は未確定で、final_usable=falseです。
v0.8は、v0.7に対して、未割当だった13市町村の所属を県の地域森林計画等の
公式資料で照合して割り当てた版です。作り直しの土台（源泉の9桁統一と
再構築）はv0.7のままです。

v0.7からの変更点
1. 未割当13市町村を、県の地域森林計画・全国森林計画等の構成市町村の
   明記に基づいて割り当てました。根拠資料のURLは、市町村データの
   forest_source_urlに市町村ごとに記録しています。
   - 紗那村（北海道）→ 釧路根室（012）
   - 滝沢市（岩手県）→ 北上川上流（021）
   - 大網白里市（千葉県）→ 千葉北部（046）
   - 新島村（東京都）→ 伊豆諸島（049）
   - 野々市市・穴水町・能登町（石川県）→ 加賀（058）・能登（057）
   - 海津市（岐阜県）→ 揖斐川（072）
   - あま市・長久手市（愛知県）→ 尾張西三河（078）
   - 丹波篠山市（兵庫県）→ 加古川（089）
   - 香美市（高知県）→ 高知（126）
   - 那珂川市（福岡県）→ 福岡（129）
2. 未割当は20件から7件になりました。残る7件は、都道府県レベルの
   所属未定地（千葉県、東京都、愛知県、和歌山県、福岡県、鹿児島県、
   沖縄県）で、市町村単位で区域が定義される制度上、公式資料では
   特定できないため、未割当のままにしています。
3. 残る閉じた穴は7件から4件になりました（飛び地のみ）。
4. 形状は、市町村の形は一切変えず、割り当てた市町村の形を計画区・
   流域に合成しただけです。属性が変わったのは13市町村の所属関係の
   項目だけです。

留保（2件）
- 紗那村： 全国森林計画の包括区域表（郡単位）では沙那郡が釧路根室に
  含まれ、他の北方領土の村も従来から同計画区です。一方、北海道の
  地域森林計画の構成リストには北方領土の町村の記載がありません。
- 野々市市と川北町： 林野庁の定義では、両市町とも加賀（058）の区域
  （6市1町）に含まれ、九頭竜川広域流域（22）に属します。一方、
  石川県の地域森林計画（加賀）の対象市町は5市（金沢市、小松市、
  加賀市、白山市、能美市）で、両市町は対象ではありません。当データ
  では区域の定義に従い、両市町とも加賀に割り当てています。
  説明図はリポジトリの docs/membership-v08/ にあります。

飛び地（4件）
- 渡良瀬川（040）の内側にある鬼怒川（039）の土地 約64,278m2
- 利根下流（043）の内側にある埼玉（045）の土地 約16,711m2
- 多摩（048）の内側にある神奈川（050）の土地 約486m2
- 神奈川（050）の内側にある多摩（048）の土地 約5,365m2

検証はv0.7との全数つき合わせで、件数・形状・属性の差分が割り当てた
13市町村とその合成先だけに限られることを確認しています。内容は
validation_v08.jsonと別添review_manifest.jsonを確認してください。
工程の詳細はBUILD_NOTES.mdに記録しています。

計画区・流域版ZIPには158計画区、44広域流域、未割当7地物、残る閉じた
穴の一覧（4件）を収録します。市町村版ZIPは1911地物の派生市町村データです。
残る穴や近接は実在の水域等も含み、すべてを不具合とは扱いません。
計画区025米代川の海岸入口付近と流域43川内・肝属川の近接箇所は、島や海岸の
断片同士が近づいているもので、誤りではないと判断し、そのまま残しています。

GEOS妥当性や近接探索は、ArcGIS ProのEsri方式Check Geometryの代替ではなく、Esri合格を意味しません。
米代川025の切れ込みの局所修正は自動採用していません。
出典と利用条件はリポジトリDATA_LICENSE.mdを参照してください。
"""
BUILD_NOTES = """# v0.8 の作り方（工程記録）

v0.8 は、検証済みの v0.7 候補（= v0.7 公開物と同一）を起点に、未割当だった
13市町村の所属だけを外科的に反映した版です。再構築はしていません。

## 工程

1. 照合： 未割当の市町村全域13件について、県の地域森林計画・全国森林計画・
   林野庁の計画書等の公式資料で、構成市町村への明記を確認した（全件明記あり）。
   長久手市については、林野庁からも「県の計画を確認して、含まれている流域に
   加える」旨の回答があった。根拠資料の URL は市町村データの
   forest_source_url に市町村ごとに記録している。
2. 属性の変更： 13市町村の所属項目（計画区コード・名称、流域コード・名称、
   forest_status、forest_source_date、forest_source_url）だけを変更した。
   forest_status は「所属計画区を県資料で照合・境界未確認」とした。
   計画区側の source_features は、取り込んだ市町村の数だけ加算した。
3. 形状の合成： 割り当てた市町村の形状（変更なし）を、所属先の計画区と
   流域に合成した。未割当レイヤーは残る7件（所属未定地）だけになり、
   残穴レイヤーは飛び地4件だけになった（未割当由来の3件は計画区に
   被覆されたため）。
4. 対応表 CSV（tables/municipality_forest_districts.csv）の13行も、
   データに合わせて更新した。

## 留保

- 紗那村（01699）： 全国森林計画の包括区域表では沙那郡が釧路根室（012）に
  含まれ、他の北方領土5村は従来から 012 に割り当て済みで整合する。ただし
  北海道の地域森林計画の構成リストには北方領土の町村の記載がない。
  この割当は 2026-11-17 にデータ作成者の確認・承認済み。
- 野々市市（17212）と川北町（17324）： 林野庁の定義では加賀（058）の区域
  （包括行政区域 6市1町）に含まれ、九頭竜川広域流域（22）に属する。一方、
  石川県の地域森林計画（加賀）の対象市町は5市のみで、両市町は対象ではない
  （県の資料では両市町の名は一切出てこない）。当データでは区域の定義に従い
  両市町とも 058 に割り当てている。説明図はリポジトリの docs/membership-v08/
  に収録している（全体図と拡大図）。

## 検証結果（v0.7 との全数つき合わせ）

- 件数： 計画区158・流域44・未割当7・残穴4・市町村1,911。無効形状ゼロ、
  全レイヤーの全頂点が小数9桁に一致。
- 形状の差分： 計画区11件（012・021・046・049・057・058・072・078・089・
  126・129）と流域8件（04・10・17・22・23・29・36・39）だけ。その他は
  v0.7 と一致。市町村の形状は全行 v0.7 と一致。
- 属性の差分： 13行×7項目のみ（所属未定地7行は未割当のまま）。
- 計画区同士の重なり： v0.7 と同じ1組（中越052×千曲川下流064、
  約0.33cm2）のみ。計画区の面積増加は各市町村の面積と全件一致。

工程スクリプトはリポジトリの scripts/build-v08/ に収録しています。
"""
open(f'{R}/forest/README.txt', 'w', encoding='utf-8').write(README)
open(f'{R}/muni/README.txt', 'w', encoding='utf-8').write(README)
open(f'{R}/forest/BUILD_NOTES.md', 'w', encoding='utf-8').write(BUILD_NOTES)

val = {'verify': json.load(open(f'{C}/verify_results.json')),
       'build_log': json.load(open(f'{C}/build_log.json'))}
json.dump(val, open(f'{R}/forest/validation_v08.json', 'w'), ensure_ascii=False, indent=1)

shutil.copy(f'{C}/forest_planning_zones_2026_provisional_labeled.gpkg', f'{R}/forest/')
shutil.copy(f'{C}/municipality_forest_zones_2026_candidate.gpkg', f'{R}/muni/')
shutil.copy(f'{R7}/forest/plane_rectangular_zones_2026.gpkg', f'{R}/forest/')
for f in os.listdir(f'{R7}/forest/styles'):
    shutil.copy(f'{R7}/forest/styles/{f}', f'{R}/forest/styles/')
for f in os.listdir(f'{R7}/forest/tables'):
    shutil.copy(f'{R7}/forest/tables/{f}', f'{R}/forest/tables/')

# patch the 13 rows of the correspondence CSV to match the v0.8 data
ASSIGN = {
 '01699': ('012', '釧路根室', '04', '十勝・釧路川'), '03216': ('021', '北上川上流', '10', '北上川'),
 '12239': ('046', '千葉北部', '17', '利根川'), '13363': ('049', '伊豆諸島', '17', '利根川'),
 '17212': ('058', '加賀', '22', '九頭竜川'), '17461': ('057', '能登', '22', '九頭竜川'),
 '17463': ('057', '能登', '22', '九頭竜川'), '21221': ('072', '揖斐川', '23', '木曽川'),
 '23237': ('078', '尾張西三河', '23', '木曽川'), '23238': ('078', '尾張西三河', '23', '木曽川'),
 '28221': ('089', '加古川', '29', '加古川'), '39212': ('126', '高知', '36', '吉野・仁淀川'),
 '40231': ('129', '福岡', '39', '筑後川')}
mdf = gpd.read_file(f'{C}/municipality_forest_zones_2026_candidate.gpkg',
                    layer='plane_rectangular_municipalities_2026')
src = {r.N03_007: (r.forest_source_url, r.forest_status) for r in mdf.itertuples() if r.N03_007 in ASSIGN}
del mdf
p = f'{R}/forest/tables/municipality_forest_districts.csv'
rows = list(csv.DictReader(open(p, encoding='utf-8')))
fields = list(rows[0].keys())
n = 0
for r in rows:
    code = r['municipality_code']
    if code in ASSIGN:
        dc, dn, bc, bn = ASSIGN[code]
        r['district_code'] = dc; r['district_name'] = dn
        r['basin_code'] = bc; r['basin_name'] = bn
        r['verification_status'] = src[code][1]
        r['source_date'] = '2026-11-17'; r['source_url'] = src[code][0]
        r['match_method'] = '県資料等の構成市町村に明記'
        r['matched_rule'] = r['municipality']
        r['checked_date'] = '2026-11-17'
        n += 1
assert n == 13, n
buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=fields); w.writeheader(); w.writerows(rows)
open(p, 'w', encoding='utf-8', newline='').write(buf.getvalue())
print('tables patched: 13 rows', flush=True)

def ghash(df): return hashlib.sha256(b''.join(shapely.to_wkb(df.geometry.values))).hexdigest()
def ahash(df): return hashlib.sha256(df.drop(columns='geometry').astype(str).to_csv(index=False).encode()).hexdigest()
def fsha(pth):
    h = hashlib.sha256()
    with open(pth, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b''): h.update(chunk)
    return h.hexdigest()
agg = {}
for layer in ['forest_plan_districts_provisional', 'forest_wide_basins_provisional',
              'forest_unassigned_review', 'gap_residual_review']:
    df = gpd.read_file(f'{R}/forest/forest_planning_zones_2026_provisional_labeled.gpkg', layer=layer)
    agg[layer] = {'features': len(df), 'geometry_sha256': ghash(df), 'attributes_sha256': ahash(df),
                  'invalid': int((~shapely.is_valid(df.geometry.values)).sum())}
    print('fp', layer, agg[layer]['features'], flush=True); del df
mdf = gpd.read_file(f'{R}/muni/municipality_forest_zones_2026_candidate.gpkg', layer='plane_rectangular_municipalities_2026')
magg = {'features': len(mdf), 'geometry_sha256': ghash(mdf), 'attributes_sha256': ahash(mdf),
        'invalid': int((~shapely.is_valid(mdf.geometry.values)).sum())}
del mdf
print('fp municipalities', magg['features'], flush=True)

def zipdir(srcdir, zippath):
    with zipfile.ZipFile(zippath, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(srcdir):
            for f in sorted(files):
                pth = os.path.join(root, f)
                z.write(pth, os.path.relpath(pth, srcdir))
zipdir(f'{R}/forest', f'{R}/forest_planning_zones_2026_v08.zip')
zipdir(f'{R}/muni', f'{R}/municipality_forest_zones_2026_v08.zip')
files_meta = []
for zn in ['forest_planning_zones_2026_v08.zip', 'municipality_forest_zones_2026_v08.zip']:
    pth = f'{R}/{zn}'
    files_meta.append({'name': zn, 'bytes': os.path.getsize(pth), 'sha256': fsha(pth)})
    print('zip', zn, files_meta[-1]['bytes'], flush=True)
open(f'{R}/SHA256SUMS.txt', 'w').write(''.join(f"{m['sha256']}  {m['name']}\n" for m in files_meta))

manifest = {
 'status': 'provisional; official membership and boundaries not certified',
 'version': 'review-v0.8-20261117',
 'base_release': 'review-v0.7-20261117',
 'build_mode': 'surgical membership assignment on top of the verified v0.7 candidate (= the published v0.7 GPKGs): 13 previously unassigned municipalities assigned from explicit listings in prefectural regional forest plans and other official documents; their unchanged geometries unioned into the receiving districts and basins; attribute edits limited to 13 municipality rows (7 fields) plus source_features increments on receiving districts; build scripts in scripts/build-v08/',
 'changes_from_v07': {
  'assigned_municipalities': {k: {'district_code': v[0], 'district_name': v[1], 'basin_code': v[2], 'basin_name': v[3]} for k, v in ASSIGN.items()},
  'unassigned_features': '20 -> 7 (only prefecture-level areas with no municipality remain)',
  'residual_holes': '7 -> 4 (enclaves only)',
  'geometry_changed_districts': ['012', '021', '046', '049', '057', '058', '072', '078', '089', '126', '129'],
  'geometry_changed_basins': ['04', '10', '17', '22', '23', '29', '36', '39'],
  'municipality_geometries_changed': 0,
  'district_overlap_total_m2_epsg6933': 3.273749889380357e-05,
  'reservations': ['01699 Shana: listed at county level in the national plan; not listed in Hokkaido regional plan municipality lists',
                   '17212 Nonoichi and 17324 Kawakita: inside district 058 area and basin 22 per the Forestry Agency definition, but not target municipalities of the Ishikawa prefectural regional forest plan (5 cities)']},
 'candidate_gpkg_file_sha256': fsha(f'{R}/forest/forest_planning_zones_2026_provisional_labeled.gpkg'),
 'aggregates': agg,
 'municipality': {'gpkg_file_sha256': fsha(f'{R}/muni/municipality_forest_zones_2026_candidate.gpkg'),
                  'layer': magg},
 'verification': 'all checks passed against v0.7 (counts, validity, 9-digit grid; geometry differences limited to the 11 districts and 8 basins receiving assignments; municipality geometries identical; attribute differences limited to the 13 assigned rows)',
 'qgis_gui_verified': False,
 'review_files': files_meta}
json.dump(manifest, open(f'{R}/review_manifest.json', 'w'), ensure_ascii=False, indent=1)
print('PACKAGE DONE', round(time.time() - t0, 1), 's')
