import { afterEach, test } from "node:test";
import assert from "node:assert/strict";
import { ApiError, api, buildUrl, onSessionExpired, setCsrfToken } from "../src/api/client.js";

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
  setCsrfToken(null);
});

function respond(status, body) {
  return new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

test("buildUrl drops empty parameters", () => {
  assert.equal(buildUrl("/customers", { q: "", branch: null, page: 2 }), "/api/customers?page=2");
  assert.equal(buildUrl("/health"), "/api/health");
});

test("unsafe requests carry the CSRF token; reads never do", async () => {
  const seen = [];
  globalThis.fetch = async (url, init) => {
    seen.push({ url, init });
    return respond(200, { ok: true });
  };
  setCsrfToken("token-123");
  await api.get("/customers");
  await api.post("/customers", { name: "x" });
  assert.equal(seen[0].init.headers["X-CSRF-Token"], undefined);
  assert.equal(seen[1].init.headers["X-CSRF-Token"], "token-123");
  assert.equal(seen[1].init.credentials, "same-origin");
  assert.equal(seen[1].init.body, JSON.stringify({ name: "x" }));
});

test("error envelopes become ApiError with field errors", async () => {
  globalThis.fetch = async () =>
    respond(422, { error: { code: "invalid_request", message: "Some fields are invalid.", details: { fields: [{ field: "body.phone", message: "Bad phone" }] } } });
  await assert.rejects(api.post("/customers", {}), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 422);
    assert.deepEqual(error.fieldErrors(), { phone: "Bad phone" });
    return true;
  });
});

test("a 401 announces session expiry, except for the sign-in call itself", async () => {
  let notified = 0;
  const stop = onSessionExpired(() => notified++);
  globalThis.fetch = async () => respond(401, { error: { code: "session_expired", message: "Session ended" } });
  await assert.rejects(api.get("/dashboard"));
  await assert.rejects(api.post("/auth/login", { username: "a", password: "b" }));
  stop();
  assert.equal(notified, 1);
});

test("network failures and server errors get readable messages", async () => {
  globalThis.fetch = async () => {
    throw new TypeError("Failed to fetch");
  };
  await assert.rejects(api.get("/x"), (error) => error.code === "network" && /internet connection/.test(error.message));
  globalThis.fetch = async () => new Response("<html>", { status: 502 });
  await assert.rejects(api.get("/x"), (error) => error.status === 502 && /server had a problem/.test(error.message));
});
