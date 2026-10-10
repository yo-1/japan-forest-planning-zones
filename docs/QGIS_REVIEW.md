# 色・ラベル・座標系区域の重ね合わせ（確認用v0.1、2026-10-05）

[Release](https://github.com/yo-1/japan-forest-planning-zones/releases)の確認用ZIPを展開してください。まだReleaseが表示されない場合は[公開処理](https://github.com/yo-1/japan-forest-planning-zones/actions/workflows/publish-review.yml)の完了状況を確認します。

| 上からの順序 | レイヤー | 表示設定 |
| --- | --- | --- |
| 1 | `plane_rectangular_zones_2026` | 19系区域（v2026.2）。透明な面・系別の境界・赤いローマ数字。内蔵`layer`スタイル |
| 2 | `forest_unassigned_review` | 未割当20地物を赤色 |
| 3 | `forest_plan_districts_provisional` | 158計画区の色分け・`district_code || '_' || district_name`ラベル |
| 4 | `forest_wide_basins_provisional` | 44広域流域の色分け・`basin_code || '_' || basin_name`ラベル |

計画区図では3を表示し4を非表示、広域流域図では4を表示し3を非表示にします。1は両方の図の最上位に置きます。以前読み込んだレイヤは新しいファイルから追加し直すか、[styles](../styles)の対応QMLを読み込んでください。座標系の元の暗色ローマ数字スタイルは`default`として保存しています。

座標系区域は japan-plane-rectangular-cs-zones v2026.2 の形状を使います。公開処理ではZIPのSHA-256と、geometry blobの順序付きSHA-256を比べ、`23fa2d62f395ce192857e2a69444e639e24d4f89c30f4da17d0976b0acb3a02b`に一致しない場合は公開を止めます。座標系区域を森林計画区と同じ意味の境界として扱いません。

QMLのXML、158・44の分類数、ラベル式、GeoPackage内部整合、スタイル付与前後の形状一致を検査しています。**QGIS実画面での描画と現行区域との一致は未確認です。**

## 境界・所属の点検

確認用の森林GeoPackageをQGIS 3.44に読み込む。作成された3レイヤーは次のとおり。

| レイヤー | 件数 | 点検する属性 |
| --- | ---: | --- |
| `forest_plan_districts_provisional` | 158 | `district_code`, `district_name`, `basin_code`, `basin_name`, `status`, `final_usable` |
| `forest_wide_basins_provisional` | 44 | `basin_code`, `basin_name`, `status`, `final_usable` |
| `forest_unassigned_review` | 20 | `municipality_code`, `status` |

1. 全レイヤーのCRSがEPSG:6668、`final_usable`が`false`（集約レイヤーのみ）であることを確認する。地区ごとに異なる色で表示し、全国の空白・重複・飛び地を目視する。未割当レイヤーは別色で重ねる。
2. 北海道の幌延町（01520）を拡大し、現在の候補が「留萌」、森林対象レイヤの観測が「宗谷」である差を記録する。森林対象レイヤのコード001等を候補の全国コード001等に直接結合しない。
3. 新島村（13363）、小笠原村（13421）、薩摩川内市（46215）、南さつま市（46220）、三島村（46303）、十島村（46304）を拡大する。[各系の森林重なり件数](../data/forest/split_municipality_forest_evidence.csv)と見比べる。森林地物0件は計画区の区域外という意味ではない。
4. 地図上で疑義がある箇所について、スクリーンショット、計画区・広域流域コード、自治体コード、地名、緯度経度、参照資料と適用日を記録する。公式境界と判断できない箇所は「要照会」に留める。

技術的検査は[形状検査結果](../data/forest/provisional_polygon_geometry_validation.json)のとおり。QGIS実機の描画確認はまだ実施していない。市町村全域が計画区域と一致するか、島・河川沿いの一部指定があるかは林野庁または県の資料で別途確定する。

