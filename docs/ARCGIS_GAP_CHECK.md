# ArcGIS実機での比較検査

`scripts/check_arcgis_gap_review.py`はArcGIS Pro付属のPythonで実行する補助スクリプトです。
このCodex環境にはArcPyがないため、実機動作は未確認です。構文とCLIの確認までを行っています。

## 出力

新しい出力フォルダーに新規File GDBを作り、指定したGPKGの対象レイヤをコピーして
Esri方式のCheck Geometryを実行します。Repair Geometryは実行しません。
対象は既定で計画区・流域・未割当と、21計画区試験の対照・候補です。補修台帳は対象から除きます。

- 原ファイルの前後SHA-256、地物数、ArcGIS版を保存します。
- 読み込み時とGDB出力後の空間参照・XY解像度・XY許容値を保存します。
- エラーの表と、エラー地物・025・流域43の出力座標をJSONへ保存します。
- 出力後の空間参照設定が異なる場合は、比較条件が揃っていないと記録します。
- 元のfidとGDBのOBJECTIDを同じ番号として扱いません。計画区・流域コードで照合します。

## 実行例

ArcGIS ProのPython Command Promptで、リポジトリのフォルダーから実行します。
`D:\test`は、実際に展開したファイルの場所へ置き換えます。

```bat
python scripts\check_arcgis_gap_review.py --source trial=D:\test\expanded_precision_trial.gpkg --source gap=D:\test\national_gap_guarded_20261017.gpkg --output D:\test\arcgis_check_run01
```

21計画区の未変更候補とClaudeの局所修正候補を比べる場合も、異なるラベルで同じコマンドへ指定します。
レイヤ名が既定と異なる場合は`--layer`で明示します。指定したレイヤがなければ停止します。
XY解像度と許容値は既定でArcGISの実値を記録します。再現試験で明示する場合は、
本流で記録した値・単位を`--xy-resolution`と`--xy-tolerance`へ指定してください。ここで値を推測しません。

正常終了でも描画・原典との境界一致を証明しません。スクリプトが成功した後も、
問題が報告された位置の描画と、本流の修正候補の差分を確認します。
実行が途中で失敗した場合は、出力フォルダーを検査完了の成果と扱わず、新しいフォルダーで再実行します。

## APIの根拠

- [Esri Check Geometry](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/data-management/check-geometry.html)
- [SpatialReference](https://doc.esri.com/en/arcgis-pro/latest/arcpy/classes/spatialreference.html)
- [ListFeatureClasses](https://doc.esri.com/en/arcgis-pro/latest/arcpy/functions/listfeatureclasses.html)

APIの記載を確認して準備したもので、ArcGIS実機での実行結果はまだありません。
