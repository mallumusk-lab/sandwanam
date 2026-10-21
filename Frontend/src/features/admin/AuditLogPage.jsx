import { useEffect, useState } from "react";
import { settings } from "../../api/endpoints.js";
import { useAsync, useDocumentTitle } from "../../hooks/useAsync.js";
import { formatDateTime } from "../../lib/dates.js";
import { Pagination } from "../../ui/controls.jsx";
import { DataTable } from "../../ui/DataTable.jsx";
import { EmptyState, ErrorState, SkeletonRows } from "../../ui/feedback.jsx";
import { TextField } from "../../ui/fields.jsx";
import { Card, PageHeader } from "../../ui/surfaces.jsx";

const PAGE_SIZE = 50;

export default function AuditLogPage() {
  useDocumentTitle("Audit log");
  const [term, setTerm] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  useEffect(() => {
    const timer = setTimeout(() => { setQuery(term.trim()); setPage(1); }, 300);
    return () => clearTimeout(timer);
  }, [term]);
  const { data, error, loading, reload } = useAsync((signal) => settings.auditLogs({ q: query, page, page_size: PAGE_SIZE }, { signal }), [query, page], query);

  const columns = [
    { key: "at", header: "When", render: (r) => formatDateTime(r.at) },
    { key: "username", header: "Who" },
    { key: "action", header: "Action", render: (r) => r.action.replaceAll("_", " ").toLowerCase() },
    { key: "entity_id", header: "Record" },
    { key: "details", header: "Details" },
  ];

  return (
    <div className="page">
      <PageHeader title="Audit log" description="Who did what, recorded by the server for every change." />
      <Card>
        <div className="stack">
          <p className="visually-hidden" role="status">
            {loading ? "Searching…" : data ? `${data.total.toLocaleString("en-IN")} log entries found` : ""}
          </p>
          <div role="search">
            <TextField label="Search the log" type="search" value={term} onChange={(e) => setTerm(e.target.value)} placeholder="User, action or loan number" autoComplete="off" />
          </div>
          {error ? <ErrorState error={error} onRetry={reload} /> : !data ? <SkeletonRows /> : (
            <div aria-busy={loading}>
              <DataTable columns={columns} rows={data.items} rowKey={(r) => r.id}
                empty={<EmptyState icon="activity" title="Nothing found" />} />
              <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPage={setPage} label="Audit log pages" />
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
