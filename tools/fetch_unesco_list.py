# -*- coding: utf-8 -*-
"""
UNESCO公式の世界遺産一覧（公開XML）を取得する。

用途は2つだけで、出題データそのものはWikidataから作る方針を変えない。
  1. 件数の答え合わせ（何件あるのが正しいか）
  2. WikidataにUNESCO ID(P757)が入っていない遺産を、英語名で突き合わせて拾い直す

出力: raw/unesco_list.json  { "1217": {name, category, year, states, iso}, ... }
"""
import io
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

URL = "https://whc.unesco.org/en/list/xml/"
UA = "HeritageQuizDataFetch/1.0 (personal study project)"
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "raw")
OUT = os.path.join(RAW, "unesco_list.json")


def text(row, tag):
    el = row.find(tag)
    return (el.text or "").strip() if el is not None else ""


def main():
    os.makedirs(RAW, exist_ok=True)
    if os.path.exists(OUT):
        print("取得済み:", OUT)
        return

    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    print("取得: %d bytes" % len(data))

    root = ET.fromstring(data)
    out = {}
    cats = {}
    for row in root.iter("row"):
        wid = text(row, "id_number")
        if not wid:
            continue
        cat = text(row, "category")
        cats[cat] = cats.get(cat, 0) + 1
        out[wid] = {
            "name": text(row, "site"),
            "category": {"Cultural": "文化", "Natural": "自然", "Mixed": "複合"}.get(cat, cat),
            "year": int(text(row, "date_inscribed") or 0) or None,
            "states": text(row, "states"),
            "iso": text(row, "iso_code"),
            "danger": text(row, "danger"),
        }

    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0, sort_keys=True)

    print("件数: %d" % len(out))
    print("区分の内訳:", cats)
    years = {}
    for v in out.values():
        if v["year"]:
            years[v["year"]] = years.get(v["year"], 0) + 1
    print("直近の登録年:", sorted(years.items())[-4:])
    print("危機遺産:", sum(1 for v in out.values() if v["danger"]))
    print("保存:", OUT)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
