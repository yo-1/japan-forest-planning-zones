# 新規リポジトリを公開する手順

1. GitHubの空のリポジトリ `yo-1/japan-forest-planning-zones` を使用します（2026-10-05時点で作成済み、mainはまだありません）。
2. 同梱のGit bundleを展開して、新規リポジトリへ履歴を送ります。

```bash
git clone japan-forest-planning-zones.bundle japan-forest-planning-zones
cd japan-forest-planning-zones
git switch main
git remote rename origin bundle-source
git remote add upstream https://github.com/yo-1/japan-plane-rectangular-cs-zones.git
git remote add origin https://github.com/yo-1/japan-forest-planning-zones.git
git push -u origin main
```

bundleには元履歴と今回の作成コミットが含まれます。派生元の全タグは新規先に自動でpushしません。
確認用ポリゴンZIPは、公開範囲を確認してから新規先のReleasesにアップロードします。
GitHub上のリポジトリは作成済みです。初回pushとRelease作成は未実施です。

次の実装担当にはREADME、docs/FEASIBILITY.md、data/forest/README.mdを渡します。
現行資料の確認を優先し、未確認情報のforest_final_usableをtrueにしません。
