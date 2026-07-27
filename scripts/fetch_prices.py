#!/usr/bin/env python3
"""Fetch adjusted daily closes, latest quotes and FX for every ticker referenced in
data/book.json, and write data/prices.json.

Stdlib only, no API keys — uses Yahoo Finance's keyless v8 chart API
(query1.finance.yahoo.com/v8/finance/chart). Returns are computed from *adjusted*
closes so splits/dividends never produce a fake step. Market-cap uses the v7 quote
endpoint if it is reachable, else degrades to null.

Usage:  python3 scripts/fetch_prices.py [--dry-run]
"""
import bisect
import http.cookiejar
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BOOK = os.path.join(ROOT, "data", "book.json")
OUT = os.path.join(ROOT, "data", "prices.json")

# market -> benchmark index (Yahoo symbol). Overridable per row later if needed.
BENCH = {
    "IN": "^CRSLDX",  # Nifty 500
    "TW": "^TWII",    # TAIEX
    "KR": "^KS11",    # KOSPI
    "US": "^GSPC",    # S&P 500
    "HK": "^HSI",     # Hang Seng
    "JP": "^N225",    # Nikkei 225
}
DEFAULT_BENCH = "^GSPC"
MKT_CCY = {"IN": "INR", "TW": "TWD", "KR": "KRW", "US": "USD", "HK": "HKD", "JP": "JPY"}

UA = "Mozilla/5.0 (global-research-portal price-fetch)"
HOSTS = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]


def _read(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        return urllib.request.urlopen(req, timeout=30).read()
    except ssl.SSLError:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return urllib.request.urlopen(req, timeout=30, context=ctx).read()


def yahoo_get(path):
    """GET a Yahoo API path (e.g. '/v8/finance/chart/AAPL?range=2y...').
    Rotates hosts and backs off on 429/5xx."""
    last = None
    for attempt in range(4):
        host = HOSTS[attempt % len(HOSTS)]
        try:
            return _read(f"https://{host}{path}")
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503):
                time.sleep(1.5 * (2 ** attempt))
                continue
            raise
        except Exception as e:  # noqa: BLE001 - transient network
            last = e
            time.sleep(1.0 * (attempt + 1))
    raise last if last else RuntimeError(f"yahoo_get failed: {path}")


def pct(a, b):
    if a is None or b in (None, 0):
        return None
    return round((a / b - 1) * 100, 2)


def on_or_before(dates_sorted, cmap, target):
    """Value at the latest date <= target (nearest prior trading day)."""
    i = bisect.bisect_right(dates_sorted, target) - 1
    return cmap[dates_sorted[i]] if i >= 0 else None


def fetch_chart(symbol):
    """Return (meta, {date: adjclose}) or (None, {}) on failure."""
    q = urllib.parse.quote(symbol, safe="^")  # encode & etc.; keep ^ for indices
    path = f"/v8/finance/chart/{q}?range=2y&interval=1d&events=div%2Csplit"
    try:
        data = json.loads(yahoo_get(path))
    except Exception as e:
        print(f"  ! {symbol}: fetch error {e}")
        return None, {}
    res = (data.get("chart") or {}).get("result")
    if not res:
        err = (data.get("chart") or {}).get("error")
        print(f"  ! {symbol}: no result ({err})")
        return None, {}
    r = res[0]
    meta = r.get("meta", {})
    ts = r.get("timestamp") or []
    ind = r.get("indicators", {})
    adj = None
    if ind.get("adjclose"):
        adj = ind["adjclose"][0].get("adjclose")
    raw = None
    if ind.get("quote"):
        raw = ind["quote"][0].get("close")
    series = adj or raw or []
    gmt = meta.get("gmtoffset") or 0
    cmap = {}
    for t, v in zip(ts, series):
        if v is None:
            continue
        d = datetime.fromtimestamp(t + gmt, tz=timezone.utc).strftime("%Y-%m-%d")
        cmap[d] = round(float(v), 4)
    return meta, cmap


def summarize(meta, cmap):
    # All % returns are computed from the (adjusted) close series for consistency.
    # NB: Yahoo's meta.chartPreviousClose is the close *before the whole range*, so it
    # must NOT be used for the 1-day move — use the second-to-last close instead.
    dates = sorted(cmap.keys())
    if not dates:
        return None
    last = cmap[dates[-1]]
    price = meta.get("regularMarketPrice") or last
    prev = cmap[dates[-2]] if len(dates) > 1 else None
    today = date.today()

    def ago(days):
        return (today - timedelta(days=days)).strftime("%Y-%m-%d")

    return {
        "price": round(price, 4),
        "prevClose": round(prev, 4) if prev else None,
        "currency": meta.get("currency"),
        "d1": pct(last, prev),
        "w1": pct(last, on_or_before(dates[:-1], cmap, ago(7))),
        "m1": pct(last, on_or_before(dates[:-1], cmap, ago(30))),
        "ytd": pct(last, on_or_before(dates[:-1], cmap, f"{today.year - 1}-12-31")),
        "asof": dates[-1],
    }


_CJ = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_CJ))
_OPENER.addheaders = [("User-Agent", UA)]


def _crumb():
    """Yahoo v7 quote needs a cookie + crumb; obtain both, or None if unavailable."""
    try:
        _OPENER.open("https://fc.yahoo.com/", timeout=15).read()
    except Exception:
        pass  # 404 is fine — the Set-Cookie still lands in the jar
    try:
        c = _OPENER.open("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=15).read()
        c = c.decode().strip()
        return c or None
    except Exception:
        return None


def fetch_mktcaps(symbols):
    """Best-effort market caps via the cookie+crumb v7 quote; {} if blocked."""
    if not symbols:
        return {}
    crumb = _crumb()
    if not crumb:
        print("  (market caps: no crumb — column will show '-')")
        return {}
    out = {}
    q = urllib.parse.quote(",".join(symbols), safe="^,-.")
    url = (f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={q}"
           f"&crumb={urllib.parse.quote(crumb, safe='')}")
    try:
        data = json.loads(_OPENER.open(url, timeout=30).read())
        for it in (data.get("quoteResponse") or {}).get("result", []):
            if it.get("marketCap") is not None:
                out[it.get("symbol")] = it["marketCap"]
    except Exception as e:
        print(f"  (market caps unavailable: {e})")
    return out


def main():
    dry = "--dry-run" in sys.argv
    with open(BOOK) as f:
        book = json.load(f)

    rows = book.get("holdings", []) + book.get("calls", []) + book.get("watchlist", [])
    tickers, markets = [], set()
    for r in rows:
        t = r.get("ticker")
        if t and t not in tickers:
            tickers.append(t)
        if r.get("market"):
            markets.add(r["market"])

    benchmarks = sorted({BENCH.get(m, DEFAULT_BENCH) for m in markets} or {DEFAULT_BENCH})
    fx_pairs = sorted({"USD" + MKT_CCY.get(m, "USD") for m in markets if MKT_CCY.get(m, "USD") != "USD"})

    print(f"Tickers: {len(tickers)} | benchmarks: {benchmarks} | fx: {fx_pairs}")

    quotes, closes, ok, bad = {}, {}, [], []
    for sym in tickers + benchmarks:
        meta, cmap = fetch_chart(sym)
        if cmap:
            closes[sym] = cmap
            s = summarize(meta, cmap)
            if s:
                quotes[sym] = s
            ok.append(sym)
        else:
            bad.append(sym)
        time.sleep(0.25)

    fx = {}
    for pair in fx_pairs:
        meta, cmap = fetch_chart(pair + "=X")
        if meta and meta.get("regularMarketPrice"):
            fx[pair] = round(meta["regularMarketPrice"], 4)
        elif cmap:
            fx[pair] = cmap[sorted(cmap)[-1]]
        time.sleep(0.25)

    caps = fetch_mktcaps(tickers)
    for sym, cap in caps.items():
        if sym in quotes:
            quotes[sym]["mktcap_native"] = cap

    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quotes": quotes,
        "closes": closes,
        "fx": fx,
    }

    print(f"OK: {len(ok)}  |  FAILED: {bad if bad else 'none'}  |  fx: {fx}  |  caps: {len(caps)}")
    if dry:
        print("(dry-run — not writing)")
        return
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"Wrote {OUT} ({os.path.getsize(OUT) // 1024} KB)")


if __name__ == "__main__":
    main()
