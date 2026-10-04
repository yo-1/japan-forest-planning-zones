# 公開記録と作業環境

2026-10-05、`yo-1/japan-forest-planning-zones` の `main` に、派生元の履歴を保持したGit bundleから初回pushしました。初回公開時のHEADは `e8e323f06bce2212df6bc702d88262bee30a3792` です。元コミットと派生元はトップページのREADMEを参照してください。

初回pushのGitHub Actions（Linux/Python 3.9・3.12、Windows/Python 3.12）は成功しました。ただし、入力N03 DBFに依存するテストはCIではスキップされます。実データでの結合確認は [FEASIBILITY.md](FEASIBILITY.md) に記録しています。

## 継続作業

通常の作業では、公開済みのリポジトリをcloneします。

```bash
git clone https://github.com/yo-1/japan-forest-planning-zones.git
cd japan-forest-planning-zones
```

派生元を比較する場合は、任意で別のremoteを追加します。

```bash
git remote add upstream https://github.com/yo-1/japan-plane-rectangular-cs-zones.git
```

初回公開に使ったbundleは履歴移送用です。以後の通常のcloneやpullには必要ありません。派生元のタグは新規リポジトリに一括移送していません。

## 公開範囲と残作業

このリポジトリの森林計画区・広域流域の対応表は確認用v0.1です。現行の公式境界ではありません。未割当20コードと島しょ部などの広域流域を確認し、必要なら市町村内の境界分割を行います。照会事項は [INQUIRY_STATUS.md](INQUIRY_STATUS.md) を参照してください。

結合済みの候補GeoPackageとZIPは、GitHub Releaseにはまだ掲載していません。公開する場合は暫定値であること、基準日、出典、未確認事項を同梱し、QGIS表示と形状を確認してください。未確認情報の `forest_final_usable` を `true` に変更しません。
