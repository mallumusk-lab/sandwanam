import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { customers } from "../../api/endpoints.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { useAsync, useDocumentTitle } from "../../hooks/useAsync.js";
import { formatDay } from "../../lib/dates.js";
import { formatGrams, formatINR } from "../../lib/money.js";
import { CREATE, can } from "../../lib/permissions.js";
import { Button } from "../../ui/controls.jsx";
import { EmptyState, ErrorState, SkeletonRows } from "../../ui/feedback.jsx";
import { Icon } from "../../ui/Icon.jsx";
import { Banner, Card, Details, LoanStatus, Pill } from "../../ui/surfaces.jsx";
import { FollowUpDialog } from "../shared/FollowUpDialog.jsx";
import { CloseLoanDialog, EditItemsDialog, PostingDialog } from "./LoanDialogs.jsx";

function LoanCard({ loan, user, onAction }) {
  const open = loan.status === "open";
  const owed = loan.outstanding;
  const editable = can(user, CREATE);
  return (
    <Card as="article" className="loan-card" headingLevel={3}
      title={
        <span>
          Loan {loan.loan_number}
          <span className="loan-meta">
            <LoanStatus status={loan.status} />
            <span>Opened {formatDay(loan.date)}</span>
            {loan.closed_on ? <span>· Closed {formatDay(loan.closed_on)}</span> : null}
          </span>
        </span>
      }
      actions={<Button size="sm" icon="file" to={`/loans/${encodeURIComponent(loan.loan_number)}`}>Statement</Button>}>
      <Details
        items={[
          ["Items", `${loan.items_text} · ${loan.item_count} item${loan.item_count === 1 ? "" : "s"}`],
          ["Net weight", `${formatGrams(loan.net_weight)} (gross ${formatGrams(loan.gross_weight)})`],
          ["Loan amount", formatINR(loan.principal)],
          ["Interest rate", `${loan.rate} % p.a.`],
          ["Tenure", `${loan.tenure_months} months`],
          loan.follow_up_date ? ["Follow-up", `${formatDay(loan.follow_up_date)}${loan.follow_up_set ? "" : " (automatic)"}`] : null,
        ]}
      />
      {open && owed ? (
        <dl className="outstanding" aria-label={`Amount due today on loan ${loan.loan_number}`}>
          <div><dt>Principal</dt><dd>{formatINR(owed.principal)}</dd></div>
          <div><dt>Interest due</dt><dd>{formatINR(owed.interest)}</dd></div>
          <div><dt>Total due today</dt><dd>{formatINR(owed.total)}</dd></div>
        </dl>
      ) : null}
      <div className="loan-actions">
        {open ? (
          <>
            <Button size="sm" variant="primary" icon="rupee" onClick={() => onAction("collect", loan)}>Record payment</Button>
            {editable ? <Button size="sm" icon="plus" onClick={() => onAction("topup", loan)}>Add principal</Button> : null}
            {editable ? <Button size="sm" icon="edit" onClick={() => onAction("items", loan)}>Edit items</Button> : null}
            <Button size="sm" icon="check" onClick={() => onAction("close", loan)}>Close loan</Button>
            {can(user, "userlist") ? <Button size="sm" icon="calendar" onClick={() => onAction("followup", loan)}>Follow-up</Button> : null}
          </>
        ) : null}
        <Button size="sm" variant="ghost" icon="printer" to={`/print/loan/${encodeURIComponent(loan.loan_number)}`}>Loan receipt</Button>
      </div>
    </Card>
  );
}

export default function CustomerPage() {
  const { customerId } = useParams();
  const { user } = useAuth();
  const { data, error, loading, reload } = useAsync((signal) => customers.get(customerId, { signal }), [customerId]);
  const [dialog, setDialog] = useState(null);
  useDocumentTitle(data?.customer.name ?? "Customer");

  if (error && !data) {
    return (
      <div className="page narrow">
        <ErrorState error={error} onRetry={error.status === 404 ? undefined : reload}
          title={error.status === 404 ? "Customer not found" : undefined} />
      </div>
    );
  }
  if (!data) {
    return (
      <div className="page">
        <SkeletonRows rows={6} label="Loading customer" />
      </div>
    );
  }

  const { customer, loans } = data;
  const openLoans = loans.filter((l) => l.status === "open");
  const closedLoans = loans.filter((l) => l.status !== "open");
  const close = () => setDialog(null);
  const newLoan = can(user, CREATE) ? (
    <Button variant="primary" icon="plus" to={`/customers/${customer.id}/loans/new`}>New loan</Button>
  ) : null;

  return (
    <div className="page" aria-busy={loading}>
      <header className="statement-topbar customer-topbar">
        <Link
          className="statement-back-btn"
          to="/customers"
          aria-label="Back to customers"
        >
          <span className="statement-back-circle" aria-hidden="true">
            <Icon name="arrowLeft" />
          </span>
          <span>Customers</span>
        </Link>
        <h1 className="statement-topbar-title">Customer</h1>
        <div className="statement-topbar-actions">
          {newLoan}
        </div>
      </header>
      <div className="stack stack-lg">
        {error ? (
          <Banner tone="warning" title="Couldn't refresh this page">
            <p>{error.message} <Button size="sm" variant="ghost" icon="refresh" onClick={reload}>Try again</Button></p>
          </Banner>
        ) : null}
        <div className="statement-card customer-card">
          <div className="statement-card-top">
            <div className="statement-borrower">
              <div className="statement-avatar" aria-hidden="true">
                <Icon name="user" />
              </div>
              <div>
                <div className="statement-badge-label">Borrower Name</div>
                <h2 className="statement-badge-val">{customer.name}</h2>
              </div>
            </div>
            <div className="statement-loan-id-stack">
              <div className="statement-badge-label"># Customer ID</div>
              <div className="cluster cluster-sm">
                <span className="statement-badge-val">{customer.customer_number}</span>
                <Pill>{customer.branch}</Pill>
              </div>
            </div>
          </div>

          <div className="statement-card-section">
            <h3 className="statement-card-title">Customer details</h3>
          </div>

          <Details
            items={[
              ["Phone", customer.phone || "—"],
              ["Address", customer.address || "—"],
              ["Branch", customer.branch || "—"],
              ["Open loans", `${openLoans.length} open`],
              ["Total loans", `${loans.length} total`],
            ]}
          />
        </div>
        <section className="stack" aria-labelledby="open-loans">
          <h2 id="open-loans">Open loans ({openLoans.length})</h2>
          {openLoans.length ? (
            openLoans.map((loan) => <LoanCard key={loan.loan_number} loan={loan} user={user} onAction={(type, l) => setDialog({ type, loan: l })} />)
          ) : (
            <Card><EmptyState icon="rupee" title="No open loans" action={newLoan}>Open a loan when the customer pledges gold.</EmptyState></Card>
          )}
        </section>
        {closedLoans.length ? (
          <section className="stack" aria-labelledby="closed-loans">
            <h2 id="closed-loans">Closed loans ({closedLoans.length})</h2>
            {closedLoans.map((loan) => <LoanCard key={loan.loan_number} loan={loan} user={user} onAction={() => {}} />)}
          </section>
        ) : null}
      </div>
      {dialog && (dialog.type === "collect" || dialog.type === "topup") ? (
        <PostingDialog open mode={dialog.type} loan={dialog.loan} onClose={close} onPosted={reload} />
      ) : null}
      {dialog?.type === "close" ? <CloseLoanDialog open loan={dialog.loan} onClose={close} onClosed={reload} /> : null}
      {dialog?.type === "items" ? <EditItemsDialog open loan={dialog.loan} onClose={close} onSaved={reload} /> : null}
      {dialog?.type === "followup" ? (
        <FollowUpDialog loan={{ ...dialog.loan, customer_name: customer.name, phone: customer.phone }} onClose={close} onSaved={reload} />
      ) : null}
    </div>
  );
}
