import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "dv_session";
const API_BASE = (process.env.RUST_API_BASE || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:3000/v1").replace(/\/$/, "");
const ALLOWED_ROOTS = new Set(["auth", "collections", "datasets", "sources", "runs", "workspaces", "me", "health"]);
type Context = { params: Promise<{ path: string[] }> };

async function handle(request: NextRequest, context: Context) {
  const { path } = await context.params;
  if (!ALLOWED_ROOTS.has(path[0]) || path.some((part) => !/^[a-zA-Z0-9_-]+$/.test(part))) {
    return NextResponse.json({ error: "Not found." }, { status: 404 });
  }
  const route = path.join("/");
  const credentialsRoute = route === "auth/login" || route === "auth/register";
  const mutation = !["GET", "HEAD"].includes(request.method);
  // Next may normalize nextUrl's hostname to localhost. Compare against the
  // browser-facing Host header, not the internal server URL, for CSRF checks.
  let sameOrigin = false;
  try {
    const origin = new URL(request.headers.get("origin") || "");
    sameOrigin = origin.host === request.headers.get("host") && origin.protocol === request.nextUrl.protocol;
  } catch { /* Missing/invalid Origin is rejected for mutations. */ }
  if (mutation && (!sameOrigin || request.headers.get("sec-fetch-site") === "cross-site")) {
    return NextResponse.json({ error: "This request must come from Datavault." }, { status: 403 });
  }
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token && !credentialsRoute && route !== "health") {
    return NextResponse.json({ error: "Sign in to continue." }, { status: 401 });
  }
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (request.headers.has("content-type")) headers.set("Content-Type", request.headers.get("content-type")!);
  try {
    const body = mutation ? await request.text() : undefined;
    if (body && body.length > 1_000_000) return NextResponse.json({ error: "Request is too large." }, { status: 413 });
    const upstream = await fetch(`${API_BASE}/${route}${request.nextUrl.search}`, {
      method: request.method, headers, body, cache: "no-store", redirect: "error",
      signal: route.endsWith("/events") ? request.signal : AbortSignal.any([request.signal, AbortSignal.timeout(60000)]),
    });
    if (credentialsRoute && upstream.ok) {
      const result = await upstream.json();
      if (typeof result.token !== "string" || !result.user?.id) throw new Error("Invalid session response");
      const response = NextResponse.json({ user: result.user }, { status: upstream.status });
      response.headers.set("Cache-Control", "no-store");
      response.cookies.set(SESSION_COOKIE, result.token, {
        httpOnly: true, secure: request.nextUrl.protocol === "https:", sameSite: "lax", path: "/", maxAge: 7 * 24 * 60 * 60,
      });
      return response;
    }
    const responseHeaders = new Headers({ "Cache-Control": "no-store" });
    for (const name of ["content-type", "content-disposition"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    const response = new NextResponse(upstream.body, { status: upstream.status, headers: responseHeaders });
    if ((route === "auth/logout" && upstream.ok) || (upstream.status === 401 && !credentialsRoute)) {
      response.cookies.set(SESSION_COOKIE, "", { httpOnly: true, sameSite: "lax", path: "/", maxAge: 0 });
    }
    return response;
  } catch {
    return NextResponse.json({ error: "Cannot reach the server. Please try again." }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}

export { handle as GET, handle as POST, handle as PATCH, handle as DELETE };
