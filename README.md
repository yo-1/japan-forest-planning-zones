# japan-forest-planning-zones

市区町村の座標系ポリゴンに、森林計画区と広域流域の情報を追加する派生プロジェクトです。

**現在は確認用v0.1です。現行の公式境界データとして使うことはできません。**

島しょ部を含め、広域流域名は現行の所属・境界を確定した値ではありません。
平面直角座標系の系ごとに地物が分かれていても、同じ市町村コードには同じ暫定値を付けています。
系の分割は広域流域の分割を意味しません。林野庁への照会事項は
[docs/INQUIRY_STATUS.md](docs/INQUIRY_STATUS.md)を参照してください。

派生元: https://github.com/yo-1/japan-plane-rectangular-cs-zones
元コミット: d6781a3b0fbc2a9ddd4b8606d0960d567495b53d
入力ポリゴン: 派生元Release v2026.1の市町村版。元のGit履歴を保持しています。

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
計画区・広域流域の集約ポリゴンは、対応を確定してから作ります。

## 公開

コードはMIT、座標系データはCC BY 4.0です。DATA_LICENSE.mdの出典表記を保持します。
森林対応表の出典と制約はdata/forest/README.mdに記録しています。
大きなGeoPackageとZIPはGitに入れず、Releasesで配ります。
新規公開手順はdocs/SETUP.md、検証結果はdocs/FEASIBILITY.mdを参照してください。
