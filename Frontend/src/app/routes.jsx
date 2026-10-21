import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { CREATE, homePath, can } from "../lib/permissions.js";
import { AppShell } from "../ui/AppShell.jsx";
import { PageLoading } from "../ui/feedback.jsx";
import { RequireAuth, RequirePermission } from "./guards.jsx";

const LoginPage = lazy(() => import("../features/auth/LoginPage.jsx"));
const AccountPage = lazy(() => import("../features/auth/AccountPage.jsx"));
const DashboardPage = lazy(() => import("../features/dashboard/DashboardPage.jsx"));
const CustomerListPage = lazy(() => import("../features/customers/CustomerListPage.jsx"));
const NewCustomerPage = lazy(() => import("../features/customers/NewCustomerPage.jsx"));
const CustomerPage = lazy(() => import("../features/customers/CustomerPage.jsx"));
const NewLoanPage = lazy(() => import("../features/loans/NewLoanPage.jsx"));
const StatementPage = lazy(() => import("../features/loans/StatementPage.jsx"));
const ReportPage = lazy(() => import("../features/reports/ReportPage.jsx"));
const HistoryImportPage = lazy(() => import("../features/history/HistoryImportPage.jsx"));
const BackupPage = lazy(() => import("../features/backup/BackupPage.jsx"));
const BranchesPage = lazy(() => import("../features/admin/BranchesPage.jsx"));
const SettingsPage = lazy(() => import("../features/admin/SettingsPage.jsx"));
const AuditLogPage = lazy(() => import("../features/admin/AuditLogPage.jsx"));
const ApplicationFormPage = lazy(() => import("../features/tools/ApplicationFormPage.jsx"));
const CalculatorPage = lazy(() => import("../features/tools/CalculatorPage.jsx"));
const LoanReceiptPage = lazy(() => import("../print/LoanReceiptPage.jsx"));
const EntryReceiptPage = lazy(() => import("../print/EntryReceiptPage.jsx"));
const NotFoundPage = lazy(() => import("../features/NotFoundPage.jsx"));

function Home() {
  const { user } = useAuth();
  return can(user, "analytics") ? <DashboardPage /> : <Navigate to={homePath(user)} replace />;
}

const guard = (element, rule) => <RequirePermission {...rule}>{element}</RequirePermission>;

export function AppRoutes() {
  return (
    <Suspense fallback={<PageLoading />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/superadmin/*" element={<Navigate to="/login" replace />} />
        <Route element={<RequireAuth />}>
          <Route path="/print/loan/:loanNumber" element={guard(<LoanReceiptPage />, { permission: "userlist" })} />
          <Route path="/print/entry/:statementId" element={guard(<EntryReceiptPage />, { permission: "userlist" })} />
          <Route element={<AppShell />}>
            <Route index element={<Home />} />
            <Route path="/account" element={<AccountPage />} />
            <Route path="/customers" element={guard(<CustomerListPage />, { permission: "userlist" })} />
            <Route path="/customers/new" element={guard(<NewCustomerPage />, { permission: CREATE })} />
            <Route path="/customers/:customerId" element={guard(<CustomerPage />, { permission: "userlist" })} />
            <Route path="/customers/:customerId/loans/new" element={guard(<NewLoanPage />, { permission: CREATE })} />
            <Route path="/loans/:loanNumber" element={guard(<StatementPage />, { permission: "userlist" })} />
            <Route path="/reports" element={guard(<ReportPage />, { permission: "report" })} />
            <Route path="/history" element={guard(<HistoryImportPage />, { permission: "history" })} />
            <Route path="/tools/application-form" element={guard(<ApplicationFormPage />, { permission: "form1" })} />
            <Route path="/tools/calculator" element={guard(<CalculatorPage />, { permission: "form1" })} />
            <Route path="/settings" element={guard(<SettingsPage />, { headOffice: true })} />
            <Route path="/backup" element={guard(<BackupPage />, { headOffice: true })} />
            <Route path="/audit" element={guard(<AuditLogPage />, { headOffice: true })} />
            <Route path="/admin/branches" element={guard(<BranchesPage />, { superadmin: true })} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>
      </Routes>
    </Suspense>
  );
}
