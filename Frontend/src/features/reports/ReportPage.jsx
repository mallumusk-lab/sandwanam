import { useEffect, useState } from "react";
import { reports } from "../../api/endpoints.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { useAsync, useDocumentTitle, useSubmit } from "../../hooks/useAsync.js";
import { formatDay, periodPreset, todayIST } from "../../lib/dates.js";
import { ENTRY_LABELS, entryAmount, entryLabel } from "../../lib/ledger.js";
import { formatINR } from "../../lib/money.js";
import { Button, Pagination, Segmented } from "../../ui/controls.jsx";
import { DataTable } from "../../ui/DataTable.jsx";
import { EmptyState, ErrorState, SkeletonRows, useToast } from "../../ui/feedback.jsx";
import { DateField, SelectField, TextField } from "../../ui/fields.jsx";
import { Banner, Card, PageHeader } from "../../ui/surfaces.jsx";
import { LoanLink } from "../shared/links.jsx";

const PRINT_LIMIT = 200; // the API's largest page; longer periods are exported as CSV

const PAGE_SIZE = 50;
const PRESETS = [
  { value: "today", label: "Today" },
  { value: "week", label: "7 days" },
  { value: "month", label: "This month" },
  { value: "custom", label: "Custom" },
];
const KINDS = Object.entries(ENTRY_LABELS);

export default function ReportPage() {
  useDocumentTitle("Reports");
  const { branch } = useAuth();
  const toast = useToast();
  const today = todayIST();
  const [preset, setPreset] = useState("today");
  const [custom, setCustom] = useState(periodPreset("month", today));
  const [kind, setKind] = useState("");
  const [term, setTerm] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const period = preset === "custom" ? custom : periodPreset(preset, today);
  const valid = period.from && period.to && period.from <= period.to && period.to <= today;

  useEffect(() => {
    const timer = setTimeout(() => setSearch(term.trim()), 300);
    return () => clearTimeout(timer);
  }, [term]);
  useEffect(() => setPage(1), [branch, period.from, period.to, kind, search]);

  const query = { branch, from: period.from, to: period.to, kind, q: search };
  const { data, error, loading, reload } = useAsync(
    (signal) => (valid ? reports.transactions({ ...query, page, page_size: PAGE_SIZE }, { signal }) : Promise.resolve(null)),
    [branch, period.from, period.to, kind, search, page, valid],
    `${branch}|${period.from}|${period.to}|${kind}|${search}`,
  );
  const [printRows, setPrintRows] = useState(null);
  useEffect(() => {
    if (!printRows) return undefined;
    const done = () => setPrintRows(null);
    window.addEventListener("afterprint", done, { once: true });
    window.print();
    return () => window.removeEventListener("afterprint", done);
  }, [printRows]);
  const [printAll, preparingPrint] = useSubmit(async () => {
    try {
      const all = await reports.transactions({ ...query, page: 1, page_size: PRINT_LIMIT });
      setPrintRows(all.items);
    } catch (err) {
      toast.error("Print failed", err.message);
    }
  });
  const [exportCsv, exporting] = useSubmit(async () => {
    try {
      await reports.exportCsv(query);
    } catch (err) {
      toast.error("Export failed", err.message);
    }
  });

  const columns = [
    { key: "date", header: "Date", render: (r) => formatDay(r.date) },
    { key: "loan_number", header: "Loan", render: (r) => <LoanLink loanNumber={r.loan_number} /> },
    { key: "customer_name", header: "Customer" },
    { key: "branch", header: "Branch" },
    { key: "kind", header: "Entry", render: (r) => entryLabel(r.kind) },
    { key: "amount", header: "Amount", numeric: true, render: (r) => formatINR(entryAmount(r)) },
    { key: "interest_paid", header: "Interest", numeric: true, render: (r) => (r.kind === "addColl" ? formatINR(r.interest_paid) : "—") },
    { key: "principal_balance", header: "Principal balance", numeric: true, render: (r) => formatINR(r.principal_balance) },
  ];

  return (
    <div className="page">
      <PageHeader title="Reports" description="Every ledger entry in a period, for reconciliation."
        actions={
          <>
            <Button icon="download" onClick={exportCsv} loading={exporting} disabled={!valid || !data?.total} className="no-print">Export CSV</Button>
            <Button icon="printer" onClick={printAll} loading={preparingPrint} className="no-print"
              disabled={!data?.total || data.total > PRINT_LIMIT}
              title={data?.total > PRINT_LIMIT ? `Over ${PRINT_LIMIT} entries: use Export CSV` : undefined}>Print</Button>
          </>
        } />
      <Card>
        <div className="stack">
          <p className="visually-hidden" role="status">
            {loading ? "Loading entries…" : data ? `${data.total.toLocaleString("en-IN")} entries found` : ""}
          </p>
          <p className="print-only">
            {ENTRY_LABELS[kind] ?? "All entries"}
            {search ? ` · Search: “${search}”` : ""}
            {` · Branch: ${branch || "all branches"}`}
          </p>
          <div className="cluster no-print">
            <Segmented label="Period" options={PRESETS} value={preset} onChange={setPreset} />
          </div>
          <div className="grid grid-tight no-print">
            {preset === "custom" ? (
              <>
                <DateField label="From" value={custom.from} max={today} onChange={(e) => setCustom((c) => ({ ...c, from: e.target.value }))} />
                <DateField label="To" value={custom.to} max={today} onChange={(e) => setCustom((c) => ({ ...c, to: e.target.value }))}
                  error={valid ? "" : "Choose a valid date range up to today."} />
              </>
            ) : null}
            <SelectField label="Entry type" value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">All entries</option>
              {KINDS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </SelectField>
            <TextField label="Search" type="search" value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Customer, loan or customer no." autoComplete="off" />
          </div>
          {error ? (
            <ErrorState error={error} onRetry={reload} />
          ) : !data && valid ? (
            <SkeletonRows label="Loading report" />
          ) : data ? (
            <div aria-busy={loading}>
              {data.total > PRINT_LIMIT ? (
                <div className="no-print"><Banner tone="info">More than {PRINT_LIMIT} entries: use Export CSV to print or reconcile the whole period.</Banner></div>
              ) : null}
              <DataTable columns={columns} rows={printRows ?? data.items} rowKey={(r) => r.id}
                caption={`${data.total.toLocaleString("en-IN")} entries, ${formatDay(data.from)} – ${formatDay(data.to)}`}
                empty={<EmptyState icon="file" title="No entries in this period">Try a longer period or clear the filters.</EmptyState>} />
              <div className="no-print">
                <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPage={setPage} label="Report pages" />
              </div>
            </div>
          ) : null}
        </div>
      </Card>
    </div>
  );
}
