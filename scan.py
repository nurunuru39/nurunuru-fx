# -*- coding: utf-8 -*-
"""
ヌルヌルFX 押し目スキャナー(GitHub Actionsで15分ごとに自動実行)

判定ルール(pullback.html の説明と同じ):
  1. 4時間足と1時間足の向きがそろっている(EMA20とEMA50の並び+価格がEMA50の外側)
  2. ADX(14)が4時間足・1時間足ともに基準以上
  3. 15分足で押し目(戻り)を作っている(戻り率50〜78.6%)
  4. 直前に確定した15分足に反転サイン(反発・包み足・ピンバー)

結果は scan.json に書き出し、ワークフローが data ブランチに置く。

あわせて、money.html のタートルズ方式ロット計算で使う ATR も scan.json の "atr" に入れる:
  d1    日足ATR(20)(確定した日足だけで計算)
  h1    1時間足ATR(20)(確定した1時間足だけで計算)
  today 今日の値動き(今日の日足の真の値幅)
  ratio today ÷ d1(1.5を超えたら「荒れている」注意)

日足ピボット(クラシック)も全銘柄で計算して、各銘柄の "pivot" に入れる:
  前日 = FXでふつうの区切り(ニューヨーク時間17時)で区切った1日。1時間足から作る。
  P  = (高値 + 安値 + 終値) / 3
  R1 = 2P - 安値          S1 = 2P - 高値
  R2 = P + (高値 - 安値)   S2 = P - (高値 - 安値)
  R3 = 高値 + 2(P - 安値)  S3 = 安値 - 2(高値 - P)
  現在値にいちばん近いピボットの名前・値・距離(距離 ÷ 1時間足ATR も)を入れ、
  1時間足ATR(20)の PIVOT_NEAR 倍以内なら「ピボット付近」(near)とする。
  押し目ゾーン/エントリー候補で、押し目方向のピボット(買いは P・S1〜S3、売りは P・R1〜R3)の
  付近なら「根拠重なり」(confluence)とする。判定(状態)そのものは変えない。

4時間足のSMA200(200本の単純移動平均)も全銘柄で計算して、各銘柄の "sma200" に入れる:
  4時間足は1時間足から作る(to_4h)。終値200本の平均。
  現在値との距離(距離 ÷ 1時間足ATR も)を入れ、ピボットと同じく
  1時間足ATR(20)の PIVOT_NEAR 倍以内なら「200SMA付近」(near)とする。
  押し目ゾーン/エントリー候補で、買いなら SMA200 の少し上(現在値 ≧ SMA200)、
  売りなら SMA200 の少し下(現在値 ≦ SMA200)の付近にいるときも「根拠重なり」とする。
  根拠重なりの元になったもの(例 ["S1", "SMA200"])は "confluence_by" に入れる。

通貨強弱(8通貨 USD・EUR・JPY・GBP・AUD・NZD・CAD・CHF)を scan.json の "strength" に入れる:
  各通貨が入っている7つのペアの変化率(%)を、その通貨の目線にそろえて平均したものが点数。
  (EUR/USD が +0.2% なら、EUR は +0.2、USD は −0.2 として数える)
  期間は「直近24時間」(h24)と「直近1時間」(h1)。15分足の最新の終値と、その時間前の終値をくらべる。
  24時間の点数で強い順に並べ、上から STRENGTH_TOP 通貨を「強い」、下から STRENGTH_TOP 通貨を「弱い」とする。
  各銘柄の "strength" には、2つの通貨の点数・順位と、
  押し目買いなら「強い通貨/弱い通貨」、戻り売りなら「弱い通貨/強い通貨」のとき ok=true(強弱OK)を入れる。
  24時間で強いのに1時間の点数がマイナスの通貨は「押し目中?」(pullback)とする。
  強弱は表示用で、状態(エントリー候補など)の判定は変えない。

通貨シリーズ(円・ドル・ユーロ・ポンド・豪ドル)を scan.json の "series" に入れる:
  各ペアの直近24時間の変化率(15分足)から、上がった(up)・下がった(down)・ほとんど動いていない(flat)を出す。
  ほとんど動いていない = 値動きの幅が日足ATR(20)の SERIES_FLAT 倍より小さい(ATRがなければ0.05%未満)。
  その通貨の目線(左にあればペアの向きのまま、右にあれば逆)で、シリーズの SERIES_ALL 以上が
  同じ向きなら「全面高」「全面安」とする(全部なら「全面高」、8割以上なら「ほぼ全面高」)。

NY反転(scan.json の "strength" の "ny"):
  ロンドンの開き = ロンドン時間8時、ニューヨークの開き = ニューヨーク時間8時、NYの終わり = ニューヨーク時間17時。
  どれも夏時間に合わせて計算する(日本時間では、ロンドン16時/17時、NY21時/22時、NYの終わり6時/7時)。
  判定するのは、NYが開いて1時間たってから、NYの終わりまで。強さはどれも「その通貨の7ペアの変化率の平均」。
  強いほう:24時間の強さが上位 NYREV_TOP(2)通貨で、
    ① ロンドンの開き → NYの開きの強さがマイナス(ロンドンで売られた)
    ② 直近1時間の強さがプラス(NYでまた買われた)
  弱いほう:24時間の強さが下位 NYREV_TOP(2)通貨で、上の①②の符号を逆にしたもの。
  当てはまった通貨は「NY反転」。狙い目は、強いほうなら最弱通貨とのペアを買う向き、
  弱いほうなら最強通貨とのペアを売る向き。そのペアが押し目ゾーン/エントリー候補で、
  方向も同じなら「根拠重なり」(confluence_by に "NY反転")にする。
  同じ判定を backtest_ny.py が過去の1時間足で確かめる(ny_reversal_check を共通で使う)。

1日の通貨強弱(scan.json の "strength" の "day"):
  その日の始まり(ニューヨーク時間17時 = 日本時間朝7時、夏は6時)から15分ごとに、
  始まりからの8通貨の強さ(7ペアの変化率の平均)を、毎回15分足からまとめて計算する(過去の分は保存しない)。
  東京(日本時間9時)・ロンドン(ロンドン時間8時)・ニューヨーク(ニューヨーク時間8時)の開く時刻も入れる。
  ロンドンが開いたあと、ロンドンの開きの時点の最強通貨がいま最弱になったか、
  最弱通貨がいま最強になったら「ロンドンで強弱が逆転」(flip)とする。
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
ATR_N = 20            # タートルズのN(ATR)の期間
PIVOT_NEAR = 0.3      # ピボット・SMA200の付近とみなす距離(1時間足ATRの何倍以内か)
SMA_N = 200           # 4時間足の単純移動平均の本数
CURRENCIES = ["USD", "EUR", "JPY", "GBP", "AUD", "NZD", "CAD", "CHF"]   # 通貨強弱の8通貨
STRENGTH_TOP = 3      # 強弱の上位・下位それぞれ何通貨を「強い」「弱い」とするか
SERIES = [            # 通貨シリーズ(通貨, 表示名, ペア)
    ("JPY", "円", ["USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY", "CADJPY", "CHFJPY"]),
    ("USD", "ドル", ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCHF", "USDCAD"]),
    ("EUR", "ユーロ", ["EURUSD", "EURJPY", "EURGBP", "EURAUD", "EURNZD", "EURCAD", "EURCHF"]),
    ("GBP", "ポンド", ["GBPUSD", "GBPJPY", "EURGBP", "GBPAUD", "GBPNZD", "GBPCAD", "GBPCHF"]),
    ("AUD", "豪ドル", ["AUDUSD", "AUDJPY", "EURAUD", "GBPAUD", "AUDNZD", "AUDCAD", "AUDCHF"]),
]
SERIES_FLAT = 0.1     # 24時間の値動きが日足ATRのこの倍より小さければ「ほとんど動いていない」(→)
SERIES_ALL = 0.8      # シリーズのこの割合以上が同じ向きなら「全面高/全面安」
NYREV_TOP = 2         # NY反転を見る、24時間の強さの上位・下位の通貨の数
LONDON = "Europe/London"
PIVOT_MIN_BARS = 12   # 前日の1時間足がこれより少ない日(祝日など)はとばして、その前の日を使う
NY = "America/New_York"

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


def atr(df, n=ATR_N):
    """ATR(真の値幅の平均)。タートルズと同じく N = (前のN × 19 + 今日の値幅) ÷ 20 の平滑化"""
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean(), tr


def sig5(x):
    """有効数字5けたに丸める(銘柄ごとに桁がちがうため)"""
    return float(f"{x:.5g}")


def atr_info(dd, d1h):
    """日足・1時間足のATRと、今日の値動き。足りなければ None"""
    dd = dd[["Open", "High", "Low", "Close"]].dropna()
    d1h = d1h[["Open", "High", "Low", "Close"]].dropna()
    if len(dd) < ATR_N + 2 or len(d1h) < ATR_N + 2:
        return None
    a_d, tr_d = atr(dd)
    a_h, _ = atr(d1h)
    d1 = float(a_d.iloc[-2])      # 最後の日足は今日(作成中)なので、その前日までの確定値
    h1 = float(a_h.iloc[-2])      # 最後の1時間足も作成中のことがあるので除く
    today = float(tr_d.iloc[-1])
    if not (d1 > 0 and h1 > 0) or math.isnan(today):
        return None
    return {
        "d1": sig5(d1), "h1": sig5(h1), "today": sig5(today),
        "ratio": round(today / d1, 2),
        "close": sig5(float(dd["Close"].iloc[-1])),
        "day": dd.index[-1].strftime("%Y-%m-%d"),
    }


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


def session_day(idx):
    """ニューヨーク時間17時で日付が変わるようにした「1日」の日付(NY時間を7時間進めた日付)"""
    t = idx.tz_localize("UTC") if idx.tz is None else idx
    return (t.tz_convert(NY) + pd.Timedelta(hours=7)).date


def pivot_levels(h, l, c):
    p = (h + l + c) / 3
    return {
        "R3": h + 2 * (p - l), "R2": p + (h - l), "R1": 2 * p - l,
        "P": p,
        "S1": 2 * p - h, "S2": p - (h - l), "S3": l - 2 * (h - p),
    }


def h1_atr(d1h):
    """確定した1時間足のATR(20)。最後の1時間足は作成中のことがあるので除く"""
    a_h, _ = atr(d1h)
    return float(a_h.iloc[-2])


def pivot_info(d1h, price, h1, now=None):
    """前日(NY17時区切り)の高安終からピボットを出し、現在値にいちばん近いものを返す。足りなければ None"""
    if now is None:
        now = datetime.now(timezone.utc)
    df = d1h.assign(day=session_day(d1h.index))
    cur = session_day(pd.DatetimeIndex([pd.Timestamp(now)]))[0]   # いまいる1日
    done = df[df["day"] < cur]                                     # もう終わった日だけ
    prev = None
    for day in sorted(done["day"].unique(), reverse=True)[:5]:
        d = done[done["day"] == day]
        if len(d) >= PIVOT_MIN_BARS:
            prev = (day, d)
            break
    if prev is None:
        return None
    day, d = prev
    h, l, c = float(d["High"].max()), float(d["Low"].min()), float(d["Close"].iloc[-1])
    lv = pivot_levels(h, l, c)
    name = min(lv, key=lambda k: abs(price - lv[k]))
    dist = price - lv[name]        # プラスなら現在値がピボットより上
    ratio = abs(dist) / h1 if h1 > 0 else float("nan")
    return {
        "from": str(day),
        "levels": {k: sig5(v) for k, v in lv.items()},
        "name": name, "level": sig5(lv[name]),
        "dist": sig5(dist),
        "dist_atr": None if math.isnan(ratio) else round(ratio, 2),
        "near": bool(ratio <= PIVOT_NEAR),
        "atr_h1": sig5(h1),
    }


def sma_info(d4h, price, h1):
    """4時間足の終値のSMA200と、現在値からの距離。本数が足りなければ None"""
    c = d4h["Close"]
    if len(c) < SMA_N:
        return None
    v = float(c.rolling(SMA_N).mean().iloc[-1])
    dist = price - v               # プラスなら現在値がSMA200より上
    ratio = abs(dist) / h1 if h1 > 0 else float("nan")
    return {
        "value": sig5(v),
        "dist": sig5(dist),
        "dist_atr": None if math.isnan(ratio) else round(ratio, 2),
        "near": bool(ratio <= PIVOT_NEAR),
        "above": bool(dist >= 0),
    }


def analyze(name, d1h, d15):
    d1h = d1h[["Open", "High", "Low", "Close"]].dropna()
    d15 = d15[["Open", "High", "Low", "Close"]].dropna()
    if len(d1h) < 120 or len(d15) < SWING_BARS + 3:
        return None
    d4h = to_4h(d1h)
    if len(d4h) < 60:
        return None
    h1 = h1_atr(d1h)

    t4, t1 = trend(d4h), trend(d1h)
    a4, a1 = float(adx(d4h).iloc[-1]), float(adx(d1h).iloc[-1])
    price = float(d15["Close"].iloc[-1])
    item = {
        "name": name, "price": price,
        "adx4": round(a4, 1), "adx1": round(a1, 1),
        "dir": t4 if (t4 and t4 == t1) else None,
        "ret": None, "signal": None, "status": "対象外",
        "pivot": None, "sma200": None, "confluence": False, "confluence_by": [],
    }
    try:
        item["pivot"] = pivot_info(d1h, price, h1)
    except Exception as e:  # ピボットが出せなくても押し目スキャンは続ける
        print(name, "pivot error:", e, file=sys.stderr)
    try:
        item["sma200"] = sma_info(d4h, price, h1)
    except Exception as e:  # SMA200が出せなくても押し目スキャンは続ける
        print(name, "sma200 error:", e, file=sys.stderr)
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

    # 根拠重なり:押し目ゾーン/エントリー候補で、押し目方向のピボットかSMA200の付近
    if item["status"] in ("エントリー候補", "押し目ゾーン"):
        by = []
        pv = item["pivot"]
        if pv and pv["near"]:
            side = ("P", "S1", "S2", "S3") if item["dir"] == "up" else ("P", "R1", "R2", "R3")
            if pv["name"] in side:
                by.append(pv["name"])
        sm = item["sma200"]
        if sm and sm["near"] and sm["above"] == (item["dir"] == "up"):
            by.append("SMA200")      # 買いは少し上、売りは少し下にいるときだけ
        item["confluence_by"] = by
        item["confluence"] = bool(by)
    return item


def pct_change(d15, hours):
    """15分足の最新の終値と、hours 時間前の終値をくらべた変化率(%)。足りなければ None"""
    c = d15["Close"].dropna()
    if len(c) < 2:
        return None
    base = c[c.index <= c.index[-1] - pd.Timedelta(hours=hours)]
    if base.empty:
        return None
    b = float(base.iloc[-1])
    return (float(c.iloc[-1]) / b - 1) * 100 if b > 0 else None


def currency_strength(m15):
    """8通貨の強弱。m15 は {ペア名: 15分足} 。通貨がそろわなければ None"""
    out = {}
    for key, hours in (("h24", 24), ("h1", 1)):
        sums = {c: [] for c in CURRENCIES}
        for pair, d15 in m15.items():
            b, q = pair[:3], pair[3:]
            if b not in sums or q not in sums:
                continue
            try:
                ch = pct_change(d15, hours)
            except Exception as e:
                print(pair, "strength error:", e, file=sys.stderr)
                ch = None
            if ch is None or math.isnan(ch):
                continue
            sums[b].append(ch)        # ペアが上がる = 左の通貨が強い
            sums[q].append(-ch)       # ペアが上がる = 右の通貨が弱い
        if any(not v for v in sums.values()):
            return None
        out[key] = {c: round(sum(v) / len(v), 3) for c, v in sums.items()}
        out[key + "_n"] = {c: len(v) for c, v in sums.items()}   # 使えたペアの数(ふつうは7)
    order = sorted(CURRENCIES, key=lambda c: -out["h24"][c])
    out["rank"] = order                                           # 24時間で強い順
    out["strong"] = order[:STRENGTH_TOP]
    out["weak"] = order[-STRENGTH_TOP:]
    out["pullback"] = [c for c in out["strong"] if out["h1"][c] < 0]   # 押し目中?
    return out


def strength_for(item, st):
    """銘柄ごとの強弱。通貨ペアでない(ゴールドなど)か、強弱がなければ None"""
    b, q = item["name"][:3], item["name"][3:]
    if not st or b not in st["h24"] or q not in st["h24"]:
        return None
    rank = st["rank"]
    if item["dir"] == "up":
        ok = b in st["strong"] and q in st["weak"]
    elif item["dir"] == "down":
        ok = b in st["weak"] and q in st["strong"]
    else:
        ok = False
    return {
        "base": b, "quote": q,
        "base_score": st["h24"][b], "quote_score": st["h24"][q],
        "base_rank": rank.index(b) + 1, "quote_rank": rank.index(q) + 1,
        "ok": ok,
    }


def series_info(m15, atrs):
    """通貨シリーズ。m15 は {ペア名: 15分足}、atrs は main の ATR({ペア名: {"d1", "close"}})"""
    out = []
    for cur, label, pairs in SERIES:
        rows, up, down = [], 0, 0
        for pair in pairs:
            ch = None
            try:
                if pair in m15:
                    ch = pct_change(m15[pair], 24)
            except Exception as e:
                print(pair, "series error:", e, file=sys.stderr)
            if ch is None or math.isnan(ch):
                rows.append({"name": pair, "chg": None, "dir": None})
                continue
            a = atrs.get(pair)
            if a and a.get("d1") and a.get("close"):
                flat = abs(ch) / 100 * a["close"] < a["d1"] * SERIES_FLAT
            else:
                flat = abs(ch) < 0.05
            d = "flat" if flat else ("up" if ch > 0 else "down")
            rows.append({"name": pair, "chg": round(ch, 3), "dir": d})
            if d != "flat":
                mine = d if pair[:3] == cur else ("down" if d == "up" else "up")   # その通貨の目線の向き
                if mine == "up":
                    up += 1
                else:
                    down += 1
        n = len(pairs)
        state, msg = None, None
        for side, cnt, word in (("up", up, "高"), ("down", down, "安")):
            if cnt >= math.ceil(n * SERIES_ALL - 1e-9):
                state = side
                msg = label + "が" + ("全面" if cnt == n else "ほぼ全面") + word
        out.append({"cur": cur, "label": label, "pairs": rows, "up": up, "down": down,
                    "total": n, "state": state, "all": state is not None and max(up, down) == n, "msg": msg})
    return out


# ===== NY反転 =====
def session_times(day):
    """NYの日付 day の、ロンドンの開き・NYの開き・NYの終わり(UTC)。夏時間はタイムゾーンで自動"""
    def at(tz, h):
        return pd.Timestamp(datetime(day.year, day.month, day.day, h)).tz_localize(tz).tz_convert("UTC")
    return at(LONDON, 8), at(NY, 8), at(NY, 17)


def price_finder(frames, bar):
    """frames = {ペア名: OHLC} から「時刻 t の値段」を返す関数を作る(t 以前に終わった足の終値)。
    bar は足の長さ(15分足なら 15min)。足の時刻は始まりの時刻なので、終わり = 始まり + bar"""
    closes = {}
    for pair, df in frames.items():
        c = df["Close"].dropna()
        if c.empty:
            continue
        idx = c.index if c.index.tz is not None else c.index.tz_localize("UTC")
        closes[pair] = pd.Series(c.values, index=idx.tz_convert("UTC") + bar)

    def price_at(pair, t):
        c = closes.get(pair)
        if c is None:
            return None
        i = c.index.searchsorted(t, side="right") - 1
        return float(c.iloc[i]) if i >= 0 else None
    return price_at


def strength_between(price_at, t0, t1):
    """t0 → t1 の8通貨の強さ(各通貨の7ペアの変化率(%)を通貨の目線にそろえた平均)。足りなければ None"""
    sums = {c: [] for c in CURRENCIES}
    for pair in PAIRS:
        a, b = price_at(pair, t0), price_at(pair, t1)
        if not a or not b:
            continue
        ch = (b / a - 1) * 100
        sums[pair[:3]].append(ch)
        sums[pair[3:]].append(-ch)
    if any(not v for v in sums.values()):
        return None
    return {c: sum(v) / len(v) for c, v in sums.items()}


def pair_of(a, b):
    """通貨 a と b のペア名と、a を買う向き(up/down)"""
    if a + b in PAIRS:
        return a + b, "up"
    return b + a, "down"


def ny_reversal_check(price_at, t):
    """時刻 t(UTC)の NY反転の判定。NYの時間でなければ active=False"""
    t = pd.Timestamp(t)
    t = t.tz_localize("UTC") if t.tz is None else t.tz_convert("UTC")
    day = t.tz_convert(NY).date()
    lon, nyo, nyc = session_times(day)
    out = {"day": str(day), "london": lon, "ny_open": nyo, "ny_close": nyc,
           "active": day.weekday() < 5 and nyo + pd.Timedelta(hours=1) <= t <= nyc,
           "cands": [], "hits": []}
    if not out["active"]:
        return out
    s24 = strength_between(price_at, t - pd.Timedelta(hours=24), t)
    slon = strength_between(price_at, lon, nyo)
    s1 = strength_between(price_at, t - pd.Timedelta(hours=1), t)
    if not (s24 and slon and s1):
        out["active"] = False
        return out
    rank = sorted(CURRENCIES, key=lambda c: -s24[c])
    seen = set()
    for side, group in (("strong", rank[:NYREV_TOP]), ("weak", rank[-NYREV_TOP:])):
        for c in group:
            hit = slon[c] < 0 < s1[c] if side == "strong" else slon[c] > 0 > s1[c]
            out["cands"].append({"cur": c, "side": side, "london": round(slon[c], 3), "h1": round(s1[c], 3), "hit": hit})
            if not hit:
                continue
            partner = rank[-1] if side == "strong" else rank[0]
            if partner == c:
                continue
            pair, buy_c = pair_of(c, partner)
            d = buy_c if side == "strong" else ("down" if buy_c == "up" else "up")
            if (pair, d) in seen:
                continue
            seen.add((pair, d))
            out["hits"].append({"cur": c, "side": side, "partner": partner, "pair": pair, "dir": d})
    out["rank"] = rank
    return out


def intraday_strength(m15, now=None):
    """その日の始まり(NY17時)から15分ごとの8通貨の強さ。足りなければ None"""
    q = pd.Timedelta(minutes=15)
    price_at = price_finder(m15, q)
    last = max((df["Close"].dropna().index[-1] for df in m15.values() if not df["Close"].dropna().empty), default=None)
    if last is None:
        return None
    last = (last.tz_localize("UTC") if last.tz is None else last.tz_convert("UTC")) + q    # 最後の足の終わり
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    now = now.tz_localize("UTC") if now.tz is None else now.tz_convert("UTC")
    end = min(now, last).floor("15min")
    ny_end = end.tz_convert(NY)
    start = ny_end.normalize() + pd.Timedelta(hours=17)       # NY17時
    if start >= ny_end:
        start -= pd.Timedelta(days=1)
    start = start.tz_convert("UTC")
    trade_day = (start + pd.Timedelta(days=1)).tz_convert(NY).date()
    lon, nyo, _ = session_times(trade_day)
    tokyo = start.tz_convert("Asia/Tokyo").normalize() + pd.Timedelta(hours=9)
    if tokyo <= start.tz_convert("Asia/Tokyo"):
        tokyo += pd.Timedelta(days=1)
    tokyo = tokyo.tz_convert("UTC")
    times, series = [], {c: [] for c in CURRENCIES}
    t = start
    while t <= end:
        sb = strength_between(price_at, start, t)
        if sb:
            times.append(t)
            for c in CURRENCIES:
                series[c].append(round(sb[c], 3))
        t += q
    if len(times) < 2:
        return None
    jst = lambda x: x.tz_convert("Asia/Tokyo").strftime("%H:%M")
    out = {
        "start": start.tz_convert("Asia/Tokyo").strftime("%m/%d %H:%M"),
        "times": [jst(x) for x in times],
        "series": series,
        "marks": [{"name": n, "time": jst(m), "i": int((m - start) / q)}
                  for n, m in (("東京", tokyo), ("ロンドン", lon), ("NY", nyo))],
        "flip": None,
    }
    # ロンドンで強弱が逆転
    li = int((lon - start) / q)
    if li < len(times) - 1 and times[li] == lon:
        at_lon = {c: series[c][li] for c in CURRENCIES}
        now_v = {c: series[c][-1] for c in CURRENCIES}
        s_lon, w_lon = max(at_lon, key=at_lon.get), min(at_lon, key=at_lon.get)
        s_now, w_now = max(now_v, key=now_v.get), min(now_v, key=now_v.get)
        msg = []
        if s_now == w_lon:
            msg.append(f"{w_lon}が最弱→最強")
        if w_now == s_lon:
            msg.append(f"{s_lon}が最強→最弱")
        if msg:
            out["flip"] = "ロンドンで強弱が逆転(" + "、".join(msg) + ")"
    return out


def ny_reversal_live(m15, now=None):
    """いまの NY反転(scan.json 用。時刻は日本時間の文字列にする)"""
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    r = ny_reversal_check(price_finder(m15, pd.Timedelta(minutes=15)), now)
    for k in ("london", "ny_open", "ny_close"):
        r[k] = r[k].tz_convert("Asia/Tokyo").strftime("%m/%d %H:%M")
    return r


def fetch():
    import yfinance as yf
    tickers = list(SYMBOLS.values())
    kw = dict(group_by="ticker", progress=False, auto_adjust=True, threads=True)
    # 4時間足のSMA200に200本以上いるので、1時間足は120日分とる(4時間足でおよそ500本)
    h1 = yf.download(tickers, period="120d", interval="1h", **kw)
    m15 = yf.download(tickers, period="5d", interval="15m", **kw)
    try:
        d1 = yf.download(tickers, period="6mo", interval="1d", **kw)
    except Exception as e:  # 日足が取れなくても押し目スキャンは続ける
        print("daily error:", e, file=sys.stderr)
        d1 = None
    return h1, m15, d1


def main(out="scan.json"):
    h1, m15, d1 = fetch()
    items, errors = [], []
    atrs = {}
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
        try:
            if d1 is not None:
                a = atr_info(d1[tk], h1[tk])
                if a:
                    atrs[name] = a
        except Exception as e:
            print(name, "atr error:", e, file=sys.stderr)
    st = None
    try:
        st = currency_strength({n: m15[tk][["Close"]] for n, tk in SYMBOLS.items() if n in PAIRS})
    except Exception as e:  # 強弱が出せなくても押し目スキャンは続ける
        print("strength error:", e, file=sys.stderr)
    for x in items:
        x["strength"] = strength_for(x, st)
    if st:
        try:
            st["ny"] = ny_reversal_live({n: m15[tk] for n, tk in SYMBOLS.items() if n in PAIRS})
        except Exception as e:  # NY反転が出せなくても押し目スキャンは続ける
            print("ny reversal error:", e, file=sys.stderr)
            st["ny"] = None
        hits = {h["pair"]: h for h in ((st.get("ny") or {}).get("hits") or [])}
        for x in items:
            h = hits.get(x["name"])
            x["ny_reversal"] = h
            # 押し目ゾーン/エントリー候補で、方向もそろっていれば根拠重なり
            if h and x["status"] in ("エントリー候補", "押し目ゾーン") and x["dir"] == h["dir"]:
                x["confluence_by"] = x.get("confluence_by", []) + ["NY反転"]
                x["confluence"] = True
    if st:
        try:
            st["day"] = intraday_strength({n: m15[tk] for n, tk in SYMBOLS.items() if n in PAIRS})
        except Exception as e:  # 1日のグラフが出せなくても押し目スキャンは続ける
            print("intraday error:", e, file=sys.stderr)
            st["day"] = None
    series = None
    try:
        series = series_info({n: m15[tk][["Close"]] for n, tk in SYMBOLS.items() if n in PAIRS}, atrs)
    except Exception as e:  # シリーズが出せなくても押し目スキャンは続ける
        print("series error:", e, file=sys.stderr)
    order = {"エントリー候補": 0, "押し目ゾーン": 1, "監視": 2, "対象外": 3}
    items.sort(key=lambda x: (order[x["status"]], -(x["adx4"] or 0)))
    data = {
        "updated": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
        "updated_ts": int(datetime.now(timezone.utc).timestamp()),
        "rules": {"adx_min": ADX_MIN, "ret_min": RET_MIN, "ret_max": RET_MAX, "pivot_near": PIVOT_NEAR, "sma_n": SMA_N, "strength_top": STRENGTH_TOP,
                  "series_flat": SERIES_FLAT, "series_all": SERIES_ALL, "nyrev_top": NYREV_TOP},
        "items": items, "errors": errors,
        "atr_n": ATR_N, "atr": atrs,
        "strength": st,
        "series": series,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"ok: {len(items)}銘柄 / 取得失敗 {len(errors)} / ATR {len(atrs)}銘柄")
    if not items:
        sys.exit(1)


if __name__ == "__main__":
    main(*sys.argv[1:])
