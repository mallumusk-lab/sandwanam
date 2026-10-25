import { useState } from "react";
import { admin } from "../../api/endpoints.js";
import { useAsync, useDocumentTitle } from "../../hooks/useAsync.js";
import { FEATURES } from "../../lib/permissions.js";
import { passwordError } from "../../lib/validation.js";
import { Button } from "../../ui/controls.jsx";
import { DataTable } from "../../ui/DataTable.jsx";
import { ErrorState, SkeletonRows, useToast } from "../../ui/feedback.jsx";
import { CheckboxField, PasswordField, TextField, TextareaField } from "../../ui/fields.jsx";
import { ConfirmDialog, Modal } from "../../ui/Modal.jsx";
import { Banner, PageHeader, Pill, Card } from "../../ui/surfaces.jsx";

const LOGO_TYPES = ["image/png", "image/jpeg", "image/webp"];
const MAX_LOGO = 200 * 1024;
const EMPTY = { username: "", branch_prefix: "", display_name: "", legal_name: "", address: "", phone: "", email: "", logo: null,
  // History import enters past-dated loans, so it is opt-in for new branches.
  permissions: Object.keys(FEATURES).filter((key) => key !== "history"), temporary_password: "" };

function readLogo(file) {
  return new Promise((resolve, reject) => {
    if (!LOGO_TYPES.includes(file.type)) return reject(new Error("Use a PNG, JPEG or WebP image."));
    if (file.size > MAX_LOGO) return reject(new Error("Logos must be 200 KB or smaller."));
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("The image could not be read."));
    reader.readAsDataURL(file);
  });
}

function BranchDialog({ account, onClose, onSaved }) {
  const creating = !account;
  const [form, setForm] = useState(() =>
    account
      ? { ...EMPTY, display_name: account.name ?? "", legal_name: account.legal_name ?? "", address: account.address ?? "",
          phone: account.phone ?? "", email: account.email ?? "", logo: account.logo, permissions: account.permissions }
      : EMPTY,
  );
  const [clearLogo, setClearLogo] = useState(false);
  const [errors, setErrors] = useState({});
  const [pending, setPending] = useState(false);
  const isBranch = creating || account.account_type === "branch";
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const pickLogo = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const logo = await readLogo(file);
      setForm((f) => ({ ...f, logo }));
      setClearLogo(false);
      setErrors((e) => ({ ...e, logo: "" }));
    } catch (err) {
      setErrors((e) => ({ ...e, logo: err.message }));
    }
  };

  const save = async () => {
    const found = {
      display_name: form.display_name.trim().length >= 2 ? "" : "Enter the branch name.",
      username: creating && !/^[A-Za-z0-9_.-]{3,32}$/.test(form.username) ? "3–32 letters, digits, dots, hyphens, or underscores." : "",
      branch_prefix: creating && !/^[A-Za-z]{2,5}$/.test(form.branch_prefix.trim()) ? "2–5 letters, for example VZM." : "",
      temporary_password: creating ? passwordError(form.temporary_password, form.username) : "",
    };
    setErrors(found);
    if (Object.values(found).some(Boolean)) return;
    setPending(true);
    try {
      const fields = {
        display_name: form.display_name.trim(),
        legal_name: form.legal_name ?? "",
        address: form.address ?? "",
        phone: form.phone ?? "",
        email: form.email ?? "",
        ...(clearLogo ? { clear_logo: true } : form.logo && form.logo !== account?.logo ? { logo: form.logo } : {}),
        ...(isBranch ? { permissions: form.permissions } : {}),
      };
      if (creating) {
        await admin.createBranch({ ...fields, username: form.username, branch_prefix: form.branch_prefix.trim().toUpperCase(), temporary_password: form.temporary_password });
      } else {
        await admin.update(account.username, fields);
      }
      onSaved(creating ? `Branch ${form.display_name.trim()} created` : "Branch updated");
    } catch (err) {
      const rename = { password: "temporary_password", username: "username", branch_prefix: "branch_prefix" };
      const fields = Object.fromEntries(Object.entries(err.fieldErrors?.() ?? {}).map(([k, v]) => [rename[k] ?? k, v]));
      const shown = ["display_name", "username", "branch_prefix", "temporary_password", "phone", "email", "logo"];
      setErrors(Object.keys(fields).some((k) => shown.includes(k)) ? fields : { form: err.message });
    } finally {
      setPending(false);
    }
  };

  const togglePermission = (key) =>
    setForm((f) => ({ ...f, permissions: f.permissions.includes(key) ? f.permissions.filter((p) => p !== key) : [...f.permissions, key] }));

  return (
    <Modal open size="lg" onClose={onClose} busy={pending} title={creating ? "New branch" : `Edit ${account.name}`}
      description="Letterhead details appear on every receipt printed for this branch."
      footer={<><Button onClick={onClose} disabled={pending}>Cancel</Button><Button variant="primary" loading={pending} onClick={save}>{creating ? "Create branch" : "Save"}</Button></>}>
      <div className="stack">
        {errors.form ? <Banner tone="danger">{errors.form}</Banner> : null}
        <div className="grid grid-tight">
          <TextField label="Branch name" value={form.display_name} onChange={set("display_name")} error={errors.display_name} data-autofocus />
          {creating ? (
            <>
              <TextField label="Sign-in username" value={form.username} onChange={set("username")} error={errors.username} autoComplete="off" />
              <TextField label="Customer ID prefix" value={form.branch_prefix} onChange={set("branch_prefix")} error={errors.branch_prefix}
                hint="Customer numbers start with this, e.g. VZM1. It can't be changed later." maxLength={5} />
            </>
          ) : null}
        </div>
        <TextField label="Legal name on receipts" optional value={form.legal_name ?? ""} onChange={set("legal_name")} />
        <TextareaField label="Address" optional rows={2} value={form.address ?? ""} onChange={set("address")} />
        <div className="grid grid-tight">
          <TextField label="Phone" optional type="tel" value={form.phone ?? ""} onChange={set("phone")} error={errors.phone} />
          <TextField label="Email" optional type="email" value={form.email ?? ""} onChange={set("email")} error={errors.email} />
        </div>
        <div className="field">
          <span className="field-label">Logo <span className="optional">(optional)</span></span>
          <div className="cluster">
            {form.logo && !clearLogo ? <img src={form.logo} alt="Current logo" className="logo-preview" /> : <span className="muted">No logo</span>}
            <label className="btn btn-secondary btn-sm">
              Choose image
              <input type="file" accept={LOGO_TYPES.join(",")} className="visually-hidden" onChange={pickLogo} />
            </label>
            {form.logo && !clearLogo ? <Button size="sm" variant="ghost" onClick={() => setClearLogo(true)}>Remove logo</Button> : null}
          </div>
          {errors.logo ? <p className="field-error" role="alert">{errors.logo}</p> : <p className="field-hint">PNG, JPEG or WebP, up to 200 KB.</p>}
        </div>
        {isBranch ? (
          <fieldset className="stack stack-sm">
            <legend>Features this branch can use</legend>
            {Object.entries(FEATURES).map(([key, label]) => (
              <CheckboxField key={key} label={label} checked={form.permissions.includes(key)} onChange={() => togglePermission(key)} />
            ))}
          </fieldset>
        ) : (
          <Banner tone="info">Head office always has every feature and sees all branches.</Banner>
        )}
        {creating ? (
          <PasswordField label="Temporary password" autoComplete="new-password" value={form.temporary_password}
            onChange={set("temporary_password")} error={errors.temporary_password}
            hint="Share it in person. The branch must choose its own password at first sign-in." />
        ) : null}
      </div>
    </Modal>
  );
}

function PasswordDialog({ account, onClose, onSaved }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const save = async () => {
    const problem = passwordError(password, account.username);
    if (problem) return setError(problem);
    setPending(true);
    try {
      await admin.resetPassword(account.username, password);
      onSaved(`Temporary password set for ${account.name}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  };
  return (
    <Modal open onClose={onClose} busy={pending} title={`Reset password · ${account.name}`}
      description="The account will be signed out everywhere and must set a new password at next sign-in."
      footer={<><Button onClick={onClose} disabled={pending}>Cancel</Button><Button variant="primary" loading={pending} onClick={save}>Set temporary password</Button></>}>
      <PasswordField label="Temporary password" autoComplete="new-password" value={password}
        onChange={(e) => setPassword(e.target.value)} error={error} data-autofocus />
    </Modal>
  );
}

export default function BranchesPage() {
  useDocumentTitle("Branches");
  const toast = useToast();
  const { data, error, reload } = useAsync((signal) => admin.accounts({ signal }), []);
  const [dialog, setDialog] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [busy, setBusy] = useState(false);

  const done = (message) => {
    setDialog(null);
    setConfirm(null);
    toast.success(message);
    reload();
  };
  const runConfirm = async () => {
    setBusy(true);
    try {
      await confirm.action();
      done(confirm.success);
    } catch (err) {
      toast.error("Action failed", err.message);
      setConfirm(null);
    } finally {
      setBusy(false);
    }
  };

  const columns = [
    { key: "name", header: "Branch", render: (a) => <span><strong>{a.name}</strong><br /><span className="muted">{a.username}</span></span> },
    { key: "code", header: "Prefix", render: (a) => a.code ?? <Pill tone="warning">Not set</Pill> },
    {
      key: "status",
      header: "Status",
      render: (a) => (
        <span className="cluster cluster-sm">
          {a.is_active ? <Pill tone="success">Active</Pill> : <Pill>Inactive</Pill>}
          {!a.has_password ? <Pill tone="danger">No password</Pill> : a.must_change_password ? <Pill tone="warning">Temporary password</Pill> : null}
          {a.is_head_office ? <Pill tone="primary">Head office</Pill> : null}
        </span>
      ),
    },
    { key: "permissions", header: "Features", render: (a) => (a.is_head_office ? "All" : `${a.permissions.length} of ${Object.keys(FEATURES).length}`) },
    {
      key: "actions",
      header: <span className="visually-hidden">Actions</span>,
      render: (a) => (
        <span className="cluster cluster-sm">
          <Button size="sm" icon="edit" onClick={() => setDialog({ type: "edit", account: a })}>Edit</Button>
          <Button size="sm" icon="key" onClick={() => setDialog({ type: "password", account: a })}>Password</Button>
          <Button size="sm" variant="ghost" onClick={() => setConfirm({ title: `Unlock ${a.name}?`, body: "Clears sign-in throttling after repeated wrong passwords.", label: "Unlock", success: "Sign-in unlocked", action: () => admin.unlock(a.username) })}>Unlock</Button>
          {!a.is_head_office ? (
            <Button size="sm" variant="ghost" onClick={() => setConfirm({
              title: a.is_active ? `Deactivate ${a.name}?` : `Activate ${a.name}?`,
              body: a.is_active ? "Staff will be signed out and cannot sign in. Customer records and loans are kept." : "Its staff can sign in again.",
              label: a.is_active ? "Deactivate" : "Activate", tone: a.is_active ? "danger" : "primary",
              success: a.is_active ? "Branch deactivated" : "Branch activated", action: () => admin.setActive(a.username, !a.is_active),
            })}>{a.is_active ? "Deactivate" : "Activate"}</Button>
          ) : null}
          {!a.is_head_office ? (
            <Button size="sm" variant="ghost" onClick={() => setConfirm({ title: `Delete ${a.name}?`, body: "Only branches without customers can be deleted. This can't be undone.", label: "Delete", tone: "danger", success: "Branch deleted", action: () => admin.remove(a.username) })}>Delete</Button>
          ) : null}
        </span>
      ),
    },
  ];

  return (
    <div className="page">
      <PageHeader title="Branches" description="Branch accounts, their letterheads and what they can use."
        actions={<Button variant="primary" icon="plus" onClick={() => setDialog({ type: "edit", account: null })}>New branch</Button>} />
      <Card>
        {error ? <ErrorState error={error} onRetry={reload} /> : !data ? <SkeletonRows label="Loading branches" /> : (
          <DataTable columns={columns} rows={data} rowKey={(a) => a.username} />
        )}
      </Card>
      {dialog?.type === "edit" ? <BranchDialog account={dialog.account} onClose={() => setDialog(null)} onSaved={done} /> : null}
      {dialog?.type === "password" ? <PasswordDialog account={dialog.account} onClose={() => setDialog(null)} onSaved={done} /> : null}
      {confirm ? (
        <ConfirmDialog open title={confirm.title} confirmLabel={confirm.label} tone={confirm.tone} busy={busy}
          onConfirm={runConfirm} onCancel={() => setConfirm(null)}>
          <p>{confirm.body}</p>
        </ConfirmDialog>
      ) : null}
    </div>
  );
}
