import { useState } from "react";
import { Link } from "react-router-dom";
import { dashboard, loans } from "../../api/endpoints.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { useAsync, useDocumentTitle } from "../../hooks/useAsync.js";
import { addDays, formatDateTime, formatDay, todayIST } from "../../lib/dates.js";
import { entryLabel } from "../../lib/ledger.js";
import { formatGrams, formatINR } from "../../lib/money.js";
import { can } from "../../lib/permissions.js";
import { BarList, ColumnChart } from "../../ui/charts.jsx";
import { Button } from "../../ui/controls.jsx";
import { DataTable } from "../../ui/DataTable.jsx";
import { EmptyState, ErrorState, SkeletonRows, useToast } from "../../ui/feedback.jsx";
import { DateField } from "../../ui/fields.jsx";
import { Modal } from "../../ui/Modal.jsx";
import { Banner, Card, PageHeader, Pill } from "../../ui/surfaces.jsx";
import { CustomerLink } from "../shared/links.jsx";
import { PerformancePanel } from "./PerformancePanel.jsx";

function Kpi({ label, value, meta }) {
  return (
    <div className="kpi">
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
      {meta ? <span className="kpi-meta">{meta}</span> : null}
    </div>
  );
}

function FollowUpDialog({ loan, onClose, onSaved }) {
  const toast = useToast();
  const [date, setDate] = useState(loan.follow_up_date ?? addDays(todayIST(), 7));
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const save = async (value) => {
    setPending(true);
    try {
      await loans.setFollowUp(loan.loan_number, value);
      toast.success(value ? "Follow-up scheduled" : "Follow-up cleared", `${loan.customer_name} · ${loan.loan_number}`);
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  };
  return (
    <Modal open onClose={onClose} busy={pending} title={`Follow up · ${loan.loan_number}`}
      description={`${loan.customer_name}, ${loan.phone}. Due ${formatDay(loan.due_date)}.`}
      footer={
        <>
          {loan.follow_up_date ? <Button onClick={() => save(null)} disabled={pending}>Clear follow-up</Button> : null}
          <Button variant="primary" loading={pending} onClick={() => (date ? save(date) : setError("Choose a date."))}>Save</Button>
        </>
      }>
      <DateField label="Next follow-up" value={date} min={todayIST()} onChange={(e) => setDate(e.target.value)} error={error} data-autofocus />
    </Modal>
  );
}

export default function DashboardPage() {
  useDocumentTitle("Dashboard");
  const { user, branch } = useAuth();
  const { data, error, loading, loadedAt, reload } = useAsync((signal) => dashboard.summary(branch, { signal }), [branch]);
  const [followUp, setFollowUp] = useState(null);

  if (error) return <div className="page"><ErrorState error={error} onRetry={reload} /></div>;
  if (!data) return <div className="page"><SkeletonRows rows={8} label="Loading dashboard" /></div>;

  const { portfolio, today, trends, recent, counts } = data;
  const scope = branch ? `Branch ${branch}` : user.is_head_office ? "All branches" : `Branch ${user.branch}`;

  const overdueColumns = [
    { key: "loan_number", header: "Loan", render: (l) => <CustomerLink customerId={l.customer_id}>{l.loan_number}</CustomerLink> },
    { key: "customer_name", header: "Customer" },
    { key: "phone", header: "Phone", render: (l) => <a href={`tel:${l.phone}`} className="num">{l.phone}</a> },
    { key: "due_date", header: "Due", render: (l) => `${formatDay(l.due_date)} (${l.days_overdue} days ago)` },
    { key: "total", header: "Due today", numeric: true, render: (l) => formatINR(l.total) },
    {
      key: "follow",
      header: "Follow-up",
      render: (l) => (
        <span className="cluster cluster-sm">
          {l.followed_up ? <Pill tone="info">{formatDay(l.follow_up_date)}</Pill> : <Pill tone="warning">Not scheduled</Pill>}
          {can(user, "userlist") ? (
            <Button size="sm" variant="ghost" onClick={() => setFollowUp(l)}>{l.followed_up ? "Change" : "Schedule"}</Button>
          ) : null}
        </span>
      ),
    },
  ];

  return (
    <div className="page" aria-busy={loading}>
      <PageHeader title="Dashboard" description={`${scope} · as of ${formatDay(portfolio.as_of)}`}
        actions={can(user, "userlist") ? <Button icon="search" to="/customers">Find a customer</Button> : null} />
      <div className="stack stack-lg">
        {!portfolio.gold_rate && user.is_head_office ? (
          <Banner tone="warning" title="Today's gold rate isn't set">
            <p>Loan-to-value figures need it. <Link to="/settings">Set the gold rate</Link>.</p>
          </Banner>
        ) : null}

        <section aria-labelledby="portfolio-heading" className="stack">
          <h2 id="portfolio-heading">Portfolio</h2>
          <div className="grid grid-tight">
            <Kpi label="Open loans" value={portfolio.open_loans.toLocaleString("en-IN")} meta={`${counts.customers.toLocaleString("en-IN")} customers · ${counts.closed_loans.toLocaleString("en-IN")} closed`} />
            <Kpi label="Principal outstanding" value={formatINR(portfolio.principal)} />
            <Kpi label="Interest due" value={formatINR(portfolio.interest)} meta="If every loan were settled today" />
            <Kpi label="Gold held" value={formatGrams(portfolio.net_weight)} meta={portfolio.ltv ? `Loan-to-value ${portfolio.ltv} %` : "Set the gold rate to see loan-to-value"} />
            <Kpi label="Collected today" value={formatINR(today.total_collected)} meta={`${today.collections} payment${today.collections === 1 ? "" : "s"}`} />
            <Kpi label="Disbursed today" value={formatINR(today.disbursed)} meta={`${today.new_loans} new loan${today.new_loans === 1 ? "" : "s"}`} />
          </div>
        </section>

        <PerformancePanel branch={branch} />

        <div className="grid">
          <Card title="Disbursed and collected">
            <ColumnChart
              title="Disbursed and collected by month, last six months"
              series={[
                { key: "disbursed", label: "Disbursed", color: "var(--color-chart-1)" },
                { key: "collected", label: "Collected", color: "var(--color-chart-2)" },
              ]}
              data={trends.map((t) => ({ label: t.label.split(" ")[0], disbursed: t.disbursed, collected: t.collected }))}
            />
          </Card>
          <Card title="Time since last payment">
            <BarList title="Open loans by days since the last payment" rows={portfolio.aging.map((a) => ({ label: a.bucket, value: a.loans }))}
              format={(v) => `${v} loan${v === 1 ? "" : "s"}`} />
            {portfolio.inactive.length ? (
              <p className="field-hint">{portfolio.inactive.length} loan{portfolio.inactive.length === 1 ? " has" : "s have"} had no payment for over 90 days.</p>
            ) : null}
          </Card>
        </div>

        {user.is_head_office && !branch && portfolio.branches.length > 1 ? (
          <Card title="Outstanding by branch">
            <BarList title="Principal outstanding by branch" rows={portfolio.branches.map((b) => ({ label: `${b.name} (${b.loans})`, value: b.principal }))}
              format={formatINR} />
          </Card>
        ) : null}

        <Card title={`Overdue loans (${portfolio.overdue.length})`}>
          <DataTable columns={overdueColumns} rows={portfolio.overdue.slice(0, 50)} rowKey={(l) => l.loan_number}
            caption="Loans past their tenure, not yet scheduled first"
            empty={<EmptyState icon="checkCircle" title="No overdue loans">Every open loan is within its tenure.</EmptyState>} />
        </Card>

        <Card title="Recent activity">
          {recent.length ? (
            <ul className="activity-list">
              {recent.map((r) => (
                <li key={r.id}>
                  <span>
                    <strong>{entryLabel(r.kind)}</strong> · <CustomerLink customerId={r.customer_id}>{r.customer_name}</CustomerLink>{" "}
                    <span className="muted">({r.loan_number})</span>
                  </span>
                  <span className="num">{formatINR(r.amount)}</span>
                  <span className="muted">{formatDay(r.date)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No activity yet" />
          )}
        </Card>
        <p className="field-hint">
          Figures refresh each time this page opens. Last loaded {formatDateTime(loadedAt)}.{" "}
          <Button size="sm" variant="ghost" icon="refresh" onClick={reload} loading={loading}>Refresh</Button>
        </p>
      </div>
      {followUp ? <FollowUpDialog loan={followUp} onClose={() => setFollowUp(null)} onSaved={reload} /> : null}
    </div>
  );
}
