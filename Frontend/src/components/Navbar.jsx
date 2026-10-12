import React, { useEffect, useState } from "react";
import "./Navbar.css";
import { NavLink, useLocation } from "react-router-dom";
import { useSelector, useDispatch } from "react-redux";
import { Myaction } from "../store/MyfinSlice";
import { API_BASE_URL, API_HEADERS } from "../Service/Index";
import { FiPlus, FiUsers, FiGrid, FiPieChart, FiFileText, FiDatabase, FiHome, FiLogOut } from "react-icons/fi";

const SHORTCUTS = [
  { key: "newcustomer", title: "New Loan", icon: <FiPlus /> },
  { key: "userlist", title: "Directory", icon: <FiUsers /> },
  { key: "report", title: "Report", icon: <FiFileText /> },
  { key: "history", title: "History", icon: <FiPlus style={{ transform: "rotate(45deg)" }} /> },
  { key: "backup", title: "Backup", icon: <FiDatabase /> },
  { key: "form1", title: "Custom form", icon: <FiGrid /> },
];

export const Navbar = () => {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  const dispatch = useDispatch();
  const userRole = useSelector((state) => state.myfin.data);
  const selectedUser = useSelector((state) => state.myfin.user);
  const [branchSettings, setBranchSettings] = useState({});

  const handleLogout = () => {
    localStorage.removeItem("myfinData");
    localStorage.removeItem("selectedUser");
  };

  useEffect(() => {
    dispatch(Myaction.userNotChangeSelected(localStorage.getItem("selectedUser") || "User1"));
    // Fetch display names from DB
    fetch(`${API_BASE_URL}/branch-settings`, { headers: API_HEADERS })
      .then((r) => r.json())
      .then(setBranchSettings)
      .catch(() => {});
  }, [dispatch]);

  const activeRole = userRole === "Admin" ? selectedUser : userRole;
  const displayName = branchSettings[userRole]?.display_name || userRole || "Guest";
  
  const getPermissions = () => {
    const settings = branchSettings[activeRole];
    if (!settings || !settings.permissions) return SHORTCUTS.map((s) => s.key);
    return settings.permissions;
  };

  const visibleShortcuts = SHORTCUTS.filter((s) => getPermissions().includes(s.key));

  const onSelectionChange = (event) => {
    const selectedValue = event.target.value;
    localStorage.setItem("selectedUser", selectedValue);
    dispatch(Myaction.userChangeSelected(selectedValue));
  };

  const branchOptions = Object.entries(branchSettings)
    .filter(([key]) => key !== "Admin" && key !== "SuperAdmin")
    .map(([key, val]) => ({ key, name: val.display_name || key }));

  return (
    <div>
      <nav>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="nav-brand" style={{ display: "flex", alignItems: "center", height: "60px", marginLeft: '10px', marginRight: '20px', fontWeight: 'bold', fontSize: '1.2rem' }}>
            {/* Logo space */}
          </div>
          <ul className={menuOpen ? "open" : ""} style={{ margin: 0, padding: 0 }}>
            {location.pathname !== "/" && (
              <li>
                <NavLink to="/admin" onClick={() => setMenuOpen(false)} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <FiHome /> <span className="nav-text">Home</span>
                </NavLink>
              </li>
            )}
            
            {location.pathname !== "/" && visibleShortcuts.map((s) => (
              <li key={s.key}>
                <NavLink to={`/${s.key}`} onClick={() => setMenuOpen(false)} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  {s.icon} <span className="nav-text">{s.title}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </div>

        <div style={{ display: 'flex', alignItems: 'center' }}>
          <ul className={menuOpen ? "open right-menu" : ""} style={{ margin: 0, padding: 0, alignItems: 'center' }}>
            {location.pathname !== "/" && userRole === "Admin" && branchOptions.length > 0 && (
              <li style={{ display: 'flex', alignItems: 'center', marginRight: '15px' }}>
                <span style={{ fontSize: '13px', marginRight: '8px', opacity: 0.9 }}>Branch:</span>
                <select 
                  value={selectedUser} 
                  onChange={onSelectionChange} 
                  style={{ 
                    padding: '6px 12px', 
                    borderRadius: '6px', 
                    border: '1px solid rgba(255,255,255,0.3)', 
                    background: 'rgba(255,255,255,0.15)', 
                    color: 'white',
                    outline: 'none',
                    cursor: 'pointer',
                    fontSize: '13px',
                    fontWeight: 600
                  }}
                >
                  {branchOptions.map((b) => (
                    <option key={b.key} value={b.key} style={{ color: '#1e293b' }}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </li>
            )}

            {location.pathname !== "/" && (
              <li className="user-role-display" style={{ marginLeft: 0 }}>
                <span className="role-badge">{displayName}</span>
              </li>
            )}
            
            {location.pathname !== "/" && (
              <li>
                <NavLink to="/" onClick={() => { handleLogout(); setMenuOpen(false); }} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <FiLogOut /> <span className="nav-text">Logout</span>
                </NavLink>
              </li>
            )}
          </ul>
        </div>

        <div className="menu" onClick={() => setMenuOpen(!menuOpen)}>
          <span></span>
          <span></span>
        </div>
      </nav>
    </div>
  );
};
