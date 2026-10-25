import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { customers } from "../../api/endpoints.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { useAsync, useDocumentTitle } from "../../hooks/useAsync.js";
import { CREATE, can } from "../../lib/permissions.js";
import { Button, Pagination } from "../../ui/controls.jsx";
import { DataTable } from "../../ui/DataTable.jsx";
import { EmptyState, ErrorState, SkeletonRows } from "../../ui/feedback.jsx";
import { TextField } from "../../ui/fields.jsx";
import { Card, PageHeader, Pill } from "../../ui/surfaces.jsx";

const PAGE_SIZE = 25;

export default function CustomerListPage() {
  useDocumentTitle("Customers");
  const { user, branch } = useAuth();
  const [term, setTerm] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(term.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [term]);
  useEffect(() => setPage(1), [branch]);

  const { data, error, loading, reload } = useAsync(
    (signal) => customers.search({ q: query, branch, page, page_size: PAGE_SIZE }, { signal }),
    [query, branch, page],
    `${query}|${branch}`,
  );

  const columns = [
    { key: "customer_number", header: "Customer no.", render: (c) => <Link className="row-link" to={`/customers/${c.id}`}>{c.customer_number}</Link> },
    { key: "name", header: "Name" },
    { key: "phone", header: "Phone", render: (c) => <span className="num">{c.phone}</span> },
    ...(user?.is_head_office ? [{ key: "branch", header: "Branch" }] : []),
    {
      key: "open_loans",
      header: "Loans",
      render: (c) => (c.open_loans ? <Pill tone="success">{c.open_loans} open</Pill> : <Pill>No open loans</Pill>),
    },
  ];

  return (
    <div className="page">
      <PageHeader
        title="Customers"
        description="Search by name, phone number or customer number."
        actions={can(user, CREATE) ? <Button variant="primary" icon="userPlus" to="/customers/new">New customer</Button> : null}
      />
      <Card>
        <div className="stack">
          <p className="visually-hidden" role="status">
            {loading ? "Searching…" : data ? `${data.total.toLocaleString("en-IN")} customers found` : ""}
          </p>
          <div role="search">
            <TextField label="Search customers" type="search" value={term} onChange={(e) => setTerm(e.target.value)}
              placeholder="For example: Lakshmi, 98765 or SAN12" autoComplete="off" />
          </div>
          {error ? (
            <ErrorState error={error} onRetry={reload} />
          ) : loading && !data ? (
            <SkeletonRows label="Loading customers" />
          ) : (
            <div aria-busy={loading}>
              <DataTable
                columns={columns}
                rows={data.items}
                rowKey={(c) => c.id}
                caption={`${data.total.toLocaleString("en-IN")} customer${data.total === 1 ? "" : "s"}${query ? ` matching “${query}”` : ""}`}
                empty={
                  <EmptyState icon="users" title={query ? "No customers match" : "No customers yet"}
                    action={can(user, CREATE) && !query ? <Button variant="primary" to="/customers/new">Add the first customer</Button> : null}>
                    {query ? "Check the spelling or search by phone number." : "Customers you add will appear here."}
                  </EmptyState>
                }
              />
              <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPage={setPage} label="Customer pages" />
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
