# -*- coding: utf-8 -*-
"""
段階①-a: 構造の目視確認用プローブ（使い捨て）
イタリアの世界遺産のみを少数取得し、返ってきた生の構造を確認する。
プロパティIDは決め打ちせず、実際のエンティティJSONを見て判断する。
"""
import json
import sys
import urllib.parse
import urllib.request

# このPCはTLS傍受環境のため、Windowsの証明書ストアを使う
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

UA = "HeritageQuizDataProbe/1.0 (personal study project; contact: local user)"
SPARQL = "https://query.wikidata.org/sparql"
ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"


def sparql(query):
    url = SPARQL + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def entity(qid):
    req = urllib.request.Request(ENTITY.format(qid=qid), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))["entities"][qid]


# --- 1) イタリアの世界遺産を数件だけ取得 -------------------------------------
Q_ITALY = "wd:Q38"
q1 = """
SELECT ?item ?itemLabel WHERE {
  ?item wdt:P1435 wd:Q9259 ;
        wdt:P17 %s .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ja,en". }
}
LIMIT 5
""" % Q_ITALY

print("=== 1) SPARQL: P1435=Q9259 かつ P17=Q38（イタリア） ===")
try:
    res = sparql(q1)
except Exception as e:
    print("SPARQL失敗:", repr(e))
    sys.exit(1)

rows = res["results"]["bindings"]
print("件数:", len(rows))
qids = []
for b in rows:
    qid = b["item"]["value"].rsplit("/", 1)[-1]
    qids.append(qid)
    print(" -", qid, b.get("itemLabel", {}).get("value"))

if not qids:
    print("0件。P1435/Q9259の組み合わせが想定と違う可能性あり。")
    sys.exit(1)

# --- 2) 1件のエンティティJSONを丸ごと見て、どのプロパティが付いているか確認 ---
qid = qids[0]
ent = entity(qid)
print("\n=== 2) エンティティ %s の全プロパティID一覧 ===" % qid)
print("ラベルja:", ent["labels"].get("ja", {}).get("value"))
print("ラベルen:", ent["labels"].get("en", {}).get("value"))
print("sitelinks数:", len(ent.get("sitelinks", {})))
print("プロパティ:", ", ".join(sorted(ent["claims"].keys())))

print("\n=== 3) P1435 ステートメントの中身（値＋修飾子） ===")
for st in ent["claims"].get("P1435", []):
    mainsnak = st["mainsnak"]
    val = mainsnak.get("datavalue", {}).get("value", {})
    print("  値:", val.get("id", val))
    for pid, snaks in st.get("qualifiers", {}).items():
        vals = []
        for s in snaks:
            dv = s.get("datavalue", {}).get("value", {})
            vals.append(dv.get("id") or dv.get("time") or dv)
        print("    修飾子", pid, "->", vals)

print("\n=== 4) 全ステートメントの生ダンプ（値のみ・修飾子キー付き） ===")
for pid, sts in sorted(ent["claims"].items()):
    out = []
    for st in sts:
        dv = st["mainsnak"].get("datavalue", {}).get("value")
        if isinstance(dv, dict):
            dv = dv.get("id") or dv.get("time") or dv.get("amount") or dv
        quals = sorted(st.get("qualifiers", {}).keys())
        out.append(str(dv) + (" [q:%s]" % ",".join(quals) if quals else ""))
    print(" ", pid, "=", "; ".join(out[:6]), ("...(%d件)" % len(sts)) if len(sts) > 6 else "")
