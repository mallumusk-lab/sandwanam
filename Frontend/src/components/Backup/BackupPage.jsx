import React, { useState, useEffect } from "react";
import { FiDatabase, FiDownload, FiUploadCloud, FiRefreshCw, FiClock, FiArrowLeft } from "react-icons/fi";
import { useNavigate } from "react-router-dom";
import { API_BASE_URL, API_HEADERS } from "../../Service/Index";
import "./BackupPage.css";

const BackupPage = () => {
  const navigate = useNavigate();
  const [backupLoading, setBackupLoading] = useState(false);
  const [backupMsg, setBackupMsg] = useState("");
  const [lastBackup, setLastBackup] = useState(null);
  const [backupPath, setBackupPath] = useState("");

  const fetchBackupStatus = async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/backup/status`, { headers: API_HEADERS });
      if (resp.ok) {
        const data = await resp.json();
        setLastBackup(data.last_backup);
        setBackupPath(data.path);
      }
    } catch (e) {
      console.error("Failed to fetch backup status", e);
    }
  };

  useEffect(() => {
    fetchBackupStatus();
  }, []);

  const handleManualBackup = async () => {
    setBackupLoading(true);
    setBackupMsg("");
    try {
      const resp = await fetch(`${API_BASE_URL}/backup/manual`, { method: "POST", headers: API_HEADERS });
      if (resp.ok) {
        setBackupMsg("✅ Manual backup triggered successfully.");
        await fetchBackupStatus(); // refresh time
      } else {
        setBackupMsg("❌ Failed to trigger manual backup.");
      }
    } catch (e) {
      setBackupMsg("❌ Error connecting to backup server.");
    }
    setBackupLoading(false);
  };

  const handleDownloadBackup = () => {
    window.open(`${API_BASE_URL}/backup/download?x_api_key=12345`, "_blank");
  };

  const handleRestoreBackup = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (!window.confirm("⚠️ WARNING: This will completely WIPE the current database and replace it with the backup. Are you sure?")) {
      e.target.value = null;
      return;
    }
    setBackupLoading(true);
    setBackupMsg("Restoring database... Please wait, this may take a moment.");
    
    const formData = new FormData();
    formData.append("file", file);

    try {
      const resp = await fetch(`${API_BASE_URL}/backup/restore`, {
        method: "POST",
        headers: { "x-api-key": "12345" }, 
        body: formData
      });
      if (resp.ok) {
        setBackupMsg("✅ Database successfully restored. All data has been replaced.");
      } else {
        const err = await resp.json();
        setBackupMsg(`❌ Restore failed: ${err.detail || "Unknown error"}`);
      }
    } catch(err) {
      setBackupMsg("❌ Error connecting to server during restore.");
    }
    setBackupLoading(false);
    e.target.value = null;
  };

  const formatLastBackup = () => {
    if (!lastBackup) return "No automated backups found.";
    const d = new Date(lastBackup);
    return d.toLocaleString('en-IN', { 
      day: 'numeric', month: 'short', year: 'numeric', 
      hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
  };

  return (
    <div className="backup-page-container">
      <div className="backup-header-bar">
        <button className="btn-back" onClick={() => navigate('/admin')}>
          <FiArrowLeft /> Back to Dashboard
        </button>
      </div>

      <div className="bp-hero">
        <div className="bp-hero-icon">
          <FiDatabase size={48} />
        </div>
        <h1>System Backup & Recovery</h1>
        <p>Ensure business continuity by protecting your critical enterprise data. Automated safety snapshots are performed continuously behind the scenes.</p>
      </div>

      <div className="bp-content">
        <div className="bp-status-card">
          <div className="bps-icon"><FiClock size={28} /></div>
          <div className="bps-info">
            <h3>Last Automated Backup</h3>
            <div className="bps-time">{formatLastBackup()}</div>
            {backupPath && (
              <div style={{ marginTop: '8px', fontSize: '0.85rem', color: '#64748b', wordBreak: 'break-all', backgroundColor: 'rgba(0,0,0,0.03)', padding: '6px 10px', borderRadius: '4px', border: '1px dashed rgba(0,0,0,0.1)', display: 'inline-block' }}>
                <strong style={{ color: '#475569' }}>Save Location:</strong> <code style={{ fontFamily: 'monospace' }}>{backupPath}</code>
              </div>
            )}
            <p className="bps-explainer" style={{ marginTop: '12px' }}>The system automatically generates a complete JSON ledger every hour. You can use the buttons below to create an overriding on-demand snapshot at this exact moment.</p>
          </div>
        </div>

        {backupMsg && (
          <div className={`bp-msg ${backupMsg.includes('❌') ? 'error' : 'success'}`}>
            {backupMsg}
          </div>
        )}

        <div className="bp-actions-grid">
          <div className="bp-action-box">
            <h3>Standard Operations</h3>
            <button className="bp-btn bp-btn-primary" onClick={handleManualBackup} disabled={backupLoading}>
              <FiRefreshCw className={backupLoading ? "spin" : ""} size={18} /> 
              {backupLoading ? "Processing..." : "Trigger Manual Backup"}
            </button>
            <p>Force the server to take an immediate snapshot of the current state, replacing the automated file.</p>
            
            <button className="bp-btn bp-btn-success mt-12" onClick={handleDownloadBackup} disabled={backupLoading}>
              <FiDownload size={18} /> Download Current Backup Let
            </button>
            <p>Securely pull the `finance_backup.json` to your local machine for cold storage.</p>
          </div>

          <div className="bp-action-box danger-zone">
            <h3>Emergency Recovery</h3>
            <div className="restore-wrap">
              <input type="file" id="restoreFile" accept=".json" onChange={handleRestoreBackup} style={{display: 'none'}} />
              <label htmlFor="restoreFile" className={`bp-btn bp-btn-danger ${backupLoading ? 'disabled' : ''}`}>
                <FiUploadCloud size={18} /> Upload & Restore JSON
              </label>
              <div className="danger-text">
                <strong>⚠️ DANGER ZONE:</strong> Uploading a backup file will completely violently wipe the live database and surgically reconstruct it from the provided file. This cannot be undone.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default BackupPage;
