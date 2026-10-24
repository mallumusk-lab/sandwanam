import { useState } from "react";
import { Link } from "react-router-dom";
import { dashboard } from "../../api/endpoints.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { useAsync, useDocumentTitle } from "../../hooks/useAsync.js";
import { formatDateTime, formatDay } from "../../lib/dates.js";
import { entryLabel } from "../../lib/ledger.js";
import { formatGrams, formatINR, fromPaise, toPaise } from "../../lib/money.js";
import { ALL_BRANCHES_LABEL, can } from "../../lib/permissions.js";
import { BarList, ColumnChart } from "../../ui/charts.jsx";
import { Button, Pagination } from "../../ui/controls.jsx";
import { DataTable } from "../../ui/DataTable.jsx";
import { EmptyState, ErrorState, SkeletonRows } from "../../ui/feedback.jsx";
import { Banner, Card, PageHeader, Pill } from "../../ui/surfaces.jsx";
import { FollowUpDialog, followUpStatus } from "../shared/FollowUpDialog.jsx";
import { CustomerLink } from "../shared/links.jsx";
import { PerformancePanel } from "./PerformancePanel.jsx";

const PAGE_SIZE = 50;

/** Every row the server sends, 50 to a page, so no follow-up or overdue loan is left out. */
function PagedTable({ rows, label, ...table }) {
  const [page, setPage] = useState(1);
  const current = Math.min(page, Math.max(1, Math.ceil(rows.length / PAGE_SIZE)));
  return (
    <>
      <DataTable {...table} rows={rows.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE)} />
      {rows.length > PAGE_SIZE ? <Pagination page={current} pageSize={PAGE_SIZE} total={rows.length} onPage={setPage} label={label} /> : null}
    </>
  );
}

function FollowUpPill({ days }) {
  const { label, tone } = followUpStatus(days);
  return <Pill tone={tone}>{label}</Pill>;
}

function Kpi({ label, value, meta }) {
  return (
    <div className="kpi">
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
      {meta ? <span className="kpi-meta">{meta}</span> : null}
    </div>
  );
}

export default function DashboardPage() {
  useDocumentTitle("Dashboard");
  const { user, branch } = useAuth();
  const { data, error, loading, loadedAt, reload } = useAsync((signal) => dashboard.summary(branch, { signal }), [branch]);
  const [followUp, setFollowUp] = useState(null);

  if (error) return <div className="page"><ErrorState error={error} onRetry={reload} /></div>;
  if (!data) return <div className="page"><SkeletonRows rows={8} label="Loading dashboard" /></div>;

  const { portfolio, trends, recent, counts } = data;
  const scope = branch ? `Branch ${branch}` : user.is_head_office ? ALL_BRANCHES_LABEL : `Branch ${user.branch}`;

  const overdueColumns = [
    { key: "loan_number", header: "Loan", render: (l) => <CustomerLink customerId={l.customer_id}>{l.loan_number}</CustomerLink> },
    { key: "customer_name", header: "Customer" },
    { key: "phone", header: "Phone", render: (l) => <a href={`tel:${l.phone}`} className="num">{l.phone}</a> },
    { key: "due_date", header: "Due", className: "cell-nowrap", render: (l) => `${formatDay(l.due_date)} (${l.days_overdue} days ago)` },
    { key: "total", header: "Due today", numeric: true, render: (l) => formatINR(l.total) },
    {
      key: "follow",
      header: "Follow-up",
      render: (l) => (
        <span className="cluster cluster-sm">
          {l.follow_up_set ? (
            <>
              <span>{formatDay(l.follow_up_date)}</span>
              <FollowUpPill days={l.follow_up_days} />
            </>
          ) : <Pill tone="warning">Not scheduled</Pill>}
          {can(user, "userlist") ? (
            <Button size="sm" variant="ghost" onClick={() => setFollowUp(l)}>{l.follow_up_set ? "Change" : "Schedule"}</Button>
          ) : null}
        </span>
      ),
    },
  ];
  const followUps = portfolio.follow_ups ?? [];
  const followUpColumns = [
    { key: "loan_number", header: "Loan", render: (l) => <CustomerLink customerId={l.customer_id}>{l.loan_number}</CustomerLink> },
    { key: "customer_name", header: "Customer" },
    { key: "phone", header: "Phone", render: (l) => <a href={`tel:${l.phone}`} className="num">{l.phone}</a> },
    {
      key: "follow_up_date",
      header: "Follow-up date",
      className: "cell-nowrap",
      render: (l) => (
        <span className="cluster cluster-sm cell-nowrap">
          <span>{`${formatDay(l.follow_up_date)}${l.follow_up_set ? "" : " (automatic)"}`}</span>
          <FollowUpPill days={l.follow_up_days} />
        </span>
      ),
    },
    { key: "total", header: "Due today", numeric: true, render: (l) => formatINR(l.total) },
    ...(can(user, "userlist")
      ? [{
          key: "change",
          header: <span className="visually-hidden">Change follow-up</span>,
          render: (l) => (
            <Button size="sm" variant="ghost" onClick={() => setFollowUp(l)}>
              Change<span className="visually-hidden"> follow-up for {l.loan_number}</span>
            </Button>
          ),
        }]
      : []),
  ];

  const overdueTotal = portfolio.overdue_total
    ? portfolio.overdue_total
    : fromPaise((portfolio.overdue ?? []).reduce((acc, l) => acc + toPaise(l.total), 0n));
  const grossWeight = portfolio.gross_weight ?? portfolio.net_weight;

  return (
    <div className="page" aria-busy={loading}>
      <PageHeader title="Dashboard" description={`${scope} · as of ${formatDay(portfolio.as_of)}`} />
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
            <Kpi
              label="Gold held"
              value={formatGrams(portfolio.net_weight)}
              meta={`Net ${formatGrams(portfolio.net_weight)} vs Gross ${formatGrams(grossWeight)}`}
            />
            <Kpi
              label="Overdue loans"
              value={portfolio.overdue.length.toLocaleString("en-IN")}
              meta={portfolio.overdue.length ? `${formatINR(overdueTotal)} total due` : "Older than 365 days"}
            />
            <Kpi
              label="Write-off amount"
              value={formatINR(portfolio.written_off || "0.00")}
              meta={portfolio.written_off_count ? `${portfolio.written_off_count} loan${portfolio.written_off_count === 1 ? "" : "s"} written off` : "Total written off"}
            />
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

        <Card title={`Follow-ups due (${followUps.length})`}>
          <PagedTable columns={followUpColumns} rows={followUps} rowKey={(l) => l.loan_number} label="Follow-up pages"
            caption={`Open loans with a follow-up in the next ${portfolio.follow_up_notice_days} days or already passed, earliest first`}
            empty={<EmptyState icon="checkCircle" title="No follow-ups due">No open loan has a follow-up in the next {portfolio.follow_up_notice_days} days.</EmptyState>} />
        </Card>

        <Card title={`Overdue loans (${portfolio.overdue.length})`}>
          <PagedTable columns={overdueColumns} rows={portfolio.overdue} rowKey={(l) => l.loan_number} label="Overdue loan pages"
            caption="Loans open for more than 365 days"
            empty={<EmptyState icon="checkCircle" title="No overdue loans">No open loan is older than 365 days.</EmptyState>} />
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
