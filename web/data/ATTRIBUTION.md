# ライセンスと出典

本プロジェクトのオリジナルのソフトウェアは MIT License で公開します。Copyright (c) 2026 Watson496 and contributors. 全文はルートの LICENSE または配布データ内の LICENSE-SOFTWARE.txt を参照してください。ソースコードの公開先は https://github.com/Watson496/awaji-geology-3d です。モデル計算で外部ライブラリとして利用する GemPy は EUPL-1.2 です。GemPy本体は同梱・改変しておらず、本プロジェクトのMITとは別のライセンスです。依存ライブラリ、入力資料、画像およびそれらに由来するデータには、それぞれの権利者の利用条件が適用されます。LICENSE は第三者の資料を再許諾するものではありません。

## 加工者と加工内容

awaji-geology-3d（Watson496）が、以下の資料を切り出し・投影変換・座標化・照合し、地下構造を推定して可視化したものです。産総研、国土地理院、地震調査研究推進本部、海上保安庁の公式モデルではなく、これらの機関による監修・承認を示すものでもありません。原資料の解釈と本プロジェクトの仮定を含み、地下構造の実測値ではありません。

## 入力資料と表示画像

| 資料・提供元 | 利用条件・加工内容 |
| --- | --- |
| [20万分の1日本シームレス地質図V2（産総研地質調査総合センター）](https://gbank.gsj.jp/seamless/v2/) | [GSJウェブサイト利用規約](https://www.gsj.jp/license/license.html)（政府標準利用規約第2.0版準拠、CC BY 4.0互換）。原凡例・色を参照し、地表区分、断層ベクトルを切り出し・投影変換。地下の地質区分・岩体は本プロジェクトの推定。公式シェープファイル5134・5135・5234・5235、2025-07-18版。 |
| [水野清秀・服部仁・寒川旭・高橋浩（1990）明石地域の地質、5万分の1地質図幅、地質調査所](https://www.gsj.jp/data/50KGM/JPG/GSJ_MAP_G050_12083_1990_200dpi.jpg) | GSJウェブサイト利用規約。公式Webの画像・GISデータを使用。断面画像6点中の明石3点は原図の断面部分を切り出したもの。地質単元・走向傾斜・断面位置を抽出し、一部の岩相点・境界・断層曲線を座標化。 |
| [高橋浩・寒川旭・水野清秀・服部仁（1992）洲本地域の地質、5万分の1地質図幅、地質調査所](https://www.gsj.jp/Map/JP/docs/5man_doc/13/13_011.htm) | GSJウェブサイト利用規約。公式Webの画像・GISデータを使用。洲本3断面を切り出し、一部を座標化。図幅全体の基図画像は同梱していません。 |
| [地質図Navi（産総研地質調査総合センター）](https://gbank.gsj.jp/geonavi/)の活断層データベース・全国主要活断層帯 | GSJウェブサイト利用規約。af_segment.json・JPF_2024.json を対象範囲で切り出し・投影変換。原レコードの属性・参照元を data/structure/official-faults.json および web/data/faults.json に保持。表示用の線は出典間の重複を整理。原属性内の文献は元データの出典であり、それらの出版物自体を再配布していません。 |
| [地理院タイル・標高タイル DEM10B（国土地理院）](https://maps.gsi.go.jp/development/ichiran.html#dem) | [国土地理院コンテンツ利用規約](https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html)。dem_png を使用し、切り出し・再標本化・投影変換・地形メッシュ化。標高タイルはタイル一覧の「基本測量成果以外で出典の記載のみで利用可能なもの」に掲載。基盤地図情報のDEM原本の配布ではありません。 |
| [地理院タイル・活断層図（都市圏活断層図）（国土地理院）](https://maps.gsi.go.jp/development/ichiran.html#afm) | 国土地理院コンテンツ利用規約。公式afmタイルを結合し、対象範囲に合わせて投影変換。画像は gsi-active-fault-map.png。取得タイル・画像範囲は gsi-active-fault-map.json に記録。[図ごとの調査者・図名等の諸元](https://www.gsi.go.jp/bousaichiri/active_fault)も参照。 |
| [岡田・熊原（2014）都市圏活断層図「洲本」「由良」「鳴門海峡」解説書（国土地理院）](https://www.gsi.go.jp/common/000096723.pdf) | 国土地理院コンテンツ利用規約。断層の分布・変位様式の解釈に参照。PDF原本は同梱していません。 |
| [地震調査研究推進本部の近畿地方の活断層長期評価](https://www.jishin.go.jp/evaluation/long_term_evaluation/regional_evaluation/kinki-detail/)・[中央構造線断層帯評価（2017）](https://www.jishin.go.jp/main/chousa/17dec_chi_shikoku/shikoku_01_mtl.pdf) | [地震本部の利用条件](https://www.jishin.go.jp/agreement/)が指定する文部科学省ウェブサイト利用規約。公表された断層の属性・評価を参照し、本プロジェクトの仮定と区別。個々の資料URL・SHA256は data/structure/sources.json に記録。PDFや第三者の図は同梱していません。 |
| [岩淵ほか（2000）反射法音波探査に基づく大阪湾の基盤と活構造（海上保安庁海洋情報部）](https://www1.kaiho.mlit.go.jp/faults/osakabay1.pdf) | [海洋情報部ホームページ利用条件](https://www1.kaiho.mlit.go.jp/copyright.html)（政府標準利用規約第2.0版準拠）。Fig.22の音響基盤深度から数値5点を読み取り、構造制約として加工。PDF・図版は同梱していません。 |

同梱する図幅の切り出し画像はGSJ公式Webから取得したもので、GSJウェブサイト利用規約の対象です（[GSJ FAQ Q-5](https://www.gsj.jp/license/faq-web.html)）。

地質調査所月報の論文（topology.json にURLを記録）および[岩屋層の化石年代研究（2000）](https://www.jstage.jst.go.jp/article/geosoc1893/106/5/106_5_379/_article/-char/ja)は地質解釈の参考文献です。論文本文や図版は再配布していません。

## データの再利用

web/data/、data/structure/、data/prepared/ は、上記資料を加工したデータと独自の仮定・計算結果を含みます。本プロジェクトが権利を有する独自のデータ・説明は [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) で提供します。元資料に由来する部分には元資料の条件も適用されます。数値や地質学的事実そのものに新たな独占権を主張するものではありません。

再配布・加工時には、本プロジェクト名、元資料の出典・URL、加工者と加工した旨を残してください。GLBを出力して配布する場合も本ファイルを添付してください。表示上の鉛直倍率や推定条件は実測精度を意味しません。

## 同梱範囲と依存ソフトウェア

表示に必要な生成データ、較正・出典・仮定の記録、再生成用の準備データを含みます。data/raw/ のダウンロード原本、計算キャッシュ、仮想環境、node_modulesは含めません。原本は再生成スクリプトの公式URLから取得します。

ブラウザ配布物に含まれる依存ソフトウェアの著作権表示・ライセンス本文は web/data/THIRD_PARTY_NOTICES.txt に収録しています。GemPyおよびPythonの依存パッケージはこのリポジトリに同梱していません。再生成環境では uv.lock の版と各パッケージのライセンスに従ってください。

確認日: 2026-11-10。
