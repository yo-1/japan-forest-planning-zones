# v0.4候補の取得・パッケージ照合（2026-10-28）

CodexがCI成果物を取得して照合した記録です。全国生成・QGIS検査・公開はMuseが担当しており、ここでは再生成していません。

## 入力と結果
- CI run: https://github.com/yo-1/japan-forest-planning-zones/actions/runs/40543634341
- Artifact: https://github.com/yo-1/japan-forest-planning-zones/actions/runs/40543634341/artifacts/12753630489
- Run head: `2e88052c0495a96bd88dc73d3d99da3b1633da50`。実際のcheckoutはPRのテスト用merge commit `0199e720d53033898e1126cd5507cd63ae19be52`。
- Artifact ZIP: 531,784,387 bytes、SHA-256 `57097efa4e8eba9bb4d6815e29cfc0792b55bf7adf969ed564cc77fc0c843ed4`。
- Python/Shapely 2.1.2 / GEOS 3.13.1による照合成功。QGISでの再検査・GUI表示確認ではありません。

取得したArtifactのSHA-256、配布ZIP2点のCRC・サイズ・SHA-256、GPKG3点のSQLite整合性、全5レイヤーの全地物のGEOS妥当性・空形状・EPSG・SQL図形型・manifest形状ハッシュを実測しました。件数は158/44/20/1,911/19、無効・空形状は全レイヤー0です。入力GPKGは検査前後のファイルSHA-256が一致しました。

未割当・市町村・座標系区域の**形状ハッシュ**はv0.3と一致しました。ただし、再生成によるメタデータ等の違いがあり、GPKGファイル全体のSHA-256はv0.3の値と異なります。実機側は今回取得した候補のファイルSHAを使用してください。ファイル全体の違いの原因となった全バイトの分類や、v0.3との全属性比較は本検査では実施していません。

`ci_gap_validation_readback`は、同梱されたCIの独立検査結果の読取確認です。今回Codexが空間差分演算を再実行した結果ではありません。CI結果はpassed=true、errors/invalidなし、44流域一致、未割当保持、増加約0.007064381383㎡、減少約4.13715544e-8㎡でした。採用1,589、分断保留50、残存閉鎖穴16を同梱manifestから確認しました。保留50は全要確認候補の総数ではありません。

## 証跡と再実行
- `independent_package_check.json`: Codex実測値とCI結果の読取確認。
- `review_manifest.json`・`gap_validation.json`: Artifact同梱原本のコピー。
- `verify_artifact.py`: 読み取り専用の検査スクリプト。

Artifact ZIPを本フォルダー内の `v04-evidence-20261028/artifact.zip` に保存し、Shapely 2.1.2の環境で `python verify_artifact.py` を実行します。展開先と結果JSONは同じ作業サブフォルダーに作成します。

## 公開前に残ること
候補のQGIS全国検査・GUI確認、および公開ワークフローが再生成する公開GPKGと検査済み候補の図形・属性の照合は別工程です。v0.3のGUI合格を今回候補の合格として転記しません。公式な境界・所属の確定や、当初の指摘画像の位置との一致を確認した記録ではありません。
