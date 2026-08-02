# mamreg-api — the Cloudflare Worker backend

Gives the static site what a browser can't get from Yahoo directly (CORS), and stores your book:

- `GET /search?q=…` — live ticker search (powers the dropdown)
- `GET /chart?symbol=…` — prices/history (entry cost, returns, index) — cached ~15 min
- `GET /book` / `PUT /book` — your holdings·calls·analysts, stored in Cloudflare KV (auto-save)

## One-time deploy (free tier)

```bash
cd worker
npm i -g wrangler            # or use: npx wrangler ...
wrangler login              # opens the browser once

# 1) create the KV store, then paste the printed id into wrangler.toml (id = "…")
wrangler kv namespace create BOOK_KV

# 2) set the save passphrase (you'll type this once in the app on first edit)
wrangler secret put WRITE_TOKEN

# 3) deploy
wrangler deploy
```

`wrangler deploy` prints your URL, e.g. `https://mamreg-api.<you>.workers.dev`.
**Send me that URL** — I set it as `WORKER` in `index.html` and deploy the site.

## Local development

```bash
cd worker
echo 'WRITE_TOKEN=localdevsecret' > .dev.vars   # already present
npx wrangler dev --port 8787 --local            # simulated KV, no account needed
```
The site auto-targets `http://127.0.0.1:8787` when opened on localhost.

## Notes

- Reads are open; writes need `Authorization: Bearer <WRITE_TOKEN>` — the app prompts once for it
  and caches it in your browser.
- Keep the Worker URL private (it's a personal tool). To rotate the passphrase:
  `wrangler secret put WRITE_TOKEN` again.
