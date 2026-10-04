# 確認用流域ポリゴンのQGIS点検（2026-10-05）

[4分割GeoPackageを結合](PROVISIONAL_GPKG.md)してQGIS 3.44に読み込む。作成された3レイヤーは次のとおり。

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
