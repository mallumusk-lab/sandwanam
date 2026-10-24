import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { branches as branchesApi, customers, imports } from "../../api/endpoints.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { useAsync, useDocumentTitle, useFocusOnChange } from "../../hooks/useAsync.js";
import { formatDay, isValidDay, todayIST } from "../../lib/dates.js";
import { itemsError } from "../../lib/items.js";
import { entryLabel, newRequestId } from "../../lib/ledger.js";
import { amountError, formatGrams, formatINR, normaliseAmount, subtract } from "../../lib/money.js";
import { can } from "../../lib/permissions.js";
import { addressError, nameError, phoneError, rateError, tenureError, weightErrors } from "../../lib/validation.js";
import { Button, IconButton, Segmented } from "../../ui/controls.jsx";
import { DataTable } from "../../ui/DataTable.jsx";
import { EmptyState, ErrorState } from "../../ui/feedback.jsx";
import {
  AmountField, CheckboxField, DateField, SelectField, TextField, TextareaField, WeightField, focusFirstError,
} from "../../ui/fields.jsx";
import { Banner, Card, PageHeader, Stepper } from "../../ui/surfaces.jsx";
import { ItemsEditor } from "../loans/ItemsEditor.jsx";

const STEPS = ["Customer", "Loan and past entries", "Review and import"];
const emptyEntry = () => ({ key: newRequestId(), date: "", kind: "addColl", amount: "", writeOff: false });
// A past settlement: the server replays it as a live close (7-day minimum, write-off only when confirmed).
const CLOSE = "close";

export function CustomerStep({ state, setState, onNext }) {
  const { user, branch } = useAuth();
  const [term, setTerm] = useState("");
  const [errors, setErrors] = useState({});
  const [results, setResults] = useState([]);
  const [searchError, setSearchError] = useState("");
  const chosenRef = useRef(null);
  const searchRef = useRef(null);
  const focusAfter = (ref) => requestAnimationFrame(() => ref.current?.focus());
  const branchList = useAsync((signal) => (user.is_head_office ? branchesApi.list({ signal }) : Promise.resolve([])), [user.is_head_office]);
  const mayCreate = can(user, "newcustomer");
  // A new customer defaults to the branch picked in the top bar, else the head-office branch.
  useEffect(() => {
    const office = branchList.data?.find((b) => b.is_head_office);
    if (office) {
      setState((s) => (s.newCustomer.branch ? s : { ...s, newCustomer: { ...s.newCustomer, branch: office.code } }));
    }
  }, [branchList.data, setState]);

  useEffect(() => {
    if (state.mode !== "existing" || term.trim().length < 2) {
      setResults([]);
      return undefined;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      customers.search({ q: term.trim(), branch, page: 1, page_size: 8 }, { signal: controller.signal })
        .then((r) => {
          setResults(r.items);
          setSearchError("");
        })
        .catch((err) => {
          if (controller.signal.aborted) return;
          setResults([]);
          setSearchError(err.status === 403 ? "Your branch can't search customers. Choose \"New customer\" or ask a SuperAdmin." : err.message);
        });
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [term, state.mode, branch]);

  const setNew = (key) => (e) => setState((s) => ({ ...s, newCustomer: { ...s.newCustomer, [key]: e.target.value } }));

  const next = (event) => {
    event.preventDefault();
    if (state.mode === "existing") {
      if (!state.customer) return setErrors({ customer: "Search for the customer and choose them from the list." });
    } else {
      const c = state.newCustomer;
      const found = { name: nameError(c.name), phone: phoneError(c.phone), address: addressError(c.address),
        branch: user.is_head_office && !c.branch ? "Choose the branch." : "" };
      setErrors(found);
      if (Object.values(found).some(Boolean)) return requestAnimationFrame(() => focusFirstError(event.target));
    }
    setErrors({});
    onNext();
  };

  return (
    <form className="stack" onSubmit={next} noValidate>
      {mayCreate ? (
        <Segmented label="Customer" value={state.mode} onChange={(mode) => setState((s) => ({ ...s, mode }))}
          options={[{ value: "existing", label: "Existing customer" }, { value: "new", label: "New customer" }]} />
      ) : null}
      {state.mode === "existing" ? (
        <div className="stack">
          {state.customer ? (
            <div ref={chosenRef} tabIndex={-1}>
              <Banner tone="success" title={`Chosen: ${state.customer.name} (${state.customer.customer_number})`}>
                <p>{state.customer.phone} · Branch {state.customer.branch}{" "}
                  <Button size="sm" variant="ghost" onClick={() => { setState((s) => ({ ...s, customer: null })); focusAfter(searchRef); }}>
                    Change
                  </Button>
                </p>
              </Banner>
            </div>
          ) : (
            <>
              <TextField ref={searchRef} label="Find the customer" type="search" value={term} onChange={(e) => setTerm(e.target.value)}
                hint="Type at least 2 letters of the name, or the phone number." error={errors.customer} autoComplete="off" />
              {results.length ? (
                <ul className="item-list" aria-label="Matching customers">
                  {results.map((c) => (
                    <li key={c.id}>
                      <span><strong>{c.name}</strong> <span className="muted">{c.customer_number} · {c.phone}</span></span>
                      <Button size="sm" onClick={() => { setState((s) => ({ ...s, customer: c })); focusAfter(chosenRef); }}>
                        Choose<span className="visually-hidden"> {c.name}</span>
                      </Button>
                    </li>
                  ))}
                </ul>
              ) : searchError ? (
                <p className="field-error" role="alert">{searchError}</p>
              ) : term.trim().length >= 2 ? <p className="field-hint" role="status">No matching customers.</p> : null}
            </>
          )}
        </div>
      ) : (
        <div className="stack">
          <TextField label="Full name" value={state.newCustomer.name} onChange={setNew("name")} error={errors.name} />
          <TextField label="Mobile number" type="tel" inputMode="numeric" value={state.newCustomer.phone} onChange={setNew("phone")} error={errors.phone} />
          <TextareaField label="Address" rows={3} value={state.newCustomer.address} onChange={setNew("address")} error={errors.address} />
          {user.is_head_office ? (
            <SelectField label="Branch" value={state.newCustomer.branch} onChange={setNew("branch")} error={errors.branch}>
              <option value="">Choose a branch</option>
              {(branchList.data ?? []).map((b) => <option key={b.code} value={b.code}>{b.name} ({b.code})</option>)}
            </SelectField>
          ) : null}
        </div>
      )}
      <div className="form-actions"><Button type="submit" variant="primary" icon="chevronRight">Continue</Button></div>
    </form>
  );
}

export function LoanStep({ state, setState, onBack, onNext }) {
  const [errors, setErrors] = useState({});
  const [pending, setPending] = useState(false);
  const addEntryRef = useRef(null);
  const closedHintId = useId();
  const today = todayIST();
  const loan = state.loan;
  const closes = state.entries.some((entry) => entry.kind === CLOSE);
  const setLoan = (key) => (e) => setState((s) => ({ ...s, loan: { ...s.loan, [key]: e.target.value } }));
  const setEntry = (key, field, value) =>
    setState((s) => ({ ...s, entries: s.entries.map((entry) => (entry.key === key ? { ...entry, [field]: value } : entry)) }));

  const gross = normaliseAmount(loan.gross);
  const deduction = normaliseAmount(loan.deduction);
  const weights = weightErrors(loan.gross, loan.deduction);
  const net = gross && deduction && !weights.gross && !weights.deduction ? subtract(gross, deduction) : null;

  const next = async (event) => {
    event.preventDefault();
    const found = {
      items: itemsError(state.items),
      gross: weights.gross,
      deduction: weights.deduction,
      principal: amountError(loan.principal, { label: "Loan amount" }),
      rate: rateError(loan.rate),
      tenure: tenureError(loan.tenure),
      date: !isValidDay(loan.date) ? "Enter the date the loan was given." : loan.date > today ? "The loan date can't be in the future." : "",
    };
    state.entries.forEach((entry, index) => {
      const closing = entry.kind === CLOSE;
      const compounding = entry.kind === "compounding";
      const dateProblem = !isValidDay(entry.date) ? "Enter a date." : entry.date < loan.date ? "This is before the loan date." : entry.date > today ? "This is in the future."
        : closing && state.entries.some((other) => other.date > entry.date) ? "The loan can't close before another entry's date." : "";
      const amountProblem = compounding
        ? (entry.amount && normaliseAmount(entry.amount) === null ? "Enter a valid amount, or leave blank to calculate." : "")
        : amountError(entry.amount, { label: closing ? "Amount received at closing" : "Amount", allowZero: closing });
      if (dateProblem) found[`date-${entry.key}`] = `Entry ${index + 1}: ${dateProblem}`;
      if (amountProblem) found[`amount-${entry.key}`] = `Entry ${index + 1}: ${amountProblem}`;
      if (closing && index !== state.entries.length - 1) found[`kind-${entry.key}`] = `Entry ${index + 1}: Only the last entry can be the loan closing.`;
    });
    setErrors(found);
    if (Object.values(found).some(Boolean)) return requestAnimationFrame(() => focusFirstError(event.target));
    setPending(true);
    try {
      const preview = await imports.preview(buildPayload(state));
      // A new preview may show a different remainder, so an earlier write-off confirmation is cleared.
      setState((s) => ({ ...s, preview, entries: s.entries.map((entry) => ({ ...entry, writeOff: false })) }));
      onNext();
    } catch (err) {
      setErrors({ form: err.message });
    } finally {
      setPending(false);
    }
  };

  return (
    <form className="stack stack-lg" onSubmit={next} noValidate>
      {errors.form ? <Banner tone="danger">{errors.form}</Banner> : null}
      <ItemsEditor items={state.items} onChange={(items) => setState((s) => ({ ...s, items }))} error={errors.items} />
      <div className="grid grid-tight">
        <WeightField label="Gross weight" value={loan.gross} onChange={setLoan("gross")} error={errors.gross} />
        <WeightField label="Deduction" value={loan.deduction} onChange={setLoan("deduction")} error={errors.deduction}
          hint="Stones, wax and other non-gold weight." />
        <TextField label="Net weight" value={net ? formatGrams(net) : "—"} readOnly aria-live="polite" optional
          hint="Gross weight minus deduction." />
        <AmountField label="Loan amount" value={loan.principal} onChange={setLoan("principal")} error={errors.principal} />
        <TextField label="Interest rate" inputMode="decimal" suffix="% p.a." value={loan.rate} onChange={setLoan("rate")} error={errors.rate} />
        <TextField label="Tenure" inputMode="numeric" suffix="months" value={loan.tenure} onChange={setLoan("tenure")} error={errors.tenure} />
        <DateField label="Loan date" value={loan.date} max={today} onChange={setLoan("date")} error={errors.date} />
      </div>
      <fieldset className="stack">
        <legend>Past entries</legend>
        <p className="field-hint">
          Payments and principal additions made before this system, oldest first or in any order. If the loan was settled, add the closing as the last entry.
        </p>
        {state.entries.map((entry, index) => {
          const closing = entry.kind === CLOSE;
          const compounding = entry.kind === "compounding";
          const last = index === state.entries.length - 1;
          return (
            <div key={entry.key} className="grid grid-tight entry-row">
              <DateField label={closing ? "Closing date" : `Entry ${index + 1} date`} value={entry.date} min={loan.date || undefined} max={today}
                onChange={(e) => setEntry(entry.key, "date", e.target.value)} error={errors[`date-${entry.key}`]} />
              <SelectField label={`Entry ${index + 1} type`} value={entry.kind} onChange={(e) => setEntry(entry.key, "kind", e.target.value)}
                error={errors[`kind-${entry.key}`]}>
                <option value="addColl">Payment received</option>
                <option value="disbursement">Additional principal</option>
                <option value="compounding">Annual compounding</option>
                {last || closing ? <option value={CLOSE}>Loan closed (settled)</option> : null}
              </SelectField>
              <AmountField label={closing ? "Amount received at closing" : compounding ? "Compounded interest" : `Entry ${index + 1} amount`}
                value={entry.amount}
                placeholder={compounding ? "Calculated on preview" : undefined}
                hint={compounding ? "Leave blank to calculate from interest rate, or enter the compounded amount." : undefined}
                optional={compounding}
                onChange={(e) => setEntry(entry.key, "amount", e.target.value)} error={errors[`amount-${entry.key}`]} />
              <div className="field">
                <span className="field-label" aria-hidden="true">&nbsp;</span>
                <IconButton icon="trash" label={`Remove entry ${index + 1}`}
                  onClick={() => {
                    setState((s) => ({ ...s, entries: s.entries.filter((e) => e.key !== entry.key) }));
                    requestAnimationFrame(() => addEntryRef.current?.focus());
                  }} />
              </div>
            </div>
          );
        })}
        <div>
          <Button ref={addEntryRef} icon="plus" disabled={closes} aria-describedby={closes ? closedHintId : undefined}
            onClick={() => setState((s) => ({ ...s, entries: [...s.entries, emptyEntry()] }))}>Add an entry</Button>
          {closes ? <p className="field-hint" id={closedHintId}>A closed loan has no later entries.</p> : null}
        </div>
      </fieldset>
      <div className="form-actions">
        <Button icon="chevronLeft" onClick={onBack}>Back</Button>
        <Button type="submit" variant="primary" loading={pending}>Preview</Button>
      </div>
    </form>
  );
}

export function buildPayload(state) {
  return {
    loan: {
      items: state.items,
      gross_weight: normaliseAmount(state.loan.gross),
      deduction: normaliseAmount(state.loan.deduction),
      principal: normaliseAmount(state.loan.principal),
      rate: normaliseAmount(state.loan.rate),
      tenure_months: Number(state.loan.tenure),
      loan_date: state.loan.date,
    },
    entries: state.entries.map((e) => ({
      date: e.date,
      kind: e.kind,
      amount: e.kind === "compounding" ? (normaliseAmount(e.amount) || "0") : normaliseAmount(e.amount),
      ...(e.kind === CLOSE ? { write_off_remaining: Boolean(e.writeOff) } : {}),
    })),
  };
}

export function ReviewStep({ state, setState, onBack, onDone }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [requestId] = useState(newRequestId);
  const { closes_on: closesOn, remaining_after_close: remaining } = state.preview;
  const closeEntry = state.entries.find((e) => e.kind === CLOSE);
  const commit = async () => {
    setPending(true);
    setError("");
    try {
      const c = state.newCustomer;
      const result = await imports.commit({
        ...buildPayload(state),
        request_id: requestId,
        customer_id: state.mode === "existing" ? state.customer.id : undefined,
        new_customer: state.mode === "new" ? { name: c.name.trim(), phone: c.phone, address: c.address.trim(), branch: c.branch || undefined } : undefined,
        expected: { principal_balance: state.preview.principal_balance, interest_balance: state.preview.interest_balance },
      });
      onDone(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  };
  const columns = [
    { key: "date", header: "Date", render: (e) => formatDay(e.date) },
    { key: "kind", header: "Entry", render: (e) => entryLabel(e.kind) },
    // A loan closes once, so the write-off row's amount is the server's remainder.
    { key: "amount", header: "Amount", numeric: true,
      render: (e) => formatINR(e.kind === "addColl" ? e.amount_paid : e.kind === "newLoan" ? e.principal_balance : e.kind === "writeoff" ? remaining : e.principal_change) },
    { key: "interest", header: "Interest paid", numeric: true, render: (e) => (e.kind === "addColl" ? formatINR(e.interest_paid) : "—") },
    { key: "days", header: "Days", numeric: true, render: (e) => e.accrued_days },
    { key: "principal_balance", header: "Principal balance", numeric: true, render: (e) => formatINR(e.principal_balance) },
    { key: "interest_balance", header: "Interest balance", numeric: true, render: (e) => formatINR(e.interest_balance) },
  ];
  return (
    <div className="stack">
      <Banner tone="info" title="Nothing has been saved yet">
        <p>Check the calculated balances. Importing creates the loan with exactly these entries.</p>
      </Banner>
      {error ? <Banner tone="danger">{error}</Banner> : null}
      <DataTable columns={columns} rows={state.preview.entries} rowKey={(e) => e.index} caption="Calculated ledger" />
      <p><strong>Balance after import:</strong> principal {formatINR(state.preview.principal_balance)}, interest {formatINR(state.preview.interest_balance)}.</p>
      {closesOn ? <p><strong>{`This loan will be imported as closed on ${formatDay(closesOn)}.`}</strong></p> : null}
      {remaining && closeEntry ? (
        <CheckboxField checked={Boolean(closeEntry.writeOff)} disabled={pending}
          onChange={(e) => {
            const writeOff = e.target.checked;
            setState((s) => ({ ...s, entries: s.entries.map((entry) => (entry.kind === CLOSE ? { ...entry, writeOff } : entry)) }));
          }}
          label={`Write off the remaining ${formatINR(remaining)}`}
          hint="The amount received at closing was short. The loan will be imported as closed with this amount written off." />
      ) : null}
      <div className="form-actions">
        <Button icon="chevronLeft" onClick={onBack} disabled={pending}>Back</Button>
        <Button variant="primary" icon="upload" loading={pending} onClick={commit}>Import loan</Button>
      </div>
    </div>
  );
}

const initialState = (branch) => ({
  mode: "existing",
  customer: null,
  newCustomer: { name: "", phone: "", address: "", branch: branch ?? "" },
  items: [],
  loan: { gross: "", deduction: "0", principal: "", rate: "", tenure: "12", date: "" },
  entries: [],
  preview: null,
});

export default function HistoryImportPage() {
  useDocumentTitle("History import");
  const { user, branch } = useAuth();
  const defaultBranch = branch || user.branch || "";
  const [step, setStep] = useState(0);
  const [state, setState] = useState(() => initialState(defaultBranch));
  const [done, setDone] = useState(null);
  const stepHeading = useFocusOnChange(step);
  const doneHeading = useFocusOnChange(done);

  if (done) {
    return (
      <div className="page narrow">
        <h1 className="visually-hidden" ref={doneHeading} tabIndex={-1}>Loan {done.loan_number} imported</h1>
        <Card>
          <EmptyState icon="checkCircle" title={`Loan ${done.loan_number} imported`}
            action={
              <div className="cluster">
                <Button variant="primary" to={`/customers/${done.customer_id}`}>Open the customer</Button>
                <Button onClick={() => { setDone(null); setState(initialState(defaultBranch)); setStep(0); }}>Import another</Button>
              </div>
            }>
            The loan and its history are now on the customer's record.
          </EmptyState>
        </Card>
      </div>
    );
  }

  return (
    <div className="page narrow">
      <PageHeader title="History import" description="Bring a loan that started before this system across with its past payments." />
      <Stepper steps={STEPS} current={step} />
      <h2 className="visually-hidden" ref={stepHeading} tabIndex={-1}>Step {step + 1} of {STEPS.length}: {STEPS[step]}</h2>
      <Card title={STEPS[step]}>
        {step === 0 ? <CustomerStep state={state} setState={setState} onNext={() => setStep(1)} /> : null}
        {step === 1 ? <LoanStep state={state} setState={setState} onBack={() => setStep(0)} onNext={() => setStep(2)} /> : null}
        {step === 2 && state.preview ? <ReviewStep state={state} setState={setState} onBack={() => setStep(1)} onDone={setDone} /> : null}
        {step === 2 && !state.preview ? <ErrorState error={{ message: "Preview the loan first." }} onRetry={() => setStep(1)} /> : null}
      </Card>
      <p className="field-hint">Need the customer's details? <Link to="/customers">Search the directory</Link>.</p>
    </div>
  );
}
