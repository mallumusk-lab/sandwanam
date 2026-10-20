import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { branches as branchesApi, customers } from "../../api/endpoints.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { useAsync, useDocumentTitle } from "../../hooks/useAsync.js";
import { addressError, nameError, phoneError } from "../../lib/validation.js";
import { Button } from "../../ui/controls.jsx";
import { useToast } from "../../ui/feedback.jsx";
import { SelectField, TextField, TextareaField, focusFirstError } from "../../ui/fields.jsx";
import { Banner, Card, PageHeader } from "../../ui/surfaces.jsx";

export default function NewCustomerPage() {
  useDocumentTitle("New customer");
  const { user, branch } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [form, setForm] = useState({ name: "", phone: "", address: "", branch: branch || user.branch || "" });
  const [errors, setErrors] = useState({});
  const [duplicate, setDuplicate] = useState(null);
  const [pending, setPending] = useState(false);
  const branchList = useAsync((signal) => (user.is_head_office ? branchesApi.list({ signal }) : Promise.resolve([])), [user.is_head_office]);

  const set = (key) => (event) => setForm((f) => ({ ...f, [key]: event.target.value }));

  const submit = async (event) => {
    event.preventDefault();
    if (pending) return;
    const found = {
      name: nameError(form.name),
      phone: phoneError(form.phone),
      address: addressError(form.address),
      branch: user.is_head_office && !form.branch ? "Choose the branch." : "",
    };
    setErrors(found);
    setDuplicate(null);
    if (Object.values(found).some(Boolean)) {
      requestAnimationFrame(() => focusFirstError(event.target));
      return;
    }
    setPending(true);
    try {
      const created = await customers.create({
        name: form.name.trim(),
        phone: form.phone,
        address: form.address.trim(),
        branch: user.is_head_office ? form.branch : undefined,
      });
      toast.success("Customer added", `${created.name} is customer ${created.customer_number}.`);
      navigate(`/customers/${created.id}`, { state: { justCreated: true } });
    } catch (error) {
      const fields = error.fieldErrors?.() ?? {};
      if (error.code === "duplicate_phone") setDuplicate(error);
      else if (Object.keys(fields).length) setErrors(fields);
      else toast.error("Customer not added", error.message);
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="page narrow">
      <PageHeader title="New customer" description="Add the customer first, then open their first loan." back={{ to: "/customers", label: "Customers" }} />
      <Card>
        <form className="stack" onSubmit={submit} noValidate>
          {duplicate ? (
            <Banner tone="warning" title={duplicate.message}>
              {duplicate.details?.customer_id ? (
                <p><Link to={`/customers/${duplicate.details.customer_id}`}>Open the existing customer</Link></p>
              ) : (
                <p>Check the number with the customer, or ask head office for help.</p>
              )}
            </Banner>
          ) : null}
          <TextField label="Full name" autoComplete="off" value={form.name} onChange={set("name")} error={errors.name} maxLength={100} />
          <TextField label="Mobile number" type="tel" inputMode="numeric" autoComplete="off" value={form.phone}
            onChange={set("phone")} error={errors.phone} hint="10 digits, without +91." maxLength={14} />
          <TextareaField label="Address" value={form.address} onChange={set("address")} error={errors.address} maxLength={255} rows={3} />
          {user.is_head_office ? (
            <SelectField label="Branch" value={form.branch} onChange={set("branch")} error={errors.branch}
              hint="The customer number starts with this branch's prefix.">
              <option value="">Choose a branch</option>
              {(branchList.data ?? []).map((b) => (
                <option key={b.code} value={b.code}>{b.name} ({b.code})</option>
              ))}
            </SelectField>
          ) : null}
          <div className="form-actions">
            <Button to="/customers">Cancel</Button>
            <Button type="submit" variant="primary" icon="check" loading={pending}>Add customer</Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
