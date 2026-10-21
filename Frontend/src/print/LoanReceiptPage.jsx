import { useParams } from "react-router-dom";
import { receipts } from "../api/endpoints.js";
import { useAsync, useDocumentTitle } from "../hooks/useAsync.js";
import { formatDay } from "../lib/dates.js";
import { formatGrams, formatINR } from "../lib/money.js";
import { ErrorState, PageLoading } from "../ui/feedback.jsx";
import { CutLine, Fields, Letterhead, PrintToolbar, Signatures, Terms } from "./printing.jsx";

function Copy({ data, copy }) {
  const { loan, customer, letterhead, printed_on: printedOn } = data;
  return (
    <article className="sheet" aria-label={`${copy} copy`}>
      <Letterhead branch={letterhead} title={`Loan voucher · ${copy} copy`} date={printedOn} />
      <Fields
        rows={[
          ["Loan number", loan.loan_number],
          ["Customer number", customer.customer_number],
          ["Customer", customer.name],
          ["Phone", customer.phone],
          ["Loan date", formatDay(loan.date)],
          ["Tenure", `${loan.tenure_months} months`],
          ["Items", loan.items_text],
          ["Number of items", loan.item_count],
          ["Interest rate", `${loan.rate} % p.a.`],
          ["Gross weight", formatGrams(loan.gross_weight)],
          ["Deduction", formatGrams(loan.deduction)],
          ["Net weight", formatGrams(loan.net_weight)],
        ]}
      />
      <div className="sheet-total">
        <span>Loan amount</span>
        <strong>{formatINR(loan.principal)}</strong>
      </div>
      <Terms />
      <Signatures />
    </article>
  );
}

export default function LoanReceiptPage() {
  const { loanNumber } = useParams();
  const { data, error, reload } = useAsync((signal) => receipts.loan(loanNumber, { signal }), [loanNumber]);
  useDocumentTitle(`Loan voucher ${loanNumber}`);
  return (
    <div className="print-page">
      <PrintToolbar title={`Loan voucher · ${loanNumber}`} />
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
