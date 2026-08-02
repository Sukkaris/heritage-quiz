# -*- coding: utf-8 -*-
"""
項目2の調査（使い捨て）: 件数差の原因をWikidata側で確認する。

- 統合済み／抹消済みの遺産に P582（終了日）や rank=deprecated が付いているか
- 欠落している3件（グアナフアト482 / フエ678 / ビスカヤ橋1217）がなぜ取得できなかったか
エンティティAPIはWDQSのレート制限の対象外なので直接叩く。
"""
import io
import json
import os
import sys
import urllib.parse
import urllib.request

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

UA = "HeritageQuizProbe/1.0 (personal study project)"
DATA_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data.js")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def entity(qid):
    return get("https://www.wikidata.org/wiki/Special:EntityData/%s.json" % qid)["entities"][qid]


def search(term):
    url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode({
        "action": "wbsearchentities", "search": term, "language": "ja",
        "uselang": "ja", "limit": 8, "format": "json", "formatversion": "2"})
    return get(url).get("search", [])


def sites():
    with io.open(DATA_JS, encoding="utf-8") as f:
        t = f.read()
    s = t.index("const HERITAGE_DATA = [")
    return [json.loads(l.strip().rstrip(",")) for l in t[s:].splitlines() if l.strip().startswith("{")]


def show_designation(qid, label):
    e = entity(qid)
    print("\n--- %s (%s) ---" % (label, qid))
    print("  P757(UNESCO ID):", [st["mainsnak"].get("datavalue", {}).get("value")
                                 for st in e["claims"].get("P757", [])])
    for st in e["claims"].get("P1435", []):
        val = st["mainsnak"].get("datavalue", {}).get("value", {}).get("id")
        quals = {}
        for pid, snaks in st.get("qualifiers", {}).items():
            quals[pid] = [s.get("datavalue", {}).get("value", {}).get("time")
                          or s.get("datavalue", {}).get("value", {}).get("id")
                          for s in snaks]
        print("  P1435=%s rank=%s 修飾子=%s" % (val, st.get("rank"), quals))
    # 上位の遺産（部分である）
    for pid in ("P361", "P1889", "P527"):
        vals = [st["mainsnak"].get("datavalue", {}).get("value", {}).get("id")
                for st in e["claims"].get(pid, [])]
        if vals:
            print("  %s: %s" % (pid, vals[:6]))


by_id = {str(s["whsid"]): s for s in sites()}

print("=== 1) 統合済み・抹消済みが疑われる遺産のWikidata上の状態 ===")
for wid, name in [("133", "バージェス頁岩"), ("161", "シャンボール城"), ("654", "アラビアオリックスの保護区"),
                  ("304", "カナディアン・ロッキー"), ("933", "ロワール渓谷")]:
    s = by_id.get(wid)
    if s:
        show_designation(s["qid"], "%s (ID %s)" % (name, wid))
    else:
        print("\n--- %s (ID %s) --- マスタに無し" % (name, wid))

print("\n\n=== 2) 抹消済みでマスタに入っていない遺産（比較用） ===")
for term in ["海商都市リヴァプール", "ドレスデン・エルベ渓谷"]:
    hits = search(term)
    if hits:
        show_designation(hits[0]["id"], term + " / " + hits[0].get("label", ""))

print("\n\n=== 3) マスタに無い3件はWikidata上でどうなっているか ===")
for term in ["グアナフアト歴史地区と鉱山", "フエの建造物群", "ビスカヤ橋"]:
    hits = search(term)
    print("\n### 検索 '%s'" % term)
    for h in hits[:3]:
        print("  候補:", h["id"], h.get("label"), "/", h.get("description", "")[:60])
    if hits:
        show_designation(hits[0]["id"], term)
