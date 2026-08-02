# Research Portal — calls by analyst

A single-page dashboard to **record and grade stock calls by analyst**, plus a light
**holdings** view grouped by country. Live at https://mamreg.github.io/mamreg/.

Static `index.html` on GitHub Pages + a tiny **Cloudflare Worker** (`worker/`) that proxies Yahoo
(live ticker search + prices) and stores your book in Cloudflare KV. No manual save/publish — edits
auto-save to the cloud. Prices are indicative (delayed ~15 min via the Worker's cache).

## Two tabs

- **Analysts** — one sub-tab per analyst (**Mark · Ang · Aloy**, add more with ＋). Each analyst
  shows a summary — **overall return · hit rate · return vs benchmark · #calls** — then:
  - **Alpha** — open calls on top, **Closed calls** table below (with exit date + exit price).
    Columns: Entry date · Ticker · Stock · Call · Entry cost · Return · Index return · Return vs
    index · Result · Close.
  - **Coverage List** — the distinct names covered, with latest stance, price, #calls and hit rate.
- **Holdings** — positions grouped by **country** (HK · China · India · Taiwan · Korea · ASEAN):
  Stock · **Cost** · LTP · 1D · 1W · 1M · YTD · Return. Upload a statement **PDF** to auto-fill.

## How it fits together

```
index.html            single-file SPA (inline CSS+JS; Chart.js + pdf.js via CDN)
worker/worker.js       Cloudflare Worker: /search, /chart (Yahoo proxy) + /book (KV store)
data/book.json         SEED book (analysts·holdings·calls) — used until the KV store has data
scripts/*.py           stdlib-only fetcher + reference scorer (local auditing only, not runtime)
.github/workflows/deploy.yml   deploy the static site to Pages
```

The live book lives in the Worker's **KV** (auto-saved from the browser). `data/book.json` is only
the initial seed. Set the Worker URL as `WORKER` in `index.html`. See **`worker/README.md`** for the
one-time deploy.

### How to add a stock (no buttons, fully automatic)

- **A call:** Analysts → pick the analyst → **Alpha** → **＋ Add call** → set the **Entry date**,
  then **type in the Ticker box** and pick from the live dropdown. Name, entry cost, return, index
  return and result fill in automatically. Click **Close** (pick an exit date) to move it to the
  Closed table. Everything auto-saves to the cloud.
- **A holding:** **Holdings** → **＋ Add holding** → type the ticker (dropdown) + cost; or upload a
  statement PDF and review.
- **Save passphrase:** the first time you edit, you're asked once for the Worker's `WRITE_TOKEN`
  (cached in your browser). That's the only prompt, ever.
- **Prices for a new ticker** appear only after you **Publish** (or Export + commit) — the fetcher
  reads tickers from the committed `book.json`, so until then the price shows "–".

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
