import { useRef, useState } from "react";
import { ApiError } from "../../api/client.js";
import { backup } from "../../api/endpoints.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { useAsync, useDocumentTitle, useSubmit } from "../../hooks/useAsync.js";
import { formatDateTime } from "../../lib/dates.js";
import { emailError } from "../../lib/validation.js";
import { Button } from "../../ui/controls.jsx";
import { ErrorState, SkeletonRows, useToast } from "../../ui/feedback.jsx";
import { CheckboxField, PasswordField, TextField, focusFirstError } from "../../ui/fields.jsx";
import { Modal } from "../../ui/Modal.jsx";
import { Banner, Card, Details, PageHeader, Pill } from "../../ui/surfaces.jsx";
import { looksLikeZip, prepareUpload } from "./backupFile.js";

// What kind of backup a file is. Files made before backups were email-only may say
// "pre_restore" or "export"; they are shown as they are.
const KIND_LABELS = { scheduled: "Nightly email", manual: "Email backup now" };
const COUNT_LABELS = [["branches", "Branches"], ["customers", "Customers"], ["loans", "Loans"], ["entries", "Ledger entries"], ["settings", "Settings"]];
const RESTORE_WARNING = "Restoring replaces all data. Keep your own copy of the current data first.";

function istTime(iso) {
  return iso ? `${formatDateTime(iso)} IST` : null;
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
      const result = await backup.restore({ confirmation, ...source.body });
      onRestored(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  };
  return (
    <Modal open onClose={onClose} busy={pending} title="Import backup"
      description={`File: ${source.label}`}
      footer={<><Button onClick={onClose} disabled={pending}>Cancel</Button><Button variant="danger" loading={pending} onClick={submit}>Replace all data</Button></>}>
      <div className="stack">
        <Banner tone="danger" title="This replaces every customer, loan, ledger entry and cash ledger day">
          <p>{RESTORE_WARNING} Nothing is saved by the app before the import. Accounts, passwords and the backup email settings are not changed.</p>
        </Banner>
        <TextField label="Type RESTORE to confirm" value={confirmation} onChange={(e) => setConfirmation(e.target.value)} error={error}
          autoComplete="off" spellCheck={false} data-autofocus />
      </div>
    </Modal>
  );
}

/** What a checked file holds (shown in the Import backup card). */
export function CheckReport({ report, canRestore }) {
  return (
    <div className="stack">
      <div>
        {report.checksum === "verified"
          ? <Pill tone="success">Checksum verified</Pill>
          : <Pill tone="warning">Older file without checksum</Pill>}
      </div>
      <Details
        items={[
          ["Taken at", istTime(report.created_at)],
          ["Made by", report.created_by],
          ["Type", report.kind ? KIND_LABELS[report.kind] ?? report.kind : null],
          ["Format version", report.format_version],
          ["Branches in the file", report.branch_prefixes?.length ? report.branch_prefixes.join(", ") : null],
          ...COUNT_LABELS.map(([key, label]) => [label, report.counts?.[key] ?? 0]),
        ]}
      />
      {report.missing_branches?.length ? (
        <Banner tone="danger" title="This file can't be restored here">
          <p>It refers to branches that don't exist here: {report.missing_branches.join(", ")}. Create them under Branches first.</p>
        </Banner>
      ) : !report.restorable ? (
        <Banner tone="danger" title="This file can't be restored here" />
      ) : null}
      {report.warnings?.length ? (
        <Banner tone="warning" title="Check these before restoring">
          <ul>{report.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </Banner>
      ) : null}
      {report.restorable && !canRestore ? <p className="muted">Only the SuperAdmin can restore a backup.</p> : null}
    </div>
  );
}

/**
 * Import backup: choose the emailed ZIP (with its password), the .json inside it or a .json.gz,
 * Check it, then (SuperAdmin) Import it. The password stays in this card's state only.
 */
export function ImportBackup({ user, initialFile = null }) {
  const toast = useToast();
  const fileInput = useRef(null);
  const formRef = useRef(null);
  const [file, setFile] = useState(initialFile);
  const [askPassword, setAskPassword] = useState(looksLikeZip(initialFile));
  const [zipPassword, setZipPassword] = useState("");
  const [errors, setErrors] = useState({});
  const [checked, setChecked] = useState(null);
  const [restoring, setRestoring] = useState(false);
  const [imported, setImported] = useState(null);
  const canRestore = Boolean(user.is_superadmin);

  const choose = (event) => {
    const chosen = event.target.files?.[0];
    event.target.value = "";
    if (!chosen) return;
    setFile(chosen);
    setAskPassword(looksLikeZip(chosen));
    setZipPassword("");
    setErrors({});
    setChecked(null);
    setImported(null);
  };
  const fail = (fieldErrors) => {
    setErrors(fieldErrors);
    requestAnimationFrame(() => focusFirstError(formRef.current));
  };

  const [runCheck, checking] = useSubmit(async (event) => {
    event.preventDefault();
    setChecked(null);
    setImported(null);
    if (!file) return fail({ file: "Choose a backup file first." });
    let body;
    try {
      body = await prepareUpload(file, { zipPassword });
    } catch (err) {
      if (err.field === "zip_password") {
        setAskPassword(true);
        return fail({ zip_password: err.message });
      }
      return fail({ file: err.message });
    }
    setErrors({});
    try {
      setChecked({ label: file.name, body, report: await backup.check(body) });
    } catch (err) {
      const fieldErrors = err instanceof ApiError ? err.fieldErrors() : {};
      if (fieldErrors.zip_password) {
        setAskPassword(true);
        return fail({ zip_password: fieldErrors.zip_password });
      }
      toast.error("Backup check failed", err.message);
    }
  });

  const description = canRestore
    ? "Choose the emailed backup ZIP as it is (with its password), the .json inside it, or a .json.gz. Check it first, then import it."
    : "Choose the emailed backup ZIP as it is (with its password), the .json inside it, or a .json.gz to see what it holds. Only the SuperAdmin can import.";

  return (
    <div className="stack">
      <p className="muted">{description}</p>
      <form ref={formRef} className="stack" onSubmit={runCheck} noValidate>
        <input ref={fileInput} type="file" accept=".zip,.json,.gz,.json.gz,application/zip,application/json,application/gzip"
          className="visually-hidden" id="restore-file" tabIndex={-1} aria-hidden="true" onChange={choose} />
        <div className="stack stack-sm">
          <div><Button icon="upload" onClick={() => fileInput.current?.click()}>Choose a backup file</Button></div>
          <p className={errors.file ? "field-error" : "muted"} role={errors.file ? "alert" : undefined}>
            {errors.file ?? (file ? <>Chosen file: <strong>{file.name}</strong></> : "No file chosen yet.")}
          </p>
        </div>
        {askPassword ? (
          <PasswordField label="ZIP password" value={zipPassword} onChange={(e) => setZipPassword(e.target.value)} error={errors.zip_password}
            autoComplete="off" spellCheck={false}
            hint="The backup password set on the server (BACKUP_ZIP_PASSWORD). It is used only to open this file and is never saved." />
        ) : null}
        <div><Button type="submit" icon="shield" loading={checking} disabled={!file}>Check</Button></div>
      </form>
      {checked ? (
        <section className="stack" aria-label="Backup check">
          <CheckReport report={checked.report} canRestore={canRestore} />
          {canRestore && checked.report.restorable ? (
            <>
              <Banner tone="warning" title="Before you import">
                <p>{RESTORE_WARNING}</p>
              </Banner>
              <div><Button variant="danger" icon="archive" onClick={() => setRestoring(true)}>Import</Button></div>
            </>
          ) : null}
        </section>
      ) : null}
      {imported ? (
        <Banner tone="success" title="Backup imported" role="status">
          <p>
            {imported.customers} customers, {imported.loans} loans and {imported.entries} ledger entries were restored
            {imported.taken_at ? ` from the backup taken ${istTime(imported.taken_at)}` : ""}.
          </p>
        </Banner>
      ) : null}
      {restoring && checked ? (
        <RestoreDialog source={checked} onClose={() => setRestoring(false)}
          onRestored={(result) => {
            setRestoring(false);
            setChecked(null);
            setZipPassword("");
            setImported(result);
            toast.success("Backup imported", `${result.customers} customers, ${result.loans} loans and ${result.entries} entries.`, { duration: 30000 });
          }} />
      ) : null}
    </div>
  );
}

function sendStatus(entry) {
  if (!entry) return { tone: undefined, label: "Not sent yet" };
  if (entry.ok) return { tone: "success", label: "Sent" };
  if (String(entry.result ?? "").startsWith("skipped")) return { tone: "warning", label: "Not sent" };
  return { tone: "danger", label: "Failed" };
}

function SendStatus({ entry }) {
  const status = sendStatus(entry);
  return (
    <span className="stack stack-sm">
      <span className="cluster cluster-sm">
        <Pill tone={status.tone}>{status.label}</Pill>
        {entry?.at ? <span>{istTime(entry.at)}</span> : null}
        {entry?.by ? <span className="muted">by {entry.by}</span> : null}
      </span>
      {entry?.message ? <span className="muted">{entry.message}</span> : null}
    </span>
  );
}

function EmailForm({ settings, onSaved }) {
  const toast = useToast();
  const [recipient, setRecipient] = useState(settings.recipient ?? "");
  const [enabled, setEnabled] = useState(Boolean(settings.enabled));
  const [errors, setErrors] = useState({});
  const formRef = useRef(null);

  const fail = (fieldErrors) => {
    setErrors(fieldErrors);
    requestAnimationFrame(() => focusFirstError(formRef.current));
  };
  const [save, saving] = useSubmit(async (event) => {
    event.preventDefault();
    const text = recipient.trim();
    const recipientError = text ? emailError(text) : enabled ? "Add the address that should receive the backups before turning the email on." : "";
    if (recipientError) return fail({ recipient: recipientError });
    setErrors({});
    try {
      onSaved(await backup.setEmail({ recipient: text || null, enabled }));
      toast.success("Backup email saved");
    } catch (err) {
      const fieldErrors = err instanceof ApiError ? err.fieldErrors() : {};
      if (fieldErrors.recipient || fieldErrors.enabled) return fail(fieldErrors);
      toast.error("Not saved", err.message);
    }
  });

  return (
    <form ref={formRef} className="stack" onSubmit={save} noValidate>
      <TextField label="Send backups to" type="email" autoComplete="email" value={recipient} optional
        onChange={(e) => setRecipient(e.target.value)} error={errors.recipient} spellCheck={false}
        hint="A password-protected ZIP is emailed every night at 00:00 IST. The ZIP password is set on the server and is never emailed." />
      <CheckboxField label="Send the nightly email" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} error={errors.enabled} />
      <div><Button type="submit" variant="primary" loading={saving}>Save</Button></div>
    </form>
  );
}

/** "Email backup now" (head office: HQ and SuperAdmin), at most once every 10 minutes (the server enforces it). */
function EmailNow({ settings, onSaved }) {
  const toast = useToast();
  const [send, sending] = useSubmit(async () => {
    try {
      const result = await backup.sendNow();
      onSaved(result);
      if (result.status?.manual?.ok) toast.success("Backup emailed", `Sent to ${result.recipient}.`);
      else toast.error("Backup email failed", result.status?.manual?.message ?? "The email could not be sent.");
    } catch (err) {
      toast.error("Backup not emailed", err.message);
    }
  });
  return (
    <div className="stack stack-sm">
      <div><Button icon="mail" onClick={send} loading={sending} disabled={!settings.configured || !settings.recipient}>Email backup now</Button></div>
      <p className="muted">Sends the same password-protected ZIP as the nightly email to the address above, now. Once every 10 minutes.</p>
    </div>
  );
}

/** Address, on/off, the last results and "Email backup now"; the SuperAdmin also gets the form. */
export function EmailDetails({ settings, user, onSaved }) {
  return (
    <div className="stack">
      {settings.configured ? null : (
        <Banner tone="warning" title="Email isn't set up on the server yet">
          <p>Ask whoever manages the hosting to add these settings:</p>
          <ul>{settings.missing.map((name) => <li key={name}>{name}</li>)}</ul>
        </Banner>
      )}
      <Details
        items={[
          ["Sent to", settings.recipient ?? "No address set"],
          ["Nightly email", settings.enabled ? "On" : "Off"],
          ["Last nightly email", <SendStatus key="nightly" entry={settings.status?.nightly} />],
          ["Last Email backup now", <SendStatus key="manual" entry={settings.status?.manual} />],
        ]}
      />
      {user.is_superadmin ? <EmailForm settings={settings} onSaved={onSaved} /> : null}
      <EmailNow settings={settings} onSaved={onSaved} />
    </div>
  );
}

function EmailCard({ user }) {
  const email = useAsync((signal) => backup.emailSettings({ signal }), []);
  const [latest, setLatest] = useState(null);
  const settings = latest ?? email.data;
  return (
    <Card title="Backup email">
      {email.error && !latest ? (
        <ErrorState error={email.error} onRetry={email.reload} />
      ) : !settings ? (
        <SkeletonRows rows={3} label="Loading backup email settings" />
      ) : (
        <EmailDetails settings={settings} user={user} onSaved={setLatest} />
      )}
    </Card>
  );
}

export default function BackupPage() {
  useDocumentTitle("Backups");
  const { user } = useAuth();
  return (
    <div className="page">
      <PageHeader title="Backups" description="Every night the app emails a password-protected backup to the address below. Nothing is stored in the app." />
      <div className="stack stack-lg">
        <EmailCard user={user} />
        {user.is_head_office ? (
          <Card title="Import backup">
            <ImportBackup user={user} />
          </Card>
        ) : null}
        <Banner tone="info">
          <p>Keep each emailed backup somewhere safe. The database provider's own backups (Supabase) stay the disaster-recovery layer, so keep them switched on.</p>
        </Banner>
      </div>
    </div>
  );
}
