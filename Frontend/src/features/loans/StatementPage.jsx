import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { loans } from "../../api/endpoints.js";
import { useAsync, useDocumentTitle } from "../../hooks/useAsync.js";
import { formatDateTime, formatDay } from "../../lib/dates.js";
import { entryAmount, entryLabel, entryPrincipalPaid } from "../../lib/ledger.js";
import { formatGrams, formatINR } from "../../lib/money.js";
import { Button } from "../../ui/controls.jsx";
import { Icon } from "../../ui/Icon.jsx";
import { DataTable } from "../../ui/DataTable.jsx";
import { ErrorState, SkeletonRows } from "../../ui/feedback.jsx";
import { Card, Details, LoanStatus, PageHeader, Pill } from "../../ui/surfaces.jsx";
import { LedgerCalculation } from "./LedgerCalculation.jsx";

const RECEIPT_KINDS = new Set(["addColl", "disbursement", "writeoff"]);

/** The ledger table; "Show calculation" adds how each entry was worked out (from the server). */
export function LedgerCard({ loan, statements, initiallyShown = false }) {
  const [shown, setShown] = useState(initiallyShown);
  const columns = [
    { key: "date", header: "Date", render: (s) => <span title={formatDateTime(s.at)}>{formatDay(s.date)}</span> },
    {
      key: "kind",
      header: "Entry",
      render: (s) => (
        <span className="cluster cluster-sm">
          {entryLabel(s.kind)}
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
      className: "no-print",
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

export function LoanDetailsCard({ loan, statements }) {
  return (
    <Card title={<span className="cluster cluster-sm">Loan details <LoanStatus status={loan.status} /></span>}>
      <Details
        items={[
          ["Loan date", formatDay(loan.date)],
          ["Items", loan.items_text],
          ["Net weight", formatGrams(loan.net_weight)],
          ["Loan amount", formatINR(loan.principal)],
          ["Interest rate", `${loan.rate} % p.a.`],
          ["Tenure", `${loan.tenure_months} months`],
          ["Principal balance", formatINR(loan.outstanding?.principal ?? loan.principal_balance ?? statements?.[0]?.principal_balance ?? "0.00")],
          ["Interest balance", formatINR(loan.outstanding?.interest ?? loan.interest_balance ?? statements?.[0]?.interest_balance ?? "0.00")],
          loan.outstanding ? ["Due today", formatINR(loan.outstanding.total)] : ["Closed on", formatDay(loan.closed_on)],
        ]}
      />
    </Card>
  );
}

export default function StatementPage() {
  const { loanNumber } = useParams();
  const { data, error, reload } = useAsync((signal) => loans.get(loanNumber, { signal }), [loanNumber]);
  useDocumentTitle(`Statement ${loanNumber}`);

  if (error) return <div className="page narrow"><ErrorState error={error} onRetry={error.status === 404 ? undefined : reload} /></div>;
  if (!data) return <div className="page"><SkeletonRows rows={8} label="Loading statement" /></div>;
  const { loan, statements } = data;

  return (
    <div className="page">
      <PageHeader
        title={`Statement · ${loan.loan_number}`}
        description={`${loan.customer_name} (${loan.customer_number})`}
        back={{ to: `/customers/${loan.customer_id}`, label: loan.customer_name }}
        actions={<Button icon="printer" onClick={() => window.print()} className="no-print">Print statement</Button>}
      />
      <div className="stack stack-lg">
        <LoanDetailsCard loan={loan} statements={statements} />
        <LedgerCard loan={loan} statements={statements} />
      </div>
    </div>
  );
}
