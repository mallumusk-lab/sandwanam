import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { branches as branchesApi } from "../api/endpoints.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { ACCOUNT_LABELS, CREATE, can } from "../lib/permissions.js";
import { IconButton, ThemeToggle } from "./controls.jsx";
import { Icon } from "./Icon.jsx";
import { useToast } from "./feedback.jsx";

const NAV = [
  {
    heading: "Daily work",
    items: [
      { to: "/", label: "Dashboard", icon: "home", permission: "analytics", end: true },
      { to: "/customers", label: "Customers", icon: "users", permission: "userlist", end: true },
      { to: "/customers/new", label: "New customer", icon: "userPlus", permission: CREATE },
      { to: "/reports", label: "Reports", icon: "file", permission: "report" },
      { to: "/history", label: "History import", icon: "clock", permission: "history" },
    ],
  },
  {
    heading: "Tools",
    items: [
      { to: "/tools/application-form", label: "Application form", icon: "clipboard", permission: "form1" },
      { to: "/tools/calculator", label: "Loan calculator", icon: "calculator", permission: "form1" },
    ],
  },
  {
    heading: "Head office",
    items: [
      { to: "/settings", label: "Gold rate", icon: "sliders", headOffice: true },
      { to: "/backup", label: "Backups", icon: "database", headOffice: true },
      { to: "/audit", label: "Audit log", icon: "activity", headOffice: true },
      { to: "/admin/branches", label: "Branches", icon: "shield", superadmin: true },
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

function BranchPicker({ id }) {
  const { branch, setBranch } = useAuth();
  const toast = useToast();
  const [options, setOptions] = useState([]);
  useEffect(() => {
    const controller = new AbortController();
    branchesApi
      .list({ signal: controller.signal })
      .then(setOptions)
      .catch((error) => {
        if (!controller.signal.aborted) toast.error("Branches could not be loaded", error.message);
      });
    return () => controller.abort();
  }, [toast]);
  return (
    <div className="field">
      <label className="visually-hidden" htmlFor={id}>
        Branch shown
      </label>
      <select id={id} className="select branch-select" value={branch} onChange={(e) => setBranch(e.target.value)}>
        <option value="">All branches</option>
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
    (!item.superadmin || user.is_superadmin);

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
