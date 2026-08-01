# -*- coding: utf-8 -*-
"""
段階①: Wikidataから世界遺産マスタの素材を取得する使い捨てスクリプト。

WDQSが障害中で 1リクエスト/分 のレート制限がかかっているため、
- 1本の巨大クエリではなく、軽量なクエリ4本に分割
- 各リクエストの間に十分な待機を入れ、429は指数バックオフで再試行
結果は raw/ に生JSONのまま保存する（加工は build_data.py 側で行う）。
"""
import json
import os
import time
import urllib.parse
import urllib.request

try:
    import truststore

    truststore.inject_into_ssl()  # TLS傍受環境のためWindows証明書ストアを使う
except ImportError:
    pass

UA = "HeritageQuizDataFetch/1.0 (personal study project; python-urllib)"
SPARQL = "https://query.wikidata.org/sparql"
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "raw")
WAIT_BETWEEN = 70          # レート制限が 1req/min のため
RETRY_WAIT = 95
MAX_RETRY = 10

# 世界遺産 = P1435（遺産保護指定）が Q9259（世界遺産）
BASE = "?item wdt:P1435 wd:Q9259 ."

QUERIES = {
    # 本体: ラベル(ja/en)、サイトリンク数、登録年(P1435文の修飾子P580)
    "items": """
SELECT ?item ?ja ?en ?sitelinks ?date ?whsid WHERE {
  %s
  OPTIONAL { ?item rdfs:label ?ja . FILTER(LANG(?ja) = "ja") }
  OPTIONAL { ?item rdfs:label ?en . FILTER(LANG(?en) = "en") }
  OPTIONAL { ?item wikibase:sitelinks ?sitelinks . }
  OPTIONAL { ?item wdt:P757 ?whsid . }
  OPTIONAL { ?item p:P1435 ?st . ?st ps:P1435 wd:Q9259 ; pq:P580 ?date . }
}""" % BASE,
    # 所在国（複数国にまたがる遺産は複数行で返る）
    "countries": """
SELECT ?item ?country WHERE {
  %s
  ?item wdt:P17 ?country .
}""" % BASE,
    # 登録基準（区分の導出に使う）
    "criteria": """
SELECT ?item ?criterion WHERE {
  %s
  ?item wdt:P2614 ?criterion .
}""" % BASE,
    # 国のラベルと所属地域（P30=大陸）。国→地域対応表の素材
    "country_meta": """
SELECT ?country ?ja ?en ?continent WHERE {
  { SELECT DISTINCT ?country WHERE { %s ?item wdt:P17 ?country . } }
  OPTIONAL { ?country rdfs:label ?ja . FILTER(LANG(?ja) = "ja") }
  OPTIONAL { ?country rdfs:label ?en . FILTER(LANG(?en) = "en") }
  OPTIONAL { ?country wdt:P30 ?continent . }
}""" % BASE,
    # 座標（取れれば取る）
    "coords": """
SELECT ?item ?coord WHERE {
  %s
  ?item wdt:P625 ?coord .
}""" % BASE,
    # 危機遺産フラグの素材: P1435 の値の種類ごとの件数ではなく、
    # 「危機にさらされている世界遺産(Q1459900)」指定を持つ遺産
    "in_danger": """
SELECT ?item WHERE {
  %s
  ?item wdt:P1435 wd:Q1459900 .
}""" % BASE,
    # §3.4 日本語ラベル補完: 日本語版Wikipediaの記事名（ラベル欠落時のフォールバック）
    "jawiki": """
SELECT ?item ?title WHERE {
  %s
  ?article schema:about ?item ;
           schema:isPartOf <https://ja.wikipedia.org/> ;
           schema:name ?title .
}""" % BASE,
}


def run(query):
    url = SPARQL + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"}
    )
    for attempt in range(1, MAX_RETRY + 1):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:200]
            print("    HTTP %s (試行%d): %s" % (e.code, attempt, body), flush=True)
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(RETRY_WAIT * min(attempt, 3))
                continue
            raise
        except Exception as e:
            print("    エラー (試行%d): %r" % (attempt, e), flush=True)
            time.sleep(RETRY_WAIT)
    raise RuntimeError("再試行上限に達した")


def main():
    os.makedirs(RAW, exist_ok=True)
    first = True
    for name, q in QUERIES.items():
        path = os.path.join(RAW, name + ".json")
        if os.path.exists(path):
            print("[skip] %s は取得済み" % name, flush=True)
            continue
        if not first:
            print("  ...レート制限待機 %d秒" % WAIT_BETWEEN, flush=True)
            time.sleep(WAIT_BETWEEN)
        first = False
        print("[get] %s" % name, flush=True)
        res = run(q)
        rows = res["results"]["bindings"]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
        print("  -> %d行 保存: %s" % (len(rows), path), flush=True)

    # 登録基準アイテム(i〜x)のラベルはエンティティAPIから取得（レート制限対象外）
    crit_path = os.path.join(RAW, "criteria_labels.json")
    if not os.path.exists(crit_path):
        qids = ["Q23038972", "Q23038976", "Q23038977", "Q23038978", "Q23038979",
                "Q23038980", "Q23038981", "Q23038983", "Q23038985", "Q23038986"]
        out = {}
        for qid in qids:
            url = "https://www.wikidata.org/wiki/Special:EntityData/%s.json" % qid
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                e = json.loads(r.read().decode("utf-8"))["entities"][qid]
            out[qid] = {
                "label": e["labels"].get("en", {}).get("value"),
                "desc_en": e.get("descriptions", {}).get("en", {}).get("value"),
                "desc_ja": e.get("descriptions", {}).get("ja", {}).get("value"),
            }
            print("  基準 %s = %s" % (qid, out[qid]["label"]), flush=True)
        with open(crit_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)

    print("完了", flush=True)


if __name__ == "__main__":
    main()
