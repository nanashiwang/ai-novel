const INTERNAL_API_BASE = (process.env.INTERNAL_API_BASE ?? "http://localhost:8000").replace(/\/$/, "");
const BODYLESS_METHODS = new Set(["GET", "HEAD"]);
const HOP_BY_HOP_HEADERS = ["connection", "content-length", "host"];

type ProxyContext = {
  params: Promise<{ path: string[] }>;
};

export const runtime = "nodejs";

async function proxy(request: Request, context: ProxyContext) {
  const { path } = await context.params;
  const incomingUrl = new URL(request.url);
  const targetUrl = new URL(
    `/api/v1/${path.map((segment) => encodeURIComponent(segment)).join("/")}`,
    INTERNAL_API_BASE,
  );
  targetUrl.search = incomingUrl.search;

  const headers = new Headers(request.headers);
  for (const header of HOP_BY_HOP_HEADERS) {
    headers.delete(header);
  }

  const upstream = await fetch(targetUrl, {
    method: request.method,
    headers,
    body: BODYLESS_METHODS.has(request.method) ? undefined : await request.arrayBuffer(),
    redirect: "manual",
  });

  const responseHeaders = new Headers(upstream.headers);
  responseHeaders.delete("content-encoding");
  responseHeaders.delete("content-length");

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const HEAD = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
