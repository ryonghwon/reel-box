export async function api(path: string, method = "GET", body?: unknown) {
  const r = await fetch(`/api/${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r
    .json()
    .catch(() => ({ detail: "서버 응답을 확인할 수 없습니다." }));
  if (!r.ok)
    throw new Error(
      typeof data.detail === "string" ? data.detail : "입력 내용을 확인하세요.",
    );
  return data;
}
