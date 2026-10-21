// Feature access for navigation. The server enforces the same rules on every request;
// this only decides what to show.

export const FEATURES = {
  analytics: "Dashboard",
  userlist: "Customers",
  newcustomer: "New customers and loans",
  report: "Reports",
  history: "History import",
  form1: "Forms and calculator",
};

/** `permission` may be a list: all of them are required. */
export function can(user, permission) {
  if (!user) return false;
  if (Array.isArray(permission)) return permission.every((p) => can(user, p));
  return user.is_head_office || user.permissions.includes(permission);
}

export const CREATE = ["newcustomer", "userlist"];

export function homePath(user) {
  if (!user) return "/login";
  if (can(user, "analytics")) return "/";
  if (can(user, "userlist")) return "/customers";
  if (can(user, "report")) return "/reports";
  if (can(user, "form1")) return "/tools/calculator";
  return "/account";
}

export const ACCOUNT_LABELS = { superadmin: "SuperAdmin", hq: "Head office", branch: "Branch" };
