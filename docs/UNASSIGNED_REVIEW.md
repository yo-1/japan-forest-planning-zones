# 未割当20コードの追加調査（2026-10-05）

この文書は確認用v0.1の `data/forest/municipality_mapping_issues.csv` に対する追加調査です。**元CSVと候補GeoPackageはまだ更新していません。** 下表は森林計画区の所属に関する資料上の候補で、広域流域の現行所属・市町村内の区域境界・公式の区画番号を確定しません。名称の後の3桁は本リポジトリの2010年一覧の番号であり、現行の公式ユニークIDであるとは検証していません。

## 実在する13自治体

| N03_007 | 市町村 | 資料で確認できた計画区候補 | 確認内容と出典 |
|---|---|---|---|
| 03216 | 滝沢市 | 北上川上流（021） | [岩手県の現行地域森林計画書](https://www.pref.iwate.jp/_res/projects/default_project/_page_/001/008/334/r7_kitakamigawajyouryuu_innsatuyou.pdf) の概要図・市町別表に記載 |
| 12239 | 大網白里市 | 千葉北部（046） | [千葉県の計画区一覧](https://www.pref.chiba.lg.jp/shinrin/keikaku/nourinsuisan/shinrinkeikaku.html) で南部以外に該当。[森林計画資料](https://www.pref.chiba.lg.jp/shinrin/keikaku/nourinsuisan/keikakukankeishiryou.html) には同市を九十九里調査区に記載。森林調査区と森林計画区は別区分 |
| 17212 | 野々市市 | 加賀（058） | [石川県の加賀地域森林計画書](https://www.pref.ishikawa.lg.jp/shinrin/kikaku/tiikisinrinkeikaku/documents/r7_kaga_henkou.pdf) の市町別表に記載。計画対象森林の有無・範囲は別に確認 |
| 17461 | 穴水町 | 能登（057） | [石川県の能登地域森林計画書](https://www.pref.ishikawa.lg.jp/shinrin/kikaku/tiikisinrinkeikaku/documents/r7_noto_henkou.pdf) の市町別表に記載 |
| 17463 | 能登町 | 能登（057） | 同上 |
| 21221 | 海津市 | 揖斐川（072） | [岐阜県の揖斐川地域森林計画書](https://www.pref.gifu.lg.jp/uploaded/attachment/403578.pdf) の対象市町に記載 |
| 23237 | あま市 | 尾張西三河（078）の区域図上 | [愛知県の計画書](https://www.pref.aichi.jp/uploaded/attachment/595533.pdf) の計画区位置図に市名あり。ただし県の[市町村森林整備計画策定市町村一覧](https://www.pref.aichi.jp/soshiki/rinmu/0000007055.html)にはない。計画対象森林の有無と、属性を付ける範囲を確認 |
| 23238 | 長久手市 | 尾張西三河（078） | [愛知県の地域森林計画](https://www.pref.aichi.jp/soshiki/rinmu/0000007055.html) の策定市町村一覧に記載 |
| 28221 | 丹波篠山市 | 加古川（089） | [兵庫県公報の計画区域一覧](https://web.pref.hyogo.lg.jp/kk32/koho/documents/20241105t.pdf) に記載 |
| 39212 | 香美市 | 高知（126）の区域図上 | [高知県の高知地域森林計画書](https://www.pref.kochi.lg.jp/doc/chiikikeikaku/file_contents/file_202412253153836_1.pdf) の計画区概要図に記載。区域詳細の確認が必要 |
| 40231 | 那珂川市 | 福岡（129） | [福岡県の福岡地域森林計画書](https://www.pref.fukuoka.lg.jp/uploaded/life/764782_62448402_misc.pdf) の構成市町に記載 |
| 01699 | 紗那村 | 未確認 | 北方領土の扱い、現在の計画区と行政区域の範囲について別途確認 |
| 13363 | 新島村 | 未確認 | 伊豆諸島の島しょ部の計画区・広域流域への所属を林野庁へ照会 |

## 所属未定地7コード

`12000` 千葉県、`13000` 東京都、`23000` 愛知県、`30000` 和歌山県、`40000` 福岡県、`46000` 鹿児島県、`47000` 沖縄県は、N03の所属未定地です。隣接自治体や同県の計画区を機械的に転記しません。位置と制度上の扱いを個別に確認します。

## 反映前の条件

1. 上表の候補を現行の計画区所属として採用する前に、当該資料の基準日、島しょ部の扱い、市町村全域か一部かを確認する。
2. 広域流域の値は、2010年一覧の計画区との対応を現行の全国森林計画または林野庁回答で照合する。
3. `build_forest_mapping.py` のルール、主CSV、問題一覧、結合済みGeoPackage、検証記録を同じ版で再生成する。手作業でCSVだけ修正しない。
4. 全行の `usable_for_final_polygon` は、境界が確定するまで `false` とする。
