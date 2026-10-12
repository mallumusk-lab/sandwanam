import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { API_BASE_URL, API_HEADERS_JSON } from "../../Service/Index";
import "./SuperAdmin.css";

function SuperAdminLogin() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    if (!username.trim() || !password.trim()) {
      setError("Both fields are required.");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/superadmin/authenticate`, {
        method: "POST",
        headers: API_HEADERS_JSON,
        body: JSON.stringify({ userName: username, password }),
      });
      const data = await res.json();
      if (res.ok && data.role === "SuperAdmin") {
        sessionStorage.setItem("superadmin_session", "superadmin-session-ok");
        navigate("/superadmin/dashboard");
      } else {
        setError(data.detail || "Authentication failed.");
      }
    } catch {
      setError("Unable to connect to server.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="sa-login-wrapper">
      {/* Animated background orbs */}
      <div className="sa-orb sa-orb-1" />
      <div className="sa-orb sa-orb-2" />
      <div className="sa-orb sa-orb-3" />

      <div className="sa-login-card">
        <div className="sa-login-badge">SUPER ADMIN</div>
        <div className="sa-login-icon">🔐</div>
        <h1 className="sa-login-title">System Control Panel</h1>
        <p className="sa-login-sub">Restricted Access — Authorized Personnel Only</p>

        <form className="sa-form" onSubmit={handleLogin}>
          <div className="sa-input-group">
            <label className="sa-label">Username</label>
            <input
              id="sa-username"
              className="sa-input"
              type="text"
              placeholder="Enter superadmin username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
            />
          </div>
          <div className="sa-input-group">
            <label className="sa-label">Password</label>
            <input
              id="sa-password"
              className="sa-input"
              type="password"
              placeholder="••••••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>

          {error && <div className="sa-error">{error}</div>}

          <button id="sa-login-btn" className="sa-btn-login" type="submit" disabled={loading}>
            {loading ? <span className="sa-spinner" /> : "Access System"}
          </button>
        </form>

        <div className="sa-footer-note">
          <a href="/" className="sa-back-link">← Back to Branch Login</a>
        </div>
      </div>
    </div>
  );
}

export default SuperAdminLogin;
