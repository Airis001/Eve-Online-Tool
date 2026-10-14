🌐 [English](README.md) · **日本語** · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md) · [Русский](README.ru.md) · [한국어](README.ko.md) · [中文](README.zh.md)

# EVE ツール（EVE Online スキルチェッカー）

EVE Online のキャラクターのスキル・資産・お金などを ESI から読み込んで、「どの艦・フィットに乗れるか」「何を訓練すればよいか」「どこで稼げるか」をまとめて確認できるツールです。
ブラウザで開く Web アプリで、自分の PC・デスクトップ版（.exe）・クラウドのどれでも動かせます。

## できること

| 分類 | 機能 |
|---|---|
| スキル | スキルチェッカー（艦・装備に必要なスキルと訓練時間）、スキル一覧、属性の割り振り |
| フィット | おすすめフィット・艦船、PvE / PvP フィット、フィット作成（PG・CPU・DPS の目安）、フィットの比較 |
| お金 | マーケット、ウォレット、資産、査定、ステーション内トレード、ハブ間の転売、PLEX とストア、LP の換金（ISK/LP と取引量） |
| 生産 | 製造・リアクション、PI（惑星開発）の集計と配置の計算 |
| 移動・情報 | 安全なルートとオートパイロットの所要時間、流通ミッション、ミッションの敵の属性・弱点、ワームホール、シグネチャ、ローカル・D-Scan・撃墜 |

複数のキャラクターを登録して、まとめて確認できます。

画面は日本語・英語・ドイツ語・フランス語・スペイン語・ロシア語・韓国語・中国語に対応しています。ナビの「🌐」のメニューで切り替えられます（初めて開いたときは、ブラウザーの言語で決まります）。艦・装備の名前も、ゲーム内と同じ表記で表示します（その言語の名前が無いものは英語名）。

## ダウンロード（Windows）

[Releases](https://github.com/Airis001/Eve-Online-Tool/releases/latest) から zip をダウンロードして展開し、`EVE Tool.exe` を起動します。Python は不要です。
初回起動時に「Windows によって PC が保護されました」と出たら、「詳細情報」→「実行」を選んでください（署名していないアプリのため）。

## 使い方（ソースから動かす）

必要なもの: Python 3（3.14 で動作確認。Windows では `py` コマンド）

1. https://developers.eveonline.com/ でアプリを作る。
   - Callback URL: `http://localhost:8080/callback`
   - スコープ: 使いたい機能のものを選ぶ（一覧は [fetch_skills.py](fetch_skills.py) の `SCOPE_` で始まる行）。
     最低限 `esi-skills.read_skills.v1` と `esi-skills.read_skillqueue.v1` があればスキルチェッカーは動きます。
2. `.env.example` を `.env` にコピーし、アプリの Client ID と Secret Key を書く。
3. 必要なライブラリを入れて起動する。
   ```powershell
   py -m pip install -r requirements.txt
   py app.py
   ```
4. ブラウザで http://localhost:8080 が開くので、「＋ キャラクター追加」から EVE にログインする。

初回は艦・装備の名前の一覧や CCP の静的データ（SDE）を取得するので、少し時間がかかります。

## ほかの動かし方

- **デスクトップ版（.exe）を自分で作る**: `desktop.env.example` を `desktop.env` にコピーして Client ID を書き、`py build_exe.py` を実行する（[build_exe.py](build_exe.py)）。
- **クラウド（スマホから使う）**: Fly.io は [DEPLOY.md](DEPLOY.md)、VPS は [DEPLOY_CONOHA.md](DEPLOY_CONOHA.md)。
  招待コードを知っている人だけがアカウントを作れ、データはアカウントごとに暗号化して分けて保存します。

## データの扱い

- キャラクターのログイン情報・取得したデータは、動かしている PC（またはサーバー）の中にだけ保存します。
- `.env` などの設定ファイルや、キャラクターのデータは Git に入らないようにしてあります（[.gitignore](.gitignore)）。

## 文言を足したり変えたりするとき

画面の文言は日本語で書き、訳を [static/i18n/](static/i18n/) の言語ごとのファイル（`en.json`・`de.json` など）に置きます（日本語の文をそのまま見出しにしています）。ある言語に訳が無い文言は英語で表示します。

- JS: `tr("{0} 星系", n)` のように書く。艦・装備の名前は `nm(item)` で、言語に合わせた名前を選ぶ。
- Python: 値を埋め込む文は `tr("{0} が見つかりません", name)`（`from i18n import tr`）。API の応答の中で辞書にそのまま載っている文字列は、自動で訳されます。
- HTML のページ（static/*.html）の固定の文字は、サーバーが返すときに訳します。

文言を変えたら `py check_i18n.py` を実行して、各言語の訳の抜けがないか確かめてください（`py check_i18n.py --missing de` で、ドイツ語に足りない文言を英語訳つきで一覧にできます）。

## ライセンス

[MIT License](LICENSE)

## 著作権表示

EVE Online and the EVE logo are the registered trademarks of CCP hf. All rights are reserved worldwide. All other trademarks are the property of their respective owners. EVE Online, the EVE logo, EVE and all associated logos and designs are the intellectual property of CCP hf. All artwork, screenshots, characters, vehicles, storylines, world facts or other recognizable features of the intellectual property relating to these trademarks are likewise the intellectual property of CCP hf. CCP hf. has granted permission to this tool to use EVE Online and all associated logos and designs for promotional and information purposes but does not endorse, and is not in any way affiliated with, this tool. CCP is in no way responsible for the content on or functioning of this tool, nor can it be liable for any damage arising from the use of this tool.

このツールは CCP hf. の公式ツールではありません。
