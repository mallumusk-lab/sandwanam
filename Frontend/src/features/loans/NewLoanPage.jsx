import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { customers, loans } from "../../api/endpoints.js";
import { useAsync, useDocumentTitle } from "../../hooks/useAsync.js";
import { itemsError } from "../../lib/items.js";
import { newRequestId } from "../../lib/ledger.js";
import { amountError, formatGrams, normaliseAmount, subtract } from "../../lib/money.js";
import { rateError, tenureError, weightErrors } from "../../lib/validation.js";
import { Button } from "../../ui/controls.jsx";
import { ErrorState, SkeletonRows, useToast } from "../../ui/feedback.jsx";
import { AmountField, TextField, WeightField, focusFirstError } from "../../ui/fields.jsx";
import { Banner, Card, PageHeader } from "../../ui/surfaces.jsx";
import { ItemsEditor } from "./ItemsEditor.jsx";

export default function NewLoanPage() {
  const { customerId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const customer = useAsync((signal) => customers.get(customerId, { signal }), [customerId]);
  useDocumentTitle("New loan");
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ gross: "", deduction: "0", principal: "", rate: "", tenure: "12" });
  const [errors, setErrors] = useState({});
  const [pending, setPending] = useState(false);
  const [requestId] = useState(newRequestId);
  const [uncertain, setUncertain] = useState(false);

  const set = (key) => (event) => setForm((f) => ({ ...f, [key]: event.target.value }));
  const gross = normaliseAmount(form.gross);
  const deduction = normaliseAmount(form.deduction);
  const weights = weightErrors(form.gross, form.deduction);
  const net = gross && deduction && !weights.gross && !weights.deduction ? subtract(gross, deduction) : null;

  const submit = async (event) => {
    event.preventDefault();
    if (pending) return;
    const found = {
      items: itemsError(items),
      gross: weights.gross,
      deduction: weights.deduction,
      principal: amountError(form.principal, { label: "Loan amount" }),
      rate: rateError(form.rate),
      tenure: tenureError(form.tenure),
    };
    setErrors(found);
    if (Object.values(found).some(Boolean)) {
      requestAnimationFrame(() => focusFirstError(event.target));
      return;
    }
    setPending(true);
    try {
      const created = await loans.create({
        customer_id: Number(customerId),
        items,
        gross_weight: gross,
        deduction,
        principal: normaliseAmount(form.principal),
        rate: normaliseAmount(form.rate),
        tenure_months: Number(form.tenure),
        request_id: requestId,
      });
      toast.success("Loan created", `Loan ${created.loan_number} is open.`);
      navigate(`/customers/${customerId}`, { replace: true });
    } catch (error) {
      if (error.status === 0) {
        setUncertain(true);
        return;
      }
      const fields = error.fieldErrors?.() ?? {};
      const map = { gross_weight: "gross", principal: "principal", interest: "rate", tenure: "tenure", weight: "gross", deduction: "deduction", items: "items" };
      const mapped = Object.fromEntries(Object.entries(fields).map(([k, v]) => [map[k] ?? k, v]));
      if (Object.keys(mapped).length) setErrors(mapped);
      else toast.error("Loan not created", error.message);
    } finally {
      setPending(false);
    }
  };

  if (customer.error) return <div className="page narrow"><ErrorState error={customer.error} onRetry={customer.reload} /></div>;
  if (!customer.data) return <div className="page narrow"><SkeletonRows label="Loading customer" /></div>;
  const person = customer.data.customer;

  return (
    <div className="page narrow">
      <PageHeader title="New loan" description={`For ${person.name} (${person.customer_number})`}
        back={{ to: `/customers/${person.id}`, label: person.name }} />
      <form className="stack stack-lg" onSubmit={submit} noValidate>
        {uncertain ? (
          <Banner tone="warning" title="The connection dropped before the server replied" role="alert">
            <p>The loan may already be created. Press "Create loan" again: it is safe, and the loan is never created twice.</p>
          </Banner>
        ) : null}
        <fieldset className="stack stack-lg" disabled={uncertain}>
        <Card title="Pledged gold">
          <div className="stack">
            <ItemsEditor items={items} onChange={(next) => { setItems(next); setErrors((e) => ({ ...e, items: "" })); }} error={errors.items} />
            <div className="grid grid-tight">
              <WeightField label="Gross weight" value={form.gross} onChange={set("gross")} error={errors.gross} />
              <WeightField label="Deduction" value={form.deduction} onChange={set("deduction")} error={errors.deduction}
                hint="Stones, wax and other non-gold weight." />
              <TextField label="Net weight" value={net ? formatGrams(net) : "—"} readOnly aria-live="polite" optional
                hint="Gross weight minus deduction." />
            </div>
          </div>
        </Card>
        <Card title="Loan terms">
          <div className="grid grid-tight">
            <AmountField label="Loan amount" value={form.principal} onChange={set("principal")} error={errors.principal} />
            <TextField label="Interest rate" inputMode="decimal" suffix="% p.a." value={form.rate} onChange={set("rate")}
              error={errors.rate} hint="Annual rate. 18 % p.a. is 1.5 % a month." />
            <TextField label="Tenure" inputMode="numeric" suffix="months" value={form.tenure} onChange={set("tenure")} error={errors.tenure} />
          </div>
        </Card>
        </fieldset>
        <Banner tone="info">Interest accrues daily from the loan date and is compounded once a year on the loan's anniversary.</Banner>
        <div className="form-actions">
          <Button to={`/customers/${person.id}`}>Cancel</Button>
          <Button type="submit" variant="primary" icon="check" loading={pending}>Create loan</Button>
        </div>
      </form>
    </div>
  );
}
