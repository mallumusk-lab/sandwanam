import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext.jsx";
import { useDocumentTitle } from "../../hooks/useAsync.js";
import { ACCOUNT_LABELS, ALL_BRANCHES_LABEL, FEATURES, homePath } from "../../lib/permissions.js";
import { passwordError } from "../../lib/validation.js";
import { Button } from "../../ui/controls.jsx";
import { PasswordField, focusFirstError } from "../../ui/fields.jsx";
import { useToast } from "../../ui/feedback.jsx";
import { Banner, Card, Details, PageHeader } from "../../ui/surfaces.jsx";

export default function AccountPage() {
  useDocumentTitle("Account");
  const { user, changePassword, logout } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const forced = user.must_change_password || Boolean(location.state?.forced);
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const [errors, setErrors] = useState({});
  const [pending, setPending] = useState(false);

  const set = (key) => (event) => setForm((f) => ({ ...f, [key]: event.target.value }));

  const submit = async (event) => {
    event.preventDefault();
    if (pending) return;
    const found = {
      current: form.current ? "" : "Enter your current password.",
      next: passwordError(form.next, user.username),
      confirm: form.confirm === form.next ? "" : "The passwords don't match.",
    };
    setErrors(found);
    if (Object.values(found).some(Boolean)) {
      requestAnimationFrame(() => focusFirstError(event.target));
      return;
    }
    setPending(true);
    try {
      const updated = await changePassword(form.current, form.next);
      toast.success("Password changed", "Other devices signed in to this account have been signed out.");
      setForm({ current: "", next: "", confirm: "" });
      if (forced) navigate(homePath(updated), { replace: true });
    } catch (error) {
      const fields = error.fieldErrors?.() ?? {};
      setErrors({ current: fields.current_password ?? "", next: fields.new_password ?? (fields.current_password ? "" : error.message) });
    } finally {
      setPending(false);
    }
  };

  const content = (
    <form className="stack" onSubmit={submit} noValidate>
      {forced ? (
        <Banner tone="warning" title="Choose a new password to continue">
          <p>Your account has a temporary password. Pick one only you know.</p>
        </Banner>
      ) : null}
      <input type="text" name="username" autoComplete="username" value={user.username} readOnly hidden />
      <PasswordField label="Current password" autoComplete="current-password" value={form.current}
        onChange={set("current")} error={errors.current} />
      <PasswordField label="New password" autoComplete="new-password" value={form.next}
        onChange={set("next")} error={errors.next}
        hint="At least 10 characters. A short phrase of unrelated words works well." />
      <PasswordField label="Repeat the new password" autoComplete="new-password" value={form.confirm}
        onChange={set("confirm")} error={errors.confirm} />
      <div className="form-actions">
        {forced ? <Button onClick={logout}>Sign out</Button> : null}
        <Button type="submit" variant="primary" loading={pending}>Change password</Button>
      </div>
    </form>
  );

  if (forced) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <Card title="Set your password" headingLevel={1}>{content}</Card>
        </div>
      </div>
    );
  }

  return (
    <div className="page narrow">
      <PageHeader title="Your account" description="Sign-in details and what your account can do." />
      <div className="stack stack-lg">
        <Card title="Profile">
          <Details
            items={[
              ["Username", user.username],
              ["Name", user.display_name],
              ["Account type", ACCOUNT_LABELS[user.account_type]],
              ["Branch", user.branch ?? ALL_BRANCHES_LABEL],
              ["Features", user.permissions.map((p) => FEATURES[p]).join(", ") || "None"],
            ]}
          />
        </Card>
        <Card title="Change password">{content}</Card>
      </div>
    </div>
  );
}
