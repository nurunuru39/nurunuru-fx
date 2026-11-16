# -*- coding: utf-8 -*-
"""
ヌルヌルFX 経済指標カレンダー(GitHub Actionsで15分ごとに自動実行)

Forex Factory が配っている今週・来週の予定(JSON)を取ってきて、
重要度「高」の指標と祝日だけにしぼり、指標名を日本語にして calendar.json に書き出す。
取得に失敗したときは、data ブランチにある前回の calendar.json をそのまま使う。

※ ファイル名を calendar.py にすると Python の標準ライブラリ calendar とぶつかるので cal.py にしている。
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone

FEEDS = [
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
]
PREV = "https://raw.githubusercontent.com/nurunuru39/nurunuru-fx/data/calendar.json"
UA = {"User-Agent": "Mozilla/5.0 (nurunuru-fx calendar)"}

# ===== 指標名の日本語対応表 =====
# 「m/m」などの比較の種類や「Prelim」などの速報・確報の言葉を外したあとの名前で引く。
NAMES = {
    # 雇用
    "Non-Farm Employment Change": "非農業部門雇用者数(雇用統計)",
    "ADP Non-Farm Employment Change": "ADP雇用統計",
    "Unemployment Rate": "失業率",
    "Unemployment Claims": "新規失業保険申請件数",
    "Average Hourly Earnings": "平均時給",
    "JOLTS Job Openings": "JOLTS求人件数",
    "Employment Change": "雇用者数",
    "Claimant Count Change": "失業保険申請件数",
    "Average Earnings Index 3m/y": "平均賃金(3か月)",
    "Challenger Job Cuts": "チャレンジャー人員削減数",
    # 物価
    "CPI": "消費者物価指数",
    "Core CPI": "コアCPI",
    "Median CPI": "CPI中央値",
    "Trimmed CPI": "CPIトリム平均",
    "Trimmed Mean CPI": "CPIトリム平均",
    "Tokyo Core CPI": "東京都区部コアCPI",
    "National Core CPI": "全国コアCPI",
    "CPI Flash Estimate": "消費者物価指数(速報)",
    "Core CPI Flash Estimate": "コアCPI(速報)",
    "PPI": "生産者物価指数",
    "Core PPI": "コアPPI",
    "PCE Price Index": "PCEデフレーター",
    "Core PCE Price Index": "コアPCEデフレーター",
    "Employment Cost Index": "雇用コスト指数",
    "RPI": "小売物価指数",
    # 景気・生産
    "GDP": "GDP",
    "GDP Price Index": "GDPデフレーター",
    "Retail Sales": "小売売上高",
    "Core Retail Sales": "コア小売売上高",
    "ISM Manufacturing PMI": "ISM製造業景況指数",
    "ISM Services PMI": "ISM非製造業景況指数",
    "Manufacturing PMI": "製造業PMI",
    "Services PMI": "サービス業PMI",
    "Non-Manufacturing PMI": "非製造業PMI",
    "Caixin Manufacturing PMI": "財新 製造業PMI",
    "Caixin Services PMI": "財新 サービス業PMI",
    "Durable Goods Orders": "耐久財受注",
    "Core Durable Goods Orders": "コア耐久財受注",
    "Industrial Production": "鉱工業生産",
    "Industrial Production y/y": "鉱工業生産(前年比)",
    "Empire State Manufacturing Index": "NY連銀製造業景気指数",
    "Philly Fed Manufacturing Index": "フィラデルフィア連銀製造業景気指数",
    "Tankan Manufacturing Index": "日銀短観(大企業製造業)",
    "Tankan Non-Manufacturing Index": "日銀短観(大企業非製造業)",
    "Trade Balance": "貿易収支",
    "Current Account": "経常収支",
    "Ivey PMI": "Ivey購買部協会指数",
    "ifo Business Climate": "ifo景況感指数",
    "ZEW Economic Sentiment": "ZEW景況感指数",
    "Building Permits": "住宅建築許可件数",
    "Housing Starts": "住宅着工件数",
    "Existing Home Sales": "中古住宅販売件数",
    "New Home Sales": "新築住宅販売件数",
    "Pending Home Sales": "中古住宅販売保留",
    "CB Consumer Confidence": "コンファレンスボード消費者信頼感指数",
    "UoM Consumer Sentiment": "ミシガン大学消費者信頼感指数",
    "UoM Inflation Expectations": "ミシガン大学 期待インフレ率",
    "Inflation Expectations": "期待インフレ率",
    "Crude Oil Inventories": "原油在庫",
    "Federal Budget Balance": "財政収支",
    "Treasury Currency Report": "為替報告書",
    # 金融政策
    "Federal Funds Rate": "政策金利(FF金利)",
    "FOMC Statement": "FOMC声明",
    "FOMC Press Conference": "FOMC記者会見",
    "FOMC Meeting Minutes": "FOMC議事録",
    "FOMC Economic Projections": "FOMC経済見通し",
    "Main Refinancing Rate": "政策金利(ECB)",
    "Monetary Policy Statement": "金融政策声明",
    "ECB Press Conference": "ECB記者会見",
    "ECB Monetary Policy Meeting Accounts": "ECB議事要旨",
    "BOJ Policy Rate": "政策金利(日銀)",
    "BOJ Outlook Report": "日銀 展望レポート",
    "BOJ Press Conference": "日銀総裁 記者会見",
    "Monetary Policy Meeting Minutes": "金融政策決定会合 議事要旨",
    "Official Bank Rate": "政策金利(英中銀)",
    "MPC Official Bank Rate Votes": "英中銀 金利投票結果",
    "Monetary Policy Summary": "金融政策要旨",
    "BOE Monetary Policy Report": "英中銀 金融政策報告",
    "Cash Rate": "政策金利(豪中銀)",
    "RBA Rate Statement": "豪中銀 声明",
    "RBA Monetary Policy Statement": "豪中銀 金融政策報告",
    "RBA Press Conference": "豪中銀 記者会見",
    "Official Cash Rate": "政策金利(NZ中銀)",
    "RBNZ Rate Statement": "NZ中銀 声明",
    "RBNZ Monetary Policy Statement": "NZ中銀 金融政策報告",
    "RBNZ Press Conference": "NZ中銀 記者会見",
    "Overnight Rate": "政策金利(加中銀)",
    "BOC Rate Statement": "加中銀 声明",
    "BOC Monetary Policy Report": "加中銀 金融政策報告",
    "BOC Press Conference": "加中銀 記者会見",
    "SNB Policy Rate": "政策金利(スイス中銀)",
    "SNB Monetary Policy Assessment": "スイス中銀 金融政策評価",
    "SNB Press Conference": "スイス中銀 記者会見",
    "Loan Prime Rate": "ローンプライムレート",
    "1-y Loan Prime Rate": "1年物ローンプライムレート",
    "5-y Loan Prime Rate": "5年物ローンプライムレート",
    "Bank Holiday": "祝日(市場休場)",
    "French Bank Holiday": "仏 祝日",
    "German Bank Holiday": "独 祝日",
}

# 発言する人の肩書き
SPEAKERS = {
    "Fed Chair": "FRB議長",
    "Fed Chairman": "FRB議長",
    "FOMC Member": "FOMC委員",
    "Fed Vice Chair": "FRB副議長",
    "ECB President": "ECB総裁",
    "BOJ Gov": "日銀総裁",
    "BOE Gov": "英中銀総裁",
    "RBA Gov": "豪中銀総裁",
    "RBNZ Gov": "NZ中銀総裁",
    "BOC Gov": "加中銀総裁",
    "SNB Chairman": "スイス中銀総裁",
    "President": "大統領",
}

COUNTRY_ADJ = {"German": "独", "French": "仏", "Italian": "伊", "Spanish": "西"}
COMPARE = {"m/m": "前月比", "q/q": "前期比", "y/y": "前年比", "q/y": "前年同期比", "3m/3m": "3か月比"}
STAGE = {"Prelim": "速報", "Flash": "速報", "Advance": "速報", "Final": "確報", "Revised": "改定"}


def ja(title):
    """英語の指標名を日本語にする。わからない名前は英語のまま返す。"""
    t = title.strip()
    if t in NAMES:
        return NAMES[t]

    m = re.match(r"^(.*?)\s+Speaks$", t)
    if m:
        who = m.group(1)
        for k in sorted(SPEAKERS, key=len, reverse=True):
            if who == k or who.startswith(k + " "):
                name = who[len(k):].strip()
                return f"{SPEAKERS[k]}{'(' + name + ')' if name else ''} 発言"
        return f"{who} 発言"

    adj = cmp_ = stage = ""
    w = t.split(" ")
    if w and w[0] in COUNTRY_ADJ:
        adj = COUNTRY_ADJ[w.pop(0)] + " "
    if w and w[0] in STAGE:
        stage = STAGE[w.pop(0)]
    if w and w[-1] in COMPARE:
        cmp_ = COMPARE[w.pop()]
    base = " ".join(w)
    if base not in NAMES:
        return title
    extra = "・".join(x for x in (cmp_, stage) if x)
    return f"{adj}{NAMES[base]}{'(' + extra + ')' if extra else ''}"


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main(out="calendar.json"):
    events, ok = [], False
    for url in FEEDS:
        try:
            events += get(url)
            ok = True
        except Exception as e:  # 来週分はまだ出ていないこともある
            print(f"取得できなかった: {url} ({e})", file=sys.stderr)

    if not ok:
        try:
            data = get(PREV)
            print("前回の calendar.json を使います", file=sys.stderr)
        except Exception as e:
            print(f"前回分も取れなかったので書き出しません ({e})", file=sys.stderr)
            return
    else:
        seen, rows = set(), []
        for e in events:
            imp = e.get("impact", "")
            if imp not in ("High", "Holiday"):
                continue
            key = (e.get("date"), e.get("country"), e.get("title"))
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "date": e.get("date"),                 # 例 2026-11-20T08:30:00-05:00
                "country": e.get("country", ""),       # USD / JPY / EUR ...
                "title": e.get("title", ""),
                "title_ja": ja(e.get("title", "")),
                "holiday": imp == "Holiday",
                "forecast": e.get("forecast", ""),
                "previous": e.get("previous", ""),
            })
        rows.sort(key=lambda r: datetime.fromisoformat(r["date"]))
        data = {
            "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "Forex Factory",
            "events": rows,
        }
        unknown = sorted({r["title"] for r in rows if r["title"] == r["title_ja"]})
        if unknown:
            print("日本語にできなかった指標:", ", ".join(unknown), file=sys.stderr)

    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:])
