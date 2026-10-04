# 確認用集約GeoPackage（2026-10-05）

元の市町村候補GeoPackageの1,911地物から、所属あり1,891地物をコード別に融合した。森林計画区158、広域流域44、未割当20地物を別レイヤーに格納。座標系EPSG:6668、SQLite整合性検査`ok`。これは2010年の候補所属を基礎に市町村界を集約した**確認用**で、現在の公式境界ではない。部分指定や島しょ部を正式に分割したものでもない。

4分割したファイルを番号順にダウンロードする。

- [part00](https://drive.google.com/file/d/1087L30BxiAm6y8boQM8XDj-LEFhSPN0f/view?usp=drivesdk)
- [part01](https://drive.google.com/file/d/1pAkVJKmQkMU8FA67GZKnH9NbxbW68QCj/view?usp=drivesdk)
- [part02](https://drive.google.com/file/d/1v6lQDCpfcvnGk_VKHN5wwPSwRyYk8PPW/view?usp=drivesdk)
- [part03](https://drive.google.com/file/d/1GrQv8ofkbWvfVgMJbTFgXxOnvQ3rol6c/view?usp=drivesdk)

4ファイルを同じフォルダに置き、`cat forest_planning_zones_2026_provisional.gpkg.part0* > forest_planning_zones_2026_provisional.gpkg`で結合する。Windowsでは `copy /b part00+part01+part02+part03 forest_planning_zones_2026_provisional.gpkg` の `part00` 等を実際の完全なファイル名に置き換える。結合後のSHA-256は `6607b8af46ba319702debbab2c3d19b2fd5ff55c0ed71d61d097eecde8bf615b`。分割ファイルの連結結果と元ファイルが同じハッシュであることを確認済み。

生成コードは [build_provisional_aggregates.py](../scripts/build_provisional_aggregates.py)。集約結果はEPSG:6668のGeoPackageとして技術検査したが、QGIS実機での描画と現行区域との一致は未確認。境界・所属の照会事項は [BOUNDARY_SOURCE_REVIEW.md](BOUNDARY_SOURCE_REVIEW.md) を参照。
