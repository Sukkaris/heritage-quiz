# -*- coding: utf-8 -*-
"""
段階①-b: 区分（文化/自然/複合）と登録基準がどこに入っているかの確認（使い捨て）
"""
import json
import urllib.parse
import urllib.request

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

UA = "HeritageQuizDataProbe/1.0 (personal study project)"
SPARQL = "https://query.wikidata.org/sparql"


def sparql(query):
    url = SPARQL + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))


def show(title, query, keys):
    print("\n=== %s ===" % title)
    try:
        rows = sparql(query)["results"]["bindings"]
    except Exception as e:
        print("失敗:", repr(e))
        return
    print("行数:", len(rows))
    for b in rows[:40]:
        print("  " + " | ".join(str(b.get(k, {}).get("value", "-")) for k in keys))


# 1) 謎のQIDのラベル確認（P2614の値・P1435の2つ目の値）
show(
    "1) 候補QIDのラベル",
    """
SELECT ?x ?xLabel ?xDescription WHERE {
  VALUES ?x { wd:Q23038972 wd:Q23038976 wd:Q23038977 wd:Q23038978 wd:Q26971668 wd:Q9259 }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ja,en". }
}""",
    ["x", "xLabel", "xDescription"],
)

# 2) P2614（登録基準らしきプロパティ）が何かをプロパティ自身のラベルで確認
show(
    "2) プロパティ P2614 / P1435 / P757 / P580 のラベル",
    """
SELECT ?p ?pLabel ?pDescription WHERE {
  VALUES ?p { wd:P2614 wd:P1435 wd:P757 wd:P580 wd:P1889 }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ja,en". }
}""",
    ["p", "pLabel", "pDescription"],
)

# 3) 世界遺産の総件数（P1435=Q9259）
show(
    "3) 総件数",
    """
SELECT (COUNT(DISTINCT ?item) AS ?n) WHERE { ?item wdt:P1435 wd:Q9259 . }""",
    ["n"],
)

# 4) 日本語ラベルあり件数 / P2614あり件数 / P17あり件数 / P580あり件数
show(
    "4) 各項目の充足件数",
    """
SELECT ?kind (COUNT(DISTINCT ?item) AS ?n) WHERE {
  ?item wdt:P1435 wd:Q9259 .
  {
    ?item rdfs:label ?l . FILTER(LANG(?l)="ja") BIND("ja_label" AS ?kind)
  } UNION {
    ?item wdt:P2614 ?c . BIND("P2614_criteria" AS ?kind)
  } UNION {
    ?item wdt:P17 ?co . BIND("P17_country" AS ?kind)
  } UNION {
    ?item p:P1435 [ ps:P1435 wd:Q9259 ; pq:P580 ?t ] . BIND("P580_year" AS ?kind)
  } UNION {
    ?item wdt:P757 ?id . BIND("P757_whs_id" AS ?kind)
  } UNION {
    ?item wdt:P625 ?g . BIND("P625_coord" AS ?kind)
  }
}
GROUP BY ?kind""",
    ["kind", "n"],
)

# 5) P2614の値の全種類（登録基準の項目一覧になるはず）
show(
    "5) P2614 の値の種類",
    """
SELECT ?c ?cLabel (COUNT(DISTINCT ?item) AS ?n) WHERE {
  ?item wdt:P1435 wd:Q9259 ; wdt:P2614 ?c .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ja,en". }
}
GROUP BY ?c ?cLabel ORDER BY ?cLabel""",
    ["c", "cLabel", "n"],
)

# 6) 区分が直接取れるプロパティがないか: 世界遺産にP31で何が付いているか上位
show(
    "6) 世界遺産アイテムのP31 上位20",
    """
SELECT ?t ?tLabel (COUNT(DISTINCT ?item) AS ?n) WHERE {
  ?item wdt:P1435 wd:Q9259 ; wdt:P31 ?t .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ja,en". }
}
GROUP BY ?t ?tLabel ORDER BY DESC(?n) LIMIT 20""",
    ["t", "tLabel", "n"],
)

# 7) P1435 の値の種類（Q9259以外に何が使われているか）
show(
    "7) 世界遺産アイテムが持つ P1435 の値の種類 上位20",
    """
SELECT ?d ?dLabel (COUNT(DISTINCT ?item) AS ?n) WHERE {
  ?item wdt:P1435 wd:Q9259 ; wdt:P1435 ?d .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ja,en". }
}
GROUP BY ?d ?dLabel ORDER BY DESC(?n) LIMIT 20""",
    ["d", "dLabel", "n"],
)
