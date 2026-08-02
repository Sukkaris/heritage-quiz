# -*- coding: utf-8 -*-
"""
日本語版Wikipediaの「世界遺産の一覧」の登録名から、対応するWikidataのQIDを引く。

WikidataのP757（UNESCO ID）は、構成資産のID（"868-062"）しか入っていない遺産が
あるため、それだけでは遺産とアイテムを対応づけきれない。登録名 → 日本語版Wikipediaの
記事（リダイレクトも解決）→ Wikidataアイテム、という経路で対応表を作る。

入力: raw/jawiki_list.json （UNESCO ID -> 日本語の登録名）
出力: raw/jawiki_qid.json  （UNESCO ID -> QID）
"""
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

UA = "HeritageQuizDataFetch/1.0 (personal study project)"
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "raw")
SRC = os.path.join(RAW, "jawiki_list.json")
OUT = os.path.join(RAW, "jawiki_qid.json")
BATCH = 50


def api(**params):
    """タイトルが長くURLに収まらないのでPOSTで送る"""
    params.setdefault("format", "json")
    params.setdefault("formatversion", "2")
    data = urllib.parse.urlencode(params).encode("utf-8")
    for attempt in range(1, 7):
        req = urllib.request.Request("https://ja.wikipedia.org/w/api.php",
                                     data=data, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            wait = 20 * attempt
            print("    429。%d秒待って再試行" % wait, flush=True)
            time.sleep(wait)
    raise RuntimeError("再試行上限")


def main():
    if os.path.exists(OUT):
        print("取得済み:", OUT)
        return
    with io.open(SRC, encoding="utf-8") as f:
        names = json.load(f)

    titles = sorted({v for v in names.values()})
    title_to_qid = {}
    for i in range(0, len(titles), BATCH):
        chunk = titles[i:i + BATCH]
        res = api(action="query", titles="|".join(chunk),
                  prop="pageprops", ppprop="wikibase_item", redirects=1)
        q = res.get("query", {})
        # リダイレクト元 -> 先
        redirect = {r["from"]: r["to"] for r in q.get("redirects", [])}
        normalized = {r["from"]: r["to"] for r in q.get("normalized", [])}
        page_qid = {p["title"]: p.get("pageprops", {}).get("wikibase_item")
                    for p in q.get("pages", [])}
        for t in chunk:
            t2 = normalized.get(t, t)
            t2 = redirect.get(t2, t2)
            if page_qid.get(t2):
                title_to_qid[t] = page_qid[t2]
        print("  %d/%d" % (min(i + BATCH, len(titles)), len(titles)), flush=True)
        time.sleep(2)

    out = {}
    for wid, name in names.items():
        if name in title_to_qid:
            out[wid] = title_to_qid[name]

    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0, sort_keys=True)
    print("QIDを引けた遺産: %d / %d" % (len(out), len(names)))
    print("保存:", OUT)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
