// Money arrives from the API as strings ("1234.50"). Formatting goes through Intl;
// arithmetic uses integer paise (BigInt) so the UI never shows float drift.

const INR = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2 });
const PLAIN = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const AMOUNT_PATTERN = /^\d{1,10}(\.\d{1,2})?$/;

export function formatINR(value) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  return Number.isFinite(number) ? INR.format(number) : "—";
}

export function formatAmount(value) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  return Number.isFinite(number) ? PLAIN.format(number) : "—";
}

export function formatGrams(value) {
  if (value === null || value === undefined || value === "") return "—";
  return `${formatAmount(value)} g`;
}

/** Normalise what a person typed ("1,23,456.5") into an API amount string, or null. */
export function normaliseAmount(text) {
  const cleaned = String(text ?? "").replace(/[,\s₹]/g, "");
  return AMOUNT_PATTERN.test(cleaned) ? cleaned : null;
}

export function amountError(text, { label = "Amount", allowZero = false, max = null } = {}) {
  if (String(text ?? "").trim() === "") return `Enter the ${label.toLowerCase()}.`;
  const value = normaliseAmount(text);
  if (value === null) return `${label} must be a number with at most 2 decimal places.`;
  const paise = toPaise(value);
  if (paise === 0n && !allowZero) return `${label} must be more than zero.`;
  if (max !== null && paise > toPaise(max)) return `${label} cannot be more than ${formatINR(max)}.`;
  return "";
}

export function toPaise(value) {
  const text = String(value ?? "0").trim();
  const negative = text.startsWith("-");
  const [whole, fraction = ""] = text.replace(/^[-+]/, "").split(".");
  const paise = BigInt(whole || "0") * 100n + BigInt((fraction + "00").slice(0, 2));
  return negative ? -paise : paise;
}

export function fromPaise(paise) {
  const negative = paise < 0n;
  const absolute = negative ? -paise : paise;
  const text = `${absolute / 100n}.${String(absolute % 100n).padStart(2, "0")}`;
  return negative ? `-${text}` : text;
}

export function subtract(a, b) {
  return fromPaise(toPaise(a) - toPaise(b));
}

export function add(a, b) {
  return fromPaise(toPaise(a) + toPaise(b));
}

export function compare(a, b) {
  const difference = toPaise(a) - toPaise(b);
  return difference === 0n ? 0 : difference > 0n ? 1 : -1;
}
