import { dashboard } from "../../api/endpoints.js";
import { useAsync } from "../../hooks/useAsync.js";
import { formatDay } from "../../lib/dates.js";
import { formatGrams, formatINR } from "../../lib/money.js";
import { DataTable } from "../../ui/DataTable.jsx";
import { EmptyState, ErrorState, SkeletonRows } from "../../ui/feedback.jsx";
import { Modal } from "../../ui/Modal.jsx";
import { Banner, Pill } from "../../ui/surfaces.jsx";
import { LoanLink } from "../shared/links.jsx";

export const METRICS = {
  disbursed: { title: "Disbursed", value: (t) => formatINR(t.disbursed), meta: (t) => `${t.new_loans} new loan${t.new_loans === 1 ? "" : "s"} and top-ups` },
  total_collected: { title: "Collected", value: (t) => formatINR(t.total_collected), meta: (t) => `${t.collections} payment${t.collections === 1 ? "" : "s"}` },
  interest_collected: { title: "Interest collected", value: (t) => formatINR(t.interest_collected) },
  principal_collected: { title: "Principal repaid", value: (t) => formatINR(t.principal_collected) },
  closures: { title: "Loans closed", value: (t) => t.closures.toLocaleString("en-IN"), meta: (t) => `${formatGrams(t.gold_released)} gold returned` },
  compounded: { title: "Interest compounded", value: (t) => formatINR(t.compounded), meta: (t) => `${t.compounded_loans} loan${t.compounded_loans === 1 ? "" : "s"}` },
  written_off: { title: "Written off", value: (t) => formatINR(t.written_off) },
  gold_pledged: { title: "Gold pledged", value: (t) => formatGrams(t.gold_pledged) },
};

const loanLink = { key: "loan_number", header: "Loan", render: (r) => <LoanLink loanNumber={r.loan_number} /> };
const customer = { key: "customer_name", header: "Customer" };
const branch = { key: "branch", header: "Branch" };
const date = { key: "date", header: "Date", render: (r) => formatDay(r.date) };
const money = (key, header) => ({ key, header, numeric: true, render: (r) => formatINR(r[key]) });

const COLUMNS = {
  disbursed: [date, loanLink, customer, { key: "kind", header: "Type" }, money("amount", "Amount"), branch],
  collections: [date, loanLink, customer, money("amount", "Paid"), money("interest", "Interest"), money("principal", "Principal"), branch],
  compounded: [date, loanLink, customer, money("amount", "Interest added"), money("new_principal", "New principal"), branch],
  written_off: [date, loanLink, customer, { ...money("amount", "Written off"), render: (r) => (
    <span className="cluster cluster-sm">{formatINR(r.amount)}{r.legacy ? <Pill>Earlier system</Pill> : null}</span>
  ) }, branch],
  loans: [date, loanLink, customer, money("principal", "Loan amount"), { key: "net_weight", header: "Net weight", numeric: true, render: (r) => formatGrams(r.net_weight) }, branch],
};
const COLUMN_SET = {
  disbursed: "disbursed", total_collected: "collections", interest_collected: "collections", principal_collected: "collections",
  compounded: "compounded", written_off: "written_off", closures: "loans", gold_pledged: "loans", gold_released: "loans", new_loans: "loans",
};

export function DetailDialog({ metric, period, branch, onClose }) {
  const { data, error, reload } = useAsync(
    (signal) => dashboard.details(metric, { branch, from: period.from, to: period.to }, { signal }),
    [metric, branch, period.from, period.to],
  );
  const title = METRICS[metric]?.title ?? "Details";
  const range = period.from === period.to ? formatDay(period.from) : `${formatDay(period.from)} – ${formatDay(period.to)}`;
  return (
    <Modal open size="lg" title={title} description={range} onClose={onClose}>
      {error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !data ? (
        <SkeletonRows rows={4} label={`Loading ${title.toLowerCase()}`} />
      ) : (
        <div className="stack">
          {data.truncated ? <Banner tone="info">Showing the latest 1,000 entries. Narrow the period to see everything.</Banner> : null}
          <DataTable columns={COLUMNS[COLUMN_SET[metric]]} rows={data.rows} caption={`${data.rows.length} row${data.rows.length === 1 ? "" : "s"}`}
            empty={<EmptyState title="Nothing in this period" />} />
        </div>
      )}
    </Modal>
  );
}
