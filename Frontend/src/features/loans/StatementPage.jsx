import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { loans } from "../../api/endpoints.js";
import { useAsync, useDocumentTitle } from "../../hooks/useAsync.js";
import { formatDateTime, formatDay, todayIST } from "../../lib/dates.js";
import { entryAmount, entryLabel, entryPrincipalPaid } from "../../lib/ledger.js";
import { formatGrams, formatINR } from "../../lib/money.js";
import { BrandMark } from "../../ui/AppShell.jsx";
import { Button } from "../../ui/controls.jsx";
import { DataTable } from "../../ui/DataTable.jsx";
import { ErrorState, SkeletonRows } from "../../ui/feedback.jsx";
import { Icon } from "../../ui/Icon.jsx";
import { Card, Details, LoanStatus, Pill } from "../../ui/surfaces.jsx";
import { LedgerCalculation } from "./LedgerCalculation.jsx";

const RECEIPT_KINDS = new Set(["addColl", "disbursement", "writeoff"]);

function formatSlashDate(isoDay) {
  if (!isoDay) return "—";
  const [y, m, d] = isoDay.split("-");
  return y && m && d ? `${d}/${m}/${y}` : formatDay(isoDay);
}

/** The letterhead header matching company identity */
export function StatementHeader({ letterhead }) {
  const name = letterhead?.legal_name || letterhead?.name || "SWATHANTRA FINANCE PRIVATE LIMITED";
  const address = letterhead?.address || "VALAMKULAM POZHIYOOR ROAD POZHIYOOR PO. PIN - 695513";
  const contact = letterhead?.email || letterhead?.phone
    ? [letterhead.email && `Email: ${letterhead.email}`, (letterhead.phone || letterhead.contact) && `Mob: ${letterhead.phone || letterhead.contact}`].filter(Boolean).join("  |  ")
    : "Email: swathantrafinance52@gmail.com  |  Mob: 8590678889";

  return (
    <header className="statement-letterhead">
      <div className="statement-logo-badge" aria-hidden="true">
        {letterhead?.logo ? (
          <img src={letterhead.logo} alt="" className="statement-logo-img" />
        ) : (
          <BrandMark />
        )}
      </div>
      <h1 className="statement-company-name">{name}</h1>
      {address ? <p className="statement-company-address">{address}</p> : null}
      {contact ? <p className="statement-company-contact">{contact}</p> : null}
    </header>
  );
}

/** Structured Loan Overview and Balances Card */
export function LoanDetailsCard({ loan, statements }) {
  const itemsCount = loan.item_count ?? (loan.items?.reduce((a, i) => a + (i.qty || 1), 0) || 1);
  const netWeight = loan.net_weight ? formatGrams(loan.net_weight) : (loan.gross_weight ? formatGrams(loan.gross_weight) : "—");

  return (
    <div className="statement-card">
      <div className="statement-card-top">
        <div className="statement-borrower">
          <div className="statement-avatar" aria-hidden="true">
            <Icon name="user" />
          </div>
          <div>
            <div className="statement-badge-label">Customer name</div>
            <h2 className="statement-badge-val">{loan.customer_name || "—"}</h2>
          </div>
        </div>
        <div className="statement-loan-id-stack">
          <div className="statement-badge-label">Loan no.</div>
          <div className="cluster cluster-sm">
            <span className="statement-badge-val">{loan.loan_number}</span>
            <LoanStatus status={loan.status} />
          </div>
        </div>
      </div>

      <div className="statement-card-section">
        <h3 className="statement-card-title">Loan details</h3>
      </div>

      <Details
        items={[
          ["Loan date", loan.date ? formatDay(loan.date) : "—"],
          ["Items", loan.items_text || (itemsCount ? `${itemsCount} item${itemsCount === 1 ? "" : "s"}` : "—")],
          ["Net weight", netWeight],
          ["Loan amount", formatINR(loan.principal)],
          ["Interest rate", loan.rate ? `${loan.rate} % p.a.` : "—"],
          ["Tenure", loan.tenure_months ? `${loan.tenure_months} months` : "—"],
          ["Principal balance", formatINR(loan.outstanding?.principal ?? loan.principal_balance ?? statements?.[0]?.principal_balance ?? "0.00")],
          ["Interest balance", formatINR(loan.outstanding?.interest ?? loan.interest_balance ?? statements?.[0]?.interest_balance ?? "0.00")],
          loan.outstanding ? ["Due today", formatINR(loan.outstanding.total)] : ["Closed on", formatDay(loan.closed_on)],
        ]}
      />
    </div>
  );
}

/** The ledger table; "Show calculation" adds how each entry was worked out (from the server). */
export function LedgerCard({ loan, statements, initiallyShown = false }) {
  const [shown, setShown] = useState(initiallyShown);
  const columns = [
    {
      key: "date",
      header: "Date",
      render: (s) => {
        const text = formatDay(s.date);
        const lastSpace = text.lastIndexOf(" ");
        const datePart = lastSpace > 0 ? text.slice(0, lastSpace) : text;
        const yearPart = lastSpace > 0 ? text.slice(lastSpace + 1) : "";
        return (
          <span className="table-date-cell" title={formatDateTime(s.at)}>
            <span className="cell-nowrap">{datePart}</span>
            {yearPart ? <> <span className="cell-nowrap">{yearPart}</span></> : null}
          </span>
        );
      },
    },
    {
      key: "kind",
      header: "Entry",
      render: (s) => (
        <span className="cluster cluster-sm table-entry-cell">
          <span>{entryLabel(s.kind)}</span>
          {s.legacy ? <Pill>Earlier system</Pill> : null}
        </span>
      ),
    },
    { key: "amount", header: "Amount", numeric: true, render: (s) => formatINR(entryAmount(s)) },
    { key: "interest", header: "Interest paid", numeric: true, render: (s) => (s.kind === "addColl" ? formatINR(s.interest_paid) : "—") },
    { key: "principal_paid", header: "Principal paid", numeric: true, render: (s) => (s.kind === "addColl" ? formatINR(entryPrincipalPaid(s)) : "—") },
    { key: "principal_balance", header: "Principal balance", numeric: true, render: (s) => formatINR(s.principal_balance) },
    { key: "interest_balance", header: "Interest balance", numeric: true, render: (s) => formatINR(s.interest_balance) },
    {
      key: "receipt",
      header: <span className="visually-hidden">Receipt</span>,
      headerText: "Receipt",
      className: "no-print table-col-action",
      render: (s) =>
        RECEIPT_KINDS.has(s.kind) && !s.legacy ? (
          <Link to={`/print/entry/${s.id}`} className="icon-btn" aria-label={`Print receipt for ${entryLabel(s.kind).toLowerCase()} on ${formatDay(s.date)}`}>
            <Icon name="printer" />
          </Link>
        ) : null,
    },
  ];
  return (
    <Card title="Ledger"
      actions={
        <>
          <span className="muted">Newest first</span>
          <Button size="sm" icon="calculator" className="no-print" aria-pressed={shown} onClick={() => setShown((v) => !v)}>
            Show calculation
          </Button>
        </>
      }>
      <DataTable columns={columns} rows={statements} rowKey={(s) => s.id} caption={`${statements.length} entries for loan ${loan.loan_number}`}
        detail={shown ? (s) => <LedgerCalculation calculation={s.calculation} entry={s} /> : undefined} />
    </Card>
  );
}

export default function StatementPage() {
  const { loanNumber } = useParams();
  const { data, error, reload } = useAsync((signal) => loans.get(loanNumber, { signal }), [loanNumber]);
  useDocumentTitle(`Loan statement – ${loanNumber}`);

  if (error) return <div className="page narrow"><ErrorState error={error} onRetry={error.status === 404 ? undefined : reload} /></div>;
  if (!data) return <div className="page"><SkeletonRows rows={8} label="Loading statement" /></div>;
  const { loan, statements, letterhead } = data;

  return (
    <div className="page">
      <header className="statement-topbar no-print">
        <Link
          className="statement-back-btn"
          to={`/customers/${loan.customer_id}`}
          aria-label={`Back to ${loan.customer_name}`}
        >
          <span className="statement-back-circle" aria-hidden="true">
            <Icon name="arrowLeft" />
          </span>
          <span>Back</span>
        </Link>
        <h1 className="statement-topbar-title">Statement</h1>
        <div className="statement-topbar-actions">
          <Button icon="printer" onClick={() => window.print()}>Print statement</Button>
        </div>
      </header>
      <div className="statement-document stack">
        <div className="print-only">
          <StatementHeader letterhead={letterhead} />
          <div className="statement-title-bar">
            <div className="statement-title-left">
              <span className="statement-accent-bar" aria-hidden="true" />
              <h2 className="statement-doc-heading">Loan Account Statement</h2>
            </div>
            <div className="statement-title-date">
              Date: {formatSlashDate(todayIST())}
            </div>
          </div>
        </div>
        <LoanDetailsCard loan={loan} statements={statements} />
        <LedgerCard loan={loan} statements={statements} />
      </div>
    </div>
  );
}
