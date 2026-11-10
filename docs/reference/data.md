# データ形式・座標系

パスはリポジトリのルートを基準にしています。コマンドは[モデルデータの再生成](../how-to/regenerate-model.md)に記載しています。

## ディレクトリ

- `data/raw/`：公式URLから取得した原本。Git管理の対象外
- `data/cache/`：計算キャッシュ。Git管理の対象外
- `data/structure/`：出典、較正、解釈、推定条件の記録
- `data/prepared/`：計算に使う準備済みデータ
- `web/data/`：ビューアの表示データと配布用の出典・ライセンス文書
- `dist/`：Web向けのビルド成果物。Git管理の対象外

## 岩体と原凡例

`rock-bodies.json` は、元の地質区分を示す `source_unit`、安定した地質学的名称の `identity`、原凡例別の操作キー `key`、表示・メッシュ用の数値 `id` を保持します。グループ、図幅記号、出典ZIPのSHA256も記録します。1つの累層が複数の原凡例を含む場合は、`identity` を共有しつつ原凡例別の岩相を保持します。

`<scenario>/body-volume.bin` はuint16の岩体ID、`volume.bin` はuint8の原凡例IDです。岩体IDを `source_unit` へ戻すと、元の `volume.bin` と全セルで一致します。表示メッシュと水平断面は、岩体を示す `body` と原凡例を示す `unit` の両方を保持します。任意断面・個別操作・GLBにも岩体IDを引き継ぎます。

`structural-packages.bin` は構造上のまとまり、`volume.bin` は原凡例の地質区分です。構造関係と出典は `data/structure/topology.json` に記録します。

## 資料の支持範囲と下位地質

`section-support.bin` は資料に近い領域を記録します。岩体の表示範囲はこの属性とは独立しています。`extrapolated-volume.bin` は `volume.bin` と同じ連続推定結果を保持します。

各シナリオの `substrate-volume.bin` は原単元ID、`substrate-distance.bin` は採用単元の制約までのグラフ距離（float32、m）、`substrate-status.bin` は採用・競合・距離外・制約なし等の状態です。未確定セルの距離は、最寄りの利用可能な制約までの距離です。条件は `data/structure/substrate-policy.json` に保存します。

## 検査結果

ここでの検査結果は、実装の動作確認と、入力資料を計算結果がどの程度再現するかを調べるための記録です。

各シナリオの `metrics.json` は、仮定、制約の使用、残差を記録します。`fault_conditioning.substrate` には、被覆単元ごとの未確定率、ソルバー残差を保存します。

`section-validation.json` は、拘束に使った断面との再現距離を記録します。基準モデルの地質境界3点との距離は約85〜220mです。独立した地下精度の値ではありません。

## 出典と断層

`data/structure/official-faults.json` は、公式断層の入力URL・SHA256・元レコード番号・原属性を保持します。テストでは元シェープファイルを再読込し、公開する断層頂点が投影変換後の原頂点と一致することを確認します。公式データのハッシュが変わった場合は、自動で対比を引き継がず停止します。

`web/data/fault-display.json` は、表示統合で採用した区間、置換先、除外延長、入力ハッシュ、原資料IDを保持します。`data/structure/faults.json` は、地下の面群ごとの線・傾斜プロファイル・拘束深度・出典・仮定を保持します。

都市圏活断層図の被覆・画像範囲・出典は `data/structure/gsi-active-fault-map.json`、記号の読み取りは `gsi-fault-kinematics.json` に記録しています。

## 追加断面の属性

`data/structure/sections-extra.json` の `sections` 配列は、既存の `sections.json` と同じ形式です。

- `id`：断面の識別子
- `name`：表示名
- `source_url`：原資料のURL
- `source_sha256`：原資料のSHA256
- `route_xy`：EPSG:32653による測線座標、単位m
- `image`：`web/data/` を基準にした画像の相対パス
- `image_range_m`：始点0から較正した測線全長までの距離と、下端・上端標高
- `picks`：岩相・境界の制約点
- `fault_picks`：断層の読み取り点
- `used_for_model`：モデルの制約に使うかどうかの指定

## GLB

単位はkm、Xは東、Yは標高、Zは南です。EPSG:32653の平面原点と鉛直倍率は、rootの `userData` に保存します。地表図や切断の表示条件も引き継ぎます。

[ドキュメント一覧](../README.md)
