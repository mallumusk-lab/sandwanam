import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import assert from "node:assert/strict";
import { addDays, addMonths, daysBetween, formatDay, isValidDay, periodPreset, todayIST } from "../src/lib/dates.js";
import { quote, dailyInterest, monthlyRate } from "../src/lib/interest.js";
import { addItem, itemsError, itemsText, totalQuantity } from "../src/lib/items.js";
import { CALCULATION_LABELS, calculationLabel, entryAmount, entryLabel, entryPrincipalPaid, newRequestId } from "../src/lib/ledger.js";
import { add, amountError, compare, formatINR, fromPaise, normaliseAmount, subtract, toPaise } from "../src/lib/money.js";
import { ALL_BRANCHES_LABEL, CREATE, FEATURES, can, homePath, isHeadOfficeStaff } from "../src/lib/permissions.js";
import { passwordError, phoneError, rateError, tenureError, weightErrors } from "../src/lib/validation.js";

test("money: exact paise arithmetic", () => {
  assert.equal(toPaise("10123.45"), 1012345n);
  assert.equal(subtract("10123.45", "10000.1"), "123.35");
  assert.equal(add("0.1", "0.2"), "0.30");
  assert.equal(fromPaise(-5n), "-0.05");
  assert.equal(compare("10.00", "9.99"), 1);
});

test("money: formatting and input normalisation", () => {
  assert.equal(formatINR("123456.5"), "₹1,23,456.50");
  assert.equal(formatINR(null), "—");
  assert.equal(normaliseAmount("₹ 1,23,456.50"), "123456.50");
  for (const bad of ["-5", "1.005", "abc", "1e5"]) assert.equal(normaliseAmount(bad), null, bad);
  assert.match(amountError("0"), /more than zero/);
  assert.equal(amountError("0", { allowZero: true }), "");
  assert.match(amountError("101", { max: "100" }), /cannot be more/);
  assert.match(amountError(""), /Enter/);
});

test("dates: IST business day regardless of device timezone", () => {
  assert.equal(todayIST(Date.UTC(2024, 1, 29, 20, 30)), "2024-03-01");
  assert.equal(todayIST(Date.UTC(2024, 1, 29, 18, 29)), "2024-02-29");
  assert.equal(addMonths("2025-01-31", 1), "2025-02-28");
  assert.equal(addMonths("2024-01-31", 1), "2024-02-29");
  assert.equal(addMonths("2025-11-15", 3), "2026-02-15");
  assert.equal(addDays("2025-12-31", 1), "2026-01-01");
  assert.equal(daysBetween("2025-01-01", "2026-01-01"), 365);
  assert.equal(isValidDay("2025-02-30"), false);
  assert.equal(formatDay("2025-03-10"), "10 Mar 2025");
  assert.deepEqual(periodPreset("fy", "2026-02-10"), { from: "2025-04-01", to: "2026-02-10" });
  assert.deepEqual(periodPreset("fy", "2026-04-02"), { from: "2026-04-01", to: "2026-04-02" });
});

test("interest: calculator matches the shared ledger vectors", () => {
  const vectors = JSON.parse(readFileSync(join(process.cwd(), "..", "test-vectors", "interest.json"), "utf8"));
  assert.ok(vectors.cases.length > 5);
  for (const c of vectors.cases) {
    const q = quote({ principal: c.principal, rate: c.rate, start: c.start, asOf: c.as_of, closing: c.closing });
    assert.equal(q.principal, c.expected.principal, `${c.name}: principal`);
    assert.equal(q.interest, c.expected.interest, `${c.name}: interest`);
    assert.equal(q.periodDays, c.expected.period_days, `${c.name}: days`);
    assert.equal(q.compoundings, c.expected.compoundings, `${c.name}: compoundings`);
  }
  const year = quote({ principal: "100000", rate: "12", start: "2025-01-01", asOf: "2026-01-01" });
  assert.equal(year.totalInterest, "12036.82", "includes interest already compounded into principal");
  assert.equal(dailyInterest("100000", "18"), "49.32");
  assert.equal(monthlyRate("18"), "1.50");
});

test("items: merge, count and validate", () => {
  let items = addItem([], "Ring", 1);
  items = addItem(items, " ring ", 2);
  items = addItem(items, "Chain", 1);
  assert.deepEqual(items, [{ name: "Ring", qty: 3 }, { name: "Chain", qty: 1 }]);
  assert.equal(totalQuantity(items), 4);
  assert.equal(itemsText(items), "Ring(3), Chain(1)");
  assert.equal(itemsError([]), "Add at least one pledged item.");
  assert.match(itemsError([{ name: "Ring", qty: 0 }]), /Quantities/);
});

test("validation mirrors the server rules", () => {
  assert.equal(phoneError("98765 43210"), "");
  assert.notEqual(phoneError("12345"), "");
  assert.equal(weightErrors("10", "10").deduction, "Deduction must be less than the gross weight.");
  assert.deepEqual(weightErrors("10.1", "0.3"), { gross: "", deduction: "" });
  assert.notEqual(rateError("101"), "");
  assert.notEqual(tenureError("1.5"), "");
  assert.notEqual(passwordError("short"), "");
  assert.notEqual(passwordError("my-User1-secret", "User1"), "");
  assert.equal(passwordError("Kerala-gold-2026", "User1"), "");
});

test("permissions and ledger labels", () => {
  const branch = { is_head_office: false, permissions: ["userlist", "report"] };
  assert.equal(can(branch, "report"), true);
  assert.equal(can(branch, "analytics"), false);
  assert.equal(homePath(branch), "/customers");
  assert.equal(can({ is_head_office: true, permissions: [] }, "history"), true);
  assert.equal(can({ is_head_office: false, permissions: ["newcustomer"] }, CREATE), false, "creating needs the customer pages too");
  assert.equal(can({ is_head_office: false, permissions: ["newcustomer", "userlist"] }, CREATE), true);
  assert.equal(entryLabel("addColl"), "Payment received");
  assert.equal(entryAmount({ kind: "compounding", principal_change: "12.00" }), "12.00");
  assert.equal(entryPrincipalPaid({ kind: "addColl", principal_paid: "500.00" }), "500.00");
  assert.equal(entryPrincipalPaid({ kind: "addColl", principal_change: "-30000.00" }), "30000.00");
  assert.equal(entryPrincipalPaid({ kind: "newLoan", principal_balance: "10000.00" }), null);
  assert.notEqual(newRequestId(), newRequestId());
  assert.match(newRequestId(), /^[A-Za-z0-9-]{8,64}$/);
});

test("permissions: SuperAdmin has only what the server lists; head office staff have everything", () => {
  const superadmin = { account_type: "superadmin", is_head_office: true, is_superadmin: true, permissions: ["newcustomer", "userlist"] };
  const hq = { account_type: "hq", is_head_office: true, is_superadmin: false, permissions: [] };
  for (const feature of ["analytics", "report", "history", "form1"]) {
    assert.equal(can(superadmin, feature), false, feature);
    assert.equal(can(hq, feature), true, feature);
  }
  assert.equal(can(superadmin, "userlist"), true);
  assert.equal(can(superadmin, CREATE), true, "SuperAdmin adds customers and loans");
  assert.equal(can({ ...superadmin, permissions: [] }, "userlist"), false);
  assert.equal(homePath(superadmin), "/customers");
  assert.equal(homePath(hq), "/");
  assert.equal(homePath(null), "/login");
  assert.equal(homePath({ is_head_office: false, permissions: ["form1"] }), "/tools/calculator");
  assert.equal(homePath({ is_head_office: false, permissions: [] }), "/account");
  assert.equal(isHeadOfficeStaff(hq), true);
  assert.equal(isHeadOfficeStaff(superadmin), false);
  assert.equal(isHeadOfficeStaff({ account_type: "branch" }), false);
  assert.equal(isHeadOfficeStaff(null), false);
  assert.equal(ALL_BRANCHES_LABEL, "Admin – all branches");
  assert.equal(FEATURES.form1, "Loan calculator");
});

test("permissions: a branch with only the cash ledger or history import starts on that page", () => {
  const branch = (permissions) => ({ account_type: "branch", is_head_office: false, permissions });
  assert.equal(homePath(branch(["cashbook"])), "/cash", "not the account page");
  assert.equal(homePath(branch(["cashbook", "history"])), "/cash");
  assert.equal(homePath(branch(["history"])), "/history");
  assert.equal(homePath(branch(["report", "cashbook"])), "/reports", "earlier choices are unchanged");
  assert.equal(homePath(branch(["form1", "cashbook"])), "/tools/calculator");
  assert.equal(homePath(branch([])), "/account");
});

test("permissions: the cash ledger is a branch feature; head office has it, SuperAdmin never does", () => {
  assert.equal(FEATURES.cashbook, "Cash ledger");
  assert.equal(can({ is_head_office: false, permissions: ["cashbook"] }, "cashbook"), true);
  assert.equal(can({ is_head_office: false, permissions: ["userlist"] }, "cashbook"), false);
  assert.equal(can({ account_type: "hq", is_head_office: true, is_superadmin: false, permissions: [] }, "cashbook"), true);
  const superadmin = { account_type: "superadmin", is_head_office: true, is_superadmin: true, permissions: ["newcustomer", "userlist"] };
  assert.equal(can(superadmin, "cashbook"), false);
  // New branches start with every feature except history import, so the cash ledger is on by default.
  const branches = readFileSync(join(process.cwd(), "src", "features", "admin", "BranchesPage.jsx"), "utf8");
  assert.match(branches, /permissions: Object\.keys\(FEATURES\)\.filter\(\(key\) => key !== "history"\)/);
  assert.ok(Object.keys(FEATURES).filter((key) => key !== "history").includes("cashbook"));
});

test("ledger: calculation method labels", () => {
  for (const method of ["opening", "first_week", "first_week_settlement", "inclusive", "compounding", "writeoff", "legacy", "as_recorded"]) {
    assert.equal(typeof CALCULATION_LABELS[method], "string", method);
    assert.equal(calculationLabel(method), CALCULATION_LABELS[method]);
  }
  assert.equal(calculationLabel("something-new"), "As recorded");
});
