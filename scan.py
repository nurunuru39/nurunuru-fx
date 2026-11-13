# -*- coding: utf-8 -*-
"""
ヌルヌルFX 押し目スキャナー(GitHub Actionsで15分ごとに自動実行)

判定ルール(pullback.html の説明と同じ):
  1. 4時間足と1時間足の向きがそろっている(EMA20とEMA50の並び+価格がEMA50の外側)
  2. ADX(14)が4時間足・1時間足ともに基準以上
  3. 15分足で押し目(戻り)を作っている(戻り率50〜78.6%)
  4. 直前に確定した15分足に反転サイン(反発・包み足・ピンバー)

結果は scan.json に書き出し、ワークフローが data ブランチに置く。
"""
import json
import math
import sys
from datetime import datetime, timezone, timedelta

import pandas as pd

# ===== 設定 =====
ADX_MIN = 20          # ADXの基準
RET_MIN = 50.0        # 押し目ゾーンの下限(%)
RET_MAX = 78.6        # 押し目ゾーンの上限(%)
SWING_BARS = 48       # 押し目を測る15分足の本数(48本=12時間)

PAIRS = [
    "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDJPY", "USDCHF", "USDCAD",
    "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY", "CADJPY", "CHFJPY",
    "EURGBP", "EURAUD", "EURNZD", "EURCAD", "EURCHF",
    "GBPAUD", "GBPNZD", "GBPCAD", "GBPCHF",
    "AUDNZD", "AUDCAD", "AUDCHF", "NZDCAD", "NZDCHF", "CADCHF",
]
SYMBOLS = {p: p + "=X" for p in PAIRS}
SYMBOLS["XAUUSD"] = "GC=F"   # ゴールド(先物で代用)
SYMBOLS["XAGUSD"] = "SI=F"   # シルバー(先物で代用)

JST = timezone(timedelta(hours=9))


# ===== 指標 =====
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def adx(df, n=14):
    h, l, c = df["High"], df["Low"], df["Close"]
    up = h.diff()
    dn = -l.diff()
    plus_dm = up.where((up > dn) & (up > 0), 0.0)
    minus_dm = dn.where((dn > up) & (dn > 0), 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    a = 1.0 / n
    atr = tr.ewm(alpha=a, adjust=False).mean()
    pdi = 100 * plus_dm.ewm(alpha=a, adjust=False).mean() / atr
    mdi = 100 * minus_dm.ewm(alpha=a, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, float("nan"))
    return dx.ewm(alpha=a, adjust=False).mean()


def trend(df):
    """'up' / 'down' / None"""
    c = df["Close"]
    e20, e50 = ema(c, 20).iloc[-1], ema(c, 50).iloc[-1]
    last = c.iloc[-1]
    if e20 > e50 and last > e50:
        return "up"
    if e20 < e50 and last < e50:
        return "down"
    return None


def to_4h(df1h):
    return df1h.resample("4h").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
    ).dropna()


def signal(prev, bar, direction):
    """直前に確定した足のサイン。なければ None"""
    o, h, l, c = bar["Open"], bar["High"], bar["Low"], bar["Close"]
    po, pc, ph, pl = prev["Open"], prev["Close"], prev["High"], prev["Low"]
    rng = h - l
    if rng <= 0:
        return None
    body = abs(c - o)
    if direction == "up":
        if c > o and pc < po and c >= po and o <= pc:
            return "包み足"
        lower = min(o, c) - l
        if lower >= body * 2 and lower >= rng * 0.6 and c >= l + rng * 0.66:
            return "ピンバー"
        if c > o and c > ph:
            return "反発"
    else:
        if c < o and pc > po and c <= po and o >= pc:
            return "包み足"
        upper = h - max(o, c)
        if upper >= body * 2 and upper >= rng * 0.6 and c <= h - rng * 0.66:
            return "ピンバー"
        if c < o and c < pl:
            return "反発"
    return None


def analyze(name, d1h, d15):
    d1h = d1h[["Open", "High", "Low", "Close"]].dropna()
    d15 = d15[["Open", "High", "Low", "Close"]].dropna()
    if len(d1h) < 120 or len(d15) < SWING_BARS + 3:
        return None
    d4h = to_4h(d1h)
    if len(d4h) < 60:
        return None

    t4, t1 = trend(d4h), trend(d1h)
    a4, a1 = float(adx(d4h).iloc[-1]), float(adx(d1h).iloc[-1])
    price = float(d15["Close"].iloc[-1])
    item = {
        "name": name, "price": price,
        "adx4": round(a4, 1), "adx1": round(a1, 1),
        "dir": t4 if (t4 and t4 == t1) else None,
        "ret": None, "signal": None, "status": "対象外",
    }
    if not item["dir"]:
        item["reason"] = "4時間足と1時間足の向きがそろっていない"
        return item
    if math.isnan(a4) or math.isnan(a1) or a4 < ADX_MIN or a1 < ADX_MIN:
        item["reason"] = "ADXが基準未満(レンジの可能性)"
        return item

    # 確定した足だけで押し目を測る(最後の足は作成中のことがあるため除く)
    # 直近SWING_BARS本の中の高値(安値)を探し、その起点となる安値(高値)は
    # さらに前のSWING_BARS本までさかのぼって探す
    closed = d15.iloc[:-1]
    n = len(closed)
    start = n - SWING_BARS
    if item["dir"] == "up":
        i = start + int(closed["High"].iloc[start:].values.argmax())
        hi = float(closed["High"].iloc[i])
        lo = float(closed["Low"].iloc[max(0, i - SWING_BARS * 2): i + 1].min())
        ret = (hi - price) / (hi - lo) * 100 if hi > lo else 0.0
    else:
        i = start + int(closed["Low"].iloc[start:].values.argmin())
        lo = float(closed["Low"].iloc[i])
        hi = float(closed["High"].iloc[max(0, i - SWING_BARS * 2): i + 1].max())
        ret = (price - lo) / (hi - lo) * 100 if hi > lo else 0.0
    item["ret"] = round(ret, 1)
    item["swing_hi"], item["swing_lo"] = hi, lo
    sig = signal(closed.iloc[-2], closed.iloc[-1], item["dir"])

    # サインは押し目ゾーンに入っているときだけ数える(浅い押しでの反発は高値づかみになりやすい)
    if ret > RET_MAX:
        item["status"] = "対象外"
        item["reason"] = "戻りが深すぎる(トレンド崩れの可能性)"
    elif ret >= RET_MIN:
        item["signal"] = sig
        item["status"] = "エントリー候補" if sig else "押し目ゾーン"
    else:
        item["status"] = "監視"
    return item


def fetch():
    import yfinance as yf
    tickers = list(SYMBOLS.values())
    kw = dict(group_by="ticker", progress=False, auto_adjust=True, threads=True)
    h1 = yf.download(tickers, period="60d", interval="1h", **kw)
    m15 = yf.download(tickers, period="5d", interval="15m", **kw)
    return h1, m15


def main(out="scan.json"):
    h1, m15 = fetch()
    items, errors = [], []
    for name, tk in SYMBOLS.items():
        try:
            r = analyze(name, h1[tk], m15[tk])
            if r:
                items.append(r)
            else:
                errors.append(name)
        except Exception as e:  # 1銘柄の失敗で全体を止めない
            errors.append(name)
            print(name, "error:", e, file=sys.stderr)
    order = {"エントリー候補": 0, "押し目ゾーン": 1, "監視": 2, "対象外": 3}
    items.sort(key=lambda x: (order[x["status"]], -(x["adx4"] or 0)))
    data = {
        "updated": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
        "updated_ts": int(datetime.now(timezone.utc).timestamp()),
        "rules": {"adx_min": ADX_MIN, "ret_min": RET_MIN, "ret_max": RET_MAX},
        "items": items, "errors": errors,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"ok: {len(items)}銘柄 / 取得失敗 {len(errors)}")
    if not items:
        sys.exit(1)


if __name__ == "__main__":
    main(*sys.argv[1:])
