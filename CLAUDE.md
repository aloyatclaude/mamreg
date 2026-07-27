# CLAUDE.md — Global Research Portal

Static, backend-less dashboard for one multi-market investment book: Holdings · Watchlist ·
Calls · per-analyst KPI scorecard. Served from GitHub Pages; prices fetched at deploy time.

## Architecture (keep it this way)

- **`index.html`** — the entire app: one self-contained file, inline CSS + vanilla JS,
  Chart.js via CDN. No framework, no build step. Dark theme via CSS variables. Deep-linkable
  tabs via `#hash`.
- **`data/book.json`** — canonical, committed, human-owned: `analysts[] · holdings[] ·
  watchlist[] · calls[]`. Source of truth; its git history is the audit trail.
- **`data/prices.json`** — generated every deploy by `scripts/fetch_prices.py`; **never
  commit it** (it's staged into the Pages artifact only).
- **`scripts/*.py`** — **stdlib only, no API keys** (mirrors the Yahoo v8 chart approach).
  `fetch_prices.py` builds the price feed; `verify_calls.py` is the reference scoring +
  auditor and must stay numerically identical to the JS in `index.html` (`scoreCall`).
- **`.github/workflows/deploy.yml`** — fetch prices → audit (non-blocking) → deploy to Pages.

## Scoring invariants (don't quietly change)

- Calls: returns from **adjusted** closes, **date-driven** (`adjClose` on the call/exit dates,
  not the typed entry price). `alpha = stockRet − benchRet` on the row's market benchmark.
- Buy hits if `alpha>0`; Sell hits if `alpha<0`; **Hold excluded** from hit-rate.
- Holdings use **cost basis** (`price/entry−1`) — that's P&L, deliberately different from calls.
- Benchmark per market: `IN ^CRSLDX · TW ^TWII · KR ^KS11 · US ^GSPC · HK ^HSI · JP ^N225`.

If you touch the scoring in one place, change it in both `index.html` and `verify_calls.py`
and re-run `python3 scripts/verify_calls.py` to confirm they agree.

## Verify a change

`python3 scripts/fetch_prices.py && python3 scripts/verify_calls.py && python3 -m http.server 8765`
then open the tabs (or screenshot headless Chrome at `#overview/#holdings/#calls/#analysts`).
