/**
 * Proxy for backend API. Forwards all requests and preserves Set-Cookie headers.
 * Fixes cross-origin cookie issues (401 after login).
 */
import { NextResponse } from "next/server";

const API_UPSTREAM =
  process.env.API_UPSTREAM_URL ||
  process.env.NEXT_PUBLIC_API_UPSTREAM_URL ||
  "http://localhost:8000";

function buildUpstreamUrl(path: string[]): string {
  const pathStr = path.length > 0 ? path.join("/") : "";
  const base = API_UPSTREAM.replace(/\/$/, "");
  return pathStr ? `${base}/api/${pathStr}` : `${base}/api`;
}

async function proxyRequest(
  request: Request,
  path: string[],
  method: string
): Promise<NextResponse> {
  let url = buildUpstreamUrl(path);
  const requestUrl = new URL(request.url);
  if (requestUrl.search) {
    url += requestUrl.search;
  }
  const headers = new Headers(request.headers);
  // Remove host to avoid upstream rejecting
  headers.delete("host");

  let body: string | undefined;
  if (method !== "GET" && method !== "HEAD") {
    try {
      body = await request.text();
    } catch {
      body = undefined;
    }
  }

  const res = await fetch(url, {
    method,
    headers,
    body: body && body.length > 0 ? body : undefined,
  });

  // Preserve multiple Set-Cookie headers (session + csrf); plain Headers(res.headers) can drop some
  const responseHeaders = new Headers();
  Array.from(res.headers.entries()).forEach(([key, value]) => {
    if (key.toLowerCase() === "set-cookie") {
      responseHeaders.append("Set-Cookie", value);
    } else {
      responseHeaders.set(key, value);
    }
  });
  return new NextResponse(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers: responseHeaders,
  });
}

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ path?: string[] }> }
) {
  const { path = [] } = await params;
  const pathArray = Array.isArray(path) ? path : [path].filter(Boolean);
  return proxyRequest(request, pathArray, "GET");
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ path?: string[] }> }
) {
  const { path = [] } = await params;
  const pathArray = Array.isArray(path) ? path : [path].filter(Boolean);
  return proxyRequest(request, pathArray, "POST");
}

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ path?: string[] }> }
) {
  const { path = [] } = await params;
  const pathArray = Array.isArray(path) ? path : [path].filter(Boolean);
  return proxyRequest(request, pathArray, "PATCH");
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ path?: string[] }> }
) {
  const { path = [] } = await params;
  const pathArray = Array.isArray(path) ? path : [path].filter(Boolean);
  return proxyRequest(request, pathArray, "DELETE");
}

export async function PUT(
  request: Request,
  { params }: { params: Promise<{ path?: string[] }> }
) {
  const { path = [] } = await params;
  const pathArray = Array.isArray(path) ? path : [path].filter(Boolean);
  return proxyRequest(request, pathArray, "PUT");
}

export async function OPTIONS(
  request: Request,
  { params }: { params: Promise<{ path?: string[] }> }
) {
  const { path = [] } = await params;
  const pathArray = Array.isArray(path) ? path : [path].filter(Boolean);
  return proxyRequest(request, pathArray, "OPTIONS");
}
