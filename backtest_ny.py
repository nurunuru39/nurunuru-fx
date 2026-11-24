# -*- coding: utf-8 -*-
"""
NY反転のバックテスト(サイトには出さない。GitHub Actions の「NY反転バックテスト」で手動実行する)

Yahoo Finance の1時間足を取れるだけ(約2年)さかのぼって、scan.py と同じ判定(ny_reversal_check)をする。
  ・判定する時刻:各平日の NYの開き+1時間 〜 NYの終わり(ニューヨーク時間17時)の1時間ごと
  ・NY反転が出たら、その時刻の値段で狙い目ペアに入る(同じ日・同じ通貨は最初の1回だけ)
  ・出口:4時間後 / 8時間後 / 翌日の東京時間(日本時間9時)
  ・逆行:入ってから翌日の東京時間までに、いちばん逆に動いた幅(1時間足の高値・安値)
くらべる相手(条件なし):
  同じ時間帯の同じ時刻に、24時間の強さの上位2・下位2の通貨について、
  NY反転と同じ組み合わせ(強い通貨は最弱通貨に対して買い、弱い通貨は最強通貨に対して売り)で
  ロンドン・NYの条件を見ずに入った場合。

使い方: python backtest_ny.py [出力フォルダ]
  出力フォルダに summary.md(日本語のまとめ)と trades.csv(1回ずつの結果)を書く。
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

import scan

HOUR = pd.Timedelta(hours=1)
JST = "Asia/Tokyo"


def pip_size(pair):
    return 0.01 if pair.endswith("JPY") else 0.0001


def load():
    import yfinance as yf
    tickers = [scan.SYMBOLS[p] for p in scan.PAIRS]
    start = (datetime.now(timezone.utc) - timedelta(days=729)).strftime("%Y-%m-%d")   # 1時間足は730日まで
    raw = yf.download(tickers, start=start, interval="1h", group_by="ticker",
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
    for key, ex in (("h4", t + 4 * HOUR), ("h8", t + 8 * HOUR), ("tokyo", tokyo)):
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


def run(frames):
    price_at = scan.price_finder(frames, HOUR)
    first = min(df.index[0] for df in frames.values())
    end = max(df.index[-1] for df in frames.values()) + HOUR
    day = (first + pd.Timedelta(days=2)).tz_convert(scan.NY).date()
    last = end.tz_convert(scan.NY).date()
    sig, base = [], []
    while day <= last:
        if day.weekday() < 5:
            _, nyo, nyc = scan.session_times(day)
            done = set()                 # この日に NY反転が出た通貨(最初の1回だけ数える)
            t = nyo + HOUR
            while t <= nyc and t <= end:
                r = scan.ny_reversal_check(price_at, t)
                if r["active"]:
                    rank = r["rank"]
                    for c in r["cands"]:
                        partner = rank[-1] if c["side"] == "strong" else rank[0]
                        if partner == c["cur"]:
                            continue
                        pair, buy_c = scan.pair_of(c["cur"], partner)
                        d = buy_c if c["side"] == "strong" else ("down" if buy_c == "up" else "up")
                        x = trade(frames, price_at, pair, d, t, end)
                        if x:
                            x.update(cur=c["cur"], side=c["side"])
                            base.append(x)
                    for h in r["hits"]:
                        if h["cur"] in done:
                            continue
                        done.add(h["cur"])
                        x = trade(frames, price_at, h["pair"], h["dir"], t, end)
                        if x:
                            x.update(cur=h["cur"], side=h["side"])
                            sig.append(x)
                t += HOUR
        day += timedelta(days=1)
    return pd.DataFrame(sig), pd.DataFrame(base), first, end


def stats(df):
    rows = []
    for key, label in (("h4", "4時間後"), ("h8", "8時間後"), ("tokyo", "翌日東京9時")):
        s = df[key]
        rows.append(f"| {label} | {len(s)} | {(s > 0).mean() * 100:.1f}% | {s.mean():+.1f} | {s.median():+.1f} | {s.min():+.1f} |")
    return rows


def summary(sig, base, first, end):
    out = ["# NY反転バックテスト", "",
           f"期間:{first.tz_convert(JST):%Y-%m-%d} 〜 {end.tz_convert(JST):%Y-%m-%d}(日本時間、Yahoo Finance の1時間足)", ""]
    for title, df in (("NY反転の印が出たとき", sig), ("条件なし(同じ時間帯・同じ組み合わせで毎時間入った場合)", base)):
        out += [f"## {title}", ""]
        if df.empty:
            out += ["(該当なし)", ""]
            continue
        out += ["| 出口 | 回数 | 勝率 | 平均pips | 中央値pips | 最悪pips |", "|---|---|---|---|---|---|"]
        out += stats(df)
        out += ["", f"翌日東京9時までの逆行:平均 {df['mae'].mean():.1f} pips / 最大 {df['mae'].max():.1f} pips"
                    f"({df.loc[df['mae'].idxmax(), 'pair']} {df.loc[df['mae'].idxmax(), 'time'].tz_convert(JST):%Y-%m-%d %H:%M})", ""]
        nyr = "のNY反転" if df is sig else ""
        for side, name in (("strong", f"強い通貨{nyr}(最弱通貨に対して買い)"), ("weak", f"弱い通貨{nyr}(最強通貨に対して売り)")):
            d = df[df["side"] == side]
            if len(d):
                out.append(f"- {name}:{len(d)}回、翌日東京9時の勝率 {(d['tokyo'] > 0).mean() * 100:.1f}%、平均 {d['tokyo'].mean():+.1f} pips")
        out.append("")
    out += ["※ pips は円がらみのペアは0.01円、それ以外は0.0001を1pipsとして計算。スプレッド・手数料は引いていない。",
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
    if not sig.empty:
        sig.assign(kind="signal").pipe(lambda d: pd.concat([d, base.assign(kind="base")])).to_csv(
            os.path.join(outdir, "trades.csv"), index=False)
    print(text)


if __name__ == "__main__":
    main(*sys.argv[1:])
