# Package the verified v0.7 candidate into release staging (mirrors the v0.5 layout).
import geopandas as gpd, numpy as np, shapely, json, hashlib, os, shutil, zipfile, time
B = '/home/hatch/workspace/forest-planning-zones'
C = f'{B}/v07-candidate'; R = f'{B}/v07-release'; R5 = f'{B}/v05-release'
t0 = time.time()
for d in [f'{R}/forest/styles', f'{R}/forest/tables', f'{R}/muni']:
    os.makedirs(d, exist_ok=True)

README = """森林計画区・広域流域 確認用データ v0.7

確認用データです。公式境界・所属は未確定で、final_usable=falseです。
v0.7は、v0.5の完成品を手直ししたものではなく、源泉から作り直した版です。

作り方
- 元データ（国土数値情報 行政区域データ 2026年版）は、形式の中で小数9桁の
  座標とフル精度の座標が混在していました。まず源泉の全フィーチャ
  （125,130件）を小数9桁のグリッドに揃えてから、市町村・計画区・流域の
  全レイヤーを再構築しました。
- そのため、全レイヤーの全頂点が小数9桁に一致しています。後付けの丸め
  ではなく、再構築の時点で計算の尾つき頂点は生じていません。
- 計画区同士の重なりは、0.33cm2が1組（中越052×千曲川下流064）だけです。

v0.5からの変更点
1. 全レイヤーを正規化した源泉から再構築しました。所属・属性はv0.5から
   変更していません。市町村版も今回は再構築しています（v0.5の市町村版
   本体はv0.4のままでした）。
2. v0.5の処置は引き継いでいます。空き地9件は埋めた状態、飛び地4件と
   未割当20件は実在の状態として残しています。
3. 補修候補台帳（gap_repair_audit）は収録をやめました。断片の大半が
   9桁グリッド未満の微細な形状で、データ本体とは分けて作業記録として
   保管しています。

飛び地（4件）
- 渡良瀬川（040）の内側にある鬼怒川（039）の土地 約64,278m2
- 利根下流（043）の内側にある埼玉（045）の土地 約16,711m2
- 多摩（048）の内側にある神奈川（050）の土地 約486m2
- 神奈川（050）の内側にある多摩（048）の土地 約5,365m2

未割当（20件・合計約2,846km2）
- 所属未定地（7件）：千葉県、東京都、愛知県、和歌山県、福岡県、
  鹿児島県、沖縄県の所属未定地
- 都市部の市（3件）：野々市市、あま市、長久手市
- 再割り当てができていないと思われる市町村（10件）：紗那村、滝沢市、
  大網白里市、新島村、穴水町、能登町、海津市、丹波篠山市、香美市、那珂川市

検証はv0.5との全数つき合わせで、件数・属性・残る穴の状態が一致し、
面積差は計画区合計で-0.28m2でした。内容はvalidation_v07.jsonと
別添review_manifest.jsonを確認してください。工程の詳細はBUILD_NOTES.md
に記録しています。

計画区・流域版ZIPには158計画区、44広域流域、未割当20地物、残る閉じた
穴の一覧（7件）を収録します。市町村版ZIPは1911地物の派生市町村データです。
残る穴や近接は実在の水域等も含み、すべてを不具合とは扱いません。
計画区025米代川の海岸入口付近と流域43川内・肝属川の近接箇所は、島や海岸の
断片同士が近づいているもので、誤りではないと判断し、そのまま残しています。

GEOS妥当性や近接探索は、ArcGIS ProのEsri方式Check Geometryの代替ではなく、Esri合格を意味しません。
米代川025の切れ込みの局所修正は自動採用していません。
出典と利用条件はリポジトリDATA_LICENSE.mdを参照してください。
"""
BUILD_NOTES = """# v0.7 の作り方（工程記録）

v0.7 は v0.5 の完成品への手直しではなく、源泉からの再構築です。

## 工程

1. 源泉の正規化： 国土数値情報 行政区域データ 2026年版（GeoJSON、全47都道府県・125,130フィーチャ）の全頂点を小数9桁グリッドに揃えた（shapely set_precision、valid_output）。正規化後は混在ゼロ・無効形状ゼロ・空形状ゼロ。
2. 市町村の再構築： 正規化した断片を市町村コードで統合（1,905コード）。平面直角座標系の系をまたぐ5市町村（小笠原村・薩摩川内市・南さつま市・三島村・十島村）は系ごとに分割し、1,911行とした。属性は v0.5 からそのまま継承。
3. 計画区・流域の再構築： 市町村を所属コードで統合（計画区158、流域44）。共有境界が源泉で一致しているため、統合の過程で計算の尾つき頂点は生じなかった（全頂点が9桁に一致）。
4. v0.5 の処置の再適用： 「空き地9件を埋める」決定（2026-11-06）を、該当する内側リングの除去で再適用した（5計画区・9リング）。飛び地4件・未割当3件の穴は残した。流域は埋めた計画区から再集約。
5. 監査台帳（gap_repair_audit）はパッケージに含めていない。断片の大半が9桁グリッド未満の微細な形状で潰れてしまうため、形状の記録ではなく工程ログとして別に保管する。

## 検証結果（v0.5 との全数つき合わせ）

- 件数： 計画区158・流域44・未割当20・残穴7・市町村1,911 で一致。無効形状ゼロ、属性は全レイヤーで完全一致。
- 桁： 全レイヤーの全頂点が小数9桁に一致（尾つき頂点ゼロ）。
- 重なり： 計画区同士は 0.33 cm2 が1組（中越052×千曲川下流064）のみ。v0.5 は約4 cm2、完成品を丸めた方式（未公開の v0.6 候補）では約173 cm2 だった。
- 残穴16件の被覆状態： v0.5 と完全一致（埋めた9件は被覆、飛び地4件は所有側の計画区で被覆、未割当3件は非被覆のまま）。
- 面積差： 計画区合計 -0.28 m2（1計画区あたり最大 0.11 m2）、市町村版合計 +0.004 m2。形状の対称差は計画区合計 1.18 m2（最大は釧路根室 0.64 m2）。

工程スクリプトはリポジトリの scripts/build-v07/ に収録しています。
"""
for name, text in [('README.txt', README)]:
    open(f'{R}/forest/{name}', 'w', encoding='utf-8').write(text)
    open(f'{R}/muni/{name}', 'w', encoding='utf-8').write(text)
open(f'{R}/forest/BUILD_NOTES.md', 'w', encoding='utf-8').write(BUILD_NOTES)

# validation summary
val = {}
for s in ['attrs', 'districts', 'holes']:
    val[s] = json.load(open(f'{C}/verify_{s}.json'))
val['build_log'] = json.load(open(f'{C}/build_log.json'))
val['normalization'] = {k: json.load(open(f'{C}/normalization_log.json'))[k]
                        for k in ['total_features', 'total_changed_features', 'unique_municipality_codes']}
json.dump(val, open(f'{R}/forest/validation_v07.json', 'w'), ensure_ascii=False, indent=1)

# stage GPKGs and carried files
shutil.copy(f'{C}/forest_planning_zones_2026_provisional_labeled.gpkg', f'{R}/forest/')
shutil.copy(f'{C}/municipality_forest_zones_2026_candidate.gpkg', f'{R}/muni/')
shutil.copy(f'{R5}/forest/plane_rectangular_zones_2026.gpkg', f'{R}/forest/')
for f in os.listdir(f'{R5}/forest/styles'): shutil.copy(f'{R5}/forest/styles/{f}', f'{R}/forest/styles/')
for f in os.listdir(f'{R5}/forest/tables'): shutil.copy(f'{R5}/forest/tables/{f}', f'{R}/forest/tables/')
print('staged', flush=True)

# fingerprints
def ghash(df): return hashlib.sha256(b''.join(shapely.to_wkb(df.geometry.values))).hexdigest()
def ahash(df): return hashlib.sha256(df.drop(columns='geometry').astype(str).to_csv(index=False).encode()).hexdigest()
def fsha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
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

# ZIPs (same internal layout as v0.5)
def zipdir(srcdir, zippath):
    with zipfile.ZipFile(zippath, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(srcdir):
            for f in sorted(files):
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, srcdir))
zipdir(f'{R}/forest', f'{R}/forest_planning_zones_2026_v07.zip')
zipdir(f'{R}/muni', f'{R}/municipality_forest_zones_2026_v07.zip')
files_meta = []
for zn in ['forest_planning_zones_2026_v07.zip', 'municipality_forest_zones_2026_v07.zip']:
    p = f'{R}/{zn}'
    files_meta.append({'name': zn, 'bytes': os.path.getsize(p), 'sha256': fsha(p)})
    print('zip', zn, files_meta[-1]['bytes'], flush=True)
open(f'{R}/SHA256SUMS.txt', 'w').write(''.join(f"{m['sha256']}  {m['name']}\n" for m in files_meta))

manifest = {
 'status': 'provisional; official membership and boundaries not certified',
 'version': 'review-v0.7-20261117',
 'base_release': 'review-v0.5-20261109',
 'build_mode': 'rebuilt from the source: KSJ admin-boundary 2026 GeoJSON normalized to a 1e-9 degree grid first (all 125,130 features), then every layer re-dissolved; attributes carried verbatim from v0.5; the v0.5 hole decisions re-applied as inner-ring removal; build scripts in scripts/build-v07/',
 'changes_from_v05': {
  'rebuilt_from_normalized_source': True,
  'source_features_normalized': 125130,
  'offgrid_vertices_after_rebuild': 0,
  'district_overlap_total_m2_epsg6933': 3.273749889380357e-05,
  'district_overlap_pairs': [['052', '064', 3.3e-05]],
  'residual_holes_filled_empty_only': 9,
  'rings_filled': 9,
  'residual_holes_kept_enclave': 4,
  'residual_holes_kept_unassigned': 3,
  'district_area_total_delta_m2_epsg6933': -0.2790745496749878,
  'municipality_data_changed': 'geometry rebuilt from the normalized source; attributes unchanged',
  'gap_repair_audit_included': False},
 'candidate_gpkg_file_sha256': fsha(f'{R}/forest/forest_planning_zones_2026_provisional_labeled.gpkg'),
 'aggregates': agg,
 'municipality': {'gpkg_file_sha256': fsha(f'{R}/muni/municipality_forest_zones_2026_candidate.gpkg'),
                  'layer': magg},
 'verification': 'all checks passed against v0.5 (counts, validity, attributes identical, residual-hole coverage pattern identical, district overlaps 3.3e-05 m2 in one pair)',
 'qgis_gui_verified': False,
 'review_files': files_meta}
json.dump(manifest, open(f'{R}/review_manifest.json', 'w'), ensure_ascii=False, indent=1)
print('PACKAGE DONE', round(time.time() - t0, 1), 's')
