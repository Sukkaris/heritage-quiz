# -*- coding: utf-8 -*-
"""
段階①-d: 日本語ラベル補完（企画書§3.4）

日本語版Wikipediaの「世界遺産の一覧 (地域名)」の表には、
  登録名（日本語） と UNESCOのID
が両方入っている。IDはWikidataのP757と同じものなので、確実に突き合わせられる。
Wikidataに日本語ラベルが無い遺産の名前をここから補う。

出力: raw/jawiki_list.json  { "102": "ベニ・ハンマードの城塞", ... }
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

    truststore.inject_into_ssl()
except ImportError:
    pass

UA = "HeritageQuizDataFetch/1.0 (personal study project)"
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "raw")
OUT = os.path.join(RAW, "jawiki_list.json")

PAGES = [
    "世界遺産の一覧 (アジア)",
    "世界遺産の一覧 (ヨーロッパ)",
    "世界遺産の一覧 (アフリカ)",
    "世界遺産の一覧 (北アメリカ・中央アメリカ)",
    "世界遺産の一覧 (南アメリカ)",
    "世界遺産の一覧 (オセアニア)",
]


def api(**params):
    params.setdefault("format", "json")
    params.setdefault("formatversion", "2")
    url = "https://ja.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


class TableParser(HTMLParser):
    """<table>の行を [[セルの文字列, ...], ...] として取り出す"""

    def __init__(self):
        super().__init__()
        self.rows = []
        self._row = None
        self._cell = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._depth += 1
        elif tag == "tr" and self._depth:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "table":
            self._depth = max(0, self._depth - 1)
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
        elif tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def main():
    os.makedirs(RAW, exist_ok=True)
    if os.path.exists(OUT):
        print("取得済み:", OUT)
        return

    result = {}
    for page in PAGES:
        try:
            res = api(action="parse", page=page, prop="text")
        except Exception as e:
            print("  取得失敗 %s: %r" % (page, e))
            continue
        if "parse" not in res:
            print("  ページが無い: %s (%s)" % (page, res.get("error", {}).get("info")))
            continue

        p = TableParser()
        p.feed(res["parse"]["text"])
        found = 0
        for row in p.rows:
            # ID列: UNESCOの登録番号（数字のみのセル）を、リンク先URLではなく
            # 表示文字列から拾う。IDらしい列がなければその行は表以外とみなす。
            ids = [c for c in row if re.fullmatch(r"\d{1,4}", c)]
            names = [c for c in row if c and not re.fullmatch(r"[\d\s年（）()、,\.]+", c)
                     and c not in ("文化", "自然", "複合")]
            if not ids or not names:
                continue
            whsid = ids[-1]           # 最後の数字セルがID（登録年は「1980年」で除外済み）
            name = names[0]
            name = html.unescape(re.sub(r"\[\d+\]", "", name))
            # MediaWikiのUNIQマーカー（テンプレート由来）を除去
            name = re.sub(r"\x7f[^\x7f]*\x7f", "", name).strip()
            if len(name) < 2:
                continue
            result.setdefault(whsid, name)
            found += 1
        print("  %s -> %d行" % (page, found))

    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=0, sort_keys=True)
    print("合計 %d件 保存: %s" % (len(result), OUT))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
