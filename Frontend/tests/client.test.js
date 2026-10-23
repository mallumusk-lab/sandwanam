import { afterEach, test } from "node:test";
import assert from "node:assert/strict";
import { ApiError, api, buildUrl, download, onSessionExpired, saveBlob, setCsrfToken } from "../src/api/client.js";

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

function fakeDownloads() {
  const saved = [];
  const realDocument = globalThis.document;
  const { createObjectURL, revokeObjectURL } = URL;
  globalThis.document = {
    createElement: () => {
      const link = { href: "", download: "", clicked: false, removed: false, click() { this.clicked = true; }, remove() { this.removed = true; } };
      saved.push(link);
      return link;
    },
    body: { appendChild: (link) => { link.attached = true; } },
  };
  URL.createObjectURL = (blob) => {
    saved.blob = blob;
    return "blob:test/1";
  };
  URL.revokeObjectURL = () => {};
  const realSetTimeout = globalThis.setTimeout;
  globalThis.setTimeout = (...args) => {
    const timer = realSetTimeout(...args);
    timer.unref?.(); // the 10 s link clean-up must not hold the test process open
    return timer;
  };
  const restore = () => {
    globalThis.setTimeout = realSetTimeout;
    globalThis.document = realDocument;
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;
  };
  return { saved, restore };
}

test("saveBlob saves through a temporary link; download uses it with the server's file name", async () => {
  const { saved, restore } = fakeDownloads();
  try {
    const blob = new Blob(["%PDF-1.4"], { type: "application/pdf" });
    saveBlob(blob, "Receipt-R7-SAN1L1.pdf");
    assert.equal(saved.blob, blob);
    assert.deepEqual({ ...saved[0], click: undefined, remove: undefined },
      { href: "blob:test/1", download: "Receipt-R7-SAN1L1.pdf", clicked: true, removed: true, attached: true, click: undefined, remove: undefined });

    globalThis.fetch = async () => new Response(new Uint8Array([0x1f, 0x8b, 8]), {
      status: 200, headers: { "Content-Type": "application/gzip", "Content-Disposition": 'attachment; filename="backup_2026-10-23_0930IST.json.gz"' },
    });
    await download("/example/file", null, "backup.json.gz");
    assert.equal(saved[1].download, "backup_2026-10-23_0930IST.json.gz");
    assert.deepEqual(new Uint8Array(await saved.blob.arrayBuffer()), new Uint8Array([0x1f, 0x8b, 8]));

    globalThis.fetch = async () => new Response("a,b", { status: 200, headers: { "Content-Type": "text/csv" } });
    await download("/reports/transactions.csv", { from: "2026-10-01" }, "transactions.csv");
    assert.equal(saved[2].download, "transactions.csv");
  } finally {
    restore();
  }
});
