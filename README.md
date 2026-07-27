# Global Research Portal — calls & per-analyst KPI tracker

A single-page dashboard for one investment book across **any market** (India, Taiwan,
Korea, US, HK, Japan…), tracking:

- **Holdings** — live positions, weight, mkt-cap, 1D/1W/1M/YTD, return vs cost basis.
- **Watchlist** — names we follow, stance, target and upside.
- **Calls** — every Buy/Sell/Hold call with return, benchmark and relative outperformance.
- **Analysts** — a per-analyst scorecard: hit rate, average alpha, cumulative alpha, drill-down.

No backend. It's a static `index.html` served from **GitHub Pages**; a scheduled GitHub
Action fetches fresh prices at deploy time. Prices are indicative (delayed), refreshed on
each scheduled run (~every 30 min during market hours).

## How it fits together

```
index.html            single-file SPA (inline CSS+JS, Chart.js via CDN)
data/book.json        CANONICAL data you own — holdings · watchlist · calls · analysts
data/prices.json      GENERATED each deploy by fetch_prices.py (adjusted closes + quotes + FX)
scripts/fetch_prices.py   stdlib-only Yahoo fetcher (no API key)
scripts/verify_calls.py   stdlib-only audit / reference scoring
.github/workflows/deploy.yml   fetch prices → audit → deploy to Pages
```

`book.json` is the source of truth and is version-controlled — its git history *is* your
auditable track record (see "Verifying" below). `prices.json` is disposable and rebuilt on
every deploy, so it is never committed.

## Editing the book (two ways — use either)

1. **In the browser.** Every table is editable; add/delete rows inline. Changes save to your
   browser's `localStorage`. When happy, click **Export book.json** and commit the downloaded
   file over `data/book.json`. **Reset** discards local edits and reloads the published book.
2. **Edit `data/book.json` directly** and commit. A push to `main` triggers a rebuild+deploy.

### Row conventions

- **Ticker** = the Yahoo symbol. Suffixes: NSE `.NS`, Taiwan `.TW`, Korea `.KS`, HK `.HK`,
  Japan `.T`, US bare (e.g. `AAPL`). Ampersands are fine (`M&M.NS`, `GVT&D.NS`).
- **Market** picks the benchmark automatically: `IN→Nifty 500 (^CRSLDX)`, `TW→TAIEX (^TWII)`,
  `KR→KOSPI (^KS11)`, `US→S&P 500 (^GSPC)`, `HK→Hang Seng (^HSI)`, `JP→Nikkei (^N225)`.
- Each **call** names its `analyst` (first-class — this is what the scorecard grades).

## Scoring methodology (the analyst KPI)

For each call, with `end = exit date` (closed) or *today* (open, marked-to-market):

```
stockRet = adjClose(end) / adjClose(entryDate) − 1      # date-driven, from ADJUSTED closes
benchRet = benchClose(end) / benchClose(entryDate) − 1   # same dates, the row's market benchmark
alpha    = stockRet − benchRet                           # same currency ⇒ FX-neutral
```

- **Hit/miss** is keyed on alpha: a **Buy** hits if `alpha > 0`; a **Sell** hits if `alpha < 0`
  (the avoided stock underperformed). **Hold** calls are logged and shown but **excluded** from
  the hit-rate (not a directional bet).
- Returns use **adjusted** closes, so splits/dividends never create a fake step.
- Returns are **date-driven** (the market close on the call date), not the price you typed — so
  an analyst can't be flattered by a cherry-picked entry. (Holdings, by contrast, use your
  actual cost basis, since that's your P&L.)
- The leaderboard ranks by average alpha and flags **small samples** (n < 5 scored).

## Verifying / auditing the track record

1. **Adjusted prices** remove the biggest correctness pitfall (unadjusted splits).
2. `python3 scripts/verify_calls.py` recomputes every call independently and flags: tickers with
   no price feed, missing benchmark, no close near the entry/exit date, `exit < entry`, and
   >40% single-day jumps (possible unadjusted corporate action). It runs in CI (non-blocking)
   and prints the same per-analyst numbers the page shows — so the two can never silently drift.
3. Because `book.json` is committed, **git history timestamps every call** — the tamper-evidence
   against retroactively deleting losers or backdating entries. Log every call, including the
   bad ones.

## Local development

```bash
python3 scripts/fetch_prices.py     # writes data/prices.json
python3 scripts/verify_calls.py     # audit + reference scorecard
python3 -m http.server 8765         # then open http://localhost:8765
```

## Deploy

Push to `main`, then in the repo settings enable **Pages → Source: GitHub Actions**. The
workflow deploys on every push, on `workflow_dispatch`, and on the schedule. The live URL is
printed in the Actions run and in Settings → Pages.
