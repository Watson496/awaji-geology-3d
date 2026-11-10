# ローカルでの起動

ビューアのコードを編集する場合は、リポジトリを取得してローカルで起動します。生成済みのデータを同梱しているため、表示やWeb向けビルドだけならPython・GemPyによる再計算は不要です。

## 準備

Git、mise、npmを利用します。Nodeのバージョンはリポジトリの `mise.toml` で指定しています。

```sh
git clone https://github.com/Watson496/awaji-geology-3d.git
cd awaji-geology-3d
mise trust
mise install
npm ci
```

## 開発サーバー

```sh
npm start
```

開発サーバーの起動後、次のURLでビューアを開けます。

http://127.0.0.1:4173/

## 公開用ビルド

GitHub Pagesのサブパスに合わせてビルドする場合は、`BASE_PATH` を指定します。

```sh
BASE_PATH=/awaji-geology-3d/ npm run build
BASE_PATH=/awaji-geology-3d/ npm run preview
```

生成物は `dist/` に出力され、モデルデータとライセンス文書は `dist/data/` にコピーされます。確認用サーバーでは次のURLを開きます。

http://127.0.0.1:4173/awaji-geology-3d/

`BASE_PATH` を指定しない場合は、ドメイン直下の `/` を使います。GitHub Pagesでの公開操作は[リリース手順](release.md)に記載しています。

[ドキュメント一覧](../README.md)
