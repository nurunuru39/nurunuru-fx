# -*- coding: utf-8 -*-
"""
NY反転(2段階)のバックテスト(サイトには出さない。GitHub Actions の「NY反転バックテスト」で手動実行する)

NYの開きから15分ごとに見る判定なので、Yahoo Finance の15分足を使う。
Yahoo の15分足は直近60日分しか取れないので、期間は約60日になる。
scan.py と同じ判定(ny_reversal_check)を、各平日の NYの開き+1時間までのデータで行い、
次の3つのタイミングで入った場合をくらべる。
  ・15分後:「NY反転の兆し」が出たとき(15分後に強さが戻った)
  ・30分後:「NY反転」になったとき(15分後・30分後とも戻ったまま)
  ・1時間後:1時間後まで戻ったまま(15・30・45・60分後すべて)
入ったペアは、NYの開きの時点の24時間の強さで決めた狙い目(強い通貨は最弱通貨に対して買い、
弱い通貨は最強通貨に対して売り)。出口は4時間後 / 8時間後 / 翌日の東京時間(日本時間9時)。
逆行は、入ってから翌日の東京時間までに、いちばん逆に動いた幅(15分足の高値・安値)。
ダマシの割合は、そのタイミングで入ったあと、1時間後までに強さがまた逆に戻った割合。
くらべる相手(条件なし):同じ日の同じタイミングで、24時間の強さの上位2・下位2の通貨について、
同じ組み合わせで、ロンドン・NYの条件を見ずに入った場合。

使い方: python backtest_ny.py [出力フォルダ]
  出力フォルダに summary.md(日本語のまとめ)と trades.csv(1回ずつの結果)を書く。
"""
import os
import sys
from datetime import timedelta

import pandas as pd

import scan

Q = pd.Timedelta(minutes=15)
JST = "Asia/Tokyo"
TIMINGS = [(15, "15分後(兆し)"), (30, "30分後(NY反転)"), (60, "1時間後(確定)")]


def pip_size(pair):
    return 0.01 if pair.endswith("JPY") else 0.0001


def load():
    import yfinance as yf
    tickers = [scan.SYMBOLS[p] for p in scan.PAIRS]
    raw = yf.download(tickers, period="60d", interval="15m", group_by="ticker",
                      progress=False, auto_adjust=True, threads=True)
    frames = {}
    for p in scan.PAIRS:
        try:
            df = raw[scan.SYMBOLS[p]][["Open", "High", "Low", "Close"]].dropna()
        except KeyError:
            continue
        if df.empty:
            continue
        df.index = df.index.tz_localize("UTC") if df.index.tz is None else df.index.tz_convert("UTC")
        frames[p] = df
    return frames


def next_tokyo(t):
    """t のあとの、いちばん近い日本時間9時(UTC)"""
    j = t.tz_convert(JST)
    nine = j.normalize() + pd.Timedelta(hours=9)
    if nine <= j:
        nine += pd.Timedelta(days=1)
    return nine.tz_convert("UTC")


def trade(frames, price_at, pair, d, t, end):
    """t に pair を d(up=買い/down=売り)で入ったときの結果(pips)。データが足りなければ None"""
    entry = price_at(pair, t)
    if not entry:
        return None
    sign = 1 if d == "up" else -1
    pip = pip_size(pair)
    tokyo = next_tokyo(t)
    if tokyo > end:
        return None
    res = {"pair": pair, "dir": d, "time": t, "entry": entry}
    for key, ex in (("h4", t + pd.Timedelta(hours=4)), ("h8", t + pd.Timedelta(hours=8)), ("tokyo", tokyo)):
        p = price_at(pair, ex)
        if not p:
            return None
        res[key] = (p - entry) / pip * sign
    bars = frames[pair]
    win = bars[(bars.index >= t) & (bars.index < tokyo)]
    if win.empty:
        res["mae"] = 0.0
    elif d == "up":
        res["mae"] = max(0.0, (entry - float(win["Low"].min())) / pip)
    else:
        res["mae"] = max(0.0, (float(win["High"].max()) - entry) / pip)
    return res


def target(rank, cur, side):
    """狙い目のペアと向き。相手がいなければ None"""
    partner = rank[-1] if side == "strong" else rank[0]
    if partner == cur:
        return None
    pair, buy_c = scan.pair_of(cur, partner)
    return pair, (buy_c if side == "strong" else ("down" if buy_c == "up" else "up"))


def run(frames):
    price_at = scan.price_finder(frames, Q)
    first = min(df.index[0] for df in frames.values())
    end = max(df.index[-1] for df in frames.values()) + Q
    day = (first + pd.Timedelta(days=2)).tz_convert(scan.NY).date()
    last = end.tz_convert(scan.NY).date()
    sig, base = [], []
    while day <= last:
        if day.weekday() < 5:
            _, nyo, _ = scan.session_times(day)
            upto = nyo + pd.Timedelta(minutes=scan.NYREV_CHECKS[-1])
            r = scan.ny_reversal_check(price_at, day, upto) if upto <= end else {"active": False}
            if r["active"] and r.get("checked") == scan.NYREV_CHECKS[-1]:
                for c in r["cands"]:
                    tg = target(r["rank"], c["cur"], c["side"])
                    if not tg:
                        continue
                    pair, d = tg
                    sgn = 1 if c["side"] == "strong" else -1
                    vals = {x["min"]: x["v"] * sgn for x in c["checks"]}     # その通貨の向きで見た強さ
                    london_ok = c["london"] * sgn < 0
                    for m, label in TIMINGS:
                        t = nyo + pd.Timedelta(minutes=m)
                        x = trade(frames, price_at, pair, d, t, end)
                        if not x:
                            continue
                        x.update(cur=c["cur"], side=c["side"], timing=m, day=str(day))
                        base.append(dict(x))
                        upto_m = [k for k in scan.NYREV_CHECKS if k <= m]
                        if london_ok and all(vals[k] > 0 for k in upto_m):
                            after = [k for k in scan.NYREV_CHECKS if k > m]
                            x["fake"] = any(vals[k] <= 0 for k in after)
                            sig.append(x)
        day += timedelta(days=1)
    sig = pd.DataFrame(sig).drop_duplicates(subset=["pair", "dir", "time"]) if sig else pd.DataFrame()
    base = pd.DataFrame(base).drop_duplicates(subset=["pair", "dir", "time"]) if base else pd.DataFrame()
    return sig, base, first, end


def table(df, with_fake):
    head = "| タイミング | 回数 | 出口 | 勝率 | 平均pips | 最悪pips | 最大逆行pips |" + (" ダマシの割合 |" if with_fake else "")
    rows = [head, "|---|---|---|---|---|---|---|" + ("---|" if with_fake else "")]
    for m, label in TIMINGS:
        d = df[df["timing"] == m] if not df.empty else df
        if d.empty:
            rows.append(f"| {label} | 0 | - | - | - | - | - |" + (" - |" if with_fake else ""))
            continue
        fake = ""
        if with_fake:
            fake = " -(確定なので無し) |" if m == scan.NYREV_CHECKS[-1] else f" {d['fake'].mean() * 100:.0f}% |"
        for i, (key, ex) in enumerate((("h4", "4時間後"), ("h8", "8時間後"), ("tokyo", "翌日東京9時"))):
            s = d[key]
            rows.append(f"| {label if i == 0 else ''} | {len(d) if i == 0 else ''} | {ex} | {(s > 0).mean() * 100:.0f}% | {s.mean():+.1f} | {s.min():+.1f} | "
                        f"{d['mae'].max():.0f} |" + (fake if i == 0 else (" |" if with_fake else "")))
    return rows


def summary(sig, base, first, end):
    days = base["day"].nunique() if not base.empty else 0
    out = ["# NY反転(2段階)バックテスト", "",
           f"期間:{first.tz_convert(JST):%Y-%m-%d} 〜 {end.tz_convert(JST):%Y-%m-%d}(日本時間、Yahoo Finance の15分足。判定できた平日 {days}日)", "",
           "## NY反転の条件がそろったとき", ""]
    out += table(sig, True) if not sig.empty else ["(該当なし)"]
    out += ["", "## 条件なし(同じ日・同じタイミング・同じ組み合わせ)", ""]
    out += table(base, False) if not base.empty else ["(該当なし)"]
    out += ["", "最大逆行は、入ってから翌日東京9時までに、いちばん逆に動いた幅。",
            "※ pips は円がらみのペアは0.01円、それ以外は0.0001を1pipsとして計算。スプレッド・手数料は引いていない。",
            "※ 週末をまたぐ出口は、金曜の最後の値段で計算している。"]
    return "\n".join(out)


def main(outdir="backtest_out"):
    os.makedirs(outdir, exist_ok=True)
    frames = load()
    if len(frames) < len(scan.PAIRS):
        print("取れなかったペア:", sorted(set(scan.PAIRS) - set(frames)), file=sys.stderr)
    sig, base, first, end = run(frames)
    text = summary(sig, base, first, end)
    with open(os.path.join(outdir, "summary.md"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    parts = [d.assign(kind=k) for d, k in ((sig, "signal"), (base, "base")) if not d.empty]
    if parts:
        pd.concat(parts).to_csv(os.path.join(outdir, "trades.csv"), index=False)
    print(text)


if __name__ == "__main__":
    main(*sys.argv[1:])
