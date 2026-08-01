# -*- coding: utf-8 -*-
"""
段階①-c: SPARQLがレート制限中のため、エンティティJSON APIで語彙を確認（使い捨て）
"""
import json
import urllib.request

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

UA = "HeritageQuizDataProbe/1.0 (personal study project)"


def entity(qid):
    url = "https://www.wikidata.org/wiki/Special:EntityData/%s.json" % qid
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))["entities"][qid]


def label(e, lang="ja"):
    return e["labels"].get(lang, {}).get("value")


for qid in ["Q23038972", "Q23038976", "Q23038977", "Q23038978", "Q26971668", "Q9259", "P2614", "P1435", "P580", "P757"]:
    try:
        e = entity(qid)
    except Exception as ex:
        print(qid, "取得失敗:", repr(ex))
        continue
    desc = e.get("descriptions", {})
    print("%-10s ja=%-28s en=%-45s desc_en=%s" % (
        qid,
        label(e, "ja") or "-",
        label(e, "en") or "-",
        (desc.get("en", {}).get("value") or "-")[:70],
    ))
    # 基準アイテムなら「どの基準か」を示すプロパティがないか見る
    if qid.startswith("Q2303"):
        print("     claims:", ", ".join(sorted(e["claims"].keys())))

# 自然遺産の例（イエローストーン? は決め打ちになるので、代わりにP2614の値集合を
# 「登録基準」プロパティのエンティティから辿る）
print("\n--- P2614 の制約情報から取りうる値を確認 ---")
p = entity("P2614")
for st in p["claims"].get("P2302", []):  # property constraint
    ctype = st["mainsnak"].get("datavalue", {}).get("value", {}).get("id")
    quals = st.get("qualifiers", {})
    if "P2305" in quals:  # item of property constraint
        vals = [s.get("datavalue", {}).get("value", {}).get("id") for s in quals["P2305"]]
        print("  制約", ctype, "許可値:", vals)
