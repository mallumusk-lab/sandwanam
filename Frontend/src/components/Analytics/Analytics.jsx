
import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';
import {
  FiTrendingUp, FiTrendingDown, FiDollarSign, FiBox, FiAlertTriangle,
  FiClock, FiCheckCircle, FiSearch, FiFileText, FiPlus, FiActivity,
  FiArrowRight, FiTarget, FiBriefcase, FiAward, FiX, FiChevronRight,
  FiUsers, FiBarChart2, FiPercent, FiRefreshCw, FiCalendar, FiChevronDown
} from 'react-icons/fi';
import { API_BASE_URL, API_HEADERS } from "../../Service/Index";
import "./Analytics.css";
import { useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";

// ─── Date Helpers ────────────────────────────────────────────────────────────
const fmt = (d) => d.toISOString().slice(0, 10);
const fmtDisplay = (iso) => {
  const [y, m, d] = iso.split("-");
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${months[parseInt(m,10)-1]} ${parseInt(d,10)}, ${y}`;
};
const getDateRangeLabel = (start, end) => {
  if (start === end) return fmtDisplay(start);
  const [sy, sm] = start.split("-");
  const [ey, em] = end.split("-");
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const startStr = `${months[parseInt(sm,10)-1]} ${parseInt(start.split("-")[2],10)}`;
  const endStr = fmtDisplay(end);
  // same year — omit year from start
  if (sy === ey) return `${startStr} – ${endStr}`;
  return `${fmtDisplay(start)} – ${endStr}`;
};
const fmtLocal = (d) => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
};
const today = () => fmtLocal(new Date());
const getPeriodDates = (period) => {
  const now = new Date();
  const t = fmtLocal(now);
  if (period === "today") return { start: t, end: t };
  if (period === "week") {
    const day = now.getDay();
    const mon = new Date(now); mon.setDate(now.getDate() - (day === 0 ? 6 : day - 1));
    return { start: fmtLocal(mon), end: t };
  }
  if (period === "month") {
    const s = new Date(now.getFullYear(), now.getMonth(), 1);
    return { start: fmtLocal(s), end: t };
  }
  if (period === "year") {
    const s = new Date(now.getFullYear(), 0, 1);
    return { start: fmtLocal(s), end: t };
  }
  return { start: t, end: t };
};

const PERIOD_OPTIONS = [
  { value: "today", label: "Today" },
  { value: "week", label: "This Week" },
  { value: "month", label: "This Month" },
  { value: "year", label: "This Year" },
  { value: "custom", label: "Custom Range" },
];

// ─── Detail Modal ─────────────────────────────────────────────────────────────
const DetailModal = ({ isOpen, onClose, detailData, loading }) => {
  if (!isOpen) return null;
  const renderCell = (key, value) => {
    if (key === "status") return (
      <span className={`detail-badge ${value === "open" ? "badge-open" : "badge-closed"}`}>{value}</span>
    );
    if (key === "days_inactive") {
      const d = Number(value);
      return <span style={{ fontWeight: 700, color: d > 365 ? "#ef4444" : d > 180 ? "#f59e0b" : "#6366f1" }}>{d}d</span>;
    }
    if (typeof value === "number" && value > 999)
      return <span style={{ fontWeight: 700, color: "var(--secondary)" }}>
        {new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(value)}
      </span>;
    return String(value ?? "—");
  };
  const colKeys = detailData?.rows?.length > 0 ? Object.keys(detailData.rows[0]) : [];
  const fmtTotal = (v) => typeof v === "number" && v > 999
    ? new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(v)
    : v;

  return (
    <div className="detail-modal-overlay" onClick={onClose}>
      <div className="detail-modal" onClick={e => e.stopPropagation()}>
        <div className="detail-modal-header">
          <div>
            <h2 className="detail-modal-title">{detailData?.title || "Details"}</h2>
            <p className="detail-modal-subtitle">
              {detailData?.rows?.length || 0} records
              {detailData?.total !== undefined && (
                <span style={{ marginLeft: 12, color: "var(--primary)", fontWeight: 700 }}>
                  Total: {fmtTotal(detailData.total)}
                </span>
              )}
            </p>
          </div>
          <button className="detail-modal-close" onClick={onClose}><FiX size={20} /></button>
        </div>
        <div className="detail-modal-body">
          {loading ? (
            <div className="detail-modal-loading"><div className="detail-spinner" /><p>Fetching data...</p></div>
          ) : !detailData?.rows?.length ? (
            <div className="detail-modal-empty">
              <FiFileText size={48} style={{ color: "var(--text-muted)", marginBottom: 12 }} />
              <p>No records found for this period.</p>
            </div>
          ) : (
            <div className="detail-table-wrapper">
              <table className="detail-table">
                <thead>
                  <tr>{colKeys.map(c => <th key={c}>{c.replace(/_/g, " ").replace(/\b\w/g, x => x.toUpperCase())}</th>)}</tr>
                </thead>
                <tbody>
                  {detailData.rows.map((row, i) => (
                    <tr key={i}>{colKeys.map(c => <td key={c}>{renderCell(c, row[c])}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// ─── Stat Card ────────────────────────────────────────────────────────────────
const StatCard = ({ label, value, sublabel, icon, color, bgColor, onClick, isCount = false, isWeight = false }) => {
  const formatted = isCount
    ? (value || 0)
    : isWeight
    ? (value || 0).toFixed(1) + "g"
    : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(value || 0);
  return (
    <div className="perf-card clickable-card" onClick={onClick}>
      <div className="perf-card-top">
        <div className="perf-card-icon" style={{ background: bgColor, color }}>{icon}</div>
        <FiChevronRight size={16} className="perf-card-arrow" />
      </div>
      <span className="perf-card-label">{label}</span>
      <p className="perf-card-value">{formatted}</p>
      <small className="perf-card-sub">{sublabel}</small>
    </div>
  );
};

// ─── Period Selector ──────────────────────────────────────────────────────────
const PeriodSelector = ({ period, setPeriod, customStart, setCustomStart, customEnd, setCustomEnd, activeDatesRef }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const currentLabel = PERIOD_OPTIONS.find(o => o.value === period)?.label || "Today";

  // Compute the display range from current period
  const dates = period === "custom"
    ? { start: customStart, end: customEnd }
    : getPeriodDates(period);
  const rangeLabel = dates.start && dates.end ? getDateRangeLabel(dates.start, dates.end) : "";

  return (
    <div className="period-selector-wrap" ref={ref}>
      <div className="period-selector-col">
        <button className="period-btn" onClick={() => setOpen(o => !o)}>
          <FiCalendar size={14} />
          <span>{currentLabel}</span>
          <FiChevronDown size={14} className={`period-chevron ${open ? "open" : ""}`} />
        </button>
        {rangeLabel && (
          <span className="period-range-label">{rangeLabel}</span>
        )}
      </div>

      {open && (
        <div className="period-dropdown">
          {PERIOD_OPTIONS.map(opt => (
            <button
              key={opt.value}
              className={`period-option ${period === opt.value ? "active" : ""}`}
              onClick={() => { setPeriod(opt.value); if (opt.value !== "custom") setOpen(false); }}
            >
              {opt.label}
            </button>
          ))}

          {period === "custom" && (
            <div className="period-custom-range">
              <div className="period-date-group">
                <label>From</label>
                <input type="date" value={customStart} max={customEnd || today()}
                  onChange={e => setCustomStart(e.target.value)} className="period-date-input" />
              </div>
              <div className="period-date-group">
                <label>To</label>
                <input type="date" value={customEnd} min={customStart} max={today()}
                  onChange={e => setCustomEnd(e.target.value)} className="period-date-input" />
              </div>
              <button className="period-apply-btn" onClick={() => setOpen(false)}>Apply</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ─── Main Analytics ───────────────────────────────────────────────────────────
const Analytics = () => {
  const [data, setData] = useState(null);
  const [totalPrinciple, setTotalPrinciple] = useState(0);
  const [totalInterest, setTotalInterest] = useState(0);
  const [adminSummary, setAdminSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [modalData, setModalData] = useState(null);

  // Period state
  const [period, setPeriod] = useState("today");
  const [customStart, setCustomStart] = useState(today());
  const [customEnd, setCustomEnd] = useState(today());
  const [perfStats, setPerfStats] = useState(null);
  const [perfLoading, setPerfLoading] = useState(false);
  // Overdue Loans State
  const [overdueLoans, setOverdueLoans] = useState([]);
  const [selectedOverdueLoan, setSelectedOverdueLoan] = useState(null);
  const [followUpDate, setFollowUpDate] = useState("");
  // Track active date range for modal calls
  const activeDates = useRef({ start: today(), end: today() });

  const navigate = useNavigate();
  const userRole = useSelector((state) => state.myfin.data);
  const isAdmin = userRole === "Admin" || userRole === "SuperAdmin";

  // Derive start/end from period
  const getActiveDates = useCallback(() => {
    if (period === "custom") return { start: customStart, end: customEnd };
    return getPeriodDates(period);
  }, [period, customStart, customEnd]);

  // Fetch main analytics (KPI overview, chart, etc.) once
  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        const [analyticsRes, adminRes, overdueRes] = await Promise.all([
          fetch(`${API_BASE_URL}/analytics_data`, { headers: API_HEADERS }),
          fetch(`${API_BASE_URL}/admin_summary`, { headers: API_HEADERS }),
          fetch(`${API_BASE_URL}/overdue_loans`, { headers: API_HEADERS }),
        ]);
        if (analyticsRes.ok) setData(await analyticsRes.json());
        if (overdueRes.ok) setOverdueLoans(await overdueRes.json());
        if (adminRes.ok) {
          const ad = await adminRes.json();
          setTotalInterest(ad.total_interest);
          setTotalPrinciple(ad.total_principal);
          if (isAdmin) {
            const [gRes, cRes, iRes] = await Promise.all([
              fetch(`${API_BASE_URL}/admin_details/given_principle`, { headers: API_HEADERS }),
              fetch(`${API_BASE_URL}/admin_details/compounded_principle`, { headers: API_HEADERS }),
              fetch(`${API_BASE_URL}/admin_details/inactive_accounts`, { headers: API_HEADERS }),
            ]);
            setAdminSummary({
              principle_remaining: ad.total_principal,
              given_principle: gRes.ok ? (await gRes.json()).total : 0,
              compounded_principle: cRes.ok ? (await cRes.json()).total : 0,
              interest_remaining: ad.total_interest,
              inactive_accounts: iRes.ok ? (await iRes.json()).total : 0,
            });
          }
        }
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    };
    fetchAnalytics();
  }, [isAdmin]);

  // Fetch performance stats whenever period or custom dates change
  useEffect(() => {
    const dates = getActiveDates();
    if (period === "custom" && (!customStart || !customEnd)) return;
    activeDates.current = dates;
    const fetchPerf = async () => {
      setPerfLoading(true);
      try {
        const res = await fetch(
          `${API_BASE_URL}/performance_summary?start_date=${dates.start}&end_date=${dates.end}`,
          { headers: API_HEADERS }
        );
        if (res.ok) setPerfStats(await res.json());
      } catch (e) { console.error(e); }
      finally { setPerfLoading(false); }
    };
    fetchPerf();
  }, [period, customStart, customEnd, getActiveDates]);

  const openDetail = useCallback(async (type, isAdminDetail = false) => {
    setModalOpen(true);
    setModalLoading(true);
    setModalData(null);
    try {
      const { start, end } = activeDates.current;
      const endpoint = isAdminDetail
        ? `${API_BASE_URL}/admin_details/${type}`
        : `${API_BASE_URL}/analytics_details/${type}?start_date=${start}&end_date=${end}`;
      const res = await fetch(endpoint, { headers: API_HEADERS });
      if (res.ok) setModalData(await res.json());
      else setModalData({ title: "Error", rows: [], total: 0 });
    } catch { setModalData({ title: "Error", rows: [], total: 0 }); }
    finally { setModalLoading(false); }
  }, []);

  const getNextWorkingDay = () => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    if (d.getDay() === 0) d.setDate(d.getDate() + 1); // Skip Sunday
    return fmtLocal(d);
  };

  const handleOverdueClick = (loan) => {
    setSelectedOverdueLoan(loan);
    setFollowUpDate(getNextWorkingDay());
  };

  const handleUpdateFollowUp = async () => {
    if (!selectedOverdueLoan || !followUpDate) return;
    try {
      const res = await fetch(`${API_BASE_URL}/update_follow_up/${selectedOverdueLoan.loan_number}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": "12345"
        },
        body: JSON.stringify({ follow_up_date: followUpDate })
      });
      if (res.ok) {
        setOverdueLoans(prev => prev.map(l => l.loan_number === selectedOverdueLoan.loan_number ? { ...l, follow_up_date: followUpDate } : l));
        setSelectedOverdueLoan(null);
      } else {
        alert("Failed to update follow-up date.");
      }
    } catch (e) {
      console.error(e);
      alert("Error updating follow-up date.");
    }
  };

  if (loading) return <div className="analytics-loading">Initializing Banking Dashboard...</div>;
  if (!data || !data.kpis) return <div className="analytics-error">Error connecting to financial services.</div>;

  const { kpis = {}, trends = [], recent_transactions = [], gold_price = { current: 0, change: "Stable" }, branch_data = [] } = data;
  const fmtCur = (v) => new Number(v || 0).toLocaleString('en-IN', { maximumFractionDigits: 0, style: 'currency', currency: 'INR' });

  // Use perfStats if available, else fall back to kpis (today)
  const ps = perfStats || {
    disbursed: kpis.disbursed_today, disbursed_count: kpis.disbursed_today_count,
    interest_collected: kpis.interest_today, principle_collected: Math.max(0, (kpis.collected_today || 0) - (kpis.interest_today || 0)),
    total_collected: kpis.collected_today, collected_count: kpis.collected_today_count,
    new_loans: kpis.disbursed_today_count, closures: kpis.closed_today,
    gold_collected: kpis.gold_collected_today
  };

  const periodLabel = PERIOD_OPTIONS.find(o => o.value === period)?.label || "Today";

  return (
    <div className="analytics-container">
      <DetailModal isOpen={modalOpen} onClose={() => setModalOpen(false)} detailData={modalData} loading={modalLoading} />

      {selectedOverdueLoan && (
        <div className="detail-modal-overlay" onClick={() => setSelectedOverdueLoan(null)}>
          <div className="detail-modal overdue-modal" onClick={e => e.stopPropagation()} style={{ maxWidth: '500px' }}>
            <div className="detail-modal-header" style={{ padding: '1.5rem', background: 'linear-gradient(135deg, #fff1f2, #fef2f2)', borderBottom: '1px solid #fecdd3' }}>
              <div>
                <h2 className="detail-modal-title" style={{ color: '#e11d48', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '1.25rem' }}>
                  <FiAlertTriangle /> Overdue Loan Details
                </h2>
                <p className="detail-modal-subtitle" style={{ color: '#be123c', opacity: 0.8 }}>Update Follow-up Date to manage this account.</p>
              </div>
              <button className="detail-modal-close" onClick={() => setSelectedOverdueLoan(null)} style={{ background: 'white', border: '1px solid #fecdd3', color: '#e11d48' }}><FiX size={20} /></button>
            </div>
            <div className="detail-modal-body" style={{ padding: '1.5rem' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem', marginBottom: '2rem', background: '#f8fafc', padding: '1.5rem', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}><span style={{ color: 'var(--text-muted)', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700 }}>Customer</span><p style={{ margin: 0, fontWeight: 700, fontSize: '1rem', color: 'var(--secondary)' }}>{selectedOverdueLoan.customername}</p></div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}><span style={{ color: 'var(--text-muted)', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700 }}>Phone</span><p style={{ margin: 0, fontWeight: 700, fontSize: '1rem', color: 'var(--secondary)' }}>{selectedOverdueLoan.phone}</p></div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}><span style={{ color: 'var(--text-muted)', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700 }}>Loan Number</span><p style={{ margin: 0, fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-main)' }}>{selectedOverdueLoan.loan_number}</p></div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}><span style={{ color: 'var(--text-muted)', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700 }}>Start Date</span><p style={{ margin: 0, fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-main)' }}>{fmtDisplay(selectedOverdueLoan.date)}</p></div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}><span style={{ color: 'var(--text-muted)', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700 }}>Principal</span><p style={{ margin: 0, fontWeight: 800, fontSize: '1.1rem', color: 'var(--primary)' }}>₹{parseFloat(selectedOverdueLoan.refreshprincipleamount).toLocaleString()}</p></div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}><span style={{ color: 'var(--text-muted)', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700 }}>Interest</span><p style={{ margin: 0, fontWeight: 800, fontSize: '1.1rem', color: 'var(--danger)' }}>₹{parseFloat(selectedOverdueLoan.refreshinterest).toLocaleString()}</p></div>
              </div>
              <div className="period-date-group" style={{ marginBottom: '1.5rem' }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Next Follow-up Date</label>
                <input type="date" value={followUpDate} min={today()} onChange={e => setFollowUpDate(e.target.value)} style={{ width: '100%', padding: '0.875rem 1rem', fontSize: '1rem', border: '2px solid #e2e8f0', borderRadius: '8px', background: '#fff', color: 'var(--secondary)', fontWeight: 600, outline: 'none', transition: 'border-color 0.2s', fontFamily: 'inherit' }} onFocus={e => e.target.style.borderColor = 'var(--primary)'} onBlur={e => e.target.style.borderColor = '#e2e8f0'} />
              </div>
              <button onClick={handleUpdateFollowUp} className="action-btn" style={{ width: '100%', background: 'linear-gradient(135deg, var(--primary), #4338ca)', color: 'white', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px', padding: '1rem', fontSize: '1rem', border: 'none', borderRadius: '8px', boxShadow: '0 4px 6px -1px rgba(79, 70, 229, 0.2), 0 2px 4px -1px rgba(79, 70, 229, 0.1)', cursor: 'pointer', transition: 'transform 0.2s, box-shadow 0.2s' }} onMouseOver={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 10px 15px -3px rgba(79, 70, 229, 0.3), 0 4px 6px -2px rgba(79, 70, 229, 0.15)'; }} onMouseOut={e => { e.currentTarget.style.transform = 'translateY(0)'; e.currentTarget.style.boxShadow = '0 4px 6px -1px rgba(79, 70, 229, 0.2), 0 2px 4px -1px rgba(79, 70, 229, 0.1)'; }}>
                <FiCheckCircle size={20} /> Save & Update Tracker
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="analytics-header">
        <h1><FiActivity size={28} color="var(--primary)" /> Financial Analytics</h1>
        <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
          Real-time portfolio monitoring • <span style={{ color: 'var(--success)', fontWeight: 600 }}>Sync Active</span>
        </div>
      </div>

      {/* ── Performance Section with Period Selector ── */}
      <div className="ops-section" style={{ marginBottom: '2.5rem' }}>
        <div className="perf-section-header">
          <div className="chart-title" style={{ marginBottom: 0 }}>
            <FiActivity /> Performance
            <span className="click-hint">Click any card for details</span>
          </div>
          <PeriodSelector
            period={period} setPeriod={setPeriod}
            customStart={customStart} setCustomStart={setCustomStart}
            customEnd={customEnd} setCustomEnd={setCustomEnd}
          />
        </div>

        {perfLoading ? (
          <div className="perf-loading">
            <div className="detail-spinner" style={{ width: 28, height: 28, borderWidth: 2 }} />
            <span>Loading {periodLabel} data...</span>
          </div>
        ) : (
          <div className="perf-grid">
            <StatCard label="Amount Disbursed" value={ps.disbursed} sublabel={`${ps.disbursed_count || 0} loans`}
              icon={<FiArrowRight size={20} />} color="#4f46e5" bgColor="#eef2ff" onClick={() => openDetail("disbursed_today")} />
            <StatCard label="Interest Collected" value={ps.interest_collected} sublabel="Direct income"
              icon={<FiPercent size={20} />} color="#10b981" bgColor="#ecfdf5" onClick={() => openDetail("interest_collected")} />
            <StatCard label="Principal Collected" value={ps.principle_collected} sublabel="Principal repayments"
              icon={<FiDollarSign size={20} />} color="#6366f1" bgColor="#f0f0ff" onClick={() => openDetail("principle_collected")} />
            <StatCard label="Total Collected" value={ps.total_collected} sublabel={`${ps.collected_count || 0} transactions`}
              icon={<FiCheckCircle size={20} />} color="#0ea5e9" bgColor="#f0f9ff" onClick={() => openDetail("total_collected")} />
            <StatCard label="New Loans" value={ps.new_loans} sublabel={fmtCur(ps.disbursed) + " disbursed"}
              icon={<FiPlus size={20} />} color="#f59e0b" bgColor="#fffbeb" onClick={() => openDetail("new_loans")} isCount />
            <StatCard label="Compounded Principal" value={ps.compounded} sublabel={`${ps.compounded_count || 0} loans`}
              icon={<FiRefreshCw size={20} />} color="#6366f1" bgColor="#f0f0ff" onClick={() => openDetail("compounded")} />
            <StatCard label="Gold Collected" value={ps.gold_collected} sublabel="Weight released"
              icon={<FiAward size={20} />} color="#d97706" bgColor="#fffbeb" onClick={() => openDetail("gold_collected")} isWeight />
            <StatCard label="Closures" value={ps.closures} sublabel="Accounts settled"
              icon={<FiBox size={20} />} color="#ef4444" bgColor="#fef2f2" onClick={() => openDetail("closures")} isCount />
          </div>
        )}
      </div>

      {/* ── Admin Section ── */}
      {isAdmin && adminSummary && (
        <div className="admin-kpi-section">
          <div className="chart-title" style={{ marginBottom: '1.5rem' }}>
            <FiBarChart2 /> Admin Overview
            <span className="click-hint">Click any card for details</span>
          </div>
          <div className="perf-grid">
            <StatCard label="Principal Remaining" value={adminSummary.principle_remaining} sublabel="Across all open loans"
              icon={<FiDollarSign size={20} />} color="#4f46e5" bgColor="#eef2ff" onClick={() => openDetail("principle_remaining", true)} />
            <StatCard label="Given Principal" value={adminSummary.given_principle} sublabel="Total ever disbursed"
              icon={<FiBriefcase size={20} />} color="#10b981" bgColor="#ecfdf5" onClick={() => openDetail("given_principle", true)} />
            <StatCard label="Compounded Principal" value={adminSummary.compounded_principle} sublabel="Interest added to principal"
              icon={<FiRefreshCw size={20} />} color="#f59e0b" bgColor="#fffbeb" onClick={() => openDetail("compounded_principle", true)} />
            <StatCard label="Interest Remaining" value={adminSummary.interest_remaining} sublabel="Pending across all loans"
              icon={<FiPercent size={20} />} color="#0ea5e9" bgColor="#f0f9ff" onClick={() => openDetail("interest_remaining", true)} />
            <StatCard label="Inactive Accounts" value={adminSummary.inactive_accounts} sublabel="No payment > 90 days"
              icon={<FiUsers size={20} />} color="#ef4444" bgColor="#fef2f2" onClick={() => openDetail("inactive_accounts", true)} isCount />
          </div>
        </div>
      )}

      {/* ── Charts + Sidebar ── */}
      <div className="dashboard-grid">
        <div className="main-feed">
          <div className="chart-container">
            <div className="chart-title"><FiTrendingUp /> Portfolio Growth Trend</div>
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={trends}>
                <defs>
                  <linearGradient id="colorPrimary" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--primary)" stopOpacity={0.1} />
                    <stop offset="95%" stopColor="var(--primary)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border-subtle)" />
                <XAxis dataKey="month" axisLine={false} tickLine={false} tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                <YAxis axisLine={false} tickLine={false} tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                <Tooltip contentStyle={{ borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)', boxShadow: 'var(--shadow-lg)' }} />
                <Area type="monotone" dataKey="disbursed" stroke="var(--primary)" fillOpacity={1} fill="url(#colorPrimary)" name="Disbursement" strokeWidth={3} />
                <Area type="monotone" dataKey="collected" stroke="var(--success)" fillOpacity={0} name="Collection" strokeWidth={3} />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="ops-section" style={{ marginTop: '2rem' }}>
            <div className="chart-title"><FiActivity /> Recent Activity</div>
            <div className="feed-container">
              {recent_transactions.map((tx, idx) => {
                const getTxDetails = (type) => {
                  switch (type) {
                    case 'addColl': return { label: 'Payment', color: '#10b981', bg: '#ecfdf5', icon: <FiCheckCircle /> };
                    case 'newLoan': return { label: 'Disbursement', color: '#4f46e5', bg: '#eef2ff', icon: <FiPlus /> };
                    case 'compounding': return { label: 'Compounding', color: '#f59e0b', bg: '#fffbeb', icon: <FiRefreshCw /> };
                    case 'closure': return { label: 'Closure', color: '#6366f1', bg: '#f5f3ff', icon: <FiBox /> };
                    default: return { label: 'Adjustment', color: '#6b7280', bg: '#f3f4f6', icon: <FiArrowRight /> };
                  }
                };
                const ui = getTxDetails(tx.transactiontype);
                const isPositive = tx.transactiontype === 'addColl';
                
                return (
                  <div key={idx} className="tx-item" style={{ 
                    borderBottom: idx === recent_transactions.length - 1 ? 'none' : '1px solid var(--border-subtle)',
                    padding: '1rem 0'
                  }}>
                    <div className="tx-icon-circle" style={{ background: ui.bg, color: ui.color }}>
                      {ui.icon}
                    </div>
                    <div className="tx-details" style={{ flex: 1, marginLeft: '1rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '2px' }}>
                        <h4 style={{ margin: 0, fontSize: '0.875rem', fontWeight: 600 }}>{tx.customername}</h4>
                        <span style={{ 
                          fontSize: '0.625rem', 
                          padding: '2px 6px', 
                          borderRadius: '4px', 
                          background: ui.bg, 
                          color: ui.color,
                          fontWeight: 700,
                          textTransform: 'uppercase',
                          letterSpacing: '0.025em'
                        }}>{ui.label}</span>
                      </div>
                      <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {tx.loan_number} • {tx.particulars || 'General'} • {fmtDisplay(tx.date)}
                      </p>
                      <div style={{ marginTop: '4px', fontSize: '0.6875rem', color: 'var(--text-light)', display: 'flex', gap: '8px' }}>
                        <span>Bal: ₹{parseFloat(tx.principlebalance).toLocaleString()} P</span>
                        {parseFloat(tx.interestbalance) > 0 && <span>/ ₹{parseFloat(tx.interestbalance).toLocaleString()} I</span>}
                      </div>
                    </div>
                    <div className="tx-amount" style={{ 
                      textAlign: 'right',
                      fontWeight: 700, 
                      fontSize: '0.9375rem',
                      color: isPositive ? 'var(--success)' : 'var(--text-main)' 
                    }}>
                      {isPositive ? '+' : ''}₹{parseFloat(tx.amountpaid || Math.abs(tx.currentprincipal)).toLocaleString()}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <div className="side-feed">
          <div style={{ background: 'linear-gradient(135deg, #fbbf24, #d97706)', padding: '1.5rem', borderRadius: 'var(--radius-lg)', color: 'white', marginBottom: '2rem', boxShadow: '0 10px 15px -3px rgba(217,119,6,0.2)' }}>
            <div className="chart-title" style={{ color: 'white', marginBottom: '1rem' }}><FiAward /> Gold Price Monitor</div>
            <p style={{ fontSize: '2rem', fontWeight: '800', margin: 0 }}>₹{gold_price.current}/g</p>
            <p style={{ fontSize: '0.8125rem', margin: '4px 0', opacity: 0.9 }}>Market Trend: {gold_price.change}</p>
          </div>



          <h2 className="section-title" style={{ marginTop: '2rem', marginBottom: '1rem' }}>Quick Actions</h2>
          <div className="quick-actions">
            <button className="action-btn" onClick={() => navigate('/newcustomer')}><FiPlus /> New Loan</button>
            <button className="action-btn" onClick={() => navigate('/userlist')}><FiDollarSign /> Collection</button>
            <button className="action-btn" onClick={() => navigate('/userlist')}><FiSearch /> Customer</button>
            <button className="action-btn" onClick={() => navigate('/report')}><FiFileText /> Report</button>
          </div>

          <div className="ops-section" style={{ marginTop: '2rem', padding: '1.5rem' }}>
            <div className="chart-title" style={{ color: 'var(--danger)', fontSize: '1.05rem', marginBottom: '1.25rem' }}>
              <FiAlertTriangle /> Overdue Tracker
              <span className="click-hint" style={{ color: 'var(--text-muted)', marginLeft: 'auto' }}>{overdueLoans.length}</span>
            </div>
            <div className="feed-container overdue-feed" style={{ maxHeight: '400px', overflowY: 'auto', paddingRight: '8px' }}>
              {overdueLoans.length === 0 ? (
                <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                  <FiCheckCircle size={24} style={{ color: 'var(--success)', marginBottom: '0.5rem' }} />
                  <p style={{ fontSize: '0.8rem', margin: 0 }}>All clear today!</p>
                </div>
              ) : (
                overdueLoans.map((loan, idx) => {
                  const isFollowedUp = loan.follow_up_date && loan.follow_up_date > today();
                  return (
                  <div key={idx} className="tx-item overdue-item clickable-card" onClick={() => handleOverdueClick(loan)} style={{ 
                    borderBottom: idx === overdueLoans.length - 1 ? 'none' : '1px solid var(--border-subtle)',
                    padding: '0.75rem 0', cursor: 'pointer', borderRadius: 'var(--radius-md)', transition: 'background 0.2s', display: 'flex', alignItems: 'center',
                    opacity: isFollowedUp ? 0.7 : 1
                  }} onMouseOver={e => e.currentTarget.style.background = 'var(--bg-secondary)'} onMouseOut={e => e.currentTarget.style.background = 'transparent'}>
                    <div className="tx-icon-circle" style={{ background: isFollowedUp ? '#e0f2fe' : '#fef2f2', color: isFollowedUp ? '#0284c7' : '#ef4444', minWidth: '32px', minHeight: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '50%', fontSize: '0.875rem' }}>
                      {isFollowedUp ? <FiCheckCircle /> : <FiClock />}
                    </div>
                    <div className="tx-details" style={{ flex: 1, marginLeft: '0.75rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', marginBottom: '2px' }}>
                        <h4 style={{ margin: 0, fontSize: '0.875rem', fontWeight: 600 }}>{loan.customername}</h4>
                      </div>
                      <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {loan.loan_number} • {loan.tenure}M
                      </p>
                      {isFollowedUp && <span style={{ display: 'inline-block', marginTop: '4px', fontSize: '0.65rem', background: '#e0f2fe', color: '#0284c7', padding: '2px 6px', borderRadius: '4px', fontWeight: 600 }}>Followed-up: {fmtDisplay(loan.follow_up_date.split("T")[0])}</span>}
                    </div>
                    <div className="tx-amount" style={{ textAlign: 'right', fontWeight: 700, fontSize: '0.875rem', color: isFollowedUp ? 'var(--text-muted)' : 'var(--primary)' }}>
                      ₹{parseFloat(loan.refreshprincipleamount || 0).toLocaleString()}
                    </div>
                  </div>
                )})
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Analytics;
