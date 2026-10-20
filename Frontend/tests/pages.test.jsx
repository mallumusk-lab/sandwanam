// Server-render every page with a signed-in user to catch render-time crashes and check
// headings and gating. Effects (data loading) don't run on the server, so pages show
// their initial loading state.
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
import CustomerListPage from "../src/features/customers/CustomerListPage.jsx";
import CustomerPage from "../src/features/customers/CustomerPage.jsx";
import NewCustomerPage from "../src/features/customers/NewCustomerPage.jsx";
import DashboardPage from "../src/features/dashboard/DashboardPage.jsx";
import HistoryImportPage from "../src/features/history/HistoryImportPage.jsx";
import NewLoanPage from "../src/features/loans/NewLoanPage.jsx";
import StatementPage from "../src/features/loans/StatementPage.jsx";
import NotFoundPage from "../src/features/NotFoundPage.jsx";
import ReportPage from "../src/features/reports/ReportPage.jsx";
import ApplicationFormPage from "../src/features/tools/ApplicationFormPage.jsx";
import CalculatorPage from "../src/features/tools/CalculatorPage.jsx";
import EntryReceiptPage from "../src/print/EntryReceiptPage.jsx";
import LoanReceiptPage from "../src/print/LoanReceiptPage.jsx";
import { AppShell } from "../src/ui/AppShell.jsx";
import { ToastProvider } from "../src/ui/feedback.jsx";

globalThis.document ??= { title: "" };

const BRANCH_USER = {
  username: "User1", display_name: "Santhwanam", account_type: "branch", branch: "SAN", is_head_office: false,
  is_superadmin: false, permissions: ["userlist", "newcustomer", "report"], must_change_password: false,
};
const SUPERADMIN = { ...BRANCH_USER, username: "root", account_type: "superadmin", branch: null, is_head_office: true, is_superadmin: true, permissions: [] };

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

const PAGES = [
  ["/customers", <CustomerListPage />, /<h1>Customers<\/h1>/],
  ["/customers/new", <NewCustomerPage />, /<h1>New customer<\/h1>/],
  ["/reports", <ReportPage />, /<h1>Reports<\/h1>/],
  ["/history", <HistoryImportPage />, /<h1>History import<\/h1>[\s\S]*aria-current="step"/],
  ["/tools/application-form", <ApplicationFormPage />, /<h1>Application form<\/h1>[\s\S]*lang="ml"/],
  ["/tools/calculator", <CalculatorPage />, /<h1>Loan calculator<\/h1>/],
  ["/account", <AccountPage />, /<h1>Your account<\/h1>/],
  ["/settings", <SettingsPage />, /<h1>Gold rate<\/h1>/],
  ["/backup", <BackupPage />, /<h1>Backups<\/h1>/],
  ["/audit", <AuditLogPage />, /<h1>Audit log<\/h1>/],
  ["/admin/branches", <BranchesPage />, /<h1>Branches<\/h1>/],
  ["/nowhere", <NotFoundPage />, /This page doesn&#x27;t exist/],
];

for (const [path, element, expected] of PAGES) {
  test(`renders ${path}`, () => {
    assert.match(renderAt(path, element, SUPERADMIN), expected);
  });
}

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

test("navigation only shows what the account may use", () => {
  const branchNav = renderAt("/customers", <AppShell />, BRANCH_USER, "/customers");
  assert.match(branchNav, /Customers/);
  assert.match(branchNav, /Reports/);
  assert.doesNotMatch(branchNav, /Backups|Audit log|Branches|History import|Dashboard/);
  assert.match(branchNav, /href="#main"/);
  const superNav = renderAt("/", <AppShell />, SUPERADMIN, "/");
  assert.match(superNav, /Backups[\s\S]*Audit log[\s\S]*Branches/);
  assert.match(superNav, /Branch shown/);
});

test("pages a branch may not use explain why instead of rendering", () => {
  const html = renderAt("/history", <RequirePermission permission="history"><HistoryImportPage /></RequirePermission>);
  assert.match(html, /You don&#x27;t have access to this page/);
  assert.doesNotMatch(html, /History import<\/h1>/);
  assert.match(renderAt("/backup", <RequirePermission headOffice><BackupPage /></RequirePermission>), /don&#x27;t have access/);
});
