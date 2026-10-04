# データのライセンス

このリポジトリのデータ（`data/` フォルダにあるファイル。これから追加する対応表やポリゴンも含みます）は、
[クリエイティブ・コモンズ 表示 4.0 国際（CC BY 4.0）](https://creativecommons.org/licenses/by/4.0/deed.ja)
で公開しています。スクリプトなどのコードには、[`LICENSE`](LICENSE)（MIT License）が適用されます。

## 出典の書き方

データを使うときは、次の内容を書いてください。

```
「平面直角座標系 適用区域データ」（Yoichi Wada）
https://github.com/yo-1/japan-plane-rectangular-cs-zones
CC BY 4.0

出典：国土交通省国土数値情報ダウンロードサイト（https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-2026.html）
「国土数値情報（行政区域データ）」（国土交通省）（https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-2026.html）をもとに Yoichi Wada 作成
```

上の枠の最後の2行（「出典：」の行と「をもとに Yoichi Wada 作成」の行）は、国土数値情報ダウンロードサイトの利用規約にある
出典の書き方の例（「出典の記載について」）に合わせています。
このデータをさらに加工して使う場合は、加工したことと、加工した人も書いてください。

## 元データと、どう加工したか

| 項目 | 内容 |
|---|---|
| 元データ | 国土交通省「国土数値情報（行政区域データ）」2026年版 |
| 元データのURL | https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-2026.html |
| 元データの使用許諾条件 | オープンデータ（CC BY 4.0）（2026-10-03に元データのページで確認） |
| 国土数値情報ダウンロードサイトの利用規約 | 公共データ利用規約（第1.0版）（PDL1.0）。2026年3月23日から施行（2026-10-04に https://nlftp.mlit.go.jp/ksj/other/agreement.html で確認） |
| 元データの基準年月日 | 2026年（令和8年）1月1日時点 |
| 加工内容 | 平面直角座標系の系番号を割り当て、系ごとにポリゴンをまとめた |
| 適用区域の参照資料 | 国土地理院「わかりやすい平面直角座標系」 https://www.gsi.go.jp/sokuchikijun/jpc.html |
| 適用区域の根拠 | 平成十四年国土交通省告示第九号（国土地理院 https://www.gsi.go.jp/LAW/heimencho.html ） |
| 作成者 | Yoichi Wada |

## ご注意

このデータは、国土交通省や国土地理院が作成・公開しているものではありません。
内容が正しいことは保証できません。測量や設計などに使う場合は、国土地理院の資料と根拠となる法令で、
必ず適用区域を確認してください。
