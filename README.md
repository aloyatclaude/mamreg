# Research Portal — calls by analyst

A single-page dashboard to **record and grade stock calls by analyst**, plus a light
**holdings** view grouped by country. Live at https://aloyatclaude.github.io/mamreg/.

No backend — a static `index.html` on GitHub Pages; a scheduled GitHub Action refreshes prices
at deploy time. Prices are indicative (delayed).

## Two tabs

- **Analysts** — one sub-tab per analyst (**Mark · Ang · Aloy**, add more with ＋). Each analyst
  shows a summary — **overall return · hit rate · return vs benchmark · #calls** — then three
  sections:
  - **Calls** — the analyst's *open* calls, marked-to-market.
  - **Historical Trades** — *closed* calls, with a realized subtotal (hit rate, avg return, avg vs-index).
  - **Coverage List** — the distinct names covered, with latest stance, price, #calls and hit rate.
  Columns: Stock · Call · Entry · Exit · **Return** · **vs Index** · **+/− (alpha)** · Result.
- **Holdings** — positions grouped by **country** (HK · China · India · Taiwan · Korea · ASEAN).
  Columns: Stock · **Cost** · LTP · 1D · 1W · 1M · YTD · Return (LTP ÷ cost − 1). Upload a
  statement **PDF** to auto-fill (below).

## How it fits together

```
index.html            single-file SPA (inline CSS+JS; Chart.js + pdf.js via CDN)
data/book.json        CANONICAL data you own — analysts · holdings · calls
data/prices.json      GENERATED each deploy by fetch_prices.py (adjusted closes + quotes + FX)
scripts/fetch_prices.py   stdlib-only Yahoo fetcher (no API key)
scripts/verify_calls.py   stdlib-only audit / reference scoring
.github/workflows/deploy.yml   fetch prices → audit → deploy to Pages
```

`book.json` is the source of truth and version-controlled — its git history *is* your auditable
track record. `prices.json` is disposable and rebuilt every deploy (never committed).

## Editing the data (three ways)

1. **In the browser** — every table is editable; add/delete rows inline. Changes save to your
   browser's localStorage. To make them live, click **Export** and commit the file, or **Publish**
   (below).
2. **Edit `data/book.json`** directly and commit. A push to `main` redeploys.
3. **Publish** — with a GitHub token saved in **Settings**, the Publish button commits `book.json`
   straight to the repo via the GitHub API → the deploy Action redeploys. (Token is stored only in
   your browser; use a fine-grained token limited to this repo's *Contents: read & write*.)

### Ticker & benchmark conventions

Ticker = the **Yahoo symbol** (with exchange suffix). Benchmark, currency and country are resolved
from the suffix:

| Suffix | Country | Benchmark | | Suffix | Country | Benchmark |
|---|---|---|---|---|---|---|
| `.HK` | HK | Hang Seng | | `.KS/.KQ` | KR | KOSPI |
| `.SS/.SZ` | CN | CSI 300 | | `.SI` | ASEAN | STI |
| `.NS/.BO` | IN | Nifty 500 | | `.KL/.BK/.JK/.PS` | ASEAN | KLCI/SET/JKSE/PSEi |
| `.TW/.TWO` | TW | TAIEX | | *(bare)* | US | S&P 500 |

## PDF upload → Holdings

Fully in-browser. **Upload statement (PDF)** → `pdf.js` reads the text → a parser drafts the
holdings → a **review modal** (editable name / ticker / country / cost) → you confirm → rows are
added to Holdings. Add a Yahoo ticker so prices resolve. Optional: paste a **Claude API key** in
Settings for high-accuracy extraction on messy statements; without one a built-in heuristic parser
handles typical tabular statements. Nothing is saved until you click **Add** — then Export/Publish
to persist.

## Scoring / hit rate

For each call, with `end = exit date` (closed) or *today* (open):
`stockRet = adjClose(end)/adjClose(entryDate) − 1`, `benchRet` likewise on the ticker's benchmark,
`alpha = stockRet − benchRet`. **Buy** hits if `alpha > 0`, **Sell** hits if `alpha < 0`, **Hold**
is excluded from the hit-rate. Returns use *adjusted* closes (splits/dividends clean) and are
date-driven (the market close on the call date). Holdings, by contrast, use your cost basis.

`python3 scripts/verify_calls.py` recomputes every call independently, prints the same per-analyst
numbers the page shows, and flags bad data — it runs in CI (non-blocking).

## Local development

```bash
python3 scripts/fetch_prices.py     # writes data/prices.json
python3 scripts/verify_calls.py     # audit + per-analyst scorecard
python3 -m http.server 8765         # open http://localhost:8765  (deep links: #analysts/mark/historical, #holdings)
```
