// Backup uploads (ZIP and gzip detection, the ZIP password, compression, base64, size limits) and the email check.
import { test } from "node:test";
import assert from "node:assert/strict";
import { gunzipSync, gzipSync } from "node:zlib";
import {
  BackupFileError, MAX_BASE64_CHARS, TOO_LARGE_MESSAGE, gzipBytes, isGzip, isZip, looksLikeZip, prepareUpload, toBase64,
  zipPasswordError,
} from "../src/features/backup/backupFile.js";
import { emailError } from "../src/lib/validation.js";

const encode = (text) => new TextEncoder().encode(text);
const DOCUMENT = { format_version: 3, app: "gold-loan-desk", tables: { customers: [[1, "Anu"]] } };

test("isGzip looks at the gzip signature, not the file name", () => {
  assert.equal(isGzip(new Uint8Array(gzipSync(Buffer.from("{}")))), true);
  assert.equal(isGzip(encode('{"format_version":3}')), false);
  assert.equal(isGzip(new Uint8Array([0x1f])), false);
  assert.equal(isGzip(new Uint8Array([])), false);
});

test("toBase64 matches Node's encoder, across chunk boundaries", () => {
  for (const length of [0, 1, 2, 3, 0x8000, 0x8001, 100003]) {
    const bytes = new Uint8Array(length).map((_, i) => (i * 131 + 7) % 256);
    assert.equal(toBase64(bytes), Buffer.from(bytes).toString("base64"), `length ${length}`);
  }
});

test("gzipBytes compresses in the browser way and round-trips", { skip: typeof CompressionStream !== "function" }, async () => {
  const input = encode(JSON.stringify(DOCUMENT).repeat(50));
  const packed = await gzipBytes(input);
  assert.ok(isGzip(packed));
  assert.ok(packed.length < input.length);
  assert.deepEqual(new Uint8Array(gunzipSync(packed)), input);
});

test("prepareUpload sends a .json.gz as it is and compresses a .json", { skip: typeof CompressionStream !== "function" }, async () => {
  const gz = new Uint8Array(gzipSync(Buffer.from(JSON.stringify(DOCUMENT))));
  const fromGz = await prepareUpload(new File([gz], "backup.json.gz", { type: "application/gzip" }));
  assert.deepEqual(Object.keys(fromGz), ["backup_gzip"]);
  assert.equal(fromGz.backup_gzip, Buffer.from(gz).toString("base64"));

  const fromJson = await prepareUpload(new File([JSON.stringify(DOCUMENT)], "backup.json", { type: "application/json" }));
  assert.deepEqual(JSON.parse(gunzipSync(Buffer.from(fromJson.backup_gzip, "base64")).toString("utf8")), DOCUMENT);
});

test("prepareUpload refuses files over the upload limit with a clear message", async () => {
  const big = new Uint8Array(Math.ceil(MAX_BASE64_CHARS / 4) * 3 + 3);
  big[0] = 0x1f;
  big[1] = 0x8b;
  await assert.rejects(prepareUpload(new File([big], "big.json.gz")), (error) => {
    assert.ok(error instanceof BackupFileError);
    assert.equal(error.title, "File too large");
    assert.equal(error.message, TOO_LARGE_MESSAGE);
    return true;
  });
  await assert.rejects(prepareUpload({ size: 49 * 1024 * 1024, arrayBuffer: () => assert.fail("not read") }), { message: TOO_LARGE_MESSAGE });
});

test("without CompressionStream a .json is sent as parsed JSON, up to 4 MB", async () => {
  const saved = globalThis.CompressionStream;
  globalThis.CompressionStream = undefined;
  try {
    assert.deepEqual(await prepareUpload(new File([JSON.stringify(DOCUMENT)], "backup.json")), { backup: DOCUMENT });
    await assert.rejects(prepareUpload(new File(["not json"], "backup.json")), { title: "Not a backup file", message: "The file isn't valid JSON." });
    await assert.rejects(prepareUpload(new File([new Uint8Array(4 * 1024 * 1024 + 1)], "backup.json")), { title: "File too large" });
    // a gzip file needs no compression, so it still goes as it is
    const gz = new Uint8Array(gzipSync(Buffer.from("{}")));
    assert.deepEqual(await prepareUpload(new File([gz], "b.json.gz")), { backup_gzip: Buffer.from(gz).toString("base64") });
  } finally {
    globalThis.CompressionStream = saved;
  }
});

// The first bytes of a ZIP (local file header) as the emailed backup has them.
const ZIP = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x33, 0x00, 0x01, 0x00, 0x63, 0x00, 1, 2, 3, 4, 5, 6]);
const PASSWORD = "Correct-horse-battery-9";

test("a ZIP is recognised by name or type to ask for the password, and by its bytes when sent", () => {
  assert.equal(looksLikeZip({ name: "backup_2026-10-23_0001IST.zip", type: "" }), true);
  assert.equal(looksLikeZip({ name: "BACKUP.ZIP", type: "" }), true);
  assert.equal(looksLikeZip({ name: "download", type: "application/x-zip-compressed" }), true);
  assert.equal(looksLikeZip({ name: "backup.json", type: "application/json" }), false);
  assert.equal(looksLikeZip({ name: "backup.json.gz", type: "application/gzip" }), false);
  assert.equal(looksLikeZip(null), false);
  assert.equal(isZip(ZIP), true);
  assert.equal(isZip(encode("PK")), false);
  assert.equal(isZip(new Uint8Array(gzipSync(Buffer.from("{}")))), false);
});

test("the ZIP is sent as it is with its password, which must be 12 to 128 characters", async () => {
  const body = await prepareUpload(new File([ZIP], "backup_2026-10-23_0001IST.zip", { type: "application/zip" }), { zipPassword: PASSWORD });
  assert.deepEqual(body, { backup_zip: Buffer.from(ZIP).toString("base64"), zip_password: PASSWORD });
  // a renamed ZIP is still a ZIP
  assert.deepEqual(Object.keys(await prepareUpload(new File([ZIP], "backup.bin"), { zipPassword: PASSWORD })), ["backup_zip", "zip_password"]);
  for (const [password, message] of [
    [undefined, /^Enter the ZIP password\./],
    ["", /^Enter the ZIP password\./],
    ["x".repeat(11), /^The ZIP password is 12 to 128 characters long\.$/],
    ["x".repeat(129), /^The ZIP password is 12 to 128 characters long\.$/],
  ]) {
    await assert.rejects(prepareUpload(new File([ZIP], "b.zip"), { zipPassword: password }), (error) => {
      assert.ok(error instanceof BackupFileError);
      assert.equal(error.field, "zip_password");
      assert.match(error.message, message);
      return true;
    });
  }
  assert.equal(zipPasswordError("x".repeat(12)), "");
  assert.equal(zipPasswordError("x".repeat(128)), "");
  const big = new Uint8Array(Math.ceil(MAX_BASE64_CHARS / 4) * 3 + 3);
  big.set(ZIP);
  await assert.rejects(prepareUpload(new File([big], "big.zip"), { zipPassword: PASSWORD }), { title: "File too large", message: TOO_LARGE_MESSAGE });
});

test("emailError accepts exactly one address, like the server", () => {
  for (const ok of ["backups@example.com", "a.b+c@x.co.in", "  office@gold-loan.in  ", "O'Neil@Example.ORG", `${"a".repeat(64)}@x.co`]) {
    assert.equal(emailError(ok), "", ok);
  }
  for (const bad of ["", null, "a,b@x.co", "a@x.co, c@y.co", "a@x.co;c@y.co", "a@b", "a b@x.co", ".a@x.co", "a..b@x.co", "a@-x.co",
    "a@x.c", "a@x.co.", "<a@x.co>", "Name <a@x.co>", `${"a".repeat(65)}@x.co`, `a@${"b".repeat(250)}.co`, "a@x.co\nb@y.co"]) {
    assert.equal(emailError(bad), "Enter one email address, for example backups@example.com.", String(bad));
  }
});
