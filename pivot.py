# -*- coding: utf-8 -*-
"""
ヌルヌルFX チャートページ用の「今日のピボット」(GitHub Actionsで15分ごとに自動実行)

1時間足から、FXでふつうの区切り(ニューヨーク時間17時 = 日本時間の朝6時か7時)で
1日ずつにまとめ、前の日の高値・安値・終値からトラディショナルのピボットを計算して
pivot.json に書き出す。ワークフローが data ブランチに置き、chart.html が読む。

  P  = (高値 + 安値 + 終値) / 3
  R1 = 2P - 安値        S1 = 2P - 高値
  R2 = P + (高値 - 安値) S2 = P - (高値 - 安値)
  R3 = 高値 + 2(P - 安値) S3 = 安値 - 2(高値 - P)

ゴールドは Yahoo に現物(XAUUSD)の1時間足がないので、今は計算しない(先物だとチャートと値がずれるため)。
"""
import json
import sys
from datetime import datetime, timezone, timedelta

import pandas as pd

# chart.html の SYMBOLS と同じ銘柄(ゴールド以外)
PAIRS = ["USDJPY", "EURUSD", "EURJPY", "GBPJPY", "GBPUSD", "AUDJPY"]
NY = "America/New_York"


def session_key(idx):
    """NY17時で日付が変わるように7時間進めた日付 = その足が入る「1日」"""
    t = idx.tz_localize("UTC") if idx.tz is None else idx
    return (t.tz_convert(NY) + pd.Timedelta(hours=7)).date


def pivots(h, l, c):
    p = (h + l + c) / 3
    return {
        "R3": h + 2 * (p - l), "R2": p + (h - l), "R1": 2 * p - l,
        "P": p,
        "S1": 2 * p - h, "S2": p - (h - l), "S3": l - 2 * (h - p),
    }


def calc(df, now):
    """1銘柄ぶん。前の日(終わった1日)の高安終からピボットを出す"""
    df = df.dropna(subset=["High", "Low", "Close"])
    if df.empty:
        return None
    df = df.assign(day=session_key(df.index))
    cur = session_key(pd.DatetimeIndex([now]))[0]          # 今いる1日
    done = df[df["day"] < cur]                              # もう終わった日だけ
    if done.empty:
        return None
    prev_day = done["day"].max()
    d = done[done["day"] == prev_day]
    if len(d) < 12:  # 足が少なすぎる日(祝日など)は使わない
        days = sorted(done["day"].unique())
        for k in reversed(days[:-1]):
            d = done[done["day"] == k]
            if len(d) >= 12:
                prev_day = k
                break
        else:
            return None
    h, l, c = float(d["High"].max()), float(d["Low"].min()), float(d["Close"].iloc[-1])
    digits = 3 if "JPY" in df.attrs.get("name", "") else 5
    lv = {k: round(v, digits) for k, v in pivots(h, l, c).items()}
    return {
        "from": str(prev_day),                      # どの日の値から計算したか(NY17時区切りの日付)
        "high": round(h, digits), "low": round(l, digits), "close": round(c, digits),
        "levels": lv,
        "price": round(float(df["Close"].iloc[-1]), digits),   # 最新の値(15分ほど遅れることがある)
        "digits": digits,
    }


def main(out="pivot.json"):
    import yfinance as yf
    now = datetime.now(timezone.utc)
    raw = yf.download([p + "=X" for p in PAIRS], period="10d", interval="1h",
                      group_by="ticker", progress=False, auto_adjust=True, threads=True)
    res = {}
    for p in PAIRS:
        try:
            df = raw[p + "=X"].copy()
            df.attrs["name"] = p
            r = calc(df, now)
            if r:
                res[p] = r
        except Exception as e:  # 1銘柄の失敗で全体を止めない
            print(p, "error:", e, file=sys.stderr)
    if not res:
        print("ピボットを1つも計算できなかったので書き出しません", file=sys.stderr)
        sys.exit(1)
    data = {
        "updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "type": "traditional",
        "pivots": res,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"ok: {len(res)}銘柄")


if __name__ == "__main__":
    main(*sys.argv[1:])
