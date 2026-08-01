# -*- coding: utf-8 -*-
"""
段階①-e: 登録基準(i)〜(x)の日本語条文を取得する（テンプレート5で使う）

Wikidataの基準アイテムの日本語説明は (iii) 以降にしか条文が入っていないため、
日本語版Wikipediaのテンプレート {{世界遺産基準条項|n}} を展開して条文を得る。
（この記事の記述は世界遺産センター公式サイトの基準を翻訳・引用したもの）

出力: raw/criteria_ja.json  { "i": "人類の創造的才能を表す傑作である。", ... }
"""
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

UA = "HeritageQuizDataFetch/1.0 (personal study project)"
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "raw")
OUT = os.path.join(RAW, "criteria_ja.json")
ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"]


def api(**params):
    params.setdefault("format", "json")
    params.setdefault("formatversion", "2")
    url = "https://ja.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    os.makedirs(RAW, exist_ok=True)
    if os.path.exists(OUT):
        print("取得済み:", OUT)
        return

    # 10個まとめて1回のリクエストで展開する
    marker = "@@%d@@"
    text = "".join(marker % (n + 1) + "{{世界遺産基準条項|%d}}" % (n + 1) for n in range(10))
    res = api(action="expandtemplates", text=text, prop="wikitext")
    expanded = res["expandtemplates"]["wikitext"]

    out = {}
    parts = re.split(r"@@(\d+)@@", expanded)[1:]
    for i in range(0, len(parts), 2):
        n = int(parts[i])
        body = parts[i + 1]
        body = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", "", body, flags=re.S)
        body = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", body)
        body = re.sub(r"\[\[([^\]]*)\]\]", r"\1", body)
        body = re.sub(r"''+", "", body)
        body = " ".join(body.split()).strip("『』 ")
        out[ROMAN[n - 1]] = body
        print("  (%s) %s" % (ROMAN[n - 1], body))

    if len(out) != 10 or any(not v for v in out.values()):
        sys.exit("10件そろわなかった。テンプレート名が変わった可能性がある: %r" % out)

    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("保存:", OUT)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
