# 確認用集約GeoPackage（2026-10-05）

元の市町村候補GeoPackageの1,911地物から、所属あり1,891地物をコード別に融合した。森林計画区158、広域流域44、未割当20地物を別レイヤーに格納。座標系EPSG:6668、SQLite整合性検査`ok`。これは2010年の候補所属を基礎に市町村界を集約した**確認用**で、現在の公式境界ではない。部分指定や島しょ部を正式に分割したものでもない。

## 新しい確認用パッケージ

色・番号・名称ラベル付き158計画区・44広域流域・未割当20地物と、19座標系区域（v2026.2）、対応CSV、QGISスタイルをまとめたZIPを[確認用Release](https://github.com/yo-1/japan-forest-planning-zones/releases/tag/review-v0.2-20261010)で公開しました。GitHub上の再生成・形状検査・公開処理とWindows/Linux CIは成功しました。[Releases](https://github.com/yo-1/japan-forest-planning-zones/releases)と[公開処理の完了状況](https://github.com/yo-1/japan-forest-planning-zones/actions/workflows/publish-review.yml)を確認してください。公開前のリンクをダウンロード済みとして扱いません。

[表示・重ね合わせ手順](QGIS_REVIEW.md)を参照してください。Releaseに添付する`review_manifest.json`と`SHA256SUMS.txt`は、その実行で生成したファイルの件数・検査結果・ハッシュを記録します。スタイルやZIPの生成日時によってファイル全体のハッシュは変わるため、下記の旧版ハッシュを新パッケージに使わないでください。

## 従来の分割版（スタイル追加前）

4分割したファイルを番号順にダウンロードする。

- [part00](https://drive.google.com/file/d/1087L30BxiAm6y8boQM8XDj-LEFhSPN0f/view?usp=drivesdk)
- [part01](https://drive.google.com/file/d/1pAkVJKmQkMU8FA67GZKnH9NbxbW68QCj/view?usp=drivesdk)
- [part02](https://drive.google.com/file/d/1v6lQDCpfcvnGk_VKHN5wwPSwRyYk8PPW/view?usp=drivesdk)
- [part03](https://drive.google.com/file/d/1GrQv8ofkbWvfVgMJbTFgXxOnvQ3rol6c/view?usp=drivesdk)

4ファイルを同じフォルダに置き、`cat forest_planning_zones_2026_provisional.gpkg.part0* > forest_planning_zones_2026_provisional.gpkg`で結合する。Windowsでは `copy /b part00+part01+part02+part03 forest_planning_zones_2026_provisional.gpkg` の `part00` 等を実際の完全なファイル名に置き換える。結合後のSHA-256は `6607b8af46ba319702debbab2c3d19b2fd5ff55c0ed71d61d097eecde8bf615b`。分割ファイルの連結結果と元ファイルが同じハッシュであることを確認済み。

生成コードは [build_provisional_aggregates.py](../scripts/build_provisional_aggregates.py)。[独立したShapely形状検査結果](../data/forest/provisional_polygon_geometry_validation.json)では全222地物に無効・空形状0件、EPSG:6668、SQLite整合性`ok`。QGIS実機での描画と現行区域との一致は未確認。境界・所属の検証結果は [BOUNDARY_SOURCE_REVIEW.md](BOUNDARY_SOURCE_REVIEW.md) を参照。

