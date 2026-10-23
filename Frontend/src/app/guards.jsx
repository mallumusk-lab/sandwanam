import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { can, isHeadOfficeStaff } from "../lib/permissions.js";
import { Button } from "../ui/controls.jsx";
import { EmptyState, ErrorState, PageLoading } from "../ui/feedback.jsx";

export function RequireAuth() {
  const { status, user, error, restore } = useAuth();
  const location = useLocation();
  if (status === "loading") return <PageLoading label="Checking your session…" />;
  if (status === "error") {
    return (
      <main className="page narrow">
        <ErrorState error={error} onRetry={restore} title="Can't reach the server" />
      </main>
    );
  }
  if (status !== "signed-in") return <Navigate to="/login" replace state={{ from: location }} />;
  if (user.must_change_password && location.pathname !== "/account") {
    return <Navigate to="/account" replace state={{ forced: true }} />;
  }
  return <Outlet />;
}

function NoAccess() {
  return (
    <div className="page narrow">
      <EmptyState icon="lock" headingLevel={1} title="You don't have access to this page" action={<Button to="/">Go to the home page</Button>}>
        Ask a SuperAdmin to give your branch access if you need it.
      </EmptyState>
    </div>
  );
}

/** headOffice: head office or SuperAdmin; hq: head office staff only; superadmin: SuperAdmin only. */
export function RequirePermission({ permission, headOffice = false, hq = false, superadmin = false, children }) {
  const { user } = useAuth();
  const allowed =
    (!permission || can(user, permission)) &&
    (!headOffice || user.is_head_office) &&
    (!hq || isHeadOfficeStaff(user)) &&
    (!superadmin || user.is_superadmin);
  return allowed ? children : <NoAccess />;
}
