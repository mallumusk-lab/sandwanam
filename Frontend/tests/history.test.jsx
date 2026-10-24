// History import: a loan settled before this system is imported with a closing entry.
// The steps are server-rendered from fixture state (effects don't run), the same way
// pages.test.jsx renders pages; the review step uses a fixture of what POST /imports/preview returns.
import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { StaticRouter } from "react-router-dom/server";
import { LoanStep, ReviewStep, buildPayload, nextCompoundingDate } from "../src/features/history/HistoryImportPage.jsx";
import { formatDay } from "../src/lib/dates.js";
import { formatINR } from "../src/lib/money.js";
import { ToastProvider } from "../src/ui/feedback.jsx";

const LOAN = { gross: "10.00", deduction: "0", principal: "10000", rate: "18", tenure: "12", date: "2025-03-01" };
const ITEMS = [{ name: "Chain", count: 1 }];
const PAYMENT = { key: "e1", date: "2025-03-02", kind: "addColl", amount: "2000", writeOff: false };
const TOP_UP = { key: "e2", date: "2025-03-04", kind: "disbursement", amount: "1000", writeOff: false };
const CLOSING = { key: "e3", date: "2025-03-05", kind: "close", amount: "8750", writeOff: false };

const ROW = { writeoff_principal: null, writeoff_interest: null };
// What the server previews for a short closing: the rows of a live close, shown as if the write-off were confirmed.
const CLOSED_PREVIEW = {
  entries: [
    { ...ROW, index: 0, kind: "newLoan", date: "2025-03-01", amount_paid: "0.00", principal_change: "10000.00", interest_paid: "0.00",
      principal_balance: "10000.00", interest_balance: "0.00", accrued_days: 0 },
    { ...ROW, index: 1, kind: "addColl", date: "2025-03-05", amount_paid: "8750.00", principal_change: "8750.00", interest_paid: "0.00",
      principal_balance: "1250.00", interest_balance: "0.00", accrued_days: 4 },
    { index: 2, kind: "writeoff", date: "2025-03-05", amount_paid: "0.00", principal_change: "0.00", interest_paid: "0.00",
      principal_balance: "0.00", interest_balance: "0.00", accrued_days: 0, writeoff_principal: "1250.00", writeoff_interest: "0.00" },
  ],
  principal_balance: "0.00",
  interest_balance: "0.00",
  closes_on: "2025-03-05",
  remaining_after_close: "1250.00",
};
const OPEN_PREVIEW = {
  entries: CLOSED_PREVIEW.entries.slice(0, 1),
  principal_balance: "10000.00",
  interest_balance: "120.00",
  closes_on: null,
  remaining_after_close: null,
};

const state = (entries, preview = null) => ({
  mode: "existing", customer: { id: 1 }, newCustomer: { name: "", phone: "", address: "", branch: "" },
  items: ITEMS, loan: LOAN, entries, preview,
});

function render(element) {
  return renderToStaticMarkup(
    <StaticRouter location="/history">
      <ToastProvider>{element}</ToastProvider>
    </StaticRouter>,
  );
}

const loanStep = (entries) => render(<LoanStep state={state(entries)} setState={() => {}} onBack={() => {}} onNext={() => {}} />);
const reviewStep = (entries, preview) =>
  render(<ReviewStep state={state(entries, preview)} setState={() => {}} onBack={() => {}} onDone={() => {}} />);
// The entry type selects (the items editor above them has its own selects).
const entryTypeSelects = (html) => (html.match(/<select[\s\S]*?<\/select>/g) ?? []).filter((s) => s.includes("Payment received"));

test("history import entry types offer a loan closing on the last entry only", () => {
  const types = entryTypeSelects(loanStep([PAYMENT, TOP_UP]));
  assert.equal(types.length, 2);
  const [first, last] = types;
  for (const label of ["Payment received", "Additional principal", "Annual compounding"]) {
    assert.match(first, new RegExp(`>${label}</option>`));
    assert.match(last, new RegExp(`>${label}</option>`));
  }
  assert.match(last, /<option value="close">Loan closed \(settled\)<\/option>/);
  assert.doesNotMatch(first, /Loan closed/);
  assert.doesNotMatch(first, /Principal added/);
});

test("history import closing entry asks for the closing date and amount received, and blocks later entries", () => {
  const html = loanStep([PAYMENT, CLOSING]);
  assert.match(html, />Closing date</);
  assert.match(html, />Amount received at closing</);
  assert.match(html, /<option value="close" selected="">Loan closed \(settled\)<\/option>/);
  assert.match(html, /<button[^>]*disabled=""[^>]*>[\s\S]*?Add an entry<\/button>/);
  assert.match(html, /A closed loan has no later entries\./);

  const open = loanStep([PAYMENT]);
  assert.doesNotMatch(open, /<button[^>]*disabled=""[^>]*>[\s\S]*?Add an entry<\/button>/);
  assert.doesNotMatch(open, /A closed loan has no later entries|Closing date|Amount received at closing/);
});

test("history import review shows the closing rows, the closing date and the server's write-off amount", () => {
  const html = reviewStep([PAYMENT, CLOSING], CLOSED_PREVIEW);
  assert.match(html, />Written off at closing</);
  assert.match(html, new RegExp(`This loan will be imported as closed on ${formatDay("2025-03-05")}\\.`));
  const writeOff = `Write off the remaining ${formatINR("1250.00")}`;
  assert.ok(writeOff.includes("₹"), writeOff);
  assert.ok(html.includes(writeOff), "write-off checkbox label uses the server's remainder");
  assert.match(html, /<input[^>]*type="checkbox"(?![^>]*checked)[^>]*>/);

  const confirmed = reviewStep([PAYMENT, { ...CLOSING, writeOff: true }], CLOSED_PREVIEW);
  assert.match(confirmed, /<input[^>]*type="checkbox"[^>]*checked=""[^>]*>/);
});

test("history import review of an open loan has no closing text or write-off", () => {
  const html = reviewStep([PAYMENT], OPEN_PREVIEW);
  assert.doesNotMatch(html, /imported as closed|Write off the remaining|type="checkbox"/);
  // A full settlement closes the loan with nothing left to write off.
  const settled = reviewStep([PAYMENT, CLOSING], { ...CLOSED_PREVIEW, entries: CLOSED_PREVIEW.entries.slice(0, 2), remaining_after_close: null });
  assert.match(settled, /This loan will be imported as closed on/);
  assert.doesNotMatch(settled, /Write off the remaining|type="checkbox"/);
});

test("history import payload sends write_off_remaining on the closing entry only", () => {
  const payload = buildPayload(state([PAYMENT, TOP_UP, { ...CLOSING, amount: "0", writeOff: true }]));
  assert.deepEqual(payload.entries, [
    { date: "2025-03-02", kind: "addColl", amount: "2000" },
    { date: "2025-03-04", kind: "disbursement", amount: "1000" },
    { date: "2025-03-05", kind: "close", amount: "0", write_off_remaining: true },
  ]);
  assert.equal(buildPayload(state([CLOSING])).entries[0].write_off_remaining, false);
});

test("history import loan step calculates and shows net weight", () => {
  const html = loanStep([PAYMENT]);
  assert.match(html, />Net weight</);
  assert.match(html, /10\.00 g/);
  assert.match(html, /Gross weight minus deduction\./);
});

test("history import loan step renders compounding entry and sends amount 0 when blank", () => {
  const compoundingEntry = { key: "c1", date: "2026-03-01", kind: "compounding", amount: "", writeOff: false };
  const html = loanStep([compoundingEntry]);
  assert.match(html, /<option value="compounding" selected="">Annual compounding<\/option>/);
  assert.match(html, />Compounded interest</);
  assert.match(html, /Calculated on preview/);

  const payload = buildPayload(state([compoundingEntry]));
  assert.equal(payload.entries[0].amount, "0");
  assert.equal(payload.entries[0].kind, "compounding");
});

test("compounding date auto-calculates from start date and compounded interest is calculated on preview", () => {
  const calculated = nextCompoundingDate("2024-03-01", [{ key: "c1", kind: "compounding" }], "c1");
  assert.equal(calculated, "2025-03-01");
  const second = nextCompoundingDate("2024-03-01", [{ key: "c1", kind: "compounding" }, { key: "c2", kind: "compounding" }], "c2");
  assert.equal(second, "2026-03-01");
});



