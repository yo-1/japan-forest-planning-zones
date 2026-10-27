# 森林計画区 v0.3：実機 GUI 確認チェックリスト

作成: Muse（検証・公開管理チャット）、2026-10-27
用途: PC 実機（Windows QGIS + qgis-dev-probe）での表示確認を最短手順で行うためのチェックリスト。手順の正本は PR #8 の devprobe-scenario.md、本リストはその実施用サマリです。
対象: 公開版 review-v0.3-20261015

## 1. 開く対象（VM 側で確定済み）

ZIP の中身は 2026-10-27 に VM で新規展開・ストリーム照合して確定しました。

forest_planning_zones_2026_review.zip（SHA-256: ebe92b11530bf89f72ff8d626de552835810d489296b2acbec1f212514b31a16）の中身は11ファイル:
- forest_planning_zones_2026_provisional_labeled.gpkg（371,232,768 バイト、SHA-256: ed4df025f6b078a7b1378adddee1eac86f277894d9dd755318963ac34acf2da7）
  - forest_plan_districts_provisional（158件）
  - forest_wide_basins_provisional（44件）
  - forest_unassigned_review（20件）
- plane_rectangular_zones_2026.gpkg（172,060,672 バイト、SHA-256: 7f8b35c97d4796cdcbb7a203e5c07c68cd6595597ee5e1f284f9b809587c00d3）
  - plane_rectangular_zones_2026（19件）
- README.txt、tables/（対応表 CSV 3点）、styles/（QML 5点）

municipality_forest_zones_2026_candidate.zip（SHA-256: 5b8f3301bc6da2616c8e55d82aef52cc3353bdcc1e57d0714de1a954fe4ed1d7）の中身は2ファイル:
- municipality_forest_zones_2026_candidate.gpkg（259,993,600 バイト、SHA-256: 5af6f5981b61e34f1c9e8487dcf78ad44c3013b40582ab339da0439210e28c46）
  - plane_rectangular_municipalities_2026（1,911件）
- README.txt

訂正: 座標系区域の GPKG は市町村候補 ZIP ではなく review ZIP の中です（以前の案内と逆でした）。PC 側 Codex の展開結果とも一致しています。

## 2. 実機チェックリスト（合否基準つき）

前提: QGIS 3.44 系 + qgis-dev-probe（interactive モード）。レシピ load_forest_zones_review.py を recipe_dir に配置済みであること。レイヤーの並びは配布 README.txt の指定どおり、上から「座標系区域 → 未割当 → 計画区 → 広域流域」とします。

| # | 手順 | 合否基準 |
|---|---|---|
| 1 | `ping` / `get_info` | 応答あり。QGIS と Dev Probe のバージョンを記録できる |
| 2 | `run_recipe load_forest_zones_review`（3つの GPKG のパスを引数に） | 戻り値の problems が空。件数が 158・44・20・1,911・19、CRS が全て EPSG:6668 |
| 3 | 全国表示の `screenshot`（計画区を表示、流域は非表示、座標系区域は最上位で表示） | 日本全体が描かれる。計画区の色分けと「番号_名称」ラベル、座標系区域の赤い ZONE_ROMAN ラベルが文字化けなく読める。表示崩れがない |
| 4 | 流域表示の `screenshot`（計画区を非表示、流域を表示に切替） | 流域の色分けとラベルが読める |
| 5 | 計画区025（米代川）の拡大 `screenshot`（範囲 139.5417, 39.6456 〜 141.1454, 40.6611） | 境界とラベルが拡大でも崩れない |
| 6 | `inspect_layer`（市町村候補、sample 3） | 属性サンプルの日本語が文字化けなく出る |
| 7 | `read_log`（level: warning） | 手順2〜6の間に新しい warning 以上が出ていない |
| 8 | 後始末（レイヤーを外す、プロジェクトは保存しない） | データファイルが変更されていない |

execute_code が許可されない場合は、手順3〜5の表示範囲の移動を利用者が手で行い、screenshot だけを実施する形に切り替えます（合否基準は同じ）。

## 3. 確認範囲の分離（記録用）

ヘッドレス検証（検証B、QGIS 3.44.14）で確認済み。再確認は不要です:
- 全5レイヤーの読み込み、件数、コードの桁・先頭0、日本語属性の値、CRS（EPSG:6668）
- Check validity（GEOS 方式、リング自己交差を無視しない）: 全件有効、無効0・エラー0
- manifest の geometry_sha256 との全件一致
- 階層整合（コード集合、計画区→流域対応、source_features、代表点の包含）
- ZIP と GPKG の SHA-256（Release 記録・シナリオ記載値との一致）

実機でしか確認できない範囲（本チェックリストの対象）:
- GUI キャンバス上での実際の描画（既定スタイル・ラベルの描画結果、フォントでの日本語表示）
- ズーム・パンに伴う再描画の様子と、レイヤー表示切替の動作
- 読み込み時に GUI が出す警告ダイアログやログの有無
- 実機での読み込み・描画の体感速度（参考記録として）

対象外（本確認では判定しない）:
- 公式な境界・所属の意味の確定（権威ある追加資料が必要）
- ArcGIS での利用可否（完了条件は QGIS で正常に利用できること）
