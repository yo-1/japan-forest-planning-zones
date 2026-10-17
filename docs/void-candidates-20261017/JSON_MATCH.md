# 空白候補のEsri JSONとGDBの照合（2026-10-17 JST）

利用者からvoid_candidates_gdb.json（103,449 bytes）を受領しました。SHA-256は `37acbb8f0b6602f35f01f9fd0de664b029e41eac1ac959caf17611296ae87dea` です。geometryTypeはesriGeometryPolygon、空間参照はwkid 104020／latestWkid 6668でした。

OBJECTIDとcandidate_idを照合し、プロジェクト5内のvoid_candidates_gdbと比較しました。13地物・2,133保存座標が、全リング・全順序で完全一致しました。GDBの全32属性もJSONの対応属性と一致し、OBJECTIDはGDB FIDと一致しました。丸め・スナップ・修復はしていません。

[検査スクリプト](../../scripts/audit_void_json_match.py)と[全件結果](void-json-match.json)を保存しました。実入力で完走し、構文検査とJSON・GDB全ファイルの処理前後ハッシュ不変を確認しました。

この一致により、[GDB本体検査](RAW_GDB_AUDIT.md)で測ったID 3・6・7・11の約1e-9度の近接は、GDALのデコードだけで新規発生した座標差ではなく、利用者のEsri JSONにも存在すると確認できました。GEOS有効13件・保存済みEsri自己交差4地物という判定差は、引き続き別の検証結果として扱います。内部クラスタリングの機序は断定しません。

このJSONは地物の形状であり、Check Geometryが報告した問題点の座標一覧ではありません。自己交差の位置をEsriが直接返した証拠とはしません。元のmain.void_candidatesを含むGPKGとの比較も未実施です。継承属性のgeometry_sha256・cause等を、原典の独立検証と読み替えません。

原典・Release・形状には変更がありません。4頂点の極小形状へ025の2頂点削除を一般化せず、全国採用は保留します。現在地メモは「空白候補のGDBとEsri JSON全件一致確認済み、元GPKG比較・直接問題位置・原因機序は未確認」へ更新したほうが良いです。
