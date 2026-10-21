import { useRef, useState } from "react";
import { backup } from "../../api/endpoints.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { useAsync, useDocumentTitle, useSubmit } from "../../hooks/useAsync.js";
import { formatDateTime } from "../../lib/dates.js";
import { Button } from "../../ui/controls.jsx";
import { DataTable } from "../../ui/DataTable.jsx";
import { EmptyState, ErrorState, SkeletonRows, useToast } from "../../ui/feedback.jsx";
import { TextField } from "../../ui/fields.jsx";
import { Modal } from "../../ui/Modal.jsx";
import { Banner, Card, PageHeader, Pill } from "../../ui/surfaces.jsx";

const KIND_LABELS = { scheduled: "Daily", manual: "Manual", pre_restore: "Before a restore" };
const MAX_UPLOAD = 4 * 1024 * 1024;

function size(bytes) {
  return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function RestoreDialog({ source, onClose, onRestored }) {
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const submit = async () => {
    if (confirmation !== "RESTORE") return setError("Type RESTORE in capital letters to confirm.");
    setPending(true);
    setError("");
    try {
      const result = await backup.restore({ confirmation, ...(source.snapshotId ? { snapshot_id: source.snapshotId } : { backup: source.document }) });
      onRestored(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  };
  return (
    <Modal open onClose={onClose} busy={pending} title="Restore a backup"
      description={`Source: ${source.label}`}
      footer={<><Button onClick={onClose} disabled={pending}>Cancel</Button><Button variant="danger" loading={pending} onClick={submit}>Replace all data</Button></>}>
      <div className="stack">
        <Banner tone="danger" title="This replaces every customer, loan and ledger entry">
          <p>Current data is saved as a snapshot first, so a mistaken restore can be undone. Accounts and passwords are not changed.</p>
        </Banner>
        <TextField label="Type RESTORE to confirm" value={confirmation} onChange={(e) => setConfirmation(e.target.value)} error={error}
          autoComplete="off" spellCheck={false} data-autofocus />
      </div>
    </Modal>
  );
}

export default function BackupPage() {
  useDocumentTitle("Backups");
  const { user } = useAuth();
  const toast = useToast();
  const fileInput = useRef(null);
  const [restore, setRestore] = useState(null);
  const snapshots = useAsync((signal) => backup.snapshots({ signal }), []);

  const [createSnapshot, creating] = useSubmit(async () => {
    try {
      await backup.createSnapshot();
      toast.success("Snapshot saved");
      snapshots.reload();
    } catch (err) {
      toast.error("Snapshot not saved", err.message);
    }
  });
  const [exportLive, exporting] = useSubmit(async () => {
    try {
      await backup.exportLive();
    } catch (err) {
      toast.error("Download failed", err.message);
    }
  });

  const readFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.size > MAX_UPLOAD) return toast.error("File too large", "Backups up to 4 MB can be uploaded. Restore larger ones from a snapshot.");
    try {
      setRestore({ label: file.name, document: JSON.parse(await file.text()) });
    } catch {
      toast.error("Not a backup file", "The file isn't valid JSON.");
    }
  };

  const columns = [
    { key: "created_at", header: "Created", render: (s) => formatDateTime(s.created_at) },
    { key: "kind", header: "Type", render: (s) => <Pill tone={s.kind === "pre_restore" ? "warning" : undefined}>{KIND_LABELS[s.kind] ?? s.kind}</Pill> },
    { key: "created_by", header: "By" },
    { key: "size_bytes", header: "Size", numeric: true, render: (s) => size(s.size_bytes) },
    {
      key: "actions",
      header: <span className="visually-hidden">Actions</span>,
      render: (s) => (
        <span className="cluster cluster-sm">
          <Button size="sm" icon="download" onClick={() => backup.downloadSnapshot(s.id).catch((err) => toast.error("Download failed", err.message))}>
            Download
          </Button>
          {user.is_superadmin ? (
            <Button size="sm" variant="ghost" onClick={() => setRestore({ label: `snapshot from ${formatDateTime(s.created_at)}`, snapshotId: s.id })}>
              Restore
            </Button>
          ) : null}
        </span>
      ),
    },
  ];

  return (
    <div className="page">
      <PageHeader title="Backups" description="A snapshot is saved automatically every night. The last 14 are kept."
        actions={
          <>
            <Button icon="download" onClick={exportLive} loading={exporting}>Download current data</Button>
            <Button variant="primary" icon="archive" onClick={createSnapshot} loading={creating}>Save a snapshot now</Button>
          </>
        } />
      <div className="stack stack-lg">
        <Banner tone="info">
          <p>Snapshots live in the same database, so they protect against mistakes. Keep the database provider's own backups switched on for disaster recovery, and store a downloaded copy somewhere safe each week.</p>
        </Banner>
        <Card title="Snapshots">
          {snapshots.error ? (
            <ErrorState error={snapshots.error} onRetry={snapshots.reload} />
          ) : !snapshots.data ? (
            <SkeletonRows label="Loading snapshots" />
          ) : (
            <DataTable columns={columns} rows={snapshots.data} rowKey={(s) => s.id}
              empty={<EmptyState icon="database" title="No snapshots yet">Save one now, or wait for tonight's automatic snapshot.</EmptyState>} />
          )}
        </Card>
        {user.is_superadmin ? (
          <Card title="Restore from a file">
            <div className="stack">
              <p className="muted">Upload a backup downloaded from this application. Older-format files from the previous system can't be restored.</p>
              <input ref={fileInput} type="file" accept="application/json,.json" className="visually-hidden" id="restore-file" tabIndex={-1} aria-hidden="true" onChange={readFile} />
              <div><Button icon="upload" onClick={() => fileInput.current?.click()}>Choose a backup file</Button></div>
            </div>
          </Card>
        ) : null}
      </div>
      {restore ? (
        <RestoreDialog source={restore} onClose={() => setRestore(null)}
          onRestored={(result) => {
            setRestore(null);
            toast.success("Data restored", `${result.customers} customers, ${result.loans} loans and ${result.entries} entries. Previous data saved as snapshot ${result.safety_snapshot_id}.`,
              { duration: 30000 });
            snapshots.reload();
          }} />
      ) : null}
    </div>
  );
}
