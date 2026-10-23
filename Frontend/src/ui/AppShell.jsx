import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { branches as branchesApi } from "../api/endpoints.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { ACCOUNT_LABELS, ALL_BRANCHES_LABEL, CREATE, can, isHeadOfficeStaff } from "../lib/permissions.js";
import { IconButton, ThemeToggle } from "./controls.jsx";
import { Icon } from "./Icon.jsx";
import { useToast } from "./feedback.jsx";

const NAV = [
  {
    heading: "Branch operations",
    items: [
      { to: "/", label: "Dashboard", icon: "home", permission: "analytics", end: true },
      { to: "/customers", label: "Customers", icon: "users", permission: "userlist", end: true },
      // A SuperAdmin adds customers from the customer list; the menu keeps to their three areas.
      { to: "/customers/new", label: "New customer", icon: "userPlus", permission: CREATE, notSuperadmin: true },
      { to: "/cash", label: "Cash ledger", icon: "rupee", permission: "cashbook" },
      { to: "/reports", label: "Reports", icon: "file", permission: "report" },
      { to: "/history", label: "History import", icon: "clock", permission: "history" },
      { to: "/tools/calculator", label: "Loan calculator", icon: "calculator", permission: "form1" },
    ],
  },
  {
    heading: "Head office",
    items: [
      { to: "/settings", label: "Gold rate", icon: "sliders", hq: true },
      { to: "/backup", label: "Backups", icon: "database", headOffice: true },
      { to: "/audit", label: "Audit log", icon: "activity", hq: true },
      { to: "/admin/branches", label: "Branches & Users", icon: "shield", superadmin: true },
    ],
  },
];

export function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 64 64" aria-hidden="true">
      <circle cx="32" cy="32" r="30" fill="var(--color-primary)" />
      <circle cx="32" cy="32" r="22" fill="none" stroke="#E9C46A" strokeWidth="4" />
      <path d="M24 22h16M24 29h16M24 36l11 10M24 36h4c9 0 9-14 0-14" fill="none" stroke="#E9C46A" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/**
 * Branches head office can pick. The head-office branch itself is left out: choosing
 * ALL_BRANCHES_LABEL ("") already covers it, along with every other branch.
 */
export function branchOptions(list) {
  return (list ?? []).filter((b) => !b.is_head_office);
}

function BranchPicker({ id }) {
  const { branch, setBranch } = useAuth();
  const toast = useToast();
  const [options, setOptions] = useState([]);
  const current = useRef(branch);
  current.current = branch;
  useEffect(() => {
    const controller = new AbortController();
    branchesApi
      .list({ signal: controller.signal })
      .then((list) => {
        const choices = branchOptions(list);
        setOptions(choices);
        // A saved branch that no longer exists (or is the head-office branch) falls back to all branches.
        if (current.current && !choices.some((b) => b.code === current.current)) setBranch("");
      })
      .catch((error) => {
        if (!controller.signal.aborted) toast.error("Branches could not be loaded", error.message);
      });
    return () => controller.abort();
  }, [toast, setBranch]);
  return (
    <div className="field">
      <label className="visually-hidden" htmlFor={id}>
        Branch shown
      </label>
      <select id={id} className="select branch-select" value={branch} onChange={(e) => setBranch(e.target.value)}>
        <option value="">{ALL_BRANCHES_LABEL}</option>
        {options.map((b) => (
          <option key={b.code} value={b.code}>
            {b.name} ({b.code})
          </option>
        ))}
      </select>
    </div>
  );
}

export function AppShell() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const menuButton = useRef(null);
  const firstLink = useRef(null);
  const mainArea = useRef(null);
  const wasOpen = useRef(false);

  useEffect(() => setOpen(false), [location.pathname]);
  useEffect(() => {
    const wide = window.matchMedia("(min-width: 1024px)");
    const onChange = (event) => event.matches && setOpen(false);
    wide.addEventListener("change", onChange);
    return () => wide.removeEventListener("change", onChange);
  }, []);
  useEffect(() => {
    // While the drawer is open the page behind it is inert; focus moves in, and back on close.
    mainArea.current?.toggleAttribute("inert", open);
    if (open) firstLink.current?.focus();
    else if (wasOpen.current) menuButton.current?.focus();
    wasOpen.current = open;
    if (!open) return undefined;
    const onKey = (event) => event.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  if (user.must_change_password) {
    // Until the temporary password is replaced, the account page is the only destination.
    return (
      <main id="main" tabIndex={-1}>
        <Outlet />
      </main>
    );
  }

  const visible = (item) =>
    (!item.permission || can(user, item.permission)) &&
    (!item.headOffice || user.is_head_office) &&
    (!item.hq || isHeadOfficeStaff(user)) &&
    (!item.superadmin || user.is_superadmin) &&
    (!item.notSuperadmin || !user.is_superadmin);

  const signOut = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <nav className="sidebar" id="primary-nav" data-open={open} aria-label="Main">
        <IconButton className="drawer-close" icon="x" label="Close menu" onClick={() => setOpen(false)} />
        <NavLink to="/" className="brand" ref={firstLink}>
          <BrandMark />
          <span>
            Gold Loan Desk
            <small>{user.display_name}</small>
          </span>
        </NavLink>
        {NAV.map((group) => {
          const items = group.items.filter(visible);
          if (!items.length) return null;
          return (
            <div className="nav-group" key={group.heading}>
              <p className="nav-heading">{group.heading}</p>
              {items.map((item) => (
                <NavLink key={item.to} to={item.to} end={item.end} className="nav-link">
                  <Icon name={item.icon} />
                  {item.label}
                </NavLink>
              ))}
            </div>
          );
        })}
        <div className="sidebar-footer">
          <div className="user-chip">
            <strong>{user.username}</strong>
            <span className="muted">
              {ACCOUNT_LABELS[user.account_type]}
              {user.branch ? ` · ${user.branch}` : ""}
            </span>
          </div>
          <NavLink to="/account" className="nav-link">
            <Icon name="key" /> Password
          </NavLink>
          <button type="button" className="nav-link nav-button" onClick={signOut}>
            <Icon name="logOut" /> Sign out
          </button>
        </div>
      </nav>
      {open ? <div className="drawer-backdrop" onClick={() => setOpen(false)} aria-hidden="true" /> : null}
      <div className="shell-main" ref={mainArea}>
        <header className="topbar">
          <IconButton
            ref={menuButton}
            className="menu-button"
            icon={open ? "x" : "menu"}
            label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            aria-controls="primary-nav"
            onClick={() => setOpen((value) => !value)}
          />
          <span className="topbar-title">{user.display_name}</span>
          {user.is_head_office ? <BranchPicker id="branch-picker" /> : null}
          <ThemeToggle />
        </header>
        <main id="main" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
