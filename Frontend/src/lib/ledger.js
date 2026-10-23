// Display names for ledger entry types (the API's transaction kinds).

export const ENTRY_LABELS = {
  newLoan: "Loan disbursed",
  addColl: "Payment received",
  disbursement: "Principal added",
  modify: "Principal added (legacy)",
  compounding: "Annual compounding",
  writeoff: "Written off at closing",
};

export function entryLabel(kind) {
  return ENTRY_LABELS[kind] ?? kind ?? "Entry";
}

// How the server worked out an entry's interest ("Show calculation" on the statement).
export const CALCULATION_LABELS = {
  opening: "Loan opened",
  first_week: "First 7 days: payment goes to principal, no daily interest",
  first_week_settlement: "7 days' interest on the highest principal, then daily",
  inclusive: "Daily interest, both days counted",
  compounding: "Yearly compounding, exact days",
  writeoff: "Closed with a write-off",
  legacy: "Earlier system",
  as_recorded: "As recorded",
};

export function calculationLabel(method) {
  return CALCULATION_LABELS[method] ?? CALCULATION_LABELS.as_recorded;
}

/** The amount that best describes an entry in lists and receipts. */
export function entryAmount(entry) {
  switch (entry.kind) {
    case "addColl":
    case "modify":
      return entry.amount_paid;
    case "disbursement":
    case "compounding":
      return entry.principal_change;
    case "writeoff":
      return entry.written_off;
    case "newLoan":
      return entry.principal_balance;
    default:
      return entry.amount_paid;
  }
}

export function newRequestId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}
