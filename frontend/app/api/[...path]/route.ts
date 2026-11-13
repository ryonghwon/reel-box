import { NextRequest } from "next/server";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
async function proxy(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const host = req.headers.get("host") || "";
  let hostname = "";
  try {
    hostname = new URL(`http://${host}`).hostname;
  } catch {
    return new Response("Invalid host", { status: 400 });
  }
  if (!["localhost", "127.0.0.1", "[::1]"].includes(hostname))
    return new Response("Local use only", { status: 403 });
  const origin = req.headers.get("origin");
  if (origin) {
    try {
      if (new URL(origin).host !== host)
        return new Response("Origin rejected", { status: 403 });
    } catch {
      return new Response("Invalid origin", { status: 400 });
    }
  }
  if (req.headers.get("sec-fetch-site") === "cross-site")
    return new Response("Origin rejected", { status: 403 });
  const { path } = await params;
  if (
    path.some((x) => !x || x === "." || x === ".." || /[^a-zA-Z0-9_.-]/.test(x))
  )
    return new Response("Invalid path", { status: 400 });
  const headers = new Headers({ "X-API-Key": process.env.API_TOKEN || "" });
  for (const name of ["content-type", "range", "if-range"]) {
    const v = req.headers.get(name);
    if (v) headers.set(name, v);
  }
  let body: BodyInit | null = null;
  if (!["GET", "HEAD"].includes(req.method)) {
    if (path[0] === "recordings" || path[0] === "imports") {
      if (
        Number(req.headers.get("content-length") || 0) >
        (path[0] === "imports" ? 32 : 512) * 1024 ** 2
      )
        return Response.json(
          { detail: "파일 크기 제한을 초과했습니다." },
          { status: 413 },
        );
      body = req.body;
    } else {
      const reader = req.body?.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      if (reader) {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          size += value.length;
          if (size > 4 * 1024 * 1024) {
            await reader.cancel();
            return new Response("Request too large", { status: 413 });
          }
          chunks.push(value);
        }
      }
      body = Buffer.concat(chunks);
    }
  }
  try {
    const upstream = await fetch(
      `${process.env.API_BASE || "http://127.0.0.1:8000"}/api/${path.join("/")}${req.nextUrl.search}`,
      {
        method: req.method,
        headers,
        body,
        cache: "no-store",
        signal: req.signal,
        duplex: "half",
      } as RequestInit & { duplex: "half" },
    );
    const output = new Headers({ "Cache-Control": "no-store" });
    for (const name of [
      "content-type",
      "content-disposition",
      "content-length",
      "content-range",
      "accept-ranges",
    ]) {
      const value = upstream.headers.get(name);
      if (value) output.set(name, value);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: output,
    });
  } catch {
    return Response.json(
      { detail: "서버에 연결할 수 없습니다. 앱 실행 상태를 확인하세요." },
      { status: 502 },
    );
  }
}
export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as DELETE,
  proxy as HEAD,
};
