// Server-render every page with a signed-in user to catch render-time crashes and check
// headings and gating. Effects (data loading) don't run on the server, so pages show
// their initial loading state.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { Route, Routes } from "react-router-dom";
import { StaticRouter } from "react-router-dom/server";
import { RequirePermission } from "../src/app/guards.jsx";
import { AuthContext } from "../src/auth/AuthContext.jsx";
import AccountPage from "../src/features/auth/AccountPage.jsx";
import LoginPage from "../src/features/auth/LoginPage.jsx";
import AuditLogPage from "../src/features/admin/AuditLogPage.jsx";
import BranchesPage from "../src/features/admin/BranchesPage.jsx";
import SettingsPage from "../src/features/admin/SettingsPage.jsx";
import BackupPage from "../src/features/backup/BackupPage.jsx";
import CashLedgerPage from "../src/features/cash/CashLedgerPage.jsx";
import CustomerListPage from "../src/features/customers/CustomerListPage.jsx";
import CustomerPage from "../src/features/customers/CustomerPage.jsx";
import { FirstWeekBanner } from "../src/features/customers/LoanDialogs.jsx";
import NewCustomerPage from "../src/features/customers/NewCustomerPage.jsx";
import DashboardPage from "../src/features/dashboard/DashboardPage.jsx";
import HistoryImportPage from "../src/features/history/HistoryImportPage.jsx";
import { calculationLines } from "../src/features/loans/LedgerCalculation.jsx";
import NewLoanPage from "../src/features/loans/NewLoanPage.jsx";
import StatementPage, { LedgerCard, LoanDetailsCard } from "../src/features/loans/StatementPage.jsx";
import NotFoundPage from "../src/features/NotFoundPage.jsx";
import ReportPage from "../src/features/reports/ReportPage.jsx";
import { defaultFollowUp, followUpStatus } from "../src/features/shared/FollowUpDialog.jsx";
import CalculatorPage from "../src/features/tools/CalculatorPage.jsx";
import { ALL_BRANCHES_LABEL } from "../src/lib/permissions.js";
import EntryReceiptPage from "../src/print/EntryReceiptPage.jsx";
import LoanReceiptPage from "../src/print/LoanReceiptPage.jsx";
import { AppShell, branchOptions } from "../src/ui/AppShell.jsx";
import { ToastProvider } from "../src/ui/feedback.jsx";

globalThis.document ??= { title: "" };

const BRANCH_USER = {
  username: "User1", display_name: "Santhwanam", account_type: "branch", branch: "SAN", is_head_office: false,
  is_superadmin: false, permissions: ["userlist", "newcustomer", "report"], must_change_password: false,
};
// What /auth/me sends for each account type.
const SUPERADMIN = {
  ...BRANCH_USER, username: "root", display_name: "Root", account_type: "superadmin", branch: null, is_head_office: true,
  is_superadmin: true, permissions: ["newcustomer", "userlist"],
};
const HQ_USER = {
  ...BRANCH_USER, username: "Admin", display_name: "Head office", account_type: "hq", branch: "AD", is_head_office: true,
  is_superadmin: false, permissions: ["newcustomer", "userlist", "form1", "analytics", "report", "history"],
};
// Migration 005 grants the cash ledger to every existing branch; new branches get it by default.
const BRANCH_CASH = { ...BRANCH_USER, permissions: [...BRANCH_USER.permissions, "cashbook"] };

function renderAt(path, element, user = BRANCH_USER, pattern = path) {
  const auth = { status: "signed-in", user, branch: user.branch ?? "", setBranch() {}, login() {}, logout() {}, changePassword() {}, restore() {} };
  return renderToStaticMarkup(
    <StaticRouter location={path}>
      <ToastProvider>
        <AuthContext.Provider value={auth}>
          <Routes>
            <Route path={pattern} element={element} />
          </Routes>
        </AuthContext.Provider>
      </ToastProvider>
    </StaticRouter>,
  );
}

// Each page is rendered as an account that may open it.
const PAGES = [
  ["/customers", CustomerListPage, /<h1>Customers<\/h1>/, SUPERADMIN],
  ["/customers/new", NewCustomerPage, /<h1>New customer<\/h1>/, SUPERADMIN],
  ["/reports", ReportPage, /<h1>Reports<\/h1>/, HQ_USER],
  ["/cash", CashLedgerPage, /<h1>Cash ledger<\/h1>[\s\S]*aria-label="Loading cash ledger"/, BRANCH_CASH],
  ["/history", HistoryImportPage, /<h1>History import<\/h1>[\s\S]*aria-current="step"/, HQ_USER],
  ["/tools/calculator", CalculatorPage, /<h1>Loan calculator<\/h1>/, HQ_USER],
  ["/account", AccountPage, /<h1>Your account<\/h1>/, SUPERADMIN],
  ["/settings", SettingsPage, /<h1>Gold rate<\/h1>/, HQ_USER],
  ["/backup", BackupPage, /<h1>Backups<\/h1>/, SUPERADMIN],
  ["/audit", AuditLogPage, /<h1>Audit log<\/h1>/, HQ_USER],
  ["/admin/branches", BranchesPage, /<h1>Branches<\/h1>/, SUPERADMIN],
  ["/nowhere", NotFoundPage, /This page doesn&#x27;t exist/, SUPERADMIN],
];

for (const [path, Page, expected, user] of PAGES) {
  test(`renders ${path}`, () => {
    assert.match(renderAt(path, <Page />, user), expected);
  });
}

test("the calculator's schedule table stacks into labelled cards on phones", () => {
  const page = readFileSync(join(process.cwd(), "src", "features", "tools", "CalculatorPage.jsx"), "utf8");
  assert.match(page, /<div className="table-wrap">\s*<table className="table table-stack">/);
  for (const label of ["After", "Date", "Interest", "Total due"]) {
    assert.match(page, new RegExp(`data-label="${label}"`), label);
  }
});

test("the application form page is gone; its old URL is an unknown page", () => {
  const src = join(process.cwd(), "src");
  assert.throws(() => statSync(join(src, "features", "tools", "ApplicationFormPage.jsx")));
  for (const file of ["app/routes.jsx", "ui/AppShell.jsx"]) {
    assert.doesNotMatch(readFileSync(join(src, file), "utf8"), /application-form|ApplicationForm/, file);
  }
  assert.match(readFileSync(join(src, "app", "routes.jsx"), "utf8"), /path="\*" element={<NotFoundPage \/>}/);
});

test("data pages render their loading state", () => {
  assert.match(renderAt("/", <DashboardPage />), /aria-label="Loading dashboard"/);
  assert.match(renderAt("/customers/5", <CustomerPage />, BRANCH_USER, "/customers/:customerId"), /Loading customer/);
  assert.match(renderAt("/customers/5/loans/new", <NewLoanPage />, BRANCH_USER, "/customers/:customerId/loans/new"), /Loading customer/);
  assert.match(renderAt("/loans/SAN1L1", <StatementPage />, BRANCH_USER, "/loans/:loanNumber"), /Loading statement/);
  assert.match(renderAt("/print/loan/SAN1L1", <LoanReceiptPage />, BRANCH_USER, "/print/loan/:loanNumber"), /Loan voucher/);
  assert.match(renderAt("/print/entry/7", <EntryReceiptPage />, BRANCH_USER, "/print/entry/:statementId"), /Receipt/);
});

test("sign-in page supports password managers", () => {
  const auth = { status: "signed-out", user: null, notice: "Your session has ended. Please sign in again." };
  const html = renderToStaticMarkup(
    <StaticRouter location="/login">
      <AuthContext.Provider value={auth}><LoginPage /></AuthContext.Provider>
    </StaticRouter>,
  );
  assert.match(html, /autoComplete="username"|autocomplete="username"/i);
  assert.match(html, /current-password/);
  assert.match(html, /Your session has ended/);
});

test("forced password change replaces the page until done", () => {
  const html = renderAt("/account", <AccountPage />, { ...BRANCH_USER, must_change_password: true });
  assert.match(html, /Choose a new password to continue/);
  assert.match(html, /new-password/);
});

/** The visible names of the links in the main navigation. */
function navLinks(html) {
  const nav = html.slice(html.indexOf('aria-label="Main"'), html.indexOf("sidebar-footer"));
  return [...nav.matchAll(/class="nav-link[^"]*"[^>]*>([\s\S]*?)<\/a>/g)].map((m) => m[1].replace(/<[^>]+>/g, "").trim());
}

test("navigation only shows what the account may use", () => {
  const branchNav = renderAt("/customers", <AppShell />, BRANCH_USER, "/customers");
  assert.deepEqual(navLinks(branchNav), ["Customers", "New customer", "Reports"]);
  assert.match(branchNav, /<p class="nav-heading">Branch operations<\/p>/);
  assert.doesNotMatch(branchNav, /Daily work|>Tools<|>Head office</);
  assert.doesNotMatch(branchNav, /Backups|Audit log|Branches|History import|Dashboard|Cash ledger/);
  assert.doesNotMatch(branchNav, /Branch shown/, "branch accounts have no branch picker");
  assert.match(branchNav, /href="#main"/);
});

test("navigation: branch staff with the cash ledger see it under Branch operations", () => {
  const branchNav = renderAt("/customers", <AppShell />, BRANCH_CASH, "/customers");
  assert.deepEqual(navLinks(branchNav), ["Customers", "New customer", "Reports", "Cash ledger"]);
  assert.match(branchNav, /<p class="nav-heading">Branch operations<\/p>[\s\S]*href="\/cash"/);
  assert.doesNotMatch(branchNav, />Head office</, "the cash ledger adds no head-office menu for branches");
});

test("SuperAdmin navigation: customers, backups, branches and the all-branches picker", () => {
  const superNav = renderAt("/customers", <AppShell />, SUPERADMIN, "/customers");
  assert.deepEqual(navLinks(superNav), ["Customers", "Backups", "Branches &amp; Users"]);
  assert.match(superNav, /<p class="nav-heading">Branch operations<\/p>[\s\S]*<p class="nav-heading">Head office<\/p>/);
  for (const hidden of ["Dashboard", "Reports", "History import", "Loan calculator", "Gold rate", "Audit log", "New customer", "Application form", "Cash ledger"]) {
    assert.doesNotMatch(superNav, new RegExp(hidden), hidden);
  }
  assert.match(superNav, /Branch shown/);
  assert.match(superNav, new RegExp(`<option value="" selected="">${ALL_BRANCHES_LABEL}</option>`));
  assert.doesNotMatch(superNav, />All branches</);
});

test("head office navigation has every branch feature but not branch administration", () => {
  const hqNav = renderAt("/", <AppShell />, HQ_USER, "/");
  assert.deepEqual(navLinks(hqNav), [
    "Dashboard", "Customers", "New customer", "Reports", "Cash ledger", "History import", "Loan calculator", "Gold rate", "Backups", "Audit log",
  ]);
  assert.match(hqNav, /Branch operations[\s\S]*Head office/);
  assert.match(hqNav, new RegExp(ALL_BRANCHES_LABEL));
});

test("the branch picker leaves out the head-office branch", () => {
  const list = [
    { code: "AD", name: "Head office", is_head_office: true },
    { code: "SAN", name: "Santhwanam", is_head_office: false },
    { code: "KOT", name: "Kottayam", is_head_office: false },
  ];
  assert.deepEqual(branchOptions(list).map((b) => b.code), ["SAN", "KOT"]);
  assert.deepEqual(branchOptions(undefined), []);
  assert.equal(ALL_BRANCHES_LABEL, "Admin – all branches");
});

test("cash ledger: branch staff see their own drawer; head office picks one branch; SuperAdmin is refused", () => {
  const branchPage = renderAt("/cash", <CashLedgerPage />, BRANCH_CASH);
  assert.match(branchPage, /<h1>Cash ledger<\/h1>/);
  assert.match(branchPage, /Cash drawer for this branch: count at the start, record every cash movement, count and close at the end\. Kept for 14 days\./);
  assert.doesNotMatch(branchPage, />Branch<\/label>/, "branch staff only ever see their own drawer");
  const hqPage = renderAt("/cash", <CashLedgerPage />, HQ_USER);
  assert.match(hqPage, /<label class="field-label" for="[^"]+">Branch<\/label><select[^>]*>/);
  assert.match(hqPage, /<option value="AD" selected="">AD<\/option>/, "defaults to head office's own branch, never all branches");
  assert.doesNotMatch(hqPage, new RegExp(ALL_BRANCHES_LABEL));
  const picked = renderToStaticMarkup(
    <StaticRouter location="/cash">
      <ToastProvider>
        <AuthContext.Provider value={{ status: "signed-in", user: HQ_USER, branch: "SAN", setBranch() {} }}>
          <CashLedgerPage />
        </AuthContext.Provider>
      </ToastProvider>
    </StaticRouter>,
  );
  assert.match(picked, /<option value="SAN" selected="">SAN<\/option>/, "starts on the branch picked in the top bar");
  const refused = renderAt("/cash", <RequirePermission permission="cashbook"><CashLedgerPage /></RequirePermission>, SUPERADMIN);
  assert.match(refused, /You don&#x27;t have access to this page/);
  assert.doesNotMatch(refused, /Cash ledger<\/h1>/);
});

test("pages a branch may not use explain why instead of rendering", () => {
  const html = renderAt("/history", <RequirePermission permission="history"><HistoryImportPage /></RequirePermission>);
  assert.match(html, /You don&#x27;t have access to this page/);
  assert.doesNotMatch(html, /History import<\/h1>/);
  assert.match(renderAt("/backup", <RequirePermission headOffice><BackupPage /></RequirePermission>), /don&#x27;t have access/);
});

test("guards: gold rate and audit log are head office staff only; backups include SuperAdmin", () => {
  const refused = /You don&#x27;t have access to this page/;
  const at = (user, rule) => renderAt("/x", <RequirePermission {...rule}><p>Allowed page</p></RequirePermission>, user, "/x");
  assert.match(at(HQ_USER, { hq: true }), /Allowed page/);
  assert.match(at(SUPERADMIN, { hq: true }), refused);
  assert.match(at(BRANCH_USER, { hq: true }), refused);
  assert.match(at(SUPERADMIN, { headOffice: true }), /Allowed page/);
  assert.match(at(HQ_USER, { headOffice: true }), /Allowed page/);
  assert.match(at(HQ_USER, { superadmin: true }), refused);
  assert.match(at(SUPERADMIN, { superadmin: true }), /Allowed page/);
  for (const feature of ["analytics", "report", "history", "form1"]) {
    assert.match(at(SUPERADMIN, { permission: feature }), refused, feature);
  }
  assert.match(at(SUPERADMIN, { permission: ["newcustomer", "userlist"] }), /Allowed page/);
  // Cash ledger: branch staff with the feature and head office; never SuperAdmin.
  assert.match(at(SUPERADMIN, { permission: "cashbook" }), refused);
  assert.match(at(HQ_USER, { permission: "cashbook" }), /Allowed page/);
  assert.match(at(BRANCH_CASH, { permission: "cashbook" }), /Allowed page/);
  assert.match(at(BRANCH_USER, { permission: "cashbook" }), refused);
  const routes = readFileSync(join(process.cwd(), "src", "app", "routes.jsx"), "utf8");
  assert.match(routes, /<SettingsPage \/>, { hq: true }/);
  assert.match(routes, /<AuditLogPage \/>, { hq: true }/);
  assert.match(routes, /<BackupPage \/>, { headOffice: true }/);
  assert.match(routes, /<Route path="\/cash" element={guard\(<CashLedgerPage \/>, { permission: "cashbook" }\)} \/>/);
});

const STATEMENT_LOAN = { loan_number: "SAN1L1", customer_id: 5, customer_name: "Lakshmi" };
const NO_CALC = {
  period_from: null, period_to: null, days: null, principal_charged: null, rate: null, interest_accrued: null, peak_principal: null,
  first_week_days: null, extra_days: null, extra_principal: null, note: null,
};
const STATEMENTS = [
  {
    id: 3, kind: "writeoff", date: "2026-01-05", at: "2026-01-05T10:00:00+05:30", amount_paid: null, principal_change: null,
    interest_paid: null, principal_balance: "0.00", interest_balance: "0.00", accrued_days: 7, written_off: "10.00", legacy: false,
    calculation: {
      ...NO_CALC, method: "writeoff", period_from: "2026-01-01", period_to: "2026-01-07", days: 7, rate: "18.00",
      interest_accrued: "414.25", peak_principal: "120000.00", first_week_days: 7, extra_days: 0,
      interest_paid: "0.00", principal_paid: "0.00", principal_balance: "0.00", interest_balance: "0.00",
    },
  },
  {
    id: 2, kind: "addColl", date: "2026-01-02", at: "2026-01-02T10:00:00+05:30", amount_paid: "30000.00", principal_change: "-30000.00",
    interest_paid: "0.00", principal_balance: "70000.00", interest_balance: "0.00", accrued_days: 0, legacy: false,
    calculation: {
      ...NO_CALC, method: "first_week", days: 0, rate: "18.00", interest_accrued: "0.00",
      interest_paid: "0.00", principal_paid: "30000.00", principal_balance: "70000.00", interest_balance: "0.00",
      note: "First 7 days: no daily interest; payment reduces principal by ₹30000.00.",
    },
  },
  {
    id: 1, kind: "newLoan", date: "2025-03-01", at: null, amount_paid: null, principal_change: null, interest_paid: null,
    principal_balance: "100000.00", interest_balance: "0.00", accrued_days: null, legacy: true,
    calculation: {
      ...NO_CALC, method: "legacy", interest_paid: "0.00", principal_paid: "0.00", principal_balance: "100000.00",
      interest_balance: "0.00", note: "Earlier system — not recalculated",
    },
  },
];

test("statement: Show calculation is a toggle that adds the server's working under each entry", () => {
  const ledger = (shown) => renderToStaticMarkup(
    <StaticRouter location="/loans/SAN1L1"><LedgerCard loan={STATEMENT_LOAN} statements={STATEMENTS} initiallyShown={shown} /></StaticRouter>,
  );
  const hidden = ledger(false);
  assert.match(hidden, /<button type="button" class="btn btn-secondary btn-sm no-print"[^>]*aria-pressed="false"[^>]*>[\s\S]*?Show calculation<\/button>/);
  assert.match(hidden, /<th[^>]*>Principal paid<\/th>/);
  assert.doesNotMatch(hidden, /Days charged/);
  assert.doesNotMatch(hidden, /table-detail|on the highest principal/);
  const shown = ledger(true);
  assert.match(shown, /aria-pressed="true"/);
  assert.equal((shown.match(/<tr class="table-detail"><td colSpan="8">/g) ?? []).length, 3);
  assert.equal((shown.match(/<tr class="has-detail">/g) ?? []).length, 3);
  assert.match(shown, /First 7 days on the highest principal: ₹1,20,000.00 × 18.00% × 7 days ÷ 365/);
  assert.match(shown, /Interest: ₹414.25, rounded once/);
  assert.match(shown, /Written off: ₹10.00/);
  assert.match(shown, /Paid ₹30,000.00 → ₹0.00 interest, ₹30,000.00 principal/);
  assert.match(shown, /Balance: principal ₹70,000.00, interest ₹0.00/);
  assert.match(shown, /First 7 days: no daily interest; payment reduces principal/);
  assert.match(shown, /Earlier system — not recalculated/);
});

test("statement: Loan details includes principal balance and interest balance", () => {
  const loan = {
    ...STATEMENT_LOAN,
    date: "2026-10-23",
    items_text: "Chain(2)",
    net_weight: "10.00",
    principal: "11111111.00",
    rate: "11.00",
    tenure_months: 12,
    status: "open",
    outstanding: { principal: "11111111.00", interest: "6697.11", total: "11117808.11" },
  };
  const html = renderToStaticMarkup(<LoanDetailsCard loan={loan} statements={STATEMENTS} />);
  assert.match(html, /<dt>Principal balance<\/dt>\s*<dd>₹1,11,11,111\.00<\/dd>/);
  assert.match(html, /<dt>Interest balance<\/dt>\s*<dd>₹6,697\.11<\/dd>/);
  assert.match(html, /<dt>Due today<\/dt>\s*<dd>₹1,11,17,808\.11<\/dd>/);
});

test("calculation lines only format the server's figures", () => {
  const lines = calculationLines({
    ...NO_CALC, method: "inclusive", period_from: "2026-02-01", period_to: "2026-02-10", days: 10, principal_charged: "70000.00",
    rate: "18.00", interest_accrued: "345.21", interest_paid: "345.21", principal_paid: "654.79", principal_balance: "69345.21",
    interest_balance: "0.00",
  }, { kind: "addColl", amount_paid: "1000.00" });
  assert.deepEqual(lines, [
    "Period: 1 Feb 2026 to 10 Feb 2026, 10 days",
    "Interest: ₹70,000.00 × 18.00% × 10 days ÷ 365 = ₹345.21",
    "Paid ₹1,000.00 → ₹345.21 interest, ₹654.79 principal",
    "Balance: principal ₹69,345.21, interest ₹0.00",
  ]);
  const settled = calculationLines({
    ...NO_CALC, method: "first_week_settlement", period_from: "2026-01-01", period_to: "2026-01-10", days: 10, rate: "18.00",
    peak_principal: "120000.00", first_week_days: 7, extra_days: 3, extra_principal: "70000.00", interest_accrued: "517.81",
    interest_paid: "0.00", principal_paid: "0.00", principal_balance: "70000.00", interest_balance: "517.81",
  }, { kind: "disbursement" });
  assert.deepEqual(settled, [
    "Period: 1 Jan 2026 to 10 Jan 2026, 10 days",
    "First 7 days on the highest principal: ₹1,20,000.00 × 18.00% × 7 days ÷ 365",
    "Plus 3 days after day 7: ₹70,000.00 × 18.00% × 3 days ÷ 365",
    "Interest: ₹517.81, rounded once",
    "Balance: principal ₹70,000.00, interest ₹517.81",
  ]);
});

test("first-week banners show the server's amounts", () => {
  const outstanding = { first_week: true, window_peak: "120000.00", first_week_interest: "414.25" };
  const posting = renderToStaticMarkup(<FirstWeekBanner outstanding={outstanding} />);
  assert.match(posting, /In the first 7 days a payment reduces the principal\. 7 days&#x27; interest on the highest principal \(₹414\.25\) is charged when the loan is closed or from day 8\./);
  const closing = renderToStaticMarkup(<FirstWeekBanner outstanding={outstanding} closing />);
  assert.match(closing, /Closing in the first 7 days charges 7 days&#x27; interest on the highest principal \(₹1,20,000\.00\)\./);
  // The dialogs (portals, so not server-rendered) show them only when the server says so.
  const dialogs = readFileSync(join(process.cwd(), "src", "features", "customers", "LoanDialogs.jsx"), "utf8");
  assert.match(dialogs, /const firstWeek = Boolean\(outstanding\?\.first_week\);/);
  assert.match(dialogs, /collect && firstWeek \? <FirstWeekBanner outstanding={outstanding} \/>/);
  assert.match(dialogs, /quote\.first_week \? <FirstWeekBanner outstanding={quote} closing \/>/);
  assert.doesNotMatch(dialogs, /daysBetween/, "the server decides whether the loan is in its first week");
});

test("follow-up dialog starts on the staff-set date, else a week from today", () => {
  assert.equal(defaultFollowUp({ follow_up_set: true, follow_up_date: "2026-03-10" }, "2026-03-01"), "2026-03-10");
  assert.equal(defaultFollowUp({ follow_up_set: true, follow_up_date: "2026-03-01" }, "2026-03-01"), "2026-03-01");
  assert.equal(defaultFollowUp({ follow_up_set: true, follow_up_date: "2026-02-20" }, "2026-03-01"), "2026-03-08");
  assert.equal(defaultFollowUp({ follow_up_set: false, follow_up_date: "2026-03-10" }, "2026-03-01"), "2026-03-08", "automatic dates are not reused");
  assert.equal(defaultFollowUp({ follow_up_set: false, follow_up_date: null }, "2026-03-01"), "2026-03-08");
});

test("follow-ups read due in N days, due today or overdue by N days, and every one is listed", () => {
  assert.deepEqual(followUpStatus(10), { label: "Due in 10 days", tone: "info" });
  assert.deepEqual(followUpStatus(1), { label: "Due in 1 day", tone: "info" });
  assert.deepEqual(followUpStatus(0), { label: "Due today", tone: "warning" });
  assert.deepEqual(followUpStatus(-1), { label: "Overdue by 1 day", tone: "danger" });
  assert.deepEqual(followUpStatus(-3), { label: "Overdue by 3 days", tone: "danger" });
  const dashboard = readFileSync(join(process.cwd(), "src", "features", "dashboard", "DashboardPage.jsx"), "utf8");
  assert.equal((dashboard.match(/<FollowUpPill days={l\.follow_up_days} \/>/g) ?? []).length, 2, "both cards show the status");
  assert.match(dashboard, /l\.follow_up_set \? \(/, "a staff-set date on an overdue loan is shown, even when it is today or past");
  assert.doesNotMatch(dashboard, /daysBetween|todayIST/, "the server counts the days");
  assert.doesNotMatch(dashboard, /\.slice\(0, 50\)/, "no follow-up or overdue loan is cut off");
  assert.match(dashboard, /<PagedTable columns={followUpColumns} rows={followUps} /);
  assert.match(dashboard, /<PagedTable columns={overdueColumns} rows={portfolio\.overdue} /);
});

test("the loan-created banner is gone; the toast and loan receipt button remain", () => {
  const src = join(process.cwd(), "src", "features");
  const customerPage = readFileSync(join(src, "customers", "CustomerPage.jsx"), "utf8");
  const newLoan = readFileSync(join(src, "loans", "NewLoanPage.jsx"), "utf8");
  assert.doesNotMatch(customerPage, /createdLoan|created`\}/);
  assert.doesNotMatch(newLoan, /createdLoan/);
  assert.match(newLoan, /toast\.success\("Loan created"/);
  assert.match(customerPage, />Loan receipt</);
  assert.match(customerPage, /can\(user, "userlist"\) \? <Button [^\n]*onAction\("followup", loan\)/);
  assert.match(customerPage, /\(automatic\)/);
});

/** Every source file under src/, found by walking the tree. */
function sourceFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(jsx?|mjs)$/.test(name) ? [path] : [];
  });
}

test("every password input is a PasswordField with a show-password toggle", () => {
  const src = join(process.cwd(), "src");
  const files = sourceFiles(src);
  assert.ok(files.length > 30);
  let passwordFields = 0;
  for (const file of files) {
    const name = relative(src, file).split(sep).join("/");
    if (name === "ui/fields.jsx") continue;
    const text = readFileSync(file, "utf8");
    assert.doesNotMatch(text, /type=\{?["']password["']/, `${name} has a raw password input`);
    for (const match of text.matchAll(/autoComplete=["'](current|new)-password["']/g)) {
      const tag = text.slice(text.lastIndexOf("<", match.index), match.index);
      assert.match(tag, /^<PasswordField\b/, `${name}: a password autocomplete outside <PasswordField>`);
      passwordFields += 1;
    }
  }
  assert.ok(passwordFields >= 6, "sign-in, account and branch password fields were all found");

  const count = (html) => ({
    inputs: (html.match(/type="password"/g) ?? []).length,
    toggles: (html.match(/aria-label="Show password"/g) ?? []).length,
  });
  const login = renderToStaticMarkup(
    <StaticRouter location="/login">
      <AuthContext.Provider value={{ status: "signed-out", user: null, notice: null }}><LoginPage /></AuthContext.Provider>
    </StaticRouter>,
  );
  assert.deepEqual(count(login), { inputs: 1, toggles: 1 });
  assert.deepEqual(count(renderAt("/account", <AccountPage />)), { inputs: 3, toggles: 3 });
  assert.deepEqual(count(renderAt("/account", <AccountPage />, { ...BRANCH_USER, must_change_password: true })), { inputs: 3, toggles: 3 });
});
