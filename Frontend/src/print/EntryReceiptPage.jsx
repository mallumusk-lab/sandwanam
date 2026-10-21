import { useParams } from "react-router-dom";
import { receipts } from "../api/endpoints.js";
import { useAsync, useDocumentTitle } from "../hooks/useAsync.js";
import { formatDay } from "../lib/dates.js";
import { formatINR, toPaise, fromPaise } from "../lib/money.js";
import { ErrorState, PageLoading } from "../ui/feedback.jsx";
import { CutLine, Fields, Letterhead, PrintToolbar, Signatures } from "./printing.jsx";

function describe(data) {
  const { entry, loan, closing_writeoff: writeoff, is_closing: closed } = data;
  if (entry.kind === "addColl" || (entry.kind === "writeoff" && closed)) {
    const paid = entry.kind === "addColl" ? entry.amount_paid : "0.00";
    const principalPaid = entry.kind === "addColl" ? fromPaise(-toPaise(entry.principal_change)) : "0.00";
    return {
      title: closed ? "Loan closure receipt" : "Payment receipt",
      rows: [
        ["Amount received", formatINR(paid)],
        ["Towards interest", formatINR(entry.kind === "addColl" ? entry.interest_paid : "0.00")],
        ["Towards principal", formatINR(principalPaid)],
        closed && writeoff ? ["Written off", formatINR(writeoff.written_off)] : null,
        closed ? ["Items returned", loan.items_text] : ["Principal balance after payment", formatINR(entry.principal_balance)],
        closed ? null : ["Interest still due after payment", formatINR(entry.interest_balance)],
      ],
      total: ["Total received", paid],
    };
  }
  if (entry.kind === "disbursement" || entry.kind === "modify") {
    const amount = entry.kind === "disbursement" ? entry.principal_change : entry.amount_paid;
    return {
      title: "Additional principal voucher",
      rows: [
        ["Additional principal", formatINR(amount)],
        ["Principal balance now", formatINR(entry.principal_balance)],
        ["Interest due carried forward", formatINR(entry.interest_balance)],
      ],
      total: ["Amount paid to customer", amount],
    };
  }
  return { title: "Ledger entry", rows: [["Principal balance", formatINR(entry.principal_balance)]], total: null };
}

function Copy({ data, copy }) {
  const { entry, loan, customer, letterhead } = data;
  const detail = describe(data);
  return (
    <article className="sheet" aria-label={`${copy} copy`}>
      <Letterhead branch={letterhead} title={`${detail.title} · ${copy} copy`} date={entry.date} />
      <Fields
        rows={[
          ["Loan number", loan.loan_number],
          ["Customer", `${customer.name} (${customer.customer_number})`],
          ["Phone", customer.phone],
          ["Entry date", formatDay(entry.date)],
          ["Loan date", formatDay(loan.date)],
          ["Interest rate", `${loan.rate} % p.a.`],
          entry.accrued_days !== null ? ["Interest days this period", entry.accrued_days] : null,
          ["Receipt number", `R${entry.id}`],
          ...detail.rows,
        ]}
      />
      {detail.total ? (
        <div className="sheet-total">
          <span>{detail.total[0]}</span>
          <strong>{formatINR(detail.total[1])}</strong>
        </div>
      ) : null}
      <Signatures left={copy === "Office" ? "Customer signature" : "Received by"} />
    </article>
  );
}

export default function EntryReceiptPage() {
  const { statementId } = useParams();
  const { data, error, reload } = useAsync((signal) => receipts.entry(statementId, { signal }), [statementId]);
  useDocumentTitle("Receipt");
  return (
    <div className="print-page">
      <PrintToolbar title={data ? `${describe(data).title} · ${data.loan.loan_number}` : "Receipt"} />
      {error ? <ErrorState error={error} onRetry={reload} /> : !data ? <PageLoading /> : (
        <div className="sheets">
          <Copy data={data} copy="Office" />
          <CutLine />
          <Copy data={data} copy="Customer" />
        </div>
      )}
    </div>
  );
}
