import { Link } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext.jsx";
import { can } from "../../lib/permissions.js";

// Customer and loan pages need the Customers feature. Without it, show plain text rather
// than a link that leads to "no access".

export function LoanLink({ loanNumber, children }) {
  const { user } = useAuth();
  const label = children ?? loanNumber;
  if (!can(user, "userlist")) return <span>{label}</span>;
  return <Link className="row-link" to={`/loans/${encodeURIComponent(loanNumber)}`}>{label}</Link>;
}

export function CustomerLink({ customerId, children }) {
  const { user } = useAuth();
  if (!can(user, "userlist") || customerId == null) return <span>{children}</span>;
  return <Link className="row-link" to={`/customers/${customerId}`}>{children}</Link>;
}
