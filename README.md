# japan-forest-planning-zones

市区町村の座標系ポリゴンに、森林計画区と広域流域の情報を追加する派生プロジェクトです。

**現在は確認用v0.1です。現行の公式境界データとして使うことはできません。**

島しょ部を含め、広域流域名は現行の所属・境界を確定した値ではありません。
平面直角座標系の系ごとに地物が分かれていても、同じ市町村コードには同じ暫定値を付けています。
系の分割は広域流域の分割を意味しません。

派生元: https://github.com/yo-1/japan-plane-rectangular-cs-zones
元コミット: d6781a3b0fbc2a9ddd4b8606d0960d567495b53d
入力ポリゴン: 派生元Release v2026.1の市町村版。元のGit履歴を保持しています。


## 確認用データのダウンロード

色・番号・名称ラベル付きの候補図と市町村の対応表を公開しています。

- [確認用データのReleases](https://github.com/yo-1/japan-forest-planning-zones/releases)
- [公開処理の実行状況](https://github.com/yo-1/japan-forest-planning-zones/actions/workflows/publish-review.yml)
- [QGISでの重ね合わせ・点検手順](docs/QGIS_REVIEW.md)
- [公開ZIP・対応表・表示設定の技術点検](docs/TECHNICAL_AUDIT_20261005.md)

平面直角座標系の区域は、[japan-plane-rectangular-cs-zones v2026.2](https://github.com/yo-1/japan-plane-rectangular-cs-zones/releases/tag/v2026.2)のものを使います。公開処理ではZIPのSHA-256と形状ハッシュを照合し、一致した形状だけを使います。赤いローマ数字のスタイルも保持します。森林計画区図と広域流域図を切り替え、その上に座標系境界を重ねます。QGIS実画面での最終表示は未確認です。

4都道県の森林計画対象森林との照合結果は[出典・境界資料の調査](docs/BOUNDARY_SOURCE_REVIEW.md)に記録しました。291コードの森林側属性を照合しましたが、市町村全域の所属又は公式境界を確定したものではありません。主対応表の暫定値と最終利用可否falseは維持しています。

## 作成

```bash
python scripts/build_forest_layer.py INPUT.gpkg output/municipality_forest_zones_2026_candidate.gpkg
```

Python標準ライブラリで動きます。入力ファイルとは別のパスに出力します。
市町村コードN03_007で結合し、元の地形・座標系属性・地物分割を保持します。
新しいCSVは data/municipality_coordinate_forest_zones.csv です。コードは文字列として読み込みます。

森林計画区コード・名称、広域流域コード・名称、確認状況、出典と日付を追加します。
1,905コードのうち96件は現行の県資料で所属を照合、1,789件は過去資料との候補一致、20件は未割当です。
全件の区域範囲は未確認で forest_final_usable は false です。
広域流域との対応は2010年2月1日の資料に基づくため、現行資料との照合が必要です。

市町村の一部が別計画区に属する場合は、市町村単位の結合では表せません。
その場合は公式の区画を取得し、分割例外データを作ってから処理します。
政令指定都市の区、所属未定地、市町村合併、区域変更も確認します。
確認用の集約ポリゴンを作成しました（158計画区・44広域流域・未割当20地物）。公式境界としての確定には現行所属・全域／一部指定の確認が必要です。

## 公開

コードはMIT、座標系データはCC BY 4.0です。DATA_LICENSE.mdの出典表記を保持します。
森林対応表の出典と制約はdata/forest/README.mdに記録しています。
大きなGeoPackageとZIPはGitに入れず、[確認用Release review-v0.2-20261010](https://github.com/yo-1/japan-forest-planning-zones/releases/tag/review-v0.2-20261010)で配布しています（旧版 review-v0.1-20261005 は、比べるために残しています）。再生成・形状検査・公開処理とWindows/Linux CIは成功しました。QGIS実画面での表示は未確認です。
新規公開手順はdocs/SETUP.md、検証結果はdocs/FEASIBILITY.mdを参照してください。
