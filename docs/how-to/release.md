# リリース手順

GitHub Pagesでビューアを公開します。生成済みの `web/data/` を使用して `dist/` をビルドし、タグpushをトリガーにデプロイします。公開先は次のURLです。

https://Watson496.github.io/awaji-geology-3d/

ビルド成果物はコミットしません。

バージョン更新PRをmainへマージしてからタグ・Releaseを作成します。公開用ビルドとGitHub PagesへのデプロイはGitHub Actionsで行います。

## 初回設定

- GitHubの Settings → Pages → Build and deployment → Source を GitHub Actions にする
- Environment `github-pages` にデプロイ制限を設定している場合は、`v*` タグからのデプロイを許可する
- `main` にCI・デプロイワークフローを含むプロジェクト一式を反映する
- CIのNodeバージョンは `mise.toml` と同じ値に保つ

## バージョン管理

`package.json` の `version` を基準とし、タグ名は `vX.Y.Z` とします。`package-lock.json` も同時に更新します。Pythonの `pyproject.toml` は内部の計算プロジェクトの情報であり、ビューアのリリース番号の管理には使いません。

## 前提

- `main` のCI（型検査・幾何テスト・Pages用ビルド）の成功
- `main` の最新コミットからのリリース
- データ更新時は出典・利用条件・加工内容を `web/data/ATTRIBUTION.md` に反映すること

## 手順

### mainの更新

```sh
git switch main
git pull --ff-only
npm ci
```

### バージョン更新PR

直前タグ以降の変更から、セマンティックバージョニング（SemVer）の `patch` / `minor` / `major` を決めます。

```sh
git switch -c chore/release-vX.Y.Z
npm version <patch|minor|major> --no-git-tag-version
```

- コミット・PRタイトルは `chore(release): vX.Y.Z`
- `package.json` と `package-lock.json` のバージョン更新のみを含める
- `.github/PULL_REQUEST_TEMPLATE.md` に従い、直前タグ以降の変更一覧とSemVer増分の根拠を書く
- 通常mergeでmainへマージする
- リリース進行中は、タグ作成まで他のPRをmainへマージしない

初回リリースのみ、初期版 `0.1.0` をそのまま公開する場合はバージョン更新PRを省略できます。

### 公開パスでの確認

```sh
git switch main
git pull --ff-only
npm ci
npm run typecheck
npm run test:geometry
BASE_PATH=/awaji-geology-3d/ npm run build
BASE_PATH=/awaji-geology-3d/ npm run preview
```

確認用サーバーで次のURLを開き、表示と出典へのリンクを確認します：

http://127.0.0.1:4173/awaji-geology-3d/

- 地形・岩体・断層が表示される
- 都市圏活断層図、比較断面の原図が表示される
- 「出典・推定条件」から出典・加工内容・利用条件と各ライセンスにアクセスできる
- モデルを比較A/Bへ切り替えてもデータを読み込める
- ブラウザのコンソールとネットワークにエラーがない

Python/GemPyでのモデル再計算は公開ビルドには不要です。計算処理やモデルデータを更新した場合の検証は[モデルデータの再生成](regenerate-model.md)と[検査の実行](validation.md)に従います。

### タグとReleaseの作成

バージョンと対象コミットを取得します。Releaseの本文はファイルに書き、主な変更点と対応Issue/PRを記載します。

```sh
release_version=$(node -p 'JSON.parse(require("node:fs").readFileSync("package.json", "utf8")).version')
release_commit=$(git rev-parse HEAD)
gh release create "v${release_version}" \
  --target "$release_commit" \
  --title "v${release_version}" \
  --notes-file /tmp/awaji-release-notes.md
```

タグがリモートに作成されると `.github/workflows/deploy.yml` が起動します。mainへのpushだけでは公開版を更新しません。ワークフローはタグ名と `package.json` の一致、および対象コミットがmainの履歴に含まれることを検査し、幾何テストと型検査を含むビルドを行って `dist/` をデプロイします。

### 公開結果の確認

- Releasesでタグ・バージョン・対象コミットを確認する
- Actionsの「Deploy to GitHub Pages」が成功したことを確認する
- 公開先で、公開パスでの確認と同じ表示・出典リンクを確認する

再デプロイする場合は、Actionsの実行をRe-runするか、手動実行で公開済みタグを選びます。手動実行でもタグとバージョンの検査を通すため、mainブランチを選んでのデプロイはできません。

[ドキュメント一覧](../README.md)
