/**
 * mamreg-api — Cloudflare Worker backing the Research Portal.
 *
 * Routes (all CORS-enabled):
 *   GET  /search?q=…            → Yahoo symbol search  → [{symbol,name,exchange,type}]
 *   GET  /chart?symbol=…&range= → Yahoo v8 chart passthrough (adjusted closes)
 *   GET  /book                  → the stored book JSON (Cloudflare KV), or {}
 *   PUT  /book                  → save book JSON to KV (needs Bearer WRITE_TOKEN)
 *
 * Bindings: KV namespace `BOOK_KV`, secret `WRITE_TOKEN`.
 */
const YH = "https://query1.finance.yahoo.com";
const UA = "Mozilla/5.0 (mamreg-worker)";
const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,PUT,OPTIONS",
  "access-control-allow-headers": "content-type,authorization",
  "access-control-max-age": "86400",
};

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json", ...CORS },
  });

async function yahoo(path, ttl) {
  return fetch(YH + path, {
    headers: { "user-agent": UA, accept: "application/json" },
    cf: ttl ? { cacheTtl: ttl, cacheEverything: true } : undefined,
  });
}

export default {
  async fetch(req, env) {
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    const url = new URL(req.url);
    const p = url.pathname.replace(/\/+$/, "");
    try {
      if (p.endsWith("/search")) {
        const q = (url.searchParams.get("q") || "").trim();
        if (!q) return json([]);
        const r = await yahoo(
          `/v1/finance/search?q=${encodeURIComponent(q)}&quotesCount=8&newsCount=0&enableFuzzyQuery=false`,
          120
        );
        const d = await r.json();
        const keep = new Set(["EQUITY", "ETF", "INDEX", "MUTUALFUND"]);
        const out = (d.quotes || [])
          .filter((x) => x.symbol && keep.has(x.quoteType))
          .map((x) => ({
            symbol: x.symbol,
            name: x.shortname || x.longname || x.symbol,
            exchange: x.exchDisp || x.exchange || "",
            type: x.quoteType,
          }));
        return json(out);
      }

      if (p.endsWith("/chart")) {
        const sym = url.searchParams.get("symbol");
        const range = url.searchParams.get("range") || "2y";
        if (!sym) return json({ error: "symbol required" }, 400);
        const r = await yahoo(
          `/v8/finance/chart/${encodeURIComponent(sym)}?range=${encodeURIComponent(range)}&interval=1d&events=div%2Csplit`,
          900
        );
        const body = await r.text();
        return new Response(body, {
          status: r.status,
          headers: { "content-type": "application/json", ...CORS },
        });
      }

      if (p.endsWith("/book")) {
        // Site password gates BOTH read and write of the book (the sensitive data).
        const auth = req.headers.get("authorization") || "";
        if (!env.WRITE_TOKEN || auth !== `Bearer ${env.WRITE_TOKEN}`)
          return json({ error: "unauthorized" }, 401);
        if (req.method === "GET") {
          const b = await env.BOOK_KV.get("book");
          return json(b ? JSON.parse(b) : {});
        }
        if (req.method === "PUT") {
          const body = await req.text();
          try {
            JSON.parse(body);
          } catch {
            return json({ error: "invalid json" }, 400);
          }
          await env.BOOK_KV.put("book", body);
          return json({ ok: true });
        }
        return json({ error: "method not allowed" }, 405);
      }

      return json({ error: "not found", path: p }, 404);
    } catch (e) {
      return json({ error: String(e) }, 500);
    }
  },
};
