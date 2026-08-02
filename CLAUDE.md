# CLAUDE.md — Research Portal (mamreg)

Static, backend-less dashboard to **record & grade stock calls by analyst**, plus holdings by
country. Served from GitHub Pages (`mamreg/mamreg`); prices fetched at deploy time.

## Architecture (keep it this way)

- **`index.html`** — the whole app: one self-contained file, inline CSS + vanilla JS, **Chart.js**
  and **pdf.js (v3 UMD)** via CDN. No framework, no build step. Dark theme. Deep-linkable via
  `#analysts/<id>/<section>` and `#holdings`.
- **`data/book.json`** — canonical, committed, human-owned: `analysts[] · holdings[] · calls[]`
  (no more overview/watchlist). Source of truth; git history = audit trail.
- **`data/prices.json`** — generated every deploy by `fetch_prices.py`; **never commit it**.
- **`scripts/*.py`** — **stdlib only, no keys**. `verify_calls.py` must stay numerically identical
  to `scoreCall` in `index.html`.
- **`.github/workflows/deploy.yml`** — fetch prices → audit (non-blocking) → deploy to Pages.

## Two tabs

- **Analysts** → per-analyst summary + segmented **Calls (open) / Historical Trades (closed) /
  Coverage List**. Calls tables are editable (record calls here).
- **Holdings** → grouped by country (HK/CN/IN/TW/KR/ASEAN); Cost · LTP · 1D/1W/1M/YTD · Return.
  PDF upload → parse → review modal → fill.

## Invariants (don't quietly change)

- Benchmark / currency / country resolve from the **Yahoo ticker suffix** — one map, mirrored in
  `index.html` (`SUFFIX_*`), `fetch_prices.py` and `verify_calls.py`. Change all three together.
- Call scoring: adjusted closes, date-driven; `alpha = stockRet − benchRet`; Buy hits α>0, Sell
  hits α<0, **Hold excluded** from hit-rate. Holdings use cost basis (`LTP/entry−1`).
- pdf.js runs **in the browser**; PDF rows are always shown in a **review modal** before saving.
  Optional Claude key (`localStorage` `grp-claude-key`) upgrades extraction; GitHub token
  (`grp-gh-token`) powers **Publish** (GitHub Contents API → commit `book.json`).

## Verify a change

`python3 scripts/fetch_prices.py && python3 scripts/verify_calls.py && python3 -m http.server 8765`
then screenshot headless Chrome at `#analysts/mark/calls`, `#analysts/mark/historical`,
`#holdings`, and `?pdftest` (runs the PDF parser on a built-in sample statement → review modal).
