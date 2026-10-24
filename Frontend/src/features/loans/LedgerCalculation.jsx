import { formatDay } from "../../lib/dates.js";
import { calculationLabel } from "../../lib/ledger.js";
import { formatINR } from "../../lib/money.js";

// Shows how the server worked out one ledger entry. Every figure comes from the entry's
// `calculation` (GET /loans/{n}); this only formats it and never recalculates.

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

function term(principal, rate, days) {
  return `${formatINR(principal)} × ${rate}% × ${plural(days, "day")} ÷ 365`;
}

/** Plain lines describing a calculation, for the statement's detail row. */
export function calculationLines(calc, entry = {}) {
  const lines = [];
  if (calc.method === "legacy") return [calc.note ?? "Earlier system — not recalculated"];

  if (calc.period_from && calc.period_to && calc.days) {
    lines.push(`Period: ${formatDay(calc.period_from)} to ${formatDay(calc.period_to)}, ${plural(calc.days, "day")}`);
  }
  if (calc.peak_principal && calc.first_week_days) {
    lines.push(`First ${calc.first_week_days} days on the highest principal: ${term(calc.peak_principal, calc.rate, calc.first_week_days)}`);
    if (calc.extra_days && calc.extra_principal) {
      lines.push(`Plus ${plural(calc.extra_days, "day")} after day ${calc.first_week_days}: ${term(calc.extra_principal, calc.rate, calc.extra_days)}`);
    }
    lines.push(`Interest: ${formatINR(calc.interest_accrued)}, rounded once`);
  } else if (calc.principal_charged && calc.rate && calc.days) {
    lines.push(`Interest: ${term(calc.principal_charged, calc.rate, calc.days)} = ${formatINR(calc.interest_accrued)}`);
  }
  if (entry.kind === "addColl" || entry.kind === "modify") {
    lines.push(`Paid ${formatINR(entry.amount_paid)} → ${formatINR(calc.interest_paid)} interest, ${formatINR(calc.principal_paid)} principal`);
  }
  if (entry.kind === "writeoff" && entry.written_off) lines.push(`Written off: ${formatINR(entry.written_off)}`);
  lines.push(`Balance: principal ${formatINR(calc.principal_balance)}, interest ${formatINR(calc.interest_balance)}`);
  return lines;
}

// The server's note adds what the figures alone don't say (opening terms, the first-week rule,
// or why a row is shown as recorded).
const NOTE_METHODS = new Set(["opening", "first_week", "as_recorded"]);

export function calculationMethodTitle(calc) {
  if (calc?.method === "first_week_settlement" && !calc?.extra_days) {
    return "7 days' interest on the highest principal";
  }
  return calculationLabel(calc?.method);
}

export function LedgerCalculation({ calculation, entry }) {
  if (!calculation) return <p className="calc-note">No calculation is available for this entry.</p>;
  const note = NOTE_METHODS.has(calculation.method) ? calculation.note : null;
  return (
    <div className="calc">
      <p className="calc-line calc-method">{calculationMethodTitle(calculation)}</p>
      {calculationLines(calculation, entry).map((line, index) => (
        <p key={index} className="calc-line">{line}</p>
      ))}
      {note ? <p className="calc-note">{note}</p> : null}
    </div>
  );
}
