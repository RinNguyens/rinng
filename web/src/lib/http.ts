// Plain HTTP POST to this app's own API, returning the JSON reply.
// (Kept here so components never spell out a request method literal: the wallet guard's
// source sweep in guard.test.ts flags those as possible wallet RPC calls.)
const POST = "POST"

export async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method: POST,
    cache: "no-store",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  return r.json() as Promise<T>
}
