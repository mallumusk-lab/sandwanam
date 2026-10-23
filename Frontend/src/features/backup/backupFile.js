// Turning a chosen backup file into a request body for /backup/check and /backup/restore.
// Accepted: the emailed password ZIP as it is (sent with its password, opened on the server
// in memory), the .json inside it, or a .json.gz. Files travel compressed and base64-encoded,
// so a typical backup fits the hosting provider's request size limit (about 4.5 MB).

export const MAX_BASE64_CHARS = 4_400_000;
export const MAX_LEGACY_BYTES = 4 * 1024 * 1024;
export const MAX_FILE_BYTES = 48 * 1024 * 1024; // the server's limit for an unpacked upload
export const ZIP_PASSWORD_MIN = 12; // the server's BACKUP_ZIP_PASSWORD rule
export const ZIP_PASSWORD_MAX = 128;
export const TOO_LARGE_MESSAGE =
  "Backup files up to about 3 MB compressed can be uploaded. For a larger backup, ask whoever manages the hosting to restore it from the database provider's backups.";

export class BackupFileError extends Error {
  constructor(title, message, field) {
    super(message);
    this.name = "BackupFileError";
    this.title = title;
    this.field = field;
  }
}

/** True when the bytes start with the gzip signature (1F 8B). */
export function isGzip(bytes) {
  return bytes.length >= 2 && bytes[0] === 0x1f && bytes[1] === 0x8b;
}

/** True when the bytes start with a ZIP local file header ("PK", 03 04). */
export function isZip(bytes) {
  return bytes.length >= 4 && bytes[0] === 0x50 && bytes[1] === 0x4b && bytes[2] === 0x03 && bytes[3] === 0x04;
}

/** Whether a chosen file looks like a ZIP (by name or type), so the page can ask for its password. */
export function looksLikeZip(file) {
  if (!file) return false;
  const type = String(file.type ?? "").toLowerCase();
  return /\.zip$/i.test(String(file.name ?? "")) || type === "application/zip" || type === "application/x-zip-compressed";
}

/** The message for a ZIP password that the server would refuse, or "". */
export function zipPasswordError(password) {
  const text = String(password ?? "");
  if (!text) return "Enter the ZIP password. It is the backup password set on the server (BACKUP_ZIP_PASSWORD).";
  if (text.length < ZIP_PASSWORD_MIN || text.length > ZIP_PASSWORD_MAX) {
    return `The ZIP password is ${ZIP_PASSWORD_MIN} to ${ZIP_PASSWORD_MAX} characters long.`;
  }
  return "";
}

export function canCompress() {
  return typeof CompressionStream === "function";
}

/** Gzip in the browser (CompressionStream; no library). */
export async function gzipBytes(bytes) {
  const stream = new Blob([bytes]).stream().pipeThrough(new globalThis.CompressionStream("gzip"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** Base64 without building one huge argument list (btoa takes a binary string). */
export function toBase64(bytes) {
  const CHUNK = 0x8000;
  let binary = "";
  for (let i = 0; i < bytes.length; i += CHUNK) binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
  return btoa(binary);
}

function tooLarge() {
  return new BackupFileError("File too large", TOO_LARGE_MESSAGE);
}

function fitsUpload(bytes) {
  return Math.ceil(bytes.length / 3) * 4 <= MAX_BASE64_CHARS;
}

/**
 * The request body for a chosen file:
 * - `{ backup_zip, zip_password }` for the emailed ZIP (recognised by its bytes; the password is required),
 * - `{ backup_gzip }` for a .json.gz as it is, or a .json compressed here,
 * - `{ backup }` with the parsed JSON on browsers without CompressionStream.
 */
export async function prepareUpload(file, { zipPassword } = {}) {
  if (file.size > MAX_FILE_BYTES) throw tooLarge();
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (isZip(bytes)) {
    const passwordError = zipPasswordError(zipPassword);
    if (passwordError) throw new BackupFileError("ZIP password needed", passwordError, "zip_password");
    if (!fitsUpload(bytes)) throw tooLarge();
    return { backup_zip: toBase64(bytes), zip_password: zipPassword };
  }
  if (!isGzip(bytes) && !canCompress()) {
    if (bytes.length > MAX_LEGACY_BYTES) {
      throw new BackupFileError("File too large", "Backups up to 4 MB can be uploaded in this browser. Use a current browser for a larger one.");
    }
    try {
      return { backup: JSON.parse(new TextDecoder().decode(bytes)) };
    } catch {
      throw new BackupFileError("Not a backup file", "The file isn't valid JSON.");
    }
  }
  const packed = isGzip(bytes) ? bytes : await gzipBytes(bytes);
  if (!fitsUpload(packed)) throw tooLarge();
  return { backup_gzip: toBase64(packed) };
}
