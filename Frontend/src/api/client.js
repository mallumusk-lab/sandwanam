// The only place that talks HTTP. The API is always same-origin ("/api"); the session
// lives in an HttpOnly cookie the browser sends automatically, and state-changing
// requests carry the CSRF token the server issued at sign-in.

export const API_BASE = "/api";
const DEFAULT_TIMEOUT_MS = 30000;
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

let csrfToken = null;
const expiryListeners = new Set();

export function setCsrfToken(token) {
  csrfToken = token || null;
}

export function onSessionExpired(listener) {
  expiryListeners.add(listener);
  return () => expiryListeners.delete(listener);
}

export class ApiError extends Error {
  constructor(status, code, message, details = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** Field-level messages from a 422 response, keyed by field name. */
  fieldErrors() {
    const result = {};
    if (this.details?.field) result[this.details.field] = this.message;
    for (const item of this.details?.fields ?? []) result[item.field.split(".").pop()] = item.message;
    return result;
  }
}

export function buildUrl(path, query) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const search = params.toString();
  return `${API_BASE}${path}${search ? `?${search}` : ""}`;
}

async function parseError(response) {
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  const error = body?.error;
  const fallback = response.status >= 500
    ? "The server had a problem. Try again in a moment."
    : "The request could not be completed.";
  return new ApiError(response.status, error?.code ?? "http_error", error?.message ?? fallback, error?.details ?? {});
}

export async function request(path, { method = "GET", body, query, signal, timeout = DEFAULT_TIMEOUT_MS, raw = false } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new DOMException("Timed out", "TimeoutError")), timeout);
  const abortFromCaller = () => controller.abort(signal.reason);
  if (signal) {
    if (signal.aborted) controller.abort(signal.reason);
    else signal.addEventListener("abort", abortFromCaller, { once: true });
  }
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (UNSAFE.has(method) && csrfToken) headers["X-CSRF-Token"] = csrfToken;

  let response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
      signal: controller.signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    if (controller.signal.aborted) {
      throw new ApiError(0, "timeout", "The server took too long to respond. Check the connection and try again.");
    }
    throw new ApiError(0, "network", "Can't reach the server. Check the internet connection and try again.");
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abortFromCaller);
  }

  if (!response.ok) {
    const error = await parseError(response);
    if (response.status === 401 && !path.startsWith("/auth/login")) {
      expiryListeners.forEach((listener) => listener(error));
    }
    throw error;
  }
  if (raw) return response;
  if (response.status === 204) return null;
  return response.json();
}

export const api = {
  get: (path, options) => request(path, { ...options, method: "GET" }),
  post: (path, body, options) => request(path, { ...options, method: "POST", body: body ?? {} }),
  put: (path, body, options) => request(path, { ...options, method: "PUT", body }),
  patch: (path, body, options) => request(path, { ...options, method: "PATCH", body }),
  del: (path, options) => request(path, { ...options, method: "DELETE" }),
};

/** Save a file made in the browser (or downloaded) under `name`, through a temporary blob link. */
export function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

/** Download a file response (CSV, backup) without putting anything sensitive in the URL bar. */
export async function download(path, query, fallbackName) {
  const response = await request(path, { query, raw: true, timeout: 120000 });
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const blob = await response.blob();
  saveBlob(blob, match?.[1] ?? fallbackName);
}
