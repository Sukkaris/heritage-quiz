# 世界遺産クイズ

ブラウザで動く4択の世界遺産クイズ。個人利用。サーバ・ログイン・課金なし。

## 使い方

`index.html` をブラウザで開くだけ。`file://` で直接開いても動く（データはJS内の定数）。
スマートフォンで使う場合は、このフォルダごと端末に置いてブラウザで開くか、
ホーム画面に追加する。

## 出題形式

すべて4択（区分のみ3択）。マスタから実行時に自動生成する。

| 種類 | 設問 |
|---|---|
| 所在国 | 「〇〇」があるのはどの国ですか？ |
| 区分 | 「〇〇」は文化遺産・自然遺産・複合遺産のどれですか？（3択） |
| 遺産名 | 次のうち、〇〇にある世界遺産はどれですか？ |
| 登録基準 | 「〇〇」の登録基準に含まれるものはどれですか？ |

誤答の引き方が難易度のレバーになっている。難しい問題ほど、同じ地域の国・
同じ地域の遺産・同じ系統（文化どうし／自然どうし）の登録基準から誤答を引く。

登録基準の設問は、その遺産が**持っていない**基準だけを誤答に使うので、
複数の基準を持つ遺産でも正解は必ず1つになる。

## ファイル

| ファイル | 中身 |
|---|---|
| `index.html` | 画面の骨組み（スタート／出題／結果） |
| `style.css` | 見た目。スマホ優先、タップ領域は最低44〜56px |
| `data.js` | **自動生成**の遺産マスタ。難易度の閾値もここ |
| `app.js` | 出題ロジック・学習記録。遺産の事実は一切書いていない |
| `manual_questions.js` | 手書き問題の置き場（初期は空） |
| `DATA_REPORT.md` | データ検品レポート |
| `tools/` | データ取得・生成スクリプト（アプリ実行時には使わない） |
| `raw/` | Wikidataから取得した生JSON |

## データ

- 主データ: [Wikidata](https://www.wikidata.org/)（CC0）
- 日本語名の補完: 日本語版Wikipedia「世界遺産の一覧」（UNESCO IDで突き合わせ）
- 登録基準の条文: 日本語版Wikipedia「世界遺産」（世界遺産センター公式基準の翻訳・引用）
- アプリ実行時に外部へ問い合わせない。`tools/` で取得済みのものを `data.js` に埋め込んでいる
- 検品結果は [DATA_REPORT.md](DATA_REPORT.md)

### データを取り直す

```bash
uv run --with truststore python tools/fetch_wikidata.py && uv run --with truststore python tools/fetch_jawiki_list.py && uv run --with truststore python tools/fetch_criteria_ja.py && uv run --with truststore python tools/build_data.py
```

`raw/` に既にあるファイルは再取得しない。取り直したいものだけ消してから実行する。
（このPCはTLS傍受環境のため `truststore` が必要。Wikidata Query Serviceは
混雑時 1リクエスト/分 に制限されることがあり、その場合は自動で待って再試行する）

## 調整しやすい場所

| 変えたいもの | 場所 |
|---|---|
| 難易度の境目 | `data.js` 冒頭の `DIFFICULTY`（サイトリンク数の閾値） |
| 1セットの問題数 | `app.js` の `SET_SIZE` |
| 誤答をどれだけ近くから引くか | `app.js` の `DISTRACTOR_NEARNESS` |
| 弱点モードの重み | `app.js` の `weightOf()` |
| 手書き問題の混ざる割合 | `app.js` の `MANUAL_RATIO` |

## 学習記録

localStorage（キー `heritageQuiz.stats.v1`）に遺産QIDごとの
`{ correct, wrong, lastAnswered }` を保存する。ブラウザのデータを消すと失われる。
スタート画面の「学習記録の管理」からJSONで書き出し・読み込みができる。

## この先

- 手書き問題（`manual_questions.js` に追記すれば自動で出題に混ざる。最大3問/セット）
- 座標を使った地図機能（`data.js` に `coord` を保持済み）

登録年代を問う設問は作らない方針（登録年代はフィルタとしてのみ使う）。
