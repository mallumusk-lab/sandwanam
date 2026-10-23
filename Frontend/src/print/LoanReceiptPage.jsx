import { useRef } from "react";
import { useParams } from "react-router-dom";
import { receipts } from "../api/endpoints.js";
import { useAsync, useDocumentTitle } from "../hooks/useAsync.js";
import { formatDay } from "../lib/dates.js";
import { formatGrams, formatINR } from "../lib/money.js";
import { ErrorState, PageLoading } from "../ui/feedback.jsx";
import { CutLine, PrintToolbar, Sheet } from "./printing.jsx";
import { ShareReceiptButton } from "./ShareReceipt.jsx";

/** One copy of the loan voucher, used by the screen, the printout and the shared PDF. */
export function loanSheet(data, copy) {
  const { loan, customer, letterhead, printed_on: printedOn } = data;
  return {
    copy,
    letterhead,
    title: `Loan voucher · ${copy} copy`,
    date: printedOn,
    fields: [
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
    ],
    total: { label: "Loan amount", value: formatINR(loan.principal) },
    terms: true,
    signatures: { left: "Customer signature", right: "Authorised signatory" },
  };
}

export default function LoanReceiptPage() {
  const { loanNumber } = useParams();
  const { data, error, reload } = useAsync((signal) => receipts.loan(loanNumber, { signal }), [loanNumber]);
  const customerCopy = useRef(null);
  useDocumentTitle(`Loan voucher ${loanNumber}`);
  return (
    <div className="print-page">
      <PrintToolbar title={`Loan voucher · ${loanNumber}`}>
        <ShareReceiptButton
          sheet={data ? loanSheet(data, "Customer") : null}
          styleSource={customerCopy}
          fileName={data ? `Loan-voucher-${data.loan.loan_number}.pdf` : ""}
          title="Loan voucher"
          phone={data?.customer.phone}
        />
      </PrintToolbar>
      {error ? <ErrorState error={error} onRetry={reload} /> : !data ? <PageLoading /> : (
        <div className="sheets">
          <Sheet sheet={loanSheet(data, "Office")} />
          <CutLine />
          <Sheet ref={customerCopy} sheet={loanSheet(data, "Customer")} />
        </div>
      )}
    </div>
  );
}
