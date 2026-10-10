森林計画区・広域流域 確認用データ v0.1（2026-10-05）

公式の境界・所属が確定したデータではありません。確認用の暫定候補データです。
自然河川流域の解析結果ではなく、森林計画の行政上の区画の候補図です。

forest_planning_zones_2026_review.zip
・forest_planning_zones_2026_provisional_labeled.gpkg：158森林計画区、44広域流域、未割当20地物
・plane_rectangular_zones_2026.gpkg：19座標系。japan-plane-rectangular-cs-zones v2026.2 の原形状（geometry blobの順序付きSHA-256が一致したもの）
・tables：1,905コードの市区町村対応表、158計画区表、44流域表
・styles：QGIS用の色分け・番号_名称ラベル、座標系の表示スタイル

municipality_forest_zones_2026_candidate.zip
・municipality_forest_zones_2026_candidate.gpkg：1,911地物、1,905コード。元市町村の座標系分割を保持

QGISでの順序（上から）
1. plane_rectangular_zones_2026：境界・赤いZONE_ROMANラベル。内蔵layerスタイルを初期値とする
2. forest_unassigned_review：未割当20地物を赤表示
3. forest_plan_districts_provisional：計画区の色分け・番号_名称ラベル
4. forest_wide_basins_provisional：広域流域の色分け・番号_名称ラベル
計画区図では3を表示して4を非表示、広域流域図では4を表示して3を非表示にします。
座標系境界は両方の図で最上位に置きます。以前読み込んだレイヤは再追加するかstylesのQMLを読み込んでください。

CSVコードは文字列として読み込んでください。自治体5桁、全国候補計画区3桁、候補広域流域2桁です。
森林計画対象森林のコードを桁揃えして全国候補コードに直接結合しないでください。
市町村全域・一部指定、島しょ部、現行所属、公式コードの適用範囲は未確定です。
機械検査は形状妥当性と内部整合の検査です。QGIS実画面での表示確認・公式境界との一致確認ではありません。

利用条件・出典：リポジトリのDATA_LICENSE.md、data/forest/README.mdを参照。
