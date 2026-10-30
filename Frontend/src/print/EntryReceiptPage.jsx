import { useRef } from "react";
import { useParams } from "react-router-dom";
import { receipts } from "../api/endpoints.js";
import { useAsync, useDocumentTitle } from "../hooks/useAsync.js";
import { formatDay } from "../lib/dates.js";
import { formatINR, toPaise, fromPaise } from "../lib/money.js";
import { ErrorState, PageLoading } from "../ui/feedback.jsx";
import { CutLine, PrintToolbar, Sheet } from "./printing.jsx";
import { ShareReceiptButton } from "./ShareReceipt.jsx";

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
        !closed && entry.kind === "addColl" && entry.in_first_week ? ["First 7 days", "Payment goes to principal"] : null,
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

/** One copy of the entry receipt, used by the screen, the printout and the shared PDF. */
export function entrySheet(data, copy) {
  const { entry, loan, customer, letterhead } = data;
  const detail = describe(data);
  return {
    copy,
    letterhead,
    title: `${detail.title} · ${copy} copy`,
    date: entry.date,
    fields: [
      ["Loan number", loan.loan_number],
      ["Customer", `${customer.name} (${customer.customer_number})`],
      ["Phone", customer.phone],
      ["Entry date", formatDay(entry.date)],
      ["Loan date", formatDay(loan.date)],
      ["Interest rate", `${loan.rate} % p.a.`],
      entry.accrued_days !== null ? ["Interest days this period", entry.accrued_days] : null,
      ["Receipt number", `R${entry.receipt_no ?? entry.id}`],
      ...detail.rows,
    ].filter(Boolean),
    total: detail.total ? { label: detail.total[0], value: formatINR(detail.total[1]) } : null,
    terms: false,
    signatures: { left: copy === "Office" ? "Customer signature" : "Received by", right: "Authorised signatory" },
  };
}

export default function EntryReceiptPage() {
  const { statementId } = useParams();
  const { data, error, reload } = useAsync((signal) => receipts.entry(statementId, { signal }), [statementId]);
  const customerCopy = useRef(null);
  useDocumentTitle("Receipt");
  return (
    <div className="print-page">
      <PrintToolbar title={data ? `${describe(data).title} · ${data.loan.loan_number}` : "Receipt"}>
        <ShareReceiptButton
          sheet={data ? entrySheet(data, "Customer") : null}
          styleSource={customerCopy}
          fileName={data ? `Receipt-R${data.entry.receipt_no ?? data.entry.id}-${data.loan.loan_number}.pdf` : ""}
          title={data ? describe(data).title : "Receipt"}
          phone={data?.customer.phone}
        />
      </PrintToolbar>
      {error ? <ErrorState error={error} onRetry={reload} /> : !data ? <PageLoading /> : (
        <div className="sheets">
          <Sheet sheet={entrySheet(data, "Office")} />
          <CutLine />
          <Sheet ref={customerCopy} sheet={entrySheet(data, "Customer")} />
        </div>
      )}
    </div>
  );
}
