# 実機GUI確認のシナリオ（qgis-dev-probe）

検証Bはヘッドレス環境で実施したため、GUI の実画面での表示確認だけが残りました。このシナリオは、qgis-dev-probe（実機 QGIS を MCP で操作する開発専用プラグイン）でその確認を行う手順です。Dev Probe の流儀どおり、同期で完結する読み込みと照合は recipe にし、画面の確認はクライアント（AI）が1手ずつ進めます。

確認の対象は表示と読み込みの様子だけです。データの内容の判定は検証Bで終わっているので、ここで新しい合否は出しません。表示崩れ・文字化け・既定スタイルの適用漏れ・読み込み時の警告がないかを見ます。

## 前提

- Windows 実機の QGIS 3.44 系で、qgis-dev-probe が有効で、MCP クライアントが interactive モードで接続していること
- 対象データは公開版 review-v0.3-20261015 の展開済み GeoPackage 3点です。手元に無い場合は Release から2つの ZIP を取り、SHA-256 が次の値と一致することを確認してから展開します
  - forest_planning_zones_2026_review.zip: ebe92b11530bf89f72ff8d626de552835810d489296b2acbec1f212514b31a16
  - municipality_forest_zones_2026_candidate.zip: 5b8f3301bc6da2616c8e55d82aef52cc3353bdcc1e57d0714de1a954fe4ed1d7
- 展開後の GeoPackage の SHA-256（照合用）
  - forest_planning_zones_2026_provisional_labeled.gpkg: ed4df025f6b078a7b1378adddee1eac86f277894d9dd755318963ac34acf2da7
  - municipality_forest_zones_2026_candidate.gpkg: 5af6f5981b61e34f1c9e8487dcf78ad44c3013b40582ab339da0439210e28c46
  - plane_rectangular_zones_2026.gpkg: 7f8b35c97d4796cdcbb7a203e5c07c68cd6595597ee5e1f284f9b809587c00d3
- recipe の `recipes/load_forest_zones_review.py` を、Dev Probe の recipe_dir に置くこと

## 手順

| 手順 | ツール | 確認すること |
|---|---|---|
| 1. 接続と版 | `ping`、`get_info` | 応答があり、QGIS のバージョンが記録できる |
| 2. 読み込みと照合 | `run_recipe load_forest_zones_review`（引数に3つの GeoPackage のパス） | 戻り値の `problems` が空で、5レイヤーの件数（158・44・20・1,911・19）と CRS（EPSG:6668）がすべて期待どおり |
| 3. 全国表示 | `execute_code` で下のコードを実行 → `wait` 2秒 → `screenshot` | 日本全体が描かれ、表示崩れがない。GeoPackage の既定スタイル（分類シンボル）が適用されている |
| 4. 拡大表示 | `execute_code` で下の拡大コードを実行 → `wait` 2秒 → `screenshot` | 計画区025（米代川、秋田市周辺）が描かれ、境界と市町村界が読み取れる |
| 5. 属性の見え方 | `inspect_layer`（対象: 市町村候補レイヤー、sample 3） | サンプルの属性値に日本語が文字化けなく出る（district_name など） |
| 6. ログ | `read_log`（level: warning） | 手順2〜5の間に新しい warning 以上が出ていない |
| 7. 後始末 | `remove_layer` を5レイヤー分、またはプロジェクトを保存せず閉じる | データファイルを変更していない。プロジェクトファイルはデータのフォルダに保存しない |

手順3のコード（計画区レイヤーの全体範囲へ移動）:

```python
lyr = QgsProject.instance().mapLayersByName("forest_plan_districts_provisional")[0]
canvas = iface.mapCanvas()
canvas.setExtent(lyr.extent())
canvas.refresh()
```

手順4のコード（計画区025の範囲。検証Bの拡大図と同じ範囲です）:

```python
from qgis.core import QgsRectangle
canvas = iface.mapCanvas()
canvas.setExtent(QgsRectangle(139.5417, 39.6456, 141.1454, 40.6611))
canvas.refresh()
```

`execute_code` はセッション限りの許可制です。実機側で許可が出た場合だけ実行し、許可が得られない場合は、利用者が手で全体表示と025付近への拡大を行い、その画面を `screenshot` で記録する形に切り替えます。

## 記録の残し方

- 手順2の recipe の戻り値（JSON）、手順3・4のスクリーンショット、手順6の結果を残します
- 保存先は、このフォルダ（docs/qgis-verification-20261027/）への追加コミットか、Drive の「森林計画区・広域流域データ_AI連絡」フォルダへの報告のどちらかです。実施した側が報告書に、実施日時・QGIS のバージョン・Dev Probe のバージョンを明記します
- スクリーンショットに個人情報が映り込まないよう、画面の他のアプリは閉じてから撮ります
