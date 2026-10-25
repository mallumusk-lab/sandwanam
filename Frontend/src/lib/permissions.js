// Feature access for navigation. The server enforces the same rules on every request;
// this only decides what to show.

export const FEATURES = {
  analytics: "Dashboard",
  userlist: "Customers",
  newcustomer: "New customers and loans",
  report: "Reports",
  history: "History import",
  form1: "Loan calculator",
  cashbook: "Cash ledger",
};

/** Shown wherever head office looks at every branch at once (branch value ""). */
export const ALL_BRANCHES_LABEL = "Admin – all branches";

/**
 * `permission` may be a list: all of them are required. Head office staff have every
 * feature; a SuperAdmin has only the ones the server lists (customers and loans).
 */
export function can(user, permission) {
  if (!user) return false;
  if (Array.isArray(permission)) return permission.every((p) => can(user, p));
  if (user.is_superadmin) return (user.permissions ?? []).includes(permission);
  return user.is_head_office || user.permissions.includes(permission);
}

/** Head office staff (not SuperAdmin): gold rate and audit log. */
export function isHeadOfficeStaff(user) {
  return user?.account_type === "hq";
}

export const CREATE = ["newcustomer", "userlist"];

export function homePath(user) {
  if (!user) return "/login";
  if (can(user, "analytics")) return "/";
  if (can(user, "userlist")) return "/customers";
  if (can(user, "report")) return "/reports";
  if (can(user, "form1")) return "/tools/calculator";
  if (can(user, "cashbook")) return "/cash";
  if (can(user, "history")) return "/history";
  return "/account";
}

export const ACCOUNT_LABELS = { superadmin: "SuperAdmin", hq: "Head office", branch: "Branch" };
