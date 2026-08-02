# -*- coding: utf-8 -*-
"""
区分（文化/自然/複合）導出の検算。

data.js の区分は登録基準から導出している（i〜vi=文化、vii〜x=自然、両方=複合）。
この導出が正しいかを2通りで確かめる。

  A. 内部整合: 基準の内訳（i〜viのみ / vii〜xのみ / 両方 / なし）が区分の件数と一致するか
  B. 外部突き合わせ: 日本語版Wikipedia「世界遺産の一覧」の表にある「分類」列と
     UNESCO IDで1件ずつ照合する（Wikidataとは独立した情報源）

出力: CATEGORY_CHECK.md と標準出力
"""
import html
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser

try:
    import truststore

    truststore.inject_into_ssl()  # HTTPS検査環境のためWindowsの証明書ストアを使う
except ImportError:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_JS = os.path.join(BASE, "..", "data.js")
RAW = os.path.join(BASE, "..", "raw")
CACHE = os.path.join(RAW, "jawiki_category.json")
OUT = os.path.join(BASE, "..", "CATEGORY_CHECK.md")

UA = "HeritageQuizVerify/1.0 (personal study project)"
PAGES = [
    "世界遺産の一覧 (アジア)",
    "世界遺産の一覧 (ヨーロッパ)",
    "世界遺産の一覧 (アフリカ)",
    "世界遺産の一覧 (北アメリカ・中央アメリカ)",
    "世界遺産の一覧 (南アメリカ)",
    "世界遺産の一覧 (オセアニア)",
]
CULTURAL = {"i", "ii", "iii", "iv", "v", "vi"}
NATURAL = {"vii", "viii", "ix", "x"}


# ---- data.js の読み込み ----------------------------------------------------
def load_sites():
    with io.open(DATA_JS, encoding="utf-8") as f:
        text = f.read()
    start = text.index("const HERITAGE_DATA = [") + len("const HERITAGE_DATA = [")
    end = text.index("\n];", start)
    sites = []
    for line in text[start:end].splitlines():
        line = line.strip().rstrip(",")
        if line.startswith("{"):
            sites.append(json.loads(line))
    return sites


# ---- 日本語版Wikipediaの「分類」列 -----------------------------------------
class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
        elif tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def fetch_wikipedia_categories():
    if os.path.exists(CACHE):
        with io.open(CACHE, encoding="utf-8") as f:
            return json.load(f)

    result = {}
    for page in PAGES:
        params = {"action": "parse", "page": page, "prop": "text",
                  "format": "json", "formatversion": "2"}
        url = "https://ja.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.loads(r.read().decode("utf-8"))
        if "parse" not in res:
            print("  ページが取れない: %s" % page)
            continue
        p = TableParser()
        p.feed(res["parse"]["text"])
        n = 0
        # 分類セルは「複合（文化的景観）[2]」のように注記が付くことがある
        cat_re = re.compile(r"^(文化|自然|複合)\s*(（[^）]*）)?\s*(\[\d+\]\s*)*$")
        for row in p.rows:
            ids = [c for c in row if re.fullmatch(r"\d{1,4}", c)]
            cats = [m.group(1) for m in (cat_re.match(c) for c in row) if m]
            if ids and cats:
                result.setdefault(ids[-1], cats[0])
                n += 1
        print("  %s -> %d件" % (page, n))

    with io.open(CACHE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=0, sort_keys=True)
    return result


# ---- 本体 ------------------------------------------------------------------
def main():
    sites = load_sites()
    L = []
    A = lambda s="": (L.append(s), print(s))  # noqa: E731

    A("# 区分導出の検算")
    A("")
    A("`tools/verify_category.py` の出力。data.js の区分は登録基準から導出している")
    A("（i〜vi=文化 / vii〜x=自然 / 両方=複合）。")
    A("")

    # --- 1) 区分ごとの件数 ---
    counts = {"文化": 0, "自然": 0, "複合": 0, None: 0}
    for s in sites:
        counts[s["category"] if s["category"] in counts else None] += 1

    # --- 2) 基準からの再計算 ---
    # 登録基準が未登録の遺産だけは、UNESCO公式の区分をそのまま採用している
    official = {}
    upath = os.path.join(RAW, "unesco_list.json")
    if os.path.exists(upath):
        with io.open(upath, encoding="utf-8") as f:
            official = json.load(f)

    recount = {"文化": 0, "自然": 0, "複合": 0, "基準なし": 0}
    mismatch_internal = []
    no_criteria = []
    for s in sites:
        cs = set(s.get("criteria") or [])
        if not cs:
            recount["基準なし"] += 1
            no_criteria.append(s)
            expect = official.get(str(s["whsid"]), {}).get("category")
        elif cs & CULTURAL and cs & NATURAL:
            expect = "複合"
        elif cs & CULTURAL:
            expect = "文化"
        elif cs & NATURAL:
            expect = "自然"
        else:
            expect = None
        if expect:
            recount[expect] += 1
        if expect != s["category"]:
            mismatch_internal.append((s, expect))

    A("## 1. 区分ごとの件数")
    A("")
    A("| 区分 | data.js の値 | 登録基準から再計算 | 一致 |")
    A("|---|---|---|---|")
    for k in ("文化", "自然", "複合"):
        A("| %s | %d | %d | %s |" % (k, counts[k], recount[k], "○" if counts[k] == recount[k] else "×"))
    A("| 区分なし | %d | – | |" % counts[None])
    A("| （うち登録基準が無くUNESCO公式の区分を採用） | %d | | |" % recount["基準なし"])
    A("| 合計 | %d | %d | |" % (len(sites), sum(recount[k] for k in ("文化", "自然", "複合"))))
    A("")
    A("data.js の値と再計算値の不一致: **%d件**" % len(mismatch_internal))
    for s, e in mismatch_internal[:10]:
        A("- %s (%s): data.js=%s / 再計算=%s / 基準=%s"
          % (s["ja"] or s["en"], s["qid"], s["category"], e, s.get("criteria")))
    A("")

    # --- 3) 登録基準を持たない遺産 ---
    A("## 2. 登録基準を1つも持たない遺産")
    A("")
    A("**%d件**" % len(no_criteria))
    A("")
    for s in no_criteria:
        A("- %s (%s) / 区分の値: `%s` / 日本語名: %s / 登録年: %s"
          % (s["ja"] or s["en"], s["qid"], s["category"], s["hasJaLabel"], s["year"]))
    A("")
    bad = [s for s in no_criteria
           if s["category"] and s["category"] != official.get(str(s["whsid"]), {}).get("category")]
    if bad:
        A("→ **要確認**: 基準が無く、公式の区分とも一致しない遺産が %d件ある。" % len(bad))
    elif no_criteria:
        A("→ いずれもUNESCO公式の区分をそのまま採用しており、公式と一致している。")
    else:
        A("→ 該当なし。区分はすべて登録基準から導出できている。")
    A("")

    # --- 4) 複合遺産の全リスト ---
    mixed = sorted([s for s in sites if s["category"] == "複合"], key=lambda s: s["ja"] or "")
    A("## 3. 「複合」と判定された遺産の全リスト（%d件）" % len(mixed))
    A("")
    for s in mixed:
        A("- %s — 基準%s / %s"
          % (s["ja"] or s["en"], "".join("(%s)" % c for c in s["criteria"]),
             "・".join(s["regions"]) or "地域不明"))
    A("")

    # --- 5) 日本語版Wikipediaとの突き合わせ ---
    A("## 4. 日本語版Wikipediaの「分類」列との照合")
    A("")
    print("Wikipediaの分類を取得中…")
    wiki = fetch_wikipedia_categories()
    A("Wikipedia側で分類が取れた件数: %d" % len(wiki))
    matched = agree = 0
    disagree, unmatched = [], []
    for s in sites:
        if not s["category"]:
            continue
        w = wiki.get(str(s["whsid"]))
        if not w:
            unmatched.append(s)
            continue
        matched += 1
        if w == s["category"]:
            agree += 1
        else:
            disagree.append((s, w))
    A("")
    A("| 項目 | 件数 |")
    A("|---|---|")
    A("| 照合できた遺産 | %d |" % matched)
    A("| 一致 | %d |" % agree)
    A("| **不一致** | **%d** |" % len(disagree))
    A("")
    if disagree:
        A("### 不一致の内訳")
        A("")
        for s, w in disagree:
            A("- %s (ID %s): 本アプリ=**%s** / Wikipedia=**%s** / 基準=%s"
              % (s["ja"] or s["en"], s["whsid"], s["category"], w,
                 "".join("(%s)" % c for c in s["criteria"])))
        A("")
    if unmatched:
        A("### Wikipedia側にIDが見つからず照合できなかった遺産（%d件）" % len(unmatched))
        A("")
        A("区分の誤りではなく、Wikipediaの一覧が別のIDで載せているもの。")
        A("（より大きな遺産の一部として記載されている等）")
        A("")
        for s in unmatched:
            A("- %s (ID %s) — 本アプリの区分: %s / %s年"
              % (s["ja"] or s["en"], s["whsid"], s["category"], s["year"]))
        A("")

    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\n出力:", OUT)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
