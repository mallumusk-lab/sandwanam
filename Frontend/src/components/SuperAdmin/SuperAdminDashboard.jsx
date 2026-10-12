import React, { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { API_BASE_URL, API_HEADERS_JSON } from "../../Service/Index";
import "./SuperAdmin.css";

// All available dashboard features
const ALL_PERMISSIONS = [
  { key: "newcustomer",  label: "Add Customer",        icon: "➕", desc: "Register new borrowers" },
  { key: "userlist",     label: "Customer Directory",  icon: "👥", desc: "View all customers & loans" },
  { key: "form1",        label: "EMI Calculator",      icon: "🧮", desc: "Generate amortization schedules" },
  { key: "analytics",   label: "Analytics Hub",       icon: "📊", desc: "Portfolio performance & risk" },
  { key: "report",      label: "Daily Report",        icon: "📄", desc: "Export reconciliation data" },
  { key: "history",     label: "History Import",      icon: "🕓", desc: "Backfill historical loan data" },
  { key: "backup",      label: "System Backup",       icon: "🛡️", desc: "Manual backup & restore" },
];

const saFetch = (url, options = {}) => {
  const key = sessionStorage.getItem("superadmin_session") || "";
  return fetch(url, {
    ...options,
    headers: { ...API_HEADERS_JSON, "x-superadmin-key": key, ...(options.headers || {}) },
  });
};

const DEFAULT_PERMS = ALL_PERMISSIONS.map(p => p.key).join(",");

function SuperAdminDashboard() {
  const navigate = useNavigate();
  const [branches, setBranches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);

  const [showAddModal, setShowAddModal]          = useState(false);
  const [showEditModal, setShowEditModal]        = useState(null);
  const [showPasswordModal, setShowPasswordModal] = useState(null);

  const EMPTY_ADD = { userName: "", password: "", display_name: "", address: "", logo: "", permissions: DEFAULT_PERMS };
  const [addForm, setAddForm] = useState(EMPTY_ADD);
  const [editForm, setEditForm] = useState({ display_name: "", address: "", logo: "", permissions: DEFAULT_PERMS });
  const [newPassword, setNewPassword]     = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const addLogoRef  = useRef();
  const editLogoRef = useRef();

  useEffect(() => {
    if (!sessionStorage.getItem("superadmin_session")) { navigate("/superadmin"); return; }
    fetchBranches();
  }, []);

  const showToast = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const fetchBranches = async () => {
    setLoading(true);
    try {
      const res = await saFetch(`${API_BASE_URL}/superadmin/branches`);
      if (res.ok) setBranches(await res.json());
      else if (res.status === 403) navigate("/superadmin");
    } catch { showToast("Failed to fetch branches.", "error"); }
    finally { setLoading(false); }
  };

  const handleLogout = () => { sessionStorage.removeItem("superadmin_session"); navigate("/superadmin"); };

  const handleLogoUpload = (e, setter) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => setter(ev.target.result);
    reader.readAsDataURL(file);
  };

  const togglePerm = (permsStr, key) => {
    const arr = permsStr ? permsStr.split(",").filter(Boolean) : [];
    const idx = arr.indexOf(key);
    if (idx >= 0) arr.splice(idx, 1); else arr.push(key);
    return arr.join(",");
  };

  const hasPerm = (permsStr, key) => (permsStr || "").split(",").includes(key);

  // ── Add ──────────────────────────────────────────────────
  const handleAdd = async (e) => {
    e.preventDefault();
    if (!addForm.userName || !addForm.password || !addForm.display_name) {
      showToast("Username, Password and Branch Name are required.", "error"); return;
    }
    setSubmitting(true);
    try {
      const res = await saFetch(`${API_BASE_URL}/superadmin/branches`, {
        method: "POST", body: JSON.stringify(addForm),
      });
      const data = await res.json();
      if (res.ok) { showToast(data.message); setShowAddModal(false); setAddForm(EMPTY_ADD); fetchBranches(); }
      else showToast(data.detail || "Failed to create branch.", "error");
    } catch { showToast("Server error.", "error"); }
    finally { setSubmitting(false); }
  };

  // ── Edit ─────────────────────────────────────────────────
  const openEdit = (branch) => {
    setEditForm({
      display_name: branch.display_name || "",
      address: branch.address || "",
      logo: branch.logo || "",
      permissions: branch.permissions || DEFAULT_PERMS,
    });
    setShowEditModal(branch);
  };

  const handleEdit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await saFetch(`${API_BASE_URL}/superadmin/branches/${showEditModal.username}`, {
        method: "PUT", body: JSON.stringify(editForm),
      });
      const data = await res.json();
      if (res.ok) { showToast(data.message); setShowEditModal(null); fetchBranches(); }
      else showToast(data.detail || "Update failed.", "error");
    } catch { showToast("Server error.", "error"); }
    finally { setSubmitting(false); }
  };

  // ── Reset Password ────────────────────────────────────────
  const handleResetPassword = async (e) => {
    e.preventDefault();
    if (!newPassword) { showToast("Password cannot be empty.", "error"); return; }
    if (newPassword !== confirmPassword) { showToast("Passwords do not match.", "error"); return; }
    setSubmitting(true);
    try {
      const res = await saFetch(`${API_BASE_URL}/superadmin/reset_password/${showPasswordModal.username}`, {
        method: "POST", body: JSON.stringify({ new_password: newPassword }),
      });
      const data = await res.json();
      if (res.ok) { showToast(data.message); setShowPasswordModal(null); setNewPassword(""); setConfirmPassword(""); }
      else showToast(data.detail || "Reset failed.", "error");
    } catch { showToast("Server error.", "error"); }
    finally { setSubmitting(false); }
  };

  // ── Delete ────────────────────────────────────────────────
  const handleDelete = async (branch) => {
    if (!window.confirm(`Delete branch "${branch.display_name}"? This cannot be undone.`)) return;
    try {
      const res = await saFetch(`${API_BASE_URL}/superadmin/branches/${branch.username}`, { method: "DELETE" });
      const data = await res.json();
      if (res.ok) { showToast(data.message); fetchBranches(); }
      else showToast(data.detail || "Delete failed.", "error");
    } catch { showToast("Server error.", "error"); }
  };

  const ROLE_COLORS = { Admin: "#6366f1", User1: "#10b981", User2: "#f59e0b" };
  const roleColor = (role) => ROLE_COLORS[role] || "#3b82f6";

  const permCount = (permsStr) => (permsStr || "").split(",").filter(Boolean).length;

  // ── Permission Toggle Row ─────────────────────────────────
  const PermissionsEditor = ({ permsStr, onChange }) => (
    <div className="sa-perms-grid">
      {ALL_PERMISSIONS.map(p => {
        const active = hasPerm(permsStr, p.key);
        return (
          <div
            key={p.key}
            className={`sa-perm-chip ${active ? "sa-perm-on" : "sa-perm-off"}`}
            onClick={() => onChange(togglePerm(permsStr, p.key))}
          >
            <span className="sa-perm-icon">{p.icon}</span>
            <div>
              <div className="sa-perm-label">{p.label}</div>
              <div className="sa-perm-desc">{p.desc}</div>
            </div>
            <div className={`sa-perm-toggle ${active ? "on" : ""}`} />
          </div>
        );
      })}
    </div>
  );

  return (
    <div className="sa-dash-wrapper">
      {toast && (
        <div className={`sa-toast ${toast.type === "error" ? "sa-toast-error" : "sa-toast-success"}`}>
          {toast.type === "success" ? "✓ " : "✕ "}{toast.msg}
        </div>
      )}

      <aside className="sa-sidebar">
        <div className="sa-sidebar-logo">
          <div className="sa-sidebar-icon">⚡</div>
          <span>SuperAdmin</span>
        </div>
        <nav className="sa-sidebar-nav">
          <div className="sa-nav-item sa-nav-active"><span>🏢</span> Branches</div>
        </nav>
        <button className="sa-logout-btn" onClick={handleLogout}>← Logout</button>
      </aside>

      <main className="sa-main">
        <div className="sa-topbar">
          <div>
            <h1 className="sa-page-title">Branch Management</h1>
            <p className="sa-page-sub">Manage branch details, logos, access permissions, and credentials</p>
          </div>
          <button id="sa-add-branch-btn" className="sa-btn-primary" onClick={() => setShowAddModal(true)}>
            + Add Branch
          </button>
        </div>

        {loading ? (
          <div className="sa-loading">Loading branches...</div>
        ) : (
          <div className="sa-branch-grid">
            {branches.map((branch) => (
              <div key={branch.username} className="sa-branch-card">
                {/* Card Header */}
                <div className="sa-branch-header">
                  <div className="sa-branch-avatar">
                    {branch.logo
                      ? <img src={branch.logo} alt="logo" className="sa-branch-logo-img" />
                      : <span className="sa-branch-initials">{(branch.display_name || branch.username || "?").charAt(0).toUpperCase()}</span>}
                  </div>
                  <div className="sa-branch-title-block">
                    <h3 className="sa-branch-name">{branch.display_name || branch.username}</h3>
                    <span className="sa-branch-role" style={{ background: roleColor(branch.role) + "20", color: roleColor(branch.role) }}>
                      {branch.role}
                    </span>
                  </div>
                </div>

                {/* Details */}
                <div className="sa-branch-details">
                  <div className="sa-detail-row">
                    <span className="sa-detail-icon">🔑</span>
                    <span className="sa-detail-label">Login ID:</span>
                    <code className="sa-id-value">{branch.username}</code>
                  </div>
                  {branch.address && (
                    <div className="sa-detail-row">
                      <span className="sa-detail-icon">📍</span>
                      <span className="sa-detail-label">Address:</span>
                      <span className="sa-detail-value">{branch.address}</span>
                    </div>
                  )}
                  <div className="sa-detail-row">
                    <span className="sa-detail-icon">🔓</span>
                    <span className="sa-detail-label">Access:</span>
                    <span className="sa-perm-count-badge">
                      {permCount(branch.permissions)} / {ALL_PERMISSIONS.length} features enabled
                    </span>
                  </div>
                </div>

                {/* Permission Pills */}
                <div className="sa-branch-perm-pills">
                  {ALL_PERMISSIONS.map(p => (
                    <span key={p.key} className={`sa-pill ${hasPerm(branch.permissions, p.key) ? "sa-pill-on" : "sa-pill-off"}`}>
                      {p.icon} {p.label}
                    </span>
                  ))}
                </div>

                {/* Actions */}
                <div className="sa-branch-actions">
                  <button className="sa-btn-edit" onClick={() => openEdit(branch)}>✏ Edit Details</button>
                  <button className="sa-btn-reset" onClick={() => { setShowPasswordModal(branch); setNewPassword(""); setConfirmPassword(""); }}>
                    🔑 Reset Password
                  </button>
                  {branch.role !== "Admin" && (
                    <button className="sa-btn-delete" onClick={() => handleDelete(branch)}>🗑</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* ── Add Modal ─────────────────────────────────────── */}
      {showAddModal && (
        <div className="sa-modal-overlay" onClick={() => setShowAddModal(false)}>
          <div className="sa-modal sa-modal-wide" onClick={e => e.stopPropagation()}>
            <div className="sa-modal-header">
              <h2>Add New Branch</h2>
              <button className="sa-modal-close" onClick={() => setShowAddModal(false)}>✕</button>
            </div>
            <form onSubmit={handleAdd} className="sa-modal-scroll">
              <div className="sa-modal-two-col">
                <div>
                  <div className="sa-section-divider">Branch Information</div>
                  <div className="sa-input-group">
                    <label className="sa-label">Branch Name *</label>
                    <input className="sa-input" placeholder="e.g. Santhwanam Branch"
                      value={addForm.display_name} onChange={e => setAddForm({ ...addForm, display_name: e.target.value })} />
                  </div>
                  <div className="sa-input-group">
                    <label className="sa-label">Login Username *</label>
                    <input className="sa-input" placeholder="e.g. User3"
                      value={addForm.userName} onChange={e => setAddForm({ ...addForm, userName: e.target.value })} />
                  </div>
                  <div className="sa-input-group">
                    <label className="sa-label">Initial Password *</label>
                    <input className="sa-input" type="password" placeholder="••••••••"
                      value={addForm.password} onChange={e => setAddForm({ ...addForm, password: e.target.value })} />
                  </div>
                  <div className="sa-input-group">
                    <label className="sa-label">Address</label>
                    <textarea className="sa-input sa-textarea" placeholder="Branch address..."
                      value={addForm.address} onChange={e => setAddForm({ ...addForm, address: e.target.value })} />
                  </div>
                  <div className="sa-input-group">
                    <label className="sa-label">Branch Logo</label>
                    <div className="sa-logo-upload-area" onClick={() => addLogoRef.current.click()}>
                      {addForm.logo
                        ? <img src={addForm.logo} alt="preview" className="sa-logo-preview" />
                        : <span className="sa-upload-placeholder">📷 Click to upload logo</span>}
                    </div>
                    <input ref={addLogoRef} type="file" accept="image/*" style={{ display: "none" }}
                      onChange={e => handleLogoUpload(e, v => setAddForm({ ...addForm, logo: v }))} />
                  </div>
                </div>
                <div>
                  <div className="sa-section-divider">Dashboard Access Permissions</div>
                  <p className="sa-perm-hint">Choose which features this branch can access in their dashboard.</p>
                  <PermissionsEditor permsStr={addForm.permissions} onChange={v => setAddForm({ ...addForm, permissions: v })} />
                </div>
              </div>
              <div className="sa-modal-footer">
                <button type="button" className="sa-btn-cancel" onClick={() => setShowAddModal(false)}>Cancel</button>
                <button type="submit" className="sa-btn-primary" disabled={submitting}>
                  {submitting ? "Creating..." : "Create Branch"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Edit Modal ────────────────────────────────────── */}
      {showEditModal && (
        <div className="sa-modal-overlay" onClick={() => setShowEditModal(null)}>
          <div className="sa-modal sa-modal-wide" onClick={e => e.stopPropagation()}>
            <div className="sa-modal-header">
              <h2>Edit Branch — {showEditModal.display_name || showEditModal.username}</h2>
              <button className="sa-modal-close" onClick={() => setShowEditModal(null)}>✕</button>
            </div>
            <form onSubmit={handleEdit} className="sa-modal-scroll">
              <div className="sa-modal-two-col">
                <div>
                  <div className="sa-section-divider">Branch Information</div>
                  <div className="sa-input-group">
                    <label className="sa-label">Branch Name</label>
                    <input className="sa-input" value={editForm.display_name}
                      onChange={e => setEditForm({ ...editForm, display_name: e.target.value })} />
                  </div>
                  <div className="sa-input-group">
                    <label className="sa-label">Address</label>
                    <textarea className="sa-input sa-textarea" placeholder="Branch address..."
                      value={editForm.address} onChange={e => setEditForm({ ...editForm, address: e.target.value })} />
                  </div>
                  <div className="sa-input-group">
                    <label className="sa-label">Branch Logo</label>
                    <div className="sa-logo-upload-area" onClick={() => editLogoRef.current.click()}>
                      {editForm.logo
                        ? <img src={editForm.logo} alt="preview" className="sa-logo-preview" />
                        : <span className="sa-upload-placeholder">📷 Click to upload / change logo</span>}
                    </div>
                    <input ref={editLogoRef} type="file" accept="image/*" style={{ display: "none" }}
                      onChange={e => handleLogoUpload(e, v => setEditForm({ ...editForm, logo: v }))} />
                    {editForm.logo && (
                      <button type="button" className="sa-clear-logo" onClick={() => setEditForm({ ...editForm, logo: "" })}>
                        ✕ Remove logo
                      </button>
                    )}
                  </div>
                </div>
                <div>
                  <div className="sa-section-divider">Dashboard Access Permissions</div>
                  <p className="sa-perm-hint">Toggle which dashboard sections this branch can access.</p>
                  <PermissionsEditor permsStr={editForm.permissions} onChange={v => setEditForm({ ...editForm, permissions: v })} />
                </div>
              </div>
              <div className="sa-modal-footer">
                <button type="button" className="sa-btn-cancel" onClick={() => setShowEditModal(null)}>Cancel</button>
                <button type="submit" className="sa-btn-primary" disabled={submitting}>
                  {submitting ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Reset Password Modal ──────────────────────────── */}
      {showPasswordModal && (
        <div className="sa-modal-overlay" onClick={() => setShowPasswordModal(null)}>
          <div className="sa-modal" onClick={e => e.stopPropagation()}>
            <div className="sa-modal-header">
              <h2>Reset Password — {showPasswordModal.display_name || showPasswordModal.username}</h2>
              <button className="sa-modal-close" onClick={() => setShowPasswordModal(null)}>✕</button>
            </div>
            <form onSubmit={handleResetPassword}>
              <div className="sa-input-group">
                <label className="sa-label">New Password</label>
                <input className="sa-input" type="password" placeholder="••••••••"
                  value={newPassword} onChange={e => setNewPassword(e.target.value)} />
              </div>
              <div className="sa-input-group">
                <label className="sa-label">Confirm Password</label>
                <input className="sa-input" type="password" placeholder="••••••••"
                  value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} />
              </div>
              <p className="sa-warning-note">⚠ The branch will use the new password on next login.</p>
              <div className="sa-modal-footer">
                <button type="button" className="sa-btn-cancel" onClick={() => setShowPasswordModal(null)}>Cancel</button>
                <button type="submit" className="sa-btn-danger" disabled={submitting}>
                  {submitting ? "Resetting..." : "Reset Password"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default SuperAdminDashboard;
