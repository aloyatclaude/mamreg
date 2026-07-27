#!/usr/bin/env python3
"""Audit every call in data/book.json against data/prices.json and print a report.

This is the *reference implementation* of the call-scoring methodology the front-end
mirrors, so it doubles as a cross-check. It recomputes each call's return, benchmark
return and alpha from adjusted closes and flags anything that would make a number
untrustworthy:

  ERROR  - ticker not in the price feed / no close near the entry (or exit) date
  ERROR  - exitDate before entryDate
  WARN   - benchmark missing for the row's market
  WARN   - >40% single-day jump in the series (possible unadjusted corporate action)
  WARN   - open call priced off a stale feed (>5 days old)

Scoring (matches the plan):
  entryPx = adjClose on-or-before entryDate  (falls back to the stored 'entry' price)
  endPx   = adjClose on-or-before exitDate (closed) or latest close (open)
  stockRet = endPx/entryPx - 1 ; benchRet likewise on the market benchmark ; alpha = stockRet - benchRet
  hit/miss: Buy hits if alpha>0, Sell hits if alpha<0, Hold excluded from the count.

Usage:  python3 scripts/verify_calls.py [--strict]   (--strict exits 1 on any ERROR)
"""
import bisect
import json
import os
import statistics
import sys
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BOOK = os.path.join(ROOT, "data", "book.json")
PRICES = os.path.join(ROOT, "data", "prices.json")

BENCH = {"IN": "^CRSLDX", "TW": "^TWII", "KR": "^KS11", "US": "^GSPC", "HK": "^HSI", "JP": "^N225"}
DEFAULT_BENCH = "^GSPC"


def on_or_before(dates_sorted, cmap, target):
    i = bisect.bisect_right(dates_sorted, target) - 1
    if i < 0:
        return None, None
    return dates_sorted[i], cmap[dates_sorted[i]]


def main():
    strict = "--strict" in sys.argv
    book = json.load(open(BOOK))
    prices = json.load(open(PRICES))
    closes = prices.get("closes", {})
    sorted_dates = {sym: sorted(cm) for sym, cm in closes.items()}
    feed_date = (prices.get("generated") or "")[:10]

    # pre-scan each series for suspicious single-day jumps (unadjusted splits)
    jumpy = set()
    for sym, cm in closes.items():
        ds = sorted_dates[sym]
        for a, b in zip(ds, ds[1:]):
            if cm[a] and abs(cm[b] / cm[a] - 1) > 0.40:
                jumpy.add(sym)
                break

    analysts = {a["id"]: a.get("name", a["id"]) for a in book.get("analysts", [])}
    rows, errors, warns = [], [], []

    for c in book.get("calls", []):
        cid, tk = c.get("id"), c.get("ticker")
        bench = BENCH.get(c.get("market"), DEFAULT_BENCH)
        entryDate = c.get("entryDate") or ""
        end_target = c.get("exitDate") or date.today().strftime("%Y-%m-%d")
        rec = {"id": cid, "analyst": analysts.get(c.get("analyst"), c.get("analyst")),
               "ticker": tk, "call": c.get("call"), "entryDate": entryDate,
               "endDate": end_target, "stockRet": None, "benchRet": None,
               "alpha": None, "result": "-", "flags": []}

        if tk not in closes:
            rec["flags"].append("ERROR no price feed for ticker")
            errors.append(f"{cid} {tk}: no price feed")
            rows.append(rec)
            continue
        if bench not in closes:
            rec["flags"].append("WARN benchmark missing")
            warns.append(f"{cid}: benchmark {bench} missing")
        if not entryDate:
            rec["flags"].append("ERROR no entryDate")
            errors.append(f"{cid} {tk}: no entryDate")
            rows.append(rec)
            continue
        if c.get("exitDate") and c["exitDate"] < entryDate:
            rec["flags"].append("ERROR exit before entry")
            errors.append(f"{cid} {tk}: exitDate<entryDate")

        ed, e_px = on_or_before(sorted_dates[tk], closes[tk], entryDate)
        xd, x_px = on_or_before(sorted_dates[tk], closes[tk], end_target)
        if e_px is None or x_px is None:
            rec["flags"].append("ERROR no close near entry/exit date")
            errors.append(f"{cid} {tk}: no close near {entryDate}/{end_target}")
            rows.append(rec)
            continue
        if not e_px and c.get("entry"):  # fallback to stated entry
            e_px = c["entry"]

        stock_ret = x_px / e_px - 1
        rec["stockRet"] = round(stock_ret * 100, 2)

        if bench in closes:
            _, be = on_or_before(sorted_dates[bench], closes[bench], entryDate)
            _, bx = on_or_before(sorted_dates[bench], closes[bench], end_target)
            if be and bx:
                bench_ret = bx / be - 1
                rec["benchRet"] = round(bench_ret * 100, 2)
                alpha = stock_ret - bench_ret
                rec["alpha"] = round(alpha * 100, 2)
                call = (c.get("call") or "").lower()
                if call == "buy":
                    rec["result"] = "HIT" if alpha > 0 else "MISS"
                elif call == "sell":
                    rec["result"] = "HIT" if alpha < 0 else "MISS"
                else:
                    rec["result"] = "n/a"  # Hold excluded

        if tk in jumpy:
            rec["flags"].append("WARN >40% single-day jump (check corporate action)")
            warns.append(f"{cid} {tk}: >40% single-day jump in series")
        if not c.get("exitDate") and feed_date and (datetime.strptime(feed_date, "%Y-%m-%d").date()
                                                     - date.today()).days < -5:
            rec["flags"].append("WARN stale feed")
        rows.append(rec)

    # ---- print report ----
    print(f"\nPrice feed generated: {prices.get('generated')}  |  calls: {len(rows)}\n")
    hdr = f"{'id':<4} {'analyst':<8} {'ticker':<14} {'call':<5} {'entry':<11} {'end':<11} " \
          f"{'stock%':>8} {'bench%':>8} {'alpha%':>8} {'result':<5} flags"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['id']:<4} {str(r['analyst'])[:8]:<8} {str(r['ticker'])[:14]:<14} "
              f"{str(r['call']):<5} {r['entryDate']:<11} {r['endDate']:<11} "
              f"{_n(r['stockRet']):>8} {_n(r['benchRet']):>8} {_n(r['alpha']):>8} "
              f"{r['result']:<5} {'; '.join(r['flags'])}")

    # ---- per-analyst cross-check ----
    print("\nPer-analyst scorecard (Buy/Sell scored; Hold excluded from hit-rate):")
    by = {}
    for r in rows:
        by.setdefault(r["analyst"], []).append(r)
    print(f"{'analyst':<10} {'calls':>5} {'scored':>6} {'hits':>5} {'hit%':>6} "
          f"{'avgRet%':>8} {'avgAlpha%':>10}")
    for name, rs in sorted(by.items()):
        scored = [r for r in rs if r["result"] in ("HIT", "MISS")]
        hits = sum(1 for r in scored if r["result"] == "HIT")
        alphas = [r["alpha"] for r in rs if r["alpha"] is not None]
        rets = [r["stockRet"] for r in rs if r["stockRet"] is not None]
        hitpct = f"{100*hits/len(scored):.0f}" if scored else "-"
        print(f"{str(name):<10} {len(rs):>5} {len(scored):>6} {hits:>5} {hitpct:>6} "
              f"{_n(round(statistics.mean(rets),2) if rets else None):>8} "
              f"{_n(round(statistics.mean(alphas),2) if alphas else None):>10}")

    print(f"\nSUMMARY: {len(errors)} error(s), {len(warns)} warning(s).")
    for e in errors:
        print("  ERROR:", e)
    for w in warns:
        print("  WARN :", w)
    if strict and errors:
        sys.exit(1)


def _n(v):
    return "-" if v is None else (f"+{v}" if v >= 0 else f"{v}")


if __name__ == "__main__":
    main()
