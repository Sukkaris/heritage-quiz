# -*- coding: utf-8 -*-
"""
段階②: raw/ のSPARQL結果を統合してマスタ(data.js)を生成し、検品レポートを出す。

判断のポイント（企画書§3.3・§3.5・§4・§5に対応）:
- 区分（文化/自然/複合）を直接持つプロパティはWikidataに存在しないため、
  登録基準 P2614（i〜vi=文化 / vii〜x=自然 / 両方=複合）から導出する。
- 世界遺産の構成資産（シャルトル大聖堂の一部…など）にもP1435=Q9259が付いており、
  そのまま数えると3,378件になる。UNESCOのID(P757)を持つものだけを「1件」とし、
  さらにID末尾の rev / bis / -001 等を落とした数値部分でグループ化して名寄せする。
"""
import io
import json
import os
import re
import statistics
import sys
import unicodedata
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "..", "raw")
OUT_JS = os.path.join(BASE, "..", "data.js")
REPORT = os.path.join(BASE, "..", "DATA_REPORT.md")

# --- 難易度の閾値（サイトリンク数の分位点）§5 ------------------------------
# ここを変えれば難易度の切り方が変わる。実データの分布から算出した値をdata.jsに書く。
EASY_QUANTILE = 0.75   # 上位25% = 易
HARD_QUANTILE = 0.25   # 下位25% = 難

# --- 大陸QID → 企画書§4.1の6地域 -------------------------------------------
CONTINENT_TO_REGION = {
    "Q48": "アジア",
    "Q46": "ヨーロッパ",
    "Q15": "アフリカ",
    "Q49": "北米",
    "Q18": "南米",
    "Q55643": "オセアニア",  # オセアニア
    "Q538": "オセアニア",    # オセアニア島嶼部
    "Q3960": "オセアニア",   # オーストラリア大陸
    "Q51": None,             # 南極（該当遺産があれば報告して手当て）
    "Q828": None,            # 「アメリカ大陸」= 粒度が粗いので単独では使わない
    "Q5401": None,           # ユーラシア = 同上
}

# 複数大陸にまたがる国の代表地域（P30が複数返る国の決着。判断根拠は
# 「その国の世界遺産が実際にどちら側に多く分布するか」ではなく、
#  一般的な地誌区分に合わせた。DATA_REPORT.md に一覧を出す）
COUNTRY_REGION_OVERRIDE = {
    "Q159": "ヨーロッパ",   # ロシア
    "Q43": "アジア",        # トルコ
    "Q79": "アフリカ",      # エジプト
    "Q232": "アジア",       # カザフスタン
    "Q399": "アジア",       # アルメニア
    "Q230": "アジア",       # ジョージア
    "Q227": "アジア",       # アゼルバイジャン
    "Q142": "ヨーロッパ",   # フランス（海外県で複数大陸を持つ）
    "Q145": "ヨーロッパ",   # イギリス
    "Q29": "ヨーロッパ",    # スペイン
    "Q55": "ヨーロッパ",    # オランダ
    "Q35": "ヨーロッパ",    # デンマーク
    "Q30": "北米",          # アメリカ合衆国
    "Q96": "北米",          # メキシコ
    "Q17": "アジア",        # 日本
    # P17（所在国）に国ではないものが入っているWikidata側の揺れへの手当て
    "Q18": "南米",          # 「南アメリカ」大陸が所在国として入っている遺産がある
    "Q15180": "ヨーロッパ",  # ソビエト連邦（歴史上の国。現代の所在国も併記されている）
    "Q12557": "アジア",     # モンゴル帝国（同上）
}

# 登録年として妥当な範囲。第1回登録は1978年。範囲外は「国立公園の設置年」等の
# 別の日付が P580 に紛れ込んでいるものなので、登録年としては採用しない。
YEAR_MIN, YEAR_MAX = 1978, 2026

CRIT_ORDER = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"]
CULTURAL = set(CRIT_ORDER[:6])
NATURAL = set(CRIT_ORDER[6:])


def load(name):
    path = os.path.join(RAW, name + ".json")
    if not os.path.exists(path):
        sys.exit("raw/%s.json がない。fetch_wikidata.py を先に実行すること。" % name)
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def qid(uri):
    return uri.rsplit("/", 1)[-1]


def main():
    # ---- 読み込み ----------------------------------------------------------
    items = defaultdict(dict)
    for r in load("items"):
        q = qid(r["item"]["value"])
        d = items[q]
        for k in ("ja", "en", "whsid"):
            if k in r:
                d[k] = r[k]["value"]
        if "sitelinks" in r:
            d["sitelinks"] = int(r["sitelinks"]["value"])
        if "date" in r:
            v = r["date"]["value"]
            if not v.startswith("-"):
                d.setdefault("years", set()).add(int(v[:4]))

    countries = defaultdict(set)
    for r in load("countries"):
        countries[qid(r["item"]["value"])].add(qid(r["country"]["value"]))

    crit_labels = {}
    with io.open(os.path.join(RAW, "criteria_labels.json"), encoding="utf-8") as f:
        for k, v in json.load(f).items():
            crit_labels[k] = (v["label"] or "").strip("()")

    criteria = defaultdict(set)
    for r in load("criteria"):
        c = crit_labels.get(qid(r["criterion"]["value"]))
        if c:
            criteria[qid(r["item"]["value"])].add(c)

    coords = {}
    for r in load("coords"):
        m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", r["coord"]["value"])
        if m:
            coords.setdefault(qid(r["item"]["value"]), [round(float(m.group(2)), 4), round(float(m.group(1)), 4)])

    danger = {qid(r["item"]["value"]) for r in load("in_danger")}

    jawiki = {}
    for r in load("jawiki"):
        jawiki[qid(r["item"]["value"])] = r["title"]["value"]

    # 日本語版Wikipediaの登録名から引いたQID（構成資産のIDしか持たない遺産の対応づけ用）
    jaqid_path = os.path.join(RAW, "jawiki_qid.json")
    jaqid = {}
    if os.path.exists(jaqid_path):
        with io.open(jaqid_path, encoding="utf-8") as f:
            jaqid = json.load(f)

    # 登録基準(i)〜(x)の日本語条文（テンプレート5で選択肢として出す）
    crit_ja_path = os.path.join(RAW, "criteria_ja.json")
    crit_ja = {}
    if os.path.exists(crit_ja_path):
        with io.open(crit_ja_path, encoding="utf-8") as f:
            crit_ja = json.load(f)

    # §3.4 日本語版Wikipedia「世界遺産の一覧」の登録名（UNESCO ID -> 日本語名）
    jalist_path = os.path.join(RAW, "jawiki_list.json")
    jalist = {}
    if os.path.exists(jalist_path):
        with io.open(jalist_path, encoding="utf-8") as f:
            jalist = json.load(f)

    # 国メタ（ラベル＋大陸）
    cmeta = {}
    for r in load("country_meta"):
        c = qid(r["country"]["value"])
        m = cmeta.setdefault(c, {"ja": None, "en": None, "continents": set()})
        if "ja" in r:
            m["ja"] = r["ja"]["value"]
        if "en" in r:
            m["en"] = r["en"]["value"]
        if "continent" in r:
            m["continents"].add(qid(r["continent"]["value"]))

    # ---- 国→地域の決定 -----------------------------------------------------
    country_out, ambiguous, no_region = {}, [], []
    for c, m in cmeta.items():
        regions = {CONTINENT_TO_REGION.get(x) for x in m["continents"]}
        regions.discard(None)
        if c in COUNTRY_REGION_OVERRIDE:
            region = COUNTRY_REGION_OVERRIDE[c]
            if len(regions) > 1:
                ambiguous.append((c, m["ja"] or m["en"], sorted(regions), region))
        elif len(regions) == 1:
            region = regions.pop()
        elif len(regions) > 1:
            region = sorted(regions)[0]
            ambiguous.append((c, m["ja"] or m["en"], sorted(regions), region + "（自動）"))
        else:
            region = None
            no_region.append((c, m["ja"] or m["en"], sorted(m["continents"])))
        country_out[c] = {"ja": m["ja"] or m["en"], "en": m["en"], "region": region}

    # UNESCO公式一覧（件数の答え合わせと、P757欠落の拾い直しに使う）
    unesco_path = os.path.join(RAW, "unesco_list.json")
    unesco = {}
    if os.path.exists(unesco_path):
        with io.open(unesco_path, encoding="utf-8") as f:
            unesco = json.load(f)

    # ---- WHS ID で名寄せ ---------------------------------------------------
    # P757 には遺産そのもののID（"669" "669bis" "620rev"）のほかに、
    # 構成資産のID（"868-062" = 巡礼路868の62番目 = アミアン大聖堂）も入っている。
    # 後者を遺産のIDとして扱うと、構成資産が親遺産を乗っ取る。数字＋rev/bis/ter/quater
    # だけを遺産のIDとみなし、ハイフン付きは構成資産として識別には使わない。
    SITE_ID = re.compile(r"^(\d+)(rev|bis|ter|quater)?$")

    groups = defaultdict(list)      # 遺産ID -> 候補アイテム
    parts = defaultdict(list)       # 遺産ID -> 構成資産アイテム
    no_whsid = []
    for q, d in items.items():
        if "whsid" not in d:
            no_whsid.append(q)
            continue
        m = SITE_ID.match(d["whsid"])
        if m:
            groups[m.group(1)].append(q)
        else:
            base = re.match(r"\d+", d["whsid"])
            if base:
                parts[base.group(0)].append(q)

    # ---- UNESCO公式のID一覧を「どの遺産が存在するか」の基準にする --------------
    rescued = []
    if unesco:
        official = set(unesco)

        def normalize(s):
            """比較用に英語名をならす（記号・発音記号・大小文字の差を吸収）"""
            s = re.sub(r"<[^>]+>", " ", s or "")
            s = unicodedata.normalize("NFKD", s)
            s = "".join(c for c in s if not unicodedata.combining(c))
            return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

        # 冠詞や前置詞の有無だけが違う名前を同一視するための、さらに緩い正規化
        STOP = {"of", "the", "a", "an", "and", "in", "at", "on", "its"}

        def loose(s):
            return " ".join(w for w in normalize(s).split() if w not in STOP)

        by_en = defaultdict(list)
        by_en_loose = defaultdict(list)
        for q, d in items.items():
            if d.get("en"):
                by_en[normalize(d["en"])].append(q)
                by_en_loose[loose(d["en"])].append(q)
        by_jatitle = defaultdict(list)
        for q, title in jawiki.items():
            by_jatitle[title].append(q)

        assigned, reps = {}, set()

        def take(wid, q, how=None):
            assigned[wid] = [q]
            reps.add(q)
            if how:
                rescued.append((wid, how, items[q].get("en") or items[q].get("ja"), q))

        # 1) 遺産IDが一致するアイテム（最優先）
        for wid in official:
            cands = groups.get(wid)
            if not cands:
                continue
            name = normalize(unesco[wid]["name"])
            cands.sort(key=lambda q: (normalize(items[q].get("en")) == name,
                                      "years" in items[q],
                                      items[q].get("sitelinks", 0)), reverse=True)
            take(wid, cands[0])

        # 2) IDが無いIDは、公式の英語名と完全一致するアイテムで拾う
        for wid in official - set(assigned):
            for q in by_en.get(normalize(unesco[wid]["name"]), []):
                if q not in reps:
                    take(wid, q, "公式英語名と一致")
                    break

        # 3) 日本語版Wikipediaの登録名から引いたQIDで拾う（リダイレクト解決済み）
        for wid in official - set(assigned):
            q = jaqid.get(wid)
            if q and q in items and q not in reps:
                take(wid, q, "jawiki一覧の登録名から引いたQID")

        # 4) 日本語版Wikipediaの記事名が登録名と一致するアイテムで拾う
        for wid in official - set(assigned):
            for q in by_jatitle.get(jalist.get(wid, "\0"), []):
                if q not in reps:
                    take(wid, q, "jawiki一覧の登録名と記事名が一致")
                    break

        # 5) 冠詞・前置詞の違いだけの英語名で拾う
        for wid in official - set(assigned):
            for q in by_en_loose.get(loose(unesco[wid]["name"]), []):
                if q not in reps:
                    take(wid, q, "公式英語名と（冠詞等を除いて）一致")
                    break

        # 併合対象（国・座標の補完に使う）: 同じIDの他アイテムと構成資産のうち、
        # 他の遺産の代表になっていないもの
        for wid in list(assigned):
            rep = assigned[wid][0]
            others = [q for q in groups.get(wid, []) + parts.get(wid, [])
                      if q != rep and q not in reps]
            assigned[wid] = [rep] + others

        dropped_ids = sorted(set(groups) - official)
        groups = assigned
    else:
        dropped_ids = []

    rescued_ids = {w for w, _, _, _ in rescued}
    sites = []
    year_anomalies = []
    for gid, members in groups.items():
        rep = members[0]
        d = items[rep]

        years = set()
        coset = set()
        # 登録基準は代表アイテムのものを使う（構成資産の基準が混ざらないように）。
        # 代表が持っていない場合だけ、同じIDの他のアイテムから補う。
        cset = set(criteria.get(rep, set()))
        for q in members:
            years |= items[q].get("years", set())
            coset |= countries.get(q, set())
            if not cset:
                cset |= criteria.get(q, set())

        # 日本語名は代表アイテムのものだけを使う（構成資産の名前が紛れ込まないように）
        ja, ja_source = items[rep].get("ja"), "wikidata"
        # 名前で拾い直した遺産は、アイテムのラベルが構成資産の名前になっていることが
        # ある（例: ID162 アミアン大聖堂 → ラベルは「ノートルダム大聖堂」）。
        # その場合は日本語版Wikipediaの登録名を優先する。
        if gid in rescued_ids and gid in jalist:
            ja, ja_source = jalist[gid], "jawiki一覧の登録名"
        if not ja and rep in jawiki:            # §3.4 補完1: 日本語版Wikipediaの記事名
            ja, ja_source = jawiki[rep], "jawiki記事名"
        if not ja and gid in jalist:            # §3.4 補完2: 「世界遺産の一覧」の登録名
            ja, ja_source = jalist[gid], "jawiki一覧の登録名"
        if not ja:
            ja_source = None

        u = unesco.get(gid, {})

        cats = ("cultural" if cset & CULTURAL else "") + ("natural" if cset & NATURAL else "")
        category = {"cultural": "文化", "natural": "自然", "culturalnatural": "複合"}.get(cats)
        cat_source = "登録基準から導出" if category else None
        if not category and u.get("category"):   # 基準が未登録の遺産は公式の区分を使う
            category, cat_source = u["category"], "UNESCO公式"

        regions = sorted({country_out[c]["region"] for c in coset if country_out.get(c, {}).get("region")})
        valid_years = sorted(y for y in years if YEAR_MIN <= y <= YEAR_MAX)
        if years and not valid_years:
            year_anomalies.append((ja or d.get("en"), sorted(years)))
        elif years and min(years) < YEAR_MIN:
            year_anomalies.append((ja or d.get("en"), sorted(years)))
        # 登録年は公式値を優先する（Wikidataには拡張登録の年などが混ざる）
        year = u.get("year") or (valid_years[0] if valid_years else None)

        sites.append({
            "qid": rep,
            "whsid": gid,
            "ja": ja,
            "en": d.get("en"),
            "hasJaLabel": bool(ja),
            "countries": sorted(coset),
            "regions": regions,
            "year": year,
            "criteria": sorted(cset, key=lambda x: CRIT_ORDER.index(x)),
            "category": category,
            "sitelinks": items[rep].get("sitelinks", 0),
            "coord": coords.get(rep) or next((coords[q] for q in members if q in coords), None),
            "inDanger": bool(u["danger"]) if u.get("danger") is not None else any(q in danger for q in members),
            "members": len(members),
            "jaSource": ja_source,
            "catSource": cat_source,
        })

    sites.sort(key=lambda s: (-s["sitelinks"], s["qid"]))

    # ---- 難易度の閾値 -------------------------------------------------------
    pool = sorted(s["sitelinks"] for s in sites if s["hasJaLabel"])
    def quantile(p):
        return int(statistics.quantiles(pool, n=100, method="inclusive")[max(0, min(98, int(p * 100) - 1))])
    easy_th, hard_th = quantile(EASY_QUANTILE), quantile(HARD_QUANTILE)

    # ---- 検品レポート §3.5 --------------------------------------------------
    L = []
    A = L.append
    A("# データ検品レポート")
    A("")
    A("生成元: Wikidata (CC0) / 取得スクリプト `tools/fetch_wikidata.py`")
    A("")
    A("## 件数")
    A("")
    A("| 項目 | 件数 |")
    A("|---|---|")
    A("| P1435=Q9259 を持つWikidataアイテム | %d |" % len(items))
    A("| うち UNESCO ID(P757) を持つ | %d |" % (len(items) - len(no_whsid)))
    A("| ID正規化後の遺産件数（本アプリのマスタ） | %d |" % len(sites))
    A("| 構成資産等としてマスタから除外 | %d |" % len(no_whsid))
    if unesco:
        A("| 公式一覧に無いIDとして除外 | %d |" % len(dropped_ids))
    A("")
    if unesco:
        A("遺産の単位はUNESCO公式一覧のIDに合わせている（%d件）。2026年登録は%d件。"
          % (len(unesco), sum(1 for s in sites if s["year"] == 2026)))
        if dropped_ids:
            A("")
            A("公式一覧に無いID: %s" % ", ".join(dropped_ids))
    A("")
    A("## 品質チェック")
    A("")
    nolabel = [s for s in sites if not s["hasJaLabel"]]
    src = defaultdict(int)
    for s in sites:
        src[s["jaSource"] or "なし"] += 1
    A("- 日本語名の取得元: " + " / ".join("%s %d件" % (k, v) for k, v in sorted(src.items(), key=lambda x: -x[1])))
    A("- 日本語ラベル欠落: **%d件**（出題対象から除外、データは保持）" % len(nolabel))
    noyear = [s for s in sites if s["year"] is None]
    A("- 登録年の欠損: **%d件**（出題対象から除外）" % len(noyear))
    A("- 登録年の異常値(1978年より前): **%d件** → %s。%d〜%d年の範囲外の日付は"
      "登録年として採用していない（国立公園の設置年などが P580 に混ざっているため）"
      % (len(year_anomalies), ", ".join("%s%s" % (n, ys) for n, ys in year_anomalies[:5]) or "なし",
         YEAR_MIN, YEAR_MAX))
    nocat = [s for s in sites if s["category"] is None]
    A("- 区分が導出できない（登録基準が未登録）: **%d件**" % len(nocat))
    nocountry = [s for s in sites if not s["countries"]]
    A("- 所在国の欠損: **%d件**" % len(nocountry))
    dup = len(sites) - len({s["qid"] for s in sites})
    A("- QIDの重複: **%d件**" % dup)
    A("- 座標あり: %d件 / 危機遺産: %d件 / 複数国にまたがる遺産: %d件"
      % (sum(1 for s in sites if s["coord"]), sum(1 for s in sites if s["inDanger"]),
         sum(1 for s in sites if len(s["countries"]) > 1)))
    eligible = [s for s in sites if s["hasJaLabel"] and s["year"] and s["category"] and s["countries"]]
    A("")
    A("→ **出題可能（日本語名・登録年・区分・所在国がすべて揃っている）: %d件**" % len(eligible))
    A("")
    A("## 区分の内訳（登録基準 i〜vi=文化 / vii〜x=自然 / 両方=複合 から導出）")
    A("")
    cnt = defaultdict(int)
    for s in sites:
        cnt[s["category"] or "不明"] += 1
    A("| 区分 | 本データ | UNESCO公式 |")
    A("|---|---|---|")
    for k in ("文化", "自然", "複合"):
        A("| %s | %d | %s |" % (k, cnt[k],
                                sum(1 for u in unesco.values() if u["category"] == k) if unesco else "-"))
    A("| 不明 | %d | - |" % cnt["不明"])
    A("")
    A("## UNESCO公式一覧との突き合わせ")
    A("")
    if not unesco:
        A("`raw/unesco_list.json` が無いため未実施（`tools/fetch_unesco_list.py` を実行する）。")
    else:
        ours = {s["whsid"] for s in sites}
        theirs = set(unesco)
        A("| 項目 | 本アプリ | UNESCO公式 |")
        A("|---|---|---|")
        A("| 総件数 | %d | %d |" % (len(sites), len(unesco)))
        for k in ("文化", "自然", "複合"):
            A("| %s | %d | %d |" % (k, sum(1 for s in sites if s["category"] == k),
                                     sum(1 for u in unesco.values() if u["category"] == k)))
        A("| 危機遺産 | %d | %d |" % (sum(1 for s in sites if s["inDanger"]),
                                      sum(1 for u in unesco.values() if u["danger"])))
        A("")
        extra_ids = sorted(ours - theirs, key=lambda x: (len(x), x))
        missing_ids = sorted(theirs - ours, key=lambda x: (len(x), x))
        A("- 公式に無いのに本アプリにある: **%d件**%s"
          % (len(extra_ids), ("　" + ", ".join(
              "%s(%s)" % (i, next((s["ja"] or s["en"] for s in sites if s["whsid"] == i), "?"))
              for i in extra_ids[:10])) if extra_ids else ""))
        A("- 公式にあるのに本アプリに無い: **%d件**%s"
          % (len(missing_ids), ("　" + ", ".join(
              "%s(%s)" % (i, unesco[i]["name"]) for i in missing_ids[:10])) if missing_ids else ""))
        if rescued:
            A("- WikidataのUNESCO IDが無い／構成資産のIDしか無いため、名前で拾い直した: **%d件**"
              % len(rescued))
            for w, how, n, q in rescued:
                A("  - %s: %s（%s）" % (w, n, how))
        A("")
        catmis = [(s, unesco[s["whsid"]]) for s in sites
                  if s["whsid"] in unesco and s["category"] and s["category"] != unesco[s["whsid"]]["category"]]
        yearmis = [(s, unesco[s["whsid"]]) for s in sites
                   if s["whsid"] in unesco and s["year"] and unesco[s["whsid"]]["year"]
                   and s["year"] != unesco[s["whsid"]]["year"]]
        A("- 区分が公式と食い違う: **%d件**" % len(catmis))
        for s, u in catmis[:15]:
            A("  - %s (%s): 本アプリ=%s / 公式=%s / 基準=%s"
              % (s["ja"] or s["en"], s["whsid"], s["category"], u["category"],
                 "".join("(%s)" % c for c in s["criteria"])))
        A("- 登録年が公式と食い違う: **%d件**" % len(yearmis))
        for s, u in yearmis[:15]:
            A("  - %s (%s): 本アプリ=%s / 公式=%s" % (s["ja"] or s["en"], s["whsid"], s["year"], u["year"]))
    A("")
    A("## 登録基準の分布（テンプレート5で使用）")
    A("")
    ccount = defaultdict(int)
    for s in sites:
        ccount[len(s["criteria"])] += 1
    A("| 基準の数 | 遺産数 |")
    A("|---|---|")
    for k in sorted(ccount):
        A("| %d個 | %d |" % (k, ccount[k]))
    A("")
    A("誤答を3つ確保するには基準が7個以下である必要がある（10個中）。"
      "8個以上は %d件で、この設問からは除外する。" % sum(v for k, v in ccount.items() if k >= 8))
    A("")
    A("## 地域の内訳")
    A("")
    rc = defaultdict(int)
    for s in sites:
        for r in (s["regions"] or ["不明"]):
            rc[r] += 1
    for k, v in sorted(rc.items(), key=lambda x: -x[1]):
        A("- %s: %d件" % (k, v))
    A("")
    if ambiguous:
        A("### 複数大陸にまたがる国の扱い（採用した代表地域）")
        A("")
        for c, name, rs, chosen in sorted(ambiguous, key=lambda x: x[1] or ""):
            A("- %s (%s): %s → **%s**" % (name, c, " / ".join(rs), chosen))
        A("")
    if no_region:
        A("### 地域を決定できなかった国")
        A("")
        for c, name, cont in no_region:
            A("- %s (%s) 大陸:%s" % (name, c, cont or "なし"))
        A("")
    A("## 難易度（サイトリンク数の分位点）")
    A("")
    A("- 出題対象(日本語ラベルあり)のサイトリンク数: 最小%d / 中央値%d / 最大%d"
      % (pool[0], int(statistics.median(pool)), pool[-1]))
    A("- 易 = %d以上（上位25%%） / 中 = %d〜%d / 難 = %d以下（下位25%%）"
      % (easy_th, hard_th + 1, easy_th - 1, hard_th))
    A("- 閾値は `data.js` の `DIFFICULTY` 定数1箇所にまとまっている")
    A("")
    A("## 日本語ラベルが無く出題対象外になった遺産（先頭20件）")
    A("")
    for s in nolabel[:20]:
        A("- %s (%s)" % (s["en"], s["qid"]))
    A("")
    A("残り %d件は DATA_REPORT の性質上省略。" % max(0, len(nolabel) - 20))

    with io.open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")

    # ---- data.js -----------------------------------------------------------
    for s in sites:
        s.pop("members", None)
        s.pop("jaSource", None)
        s.pop("catSource", None)
    js = [
        "// 世界遺産マスタ（自動生成 / tools/build_data.py）",
        "// 出典: Wikidata (CC0)。手で編集せず、再生成すること。",
        "// 将来ジャンルを差し替える場合は、このファイルだけを入れ替える。",
        "",
        "// 難易度の閾値（サイトリンク数）。ここだけ変えれば難易度の切り方が変わる。",
        "const DIFFICULTY = { easyMin: %d, hardMax: %d };" % (easy_th, hard_th),
        "",
        "// 国コード -> { ja, en, region }",
        "const COUNTRIES = " + json.dumps(country_out, ensure_ascii=False, sort_keys=True) + ";",
        "",
        "// 地域の一覧（出題フィルタの並び順）",
        'const REGIONS = ["アジア", "ヨーロッパ", "アフリカ", "北米", "南米", "オセアニア"];',
        "",
        "// 登録基準 i〜x の条文（出典: 日本語版Wikipedia『世界遺産』。",
        "// 世界遺産センター公式サイトの基準を翻訳・引用したもの）",
        "const CRITERIA_TEXT = " + json.dumps(crit_ja, ensure_ascii=False) + ";",
        "const CRITERIA_ORDER = " + json.dumps(CRIT_ORDER, ensure_ascii=False) + ";",
        "",
        "// 遺産マスタ",
        "const HERITAGE_DATA = [",
    ]
    for s in sites:
        js.append(json.dumps(s, ensure_ascii=False, sort_keys=True) + ",")
    js.append("];")
    js.append("")
    with io.open(OUT_JS, "w", encoding="utf-8") as f:
        f.write("\n".join(js))

    print("data.js: %d件" % len(sites))
    print("DATA_REPORT.md を出力")


if __name__ == "__main__":
    main()
