// Business dates are IST calendar days ("YYYY-MM-DD"). India has no daylight saving,
// so a fixed +05:30 offset is exact on every device, whatever its own timezone.

const IST_OFFSET_MS = 330 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

const DATE_FORMAT = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const DATE_TIME_FORMAT = new Intl.DateTimeFormat("en-IN", {
  day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata",
});

function toUTCDate(day) {
  const match = ISO_DATE.exec(day ?? "");
  if (!match) return null;
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  return date.toISOString().slice(0, 10) === day ? date : null;
}

export function isValidDay(day) {
  return toUTCDate(day) !== null;
}

export function todayIST(now = Date.now()) {
  return new Date(now + IST_OFFSET_MS).toISOString().slice(0, 10);
}

export function addDays(day, days) {
  const date = toUTCDate(day);
  return new Date(date.getTime() + days * DAY_MS).toISOString().slice(0, 10);
}

export function addMonths(day, months) {
  const date = toUTCDate(day);
  const index = date.getUTCMonth() + months;
  const year = date.getUTCFullYear() + Math.floor(index / 12);
  const month = ((index % 12) + 12) % 12;
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return new Date(Date.UTC(year, month, Math.min(date.getUTCDate(), lastDay))).toISOString().slice(0, 10);
}

export function daysBetween(from, to) {
  return Math.round((toUTCDate(to).getTime() - toUTCDate(from).getTime()) / DAY_MS);
}

export function formatDay(day) {
  const date = toUTCDate(day);
  return date ? DATE_FORMAT.format(date).replace(/\bSept\b/g, "Sep") : "—";
}

export function formatDateTime(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : DATE_TIME_FORMAT.format(date).replace(/\bSept\b/g, "Sep");
}

/** Named reporting periods. The Indian financial year runs April–March. */
export function periodPreset(name, today = todayIST()) {
  const [year, month] = today.split("-").map(Number);
  switch (name) {
    case "today":
      return { from: today, to: today };
    case "week":
      return { from: addDays(today, -6), to: today };
    case "month":
      return { from: `${today.slice(0, 7)}-01`, to: today };
    case "last30":
      return { from: addDays(today, -29), to: today };
    case "fy": {
      const start = month >= 4 ? year : year - 1;
      return { from: `${start}-04-01`, to: today };
    }
    default:
      throw new Error(`Unknown period ${name}`);
  }
}
