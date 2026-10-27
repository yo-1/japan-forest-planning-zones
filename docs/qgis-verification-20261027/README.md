# QGIS全国検証（検証B）の記録（2026-10-27）

公開版 review-v0.3-20261015 の本体そのものを、QGIS 3.44 で読み込み、件数・属性・座標系と形状の有効性を確認した記録です。完了条件は「QGISで正常に利用できること」で、ArcGIS の検査合格は条件に入れていません。この記録は検証結果であり、全国版の採用や公開の判断ではありません。

## 実施環境

- QGIS 3.44.14-Solothurn、GDAL/OGR 3.13.3、GEOS 3.14.1、PROJ 9.9.0、Python 3.12.15
- Linux のヘッドレス環境です。GUI の実画面は確認していません。描画の確認はレンダリング画像の出力までです
- 階層整合のうち属性の照合だけ、相互確認として QGIS 4.2.3 / GEOS 3.14.1 の環境（geopandas 1.2.0、shapely 2.2.0）でも実行しました

## 対象入力

検証Aで確定した公開 v0.3 の展開済み GeoPackage です。ZIP の SHA-256 は検証Aで同梱記録と一致を確認済みです。

| ファイル | バイト数 | SHA-256 |
|---|---:|---|
| forest_planning_zones_2026_provisional_labeled.gpkg | 371,232,768 | ed4df025f6b078a7b1378adddee1eac86f277894d9dd755318963ac34acf2da7 |
| municipality_forest_zones_2026_candidate.gpkg | 259,993,600 | 5af6f5981b61e34f1c9e8487dcf78ad44c3013b40582ab339da0439210e28c46 |
| plane_rectangular_zones_2026.gpkg | 172,060,672 | 7f8b35c97d4796cdcbb7a203e5c07c68cd6595597ee5e1f284f9b809587c00d3 |

## 結果1: 読み込み・件数・属性・座標系（layer_inspection.json）

全5レイヤーが QGIS で正常に読み込めました。件数はすべて manifest の記録と一致し、空の形状と NULL の形状は0件でした。全レイヤーの CRS は EPSG:6668（JGD2024。JGD2011 から名称が変わったもので、定義と座標値に変更はありません）です。

| レイヤー | 件数 | コード | 名前属性 |
|---|---:|---|---|
| forest_plan_districts_provisional | 158 | district_code は3桁の文字列で全件一致、うち先頭0が99件。basin_code は2桁、44種類 | district_name・basin_name は全件日本語 |
| forest_wide_basins_provisional | 44 | basin_code は2桁で44件すべて異なる | basin_name は全件日本語 |
| forest_unassigned_review | 20 | municipality_code は5桁の文字列で全件一致 | prefecture・municipality は全件日本語 |
| plane_rectangular_municipalities_2026 | 1,911 | N03_007 は5桁の文字列。forest_district_code・wide_basin_code は割当済み1,891件でそれぞれ3桁・2桁の文字列に全件一致し、未割当20件は NULL | 割当済みの名前は全件日本語。N03_005 は区のある171件だけ値があり全件日本語 |
| plane_rectangular_zones_2026 | 19 | ZONE は1〜19 | ZONE_ROMAN はローマ数字 |

- 集約レイヤーの status は全件「確認用・区域未確定」、final_usable は全件 false で、公開仕様どおりです
- 集約レイヤーの source_features の合計は計画区・流域とも1,891で、割当済みの市町村候補の行数と一致します
- N03_007 の重複は5コード6行分あります（小笠原村13421が3行、三島村46303・十島村46304・薩摩川内市46215・南さつま市46220が各2行）。座標系の区域で分かれた N03 原典の行構成によるもので、QGIS_REVIEW.md で拡大対象として挙げられている市町村と一致します
- GeoPackage に保存された既定スタイル（分類シンボル）は QGIS の読み込み時に適用されることを確認しました

## 結果2: Check validity（validity_summary.json、logs/）

QGIS の Check validity（native:checkvalidity）を、方式は GEOS（METHOD=2）、「リング自己交差を無視」はオフ（IGNORE_RING_SELF_INTERSECTION=0）で、全5レイヤーに実行しました。

| レイヤー | 有効 | 無効 | エラー |
|---|---:|---:|---:|
| forest_plan_districts_provisional | 158 | 0 | 0 |
| forest_wide_basins_provisional | 44 | 0 | 0 |
| forest_unassigned_review | 20 | 0 | 0 |
| plane_rectangular_municipalities_2026 | 1,911 | 0 | 0 |
| plane_rectangular_zones_2026 | 19 | 0 | 0 |

有効・無効・エラーの出力 GeoPackage も作成し、件数の一致を別途確認しました。出力 GeoPackage は合計約763 MB あり入力データの複製になるため、このリポジトリには入れていません（Muse の VM の作業領域に保持しています）。

## 結果3: manifest の形状ハッシュとの突き合わせ（geometry_hash_reconciliation.json）

geometry_sha256 は、生成コード（scripts/build_review_release.py の inspect_gpkg）の定義どおり、表に保存された形状 BLOB を fid の順に連結した SHA-256 です。同じ方法で実測し、全5レイヤーが manifest の記録と一致しました。

| レイヤー | geometry_sha256（manifest・実測とも同じ） |
|---|---|
| forest_plan_districts_provisional | 67d44f743777d72b1ed9acabc195c1ad184983bee9a2ec870c663b2c1a8cbca0 |
| forest_wide_basins_provisional | 67388e07d9e486f36634edf700d00137d4b41e0a6571496e8958cad69612e454 |
| forest_unassigned_review | a3193c944bd3f44f4ad7621a95c1865d930f26da4a379ef00640d2b1e6bf9d6f |
| plane_rectangular_municipalities_2026 | 7e4c91ec0ffc7a3e69e7b77248d9a65b73080a3353f3a663a84cdeb13144e1aa |
| plane_rectangular_zones_2026 | 23fa2d62f395ce192857e2a69444e639e24d4f89c30f4da17d0976b0acb3a02b |

## 結果4: 階層整合（hierarchy_check.json）

形状の再集約の監査は geometry-audit-20261013 に v0.1/v0.2 の全件結果があり、森林3レイヤーは v0.2 と v0.3 で全列ハッシュが一致するため（検証A）、その結果を v0.3 にも使います。ここでは v0.3 本体でまだ確認していなかった属性の階層と、代表点による包含の点検を追加しました。

- 市町村候補の計画区コードの集合（158）と計画区レイヤー、流域コードの集合（44）と流域レイヤーが一致しました
- 計画区ごとに流域コード・流域名は1つだけで、候補側と計画区レイヤー側の対応に不一致はありませんでした
- コードが NULL の候補は両コードとも NULL の20行だけで、その市町村コードの集合は未割当レイヤーと一致しました
- source_features は計画区・流域とも全件、候補の行数と一致しました
- 割当済み候補1,891件の代表点はすべて、その計画区と流域の形状に含まれました。未割当20件の代表点は、どの計画区の形状にも含まれませんでした。これは代表点だけの点検で、ポリゴン全体の重なり・隙間の監査は geometry-audit-20261013 の結果を使います

## 描画図（figures/）

ヘッドレスのレンダリング画像です。GUI の実画面確認ではありません。

- fig_overview_districts.png: 全国の計画区（緑）と流域の境界（青）
- fig_overview_unassigned.png: 全国の計画区と未割当（赤）
- fig_zoom_district025.png: 計画区025（米代川、秋田市周辺）の拡大。市町村界（灰色）と流域の境界（青）を重ねています

全国図は、原型の形状のままだとこの VM のメモリ（7.7 GB）ではレンダリングが完了しなかったため、許容差0.0015度で簡略化したコピーから描きました（行数は158・44・20で変わりません）。拡大図は原型の形状を対象範囲で切り取って描いています。簡略化したコピーは図の作成専用で、検証の数値はすべて原型の形状で測っています。

## 再実行の方法

scripts/ に実施したコードをそのまま置いています。

1. inspect_layers.py: QGIS 3.44 の環境で実行し、読み込み・件数・属性・CRS を記録します
2. run_checkvalidity.sh: qgis_process で Check validity を実行し、ログと出力先を残します
3. reconcile_geometry_hash.py: 形状ハッシュを実測して manifest と比べます
4. hierarchy_check.py: 属性の階層と代表点の包含を点検します
5. prep_figure_data.py と render_figures.py: 図の入力を用意して描画します

実施時の注意として、inspect_layers.py は結果 JSON を書き終えたあとの終了処理で異常終了しました（終了コード134）。JSON は書き込み済みで、読み直して全5レイヤーの記録がそろっていることを確認しています。検査結果そのものへの影響はありません。

## 実機GUI確認（qgis-dev-probe）

GUI の実画面での表示確認は、qgis-dev-probe で実機の QGIS を操作して行う手順を devprobe-scenario.md に用意しました。同期で済む読み込みと件数・CRS の照合は recipes/load_forest_zones_review.py にしてあります。この確認は表示と読み込みの様子の確認で、データ内容の合否はこの検証Bの結果を使います。

## 結論と未確認事項

- QGIS 3.44 では、v0.3 の全レイヤーが正常に読み込め、件数・コード・日本語属性・CRS は仕様どおりで、GEOS 方式の有効性検査は全件合格でした。加工によって新たに生じた形状の問題は、今回の検証範囲では確認されませんでした
- そのため、依頼の条件にある候補比較（検証C）は実施しません。精度を変える全国処理を進める根拠が、QGIS を基準とする限り見つからなかったためです
- この結果は QGIS/GEOS の検査結果です。ArcGIS の Esri 検査の合格として扱いません
- 未確認は次のとおりです。GUI の実画面での表示確認、公式な境界・所属の意味の確定、生 GDB 本体への新規の直接照合（保存済み結果の再利用で進めました）
