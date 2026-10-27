# QGIS 全国検証の記録（確認用 v0.4 候補・全国補修適用）

2026-10-28、Muse が実施した検証の記録です。対象は、PR #11 の build-check CI（run 40543634341）が生成した全国補修適用の確認用候補で、公開前の確認です。

## 対象の識別

- forest_planning_zones_2026_gap_trial.zip: 358,919,264 バイト、SHA-256 0cdb715bbcfa9104ff5ac36834295faee2acb9b7b0192cf08646f9900e72b8cc
- municipality_forest_zones_2026_gap_trial.zip: 173,158,617 バイト、SHA-256 6330c8e5bb739cf3321e44420241891aa262d828292d08a8b6b20d8024f8f559
- 補修条件: 幅 0.001m（--gap-width-m 0.001）。ビルド内蔵の独立検査 gap_validation は合格し、補修台帳（採用 1,589 件、分断のため保留 50 件、残る閉じた穴 16 件）は 2026-10-17 の試験記録と完全一致しました（results/review_manifest.json、results/gap_validation.json）。

## 環境

- QGIS 3.44.14（読込検査と Check validity）、GDAL 3.13.3、GEOS 3.14.1
- 階層整合は geopandas 1.2.0 で実施しました
- 実施コードは scripts/ にあります（検証Bの docs/qgis-verification-20261027/ のコードを対象パスだけ差し替えたもの）

## 結果

- 読込検査（results/layer_inspection.json）: 全5レイヤーが正常に読めました。件数は manifest と一致（計画区 158、広域流域 44、未割当 20、市町村候補 1,911、座標系区域 19）。CRS はすべて EPSG:6668、NULL・空形状は 0 件です。集約レイヤーの status は全件「確認用・区域未確定」、final_usable は全件 false です。検査スクリプトは JSON 書出し完了後の終了処理で異常終了しましたが、JSON を読み直して完全性を確認済みで、結果への影響はありません。
- Check validity（results/validity_summary.json）: native:checkvalidity、METHOD=2（GEOS）、リング自己交差を無視しない設定で、全5レイヤーとも有効が全件、無効 0 件・エラー 0 件でした。
- geometry_sha256 の突合（results/geometry_hash_reconciliation.json）: 全5レイヤーが manifest と一致しました。計画区 02739435dff682a9b8a77085e6e3e89b40103051243ee73467a590d9950e7c67 と広域流域 a4a4acf922e4da1daea71b26a4289ad616c412a0b79c0f8d4d33e7aef8ad1db1 は v0.3 から変化し（補修の適用先）、未割当・市町村候補・座標系区域は v0.3 と同一でした。
- 階層整合（results/hierarchy_check.json）: H1–H6 のすべてを通過しました。コード集合の一致（158 / 44）、計画区から流域への対応の不一致 0 件、未割当コード集合の一致、source_features の全件一致（合計 1,891）、代表点の包含（割当済み 1,891 件すべてが自計画区・自流域内、未割当 20 件はどの計画区内にもなし）。

## 留保

- 判定は QGIS / GEOS 基準であり、Esri 合格とは扱いません。
- 補修は細い隙間への対処で、公式の境界・所属を確定するものではありません。final_usable=false と「確認用・区域未確定」の位置づけは変わりません。
- 計画区 025 の入口と流域 43 の近接は残ります（補修の対象外で、不具合とは判定していません）。
- 実機（Windows QGIS）での表示確認は、この後に Dev Probe で別途実施します。
