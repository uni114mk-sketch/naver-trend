/**
 * 네이버 검색 MCP 서버 (Cloudflare Worker, Streamable HTTP).
 *
 * claude.ai 커스텀 커넥터로 붙여서 대시보드 페이지가 블로그·카페·지역 검색을 호출하게 한다.
 * 환경변수(Secrets):
 *   ACCESS_TOKEN                      URL 경로에 들어가는 열쇠
 *   NCP_API_KEY_ID, NCP_API_KEY       NAVER API HUB 키 (2026-07-31 이후 신규 발급은 이것만 가능)
 *   NAVER_CLIENT_ID, NAVER_CLIENT_SECRET   (구) 네이버 개발자센터 검색 API 키. 2027-06-30 까지만 동작
 * 둘 중 한 쌍만 있으면 되고, 둘 다 있으면 API HUB 를 쓴다.
 * 엔드포인트: https://<worker>.workers.dev/mcp/<ACCESS_TOKEN>
 */

const TOOLS = [
  {
    name: "search_blog",
    description: "네이버 블로그 검색. 정확도순 상위 결과의 제목·링크·요약·블로거명을 돌려준다.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "검색어 (예: 강남피부과)" },
        display: { type: "integer", description: "결과 수 (1~100, 기본 30)" },
        start: { type: "integer", description: "시작 위치 (1~1000, 기본 1)" },
        sort: { type: "string", enum: ["sim", "date"], description: "sim=정확도순, date=최신순" },
      },
      required: ["query"],
    },
    annotations: { readOnlyHint: true },
  },
  {
    name: "search_cafearticle",
    description: "네이버 카페글 검색. 제목·링크·요약·카페명을 돌려준다.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "검색어" },
        display: { type: "integer", description: "결과 수 (1~100, 기본 30)" },
        start: { type: "integer", description: "시작 위치 (기본 1)" },
        sort: { type: "string", enum: ["sim", "date"] },
      },
      required: ["query"],
    },
    annotations: { readOnlyHint: true },
  },
  {
    name: "search_local",
    description: "네이버 지역(업체) 검색. 업체명·주소·링크를 돌려준다 (최대 5개).",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "검색어 (예: 강남피부과)" },
        display: { type: "integer", description: "결과 수 (1~5, 기본 5)" },
      },
      required: ["query"],
    },
    annotations: { readOnlyHint: true },
  },
];

const KIND = { search_blog: "blog", search_cafearticle: "cafearticle", search_local: "local" };

function strip(s) {
  return String(s || "").replace(/<[^>]+>/g, "").replace(/&quot;/g, '"').replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").trim();
}

async function naver(env, kind, args) {
  const maxDisplay = kind === "local" ? 5 : 100;
  const display = Math.min(maxDisplay, Math.max(1, parseInt(args.display, 10) || (kind === "local" ? 5 : 30)));
  const params = new URLSearchParams({ query: String(args.query || ""), display: String(display) });
  if (kind !== "local") {
    params.set("start", String(Math.max(1, parseInt(args.start, 10) || 1)));
    params.set("sort", args.sort === "date" ? "date" : "sim");
  }
  const hub = !!(env.NCP_API_KEY_ID && env.NCP_API_KEY);
  const url = hub
    ? `https://naverapihub.apigw.ntruss.com/search/v1/${kind}?${params}`
    : `https://openapi.naver.com/v1/search/${kind}.json?${params}`;
  const headers = hub
    ? { "X-NCP-APIGW-API-KEY-ID": env.NCP_API_KEY_ID, "X-NCP-APIGW-API-KEY": env.NCP_API_KEY }
    : { "X-Naver-Client-Id": env.NAVER_CLIENT_ID, "X-Naver-Client-Secret": env.NAVER_CLIENT_SECRET };
  const r = await fetch(url, { headers });
  if (!r.ok) throw new Error(`네이버 API ${r.status}: ${(await r.text()).slice(0, 300)}`);
  const data = await r.json();
  const items = (data.items || []).map((it) => ({
    title: strip(it.title),
    link: it.link,
    description: strip(it.description),
    bloggername: it.bloggername,
    cafename: it.cafename,
    postdate: it.postdate,
    address: it.address,
    roadAddress: it.roadAddress,
    category: it.category,
    telephone: it.telephone,
  }));
  return { query: args.query, total: data.total, display: items.length, items };
}

const json = (obj, status = 200, extra = {}) =>
  new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json", ...extra } });
const rpcResult = (id, result) => ({ jsonrpc: "2.0", id, result });
const rpcError = (id, code, message) => ({ jsonrpc: "2.0", id, error: { code, message } });

async function handle(msg, env) {
  const { id, method, params = {} } = msg;
  if (method === "initialize") {
    return rpcResult(id, {
      protocolVersion: params.protocolVersion || "2025-06-18",
      capabilities: { tools: {} },
      serverInfo: { name: "naver-search", version: "1.0.0" },
    });
  }
  if (method === "ping") return rpcResult(id, {});
  if (method === "tools/list") return rpcResult(id, { tools: TOOLS });
  if (method === "tools/call") {
    const kind = KIND[params.name];
    if (!kind) return rpcResult(id, { content: [{ type: "text", text: `unknown tool: ${params.name}` }], isError: true });
    try {
      const out = await naver(env, kind, params.arguments || {});
      return rpcResult(id, { content: [{ type: "text", text: JSON.stringify(out) }], structuredContent: out, isError: false });
    } catch (e) {
      return rpcResult(id, { content: [{ type: "text", text: String(e.message || e) }], isError: true });
    }
  }
  if (method && method.startsWith("notifications/")) return null;
  return rpcError(id, -32601, `Method not found: ${method}`);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "/health") {
      const mode = env.NCP_API_KEY_ID && env.NCP_API_KEY ? "api-hub" : env.NAVER_CLIENT_ID ? "developers(legacy)" : "no-key";
      return new Response(`naver-search mcp ok (${mode})`, { status: 200 });
    }
    if (!env.ACCESS_TOKEN || url.pathname !== `/mcp/${env.ACCESS_TOKEN}`) return new Response("not found", { status: 404 });
    const hasHub = env.NCP_API_KEY_ID && env.NCP_API_KEY, hasLegacy = env.NAVER_CLIENT_ID && env.NAVER_CLIENT_SECRET;
    if (!hasHub && !hasLegacy) return json({ error: "NCP_API_KEY_ID / NCP_API_KEY (API HUB) 또는 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 시크릿이 없습니다" }, 500);
    if (request.method === "GET") return new Response("SSE stream not supported", { status: 405, headers: { allow: "POST, DELETE" } });
    if (request.method === "DELETE") return new Response(null, { status: 204 });
    if (request.method !== "POST") return new Response("method not allowed", { status: 405 });

    let body;
    try { body = await request.json(); } catch (e) { return json(rpcError(null, -32700, "Parse error"), 400); }
    const msgs = Array.isArray(body) ? body : [body];
    const results = [];
    for (const m of msgs) {
      const r = await handle(m, env);
      if (r) results.push(r);
    }
    if (!results.length) return new Response(null, { status: 202 });
    return json(Array.isArray(body) ? results : results[0]);
  },
};
