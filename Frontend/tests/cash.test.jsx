// Cash ledger page, server-rendered from a fixture overview (the shape GET /cash returns).
// Effects don't run on the server, so these check what each overview state draws.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { StaticRouter } from "react-router-dom/server";
import { CashLedgerView } from "../src/features/cash/CashLedgerPage.jsx";
import { DifferencePill, differenceLabel } from "../src/features/cash/CashParts.jsx";
import { ToastProvider } from "../src/ui/feedback.jsx";

const CATEGORIES = [
  { key: "loan_collection", label: "Loan collection", direction: "in" },
  { key: "from_head_office", label: "Cash from head office", direction: "in" },
  { key: "other_income", label: "Other income", direction: "in" },
  { key: "loan_disbursement", label: "Loan disbursement", direction: "out" },
  { key: "bill_payment", label: "Bill payment", direction: "out" },
  { key: "donation", label: "Donation", direction: "out" },
  { key: "expense", label: "Expense", direction: "out" },
  { key: "to_head_office", label: "Cash to head office / bank", direction: "out" },
  { key: "other", label: "Other (type a description)", direction: "any" },
];

const NOT_VOIDED = { voided: false, voided_at: null, voided_by: null, void_reason: null };
const COLLECTION = {
  id: 11, at: "2026-10-23T04:30:00Z", direction: "in", category: "loan_collection", category_label: "Loan collection",
  description: null, reference: "SAN1L4", amount: "5000.00", recorded_by: "User1", ...NOT_VOIDED,
};
const VOIDED = {
  id: 12, at: "2026-10-23T05:00:00Z", direction: "out", category: "other", category_label: "Other (type a description)",
  description: "Tea for staff", reference: null, amount: "120.00", recorded_by: "User1",
  voided: true, voided_at: "2026-10-23T05:10:00Z", voided_by: "User1", void_reason: "Entered twice",
};
const BILL = {
  id: 9, at: "2026-10-22T07:00:00Z", direction: "out", category: "bill_payment", category_label: "Bill payment",
  description: "Electricity", reference: "KSEB-1", amount: "1000.00", recorded_by: "User1", ...NOT_VOIDED,
};

const DAY = {
  carried_forward: "0.00", opening_counted: "0.00", opening_difference: "0.00", cash_in: "0.00", cash_out: "0.00", expected: "0.00",
  closing_counted: null, closing_difference: null, closed_automatically: false, opened_by: "User1", opened_at: "2026-10-23T03:30:00Z",
  closed_by: null, closed_at: null, entries: [],
};
// Server figures on purpose differ from anything the browser could add up from the entries.
const TODAY_OPEN = {
  ...DAY, id: 7, day: "2026-10-23", status: "open", carried_forward: "10000.00", opening_counted: "9950.00", opening_difference: "-50.00",
  cash_in: "5000.00", cash_out: "0.00", expected: "14950.00", entries: [COLLECTION, VOIDED],
};
const YESTERDAY = {
  ...DAY, id: 6, day: "2026-10-22", status: "closed", carried_forward: "8000.00", opening_counted: "8000.00", cash_in: "3000.00",
  cash_out: "1000.00", expected: "10000.00", closing_counted: "10025.00", closing_difference: "25.00", closed_by: "User1",
  closed_at: "2026-10-22T13:00:00Z", opened_at: "2026-10-22T03:30:00Z", entries: [BILL],
};
const AUTO_CLOSED = {
  ...DAY, id: 5, day: "2026-10-21", status: "closed", carried_forward: "8000.00", opening_counted: "8000.00", expected: "8000.00",
  closing_counted: "8000.00", closing_difference: "0.00", closed_automatically: true, closed_by: "system", closed_at: "2026-10-21T18:30:00Z",
};

const OVERVIEW = {
  branch: "SAN", branch_name: "Santhwanam", today: "2026-10-23",
  carry_forward: { amount: "10025.00", from_day: "2026-10-22" },
  today_day: null, history: [YESTERDAY, AUTO_CLOSED], categories: CATEGORIES,
  suggestions: ["Tea for staff", "Courier"], can_reopen: false,
};

function render(overview, props = {}) {
  return renderToStaticMarkup(
    <StaticRouter location="/cash">
      <ToastProvider>
        <CashLedgerView overview={overview} onSaved={() => {}} onChanged={async () => {}} {...props} />
      </ToastProvider>
    </StaticRouter>,
  );
}

const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

test("cash ledger: with no day today the start card shows the carry forward and the counted field", () => {
  const html = render(OVERVIEW);
  assert.match(html, /<h2 class="card-title">Start the day<\/h2>/);
  assert.match(text(html), /Carried forward from 22 Oct 2026: ₹10,025\.00/);
  assert.match(html, /<label class="field-label" for="[^"]+">Cash in hand now \(counted\)<\/label>/);
  assert.match(text(html), /Enter the counted amount to compare it with the carry forward\./);
  assert.match(html, /<button type="submit" class="btn btn-primary"[^>]*>[\s\S]*?Start the day<\/button>/);
  assert.doesNotMatch(html, /Add entry|Close the day|Cash in drawer now/, "nothing can be recorded before the day starts");
  assert.match(text(html), /Santhwanam \(SAN\) · today is 23 Oct 2026/);
});

test("cash ledger: a branch's first day carries forward ₹0.00", () => {
  const html = render({ ...OVERVIEW, carry_forward: { amount: "0.00", from_day: null }, history: [] });
  assert.match(text(html), /No earlier closed day, so the carry forward is ₹0\.00\./);
  assert.match(text(html), /No earlier days yet\. Each day is kept for 14 days\./);
});

test("cash ledger: differences are shown in words, not colour alone", () => {
  assert.equal(differenceLabel("0.00"), "Matches");
  assert.equal(differenceLabel("50.00"), "Excess ₹50.00");
  assert.equal(differenceLabel("-50.00"), "Shortage ₹50.00");
  assert.equal(differenceLabel("-0.05"), "Shortage ₹0.05");
  assert.equal(differenceLabel(null), "—");
  const pill = (value) => renderToStaticMarkup(<DifferencePill value={value} />);
  assert.equal(pill("0.00"), '<span class="pill pill-success">Matches</span>');
  assert.equal(pill("25.00"), '<span class="pill pill-warning">Excess ₹25.00</span>');
  assert.equal(pill("-1.50"), '<span class="pill pill-danger">Shortage ₹1.50</span>');
});

test("cash ledger: today's summary shows the server's figures and the add-entry form", () => {
  const html = render({ ...OVERVIEW, today_day: TODAY_OPEN });
  const plain = text(html);
  assert.match(html, /<h2 class="card-title">Today · 23 Oct 2026<\/h2>/);
  assert.match(plain, /Carried forward ₹10,000\.00/);
  assert.match(plain, /Opening counted ₹9,950\.00/);
  assert.match(plain, /Opening difference Shortage ₹50\.00/);
  assert.match(plain, /Cash in ₹5,000\.00/);
  assert.match(plain, /Cash out ₹0\.00/);
  assert.match(html, /<div class="total"><dt>Cash in drawer now<\/dt><dd class="num">₹14,950\.00<\/dd><\/div>/);
  assert.match(html, />Close the day<\/button>/);
  assert.doesNotMatch(html, /Start the day|>Reopen</);
  // Add entry: cash in is chosen first, so only cash-in categories and Other are offered.
  assert.match(html, /<h2 class="card-title">Add entry<\/h2>/);
  assert.match(html, /<legend class="visually-hidden">Cash in or out<\/legend>/);
  for (const label of ["Loan collection", "Cash from head office", "Other income", "Other (type a description)"]) {
    assert.match(html, new RegExp(`<option value="[a-z_]+">${label.replace(/[()]/g, "\\$&")}</option>`), label);
  }
  for (const label of ["Loan disbursement", "Bill payment", "Donation"]) {
    assert.doesNotMatch(html, new RegExp(`<option value="[a-z_]+">${label}</option>`), label);
  }
  const listId = /list="([^"]+)"/.exec(html)[1];
  assert.match(html, new RegExp(`<datalist id="${listId}"><option value="Tea for staff"></option><option value="Courier"></option></datalist>`));
  assert.match(html, />Reference<span class="optional"> \(optional\)<\/span>/);
  assert.match(html, />Record cash in<\/button>/);
  assert.doesNotMatch(html, /type="date"/, "every entry is dated today by the server");
});

test("cash ledger: a voided entry stays listed, struck through and labelled, with its reason", () => {
  const html = render({ ...OVERVIEW, today_day: TODAY_OPEN });
  assert.match(html, /<caption>Today&#x27;s cash movements<\/caption>/);
  assert.match(html, /<s class="cash-voided">₹120\.00<\/s>/);
  assert.match(html, /<s class="cash-voided">Tea for staff<\/s>/);
  assert.match(html, /<span class="pill pill-danger">Voided<\/span><span>Entered twice<\/span>/);
  // Only the live entry can be voided, and the button says which entry it is.
  assert.equal((html.match(/>Void<span class="visually-hidden">/g) ?? []).length, 1);
  assert.match(html, /Void<span class="visually-hidden"> entry of ₹5,000\.00, Loan collection<\/span>/);
  assert.match(html, /<span class="pill pill-success">Cash in<\/span>/);
  assert.match(html, /<span class="pill pill-warning">Cash out<\/span>/);
});

test("cash ledger: a closed day is locked; head office may reopen only when the server allows", () => {
  const closed = {
    ...TODAY_OPEN, status: "closed", closing_counted: "14900.00", closing_difference: "-50.00", closed_by: "User1",
    closed_at: "2026-10-23T13:00:00Z", entries: [COLLECTION],
  };
  const html = render({ ...OVERVIEW, today_day: closed });
  const plain = text(html);
  assert.match(plain, /Expected at closing ₹14,950\.00/);
  assert.match(plain, /Counted at closing ₹14,900\.00/);
  assert.match(plain, /Closing difference Shortage ₹50\.00/);
  assert.match(plain, /Closed by User1/);
  assert.match(html, /<span class="pill">Closed<\/span>/);
  assert.doesNotMatch(html, /Add entry|>Close the day<|>Void<|>Reopen</);
  assert.match(render({ ...OVERVIEW, today_day: closed, can_reopen: true }), /<\/svg>Reopen<\/button>/);
});

test("cash ledger: history days are collapsed disclosures that reveal each day's entries", () => {
  const html = render({ ...OVERVIEW, today_day: TODAY_OPEN });
  assert.match(html, /<h2 class="card-title">Last 14 days<\/h2>/);
  for (const day of [YESTERDAY, AUTO_CLOSED]) {
    const button = new RegExp(`<button type="button" class="btn btn-ghost" aria-expanded="false" aria-controls="cash-day-${day.id}">`);
    assert.match(html, button, day.day);
    assert.match(html, new RegExp(`<div id="cash-day-${day.id}" class="cash-history-entries" hidden="">`), day.day);
  }
  assert.match(text(html), /22 Oct 2026 · 1 cash movement Closed/);
  assert.match(text(html), /Opening counted ₹8,000\.00 Cash in ₹3,000\.00 Cash out ₹1,000\.00 Closing counted ₹10,025\.00 Difference Excess ₹25\.00/);
  assert.match(html, /<caption>Cash movements on 22 Oct 2026<\/caption>/);
  assert.match(html, /<span class="pill pill-warning">Closed automatically<\/span>/);
  assert.match(text(html), /Closed automatically \(not counted\)\./);
  assert.doesNotMatch(html.slice(html.indexOf("Last 14 days")), />Void</, "earlier days are locked");
});

test("cash ledger: amounts are never added up in the browser", () => {
  const src = join(process.cwd(), "src", "features", "cash");
  for (const file of ["CashLedgerPage.jsx", "CashParts.jsx", "CashDialogs.jsx"]) {
    const code = readFileSync(join(src, file), "utf8");
    assert.doesNotMatch(code, /(?<![.\w])add\(|parseFloat|toFixed\(|Number\(|\.reduce\(/, file);
    assert.doesNotMatch(code, /#[0-9a-fA-F]{3,6}\b|style=|localStorage|console\.log/, file);
  }
  const dialogs = readFileSync(join(src, "CashDialogs.jsx"), "utf8");
  assert.match(dialogs, /closing_counted: amount, expected_total: day\.expected/, "close sends the expected figure the server showed");
  assert.match(dialogs, /err\.code === "cash_changed"/);
});
