/**
 * mamreg-api — Cloudflare Worker backing the Research Portal.
 *
 * Roles (Bearer password ⇒ role):
 *   WRITE_TOKEN  → admin  — edits everything (all analysts + Holdings + roster)
 *   EDITORS      → editor — JSON {"<password>":"<analystId>"}; edits ONLY that analyst's calls/coverage
 *   VIEW_TOKEN   → viewer — read-only
 *
 * Routes (all CORS-enabled):
 *   GET  /search?q=…            → Yahoo symbol search  → [{symbol,name,exchange,type}]
 *   GET  /chart?symbol=…&range= → Yahoo v8 chart passthrough (adjusted closes)
 *   GET  /me                    → {role, analyst} for the Bearer token (401 if unknown)
 *   GET  /book                  → the stored book JSON (any valid role), or {}
 *   PUT  /book                  → admin: full write · editor: scoped to own calls/coverage · viewer: 403
 *
 * Bindings: KV namespace `BOOK_KV`; secrets `WRITE_TOKEN` (admin), `VIEW_TOKEN` (viewer),
 *           `EDITORS` (JSON string, password→analystId).
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

// Map a request's Bearer token to a role. admin > editor > viewer.
function resolveRole(req, env) {
  const tok = (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "").trim();
  if (!tok) return { role: "none", analyst: null };
  if (env.WRITE_TOKEN && tok === env.WRITE_TOKEN) return { role: "admin", analyst: null };
  let editors = {};
  try { editors = JSON.parse(env.EDITORS || "{}"); } catch {}
  if (editors[tok]) return { role: "editor", analyst: editors[tok] };
  if (env.VIEW_TOKEN && tok === env.VIEW_TOKEN) return { role: "viewer", analyst: null };
  return { role: "none", analyst: null };
}
const asArr = (x) => (Array.isArray(x) ? x : []);

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

      if (p.endsWith("/me")) {
        const who = resolveRole(req, env);
        if (who.role === "none") return json({ error: "unauthorized" }, 401);
        return json({ role: who.role, analyst: who.analyst });
      }

      if (p.endsWith("/book")) {
        const who = resolveRole(req, env);
        if (who.role === "none") return json({ error: "unauthorized" }, 401); // any valid role may read

        if (req.method === "GET") {
          const b = await env.BOOK_KV.get("book");
          return json(b ? JSON.parse(b) : {});
        }

        if (req.method === "PUT") {
          if (who.role !== "admin" && who.role !== "editor")
            return json({ error: "forbidden (view only)" }, 403);
          const body = await req.text();
          let inc;
          try { inc = JSON.parse(body); } catch { return json({ error: "invalid json" }, 400); }

          if (who.role === "admin") {
            await env.BOOK_KV.put("book", body);   // full write
            return json({ ok: true, role: "admin" });
          }

          // editor: keep everyone else's data + Holdings + roster from the CURRENT book;
          // accept only this editor's own calls/coverage rows from the incoming book.
          const X = who.analyst;
          const curRaw = await env.BOOK_KV.get("book");
          const cur = curRaw ? JSON.parse(curRaw) : {};
          const merged = {
            ...cur,
            updated: inc.updated || cur.updated,
            analysts: asArr(cur.analysts),
            holdings: asArr(cur.holdings),
            calls: asArr(cur.calls).filter((c) => c.analyst !== X)
              .concat(asArr(inc.calls).filter((c) => c.analyst === X)),
            coverage: asArr(cur.coverage).filter((c) => c.analyst !== X)
              .concat(asArr(inc.coverage).filter((c) => c.analyst === X)),
          };
          await env.BOOK_KV.put("book", JSON.stringify(merged));
          return json({ ok: true, role: "editor", analyst: X });
        }
        return json({ error: "method not allowed" }, 405);
      }

      return json({ error: "not found", path: p }, 404);
    } catch (e) {
      return json({ error: String(e) }, 500);
    }
  },
};
