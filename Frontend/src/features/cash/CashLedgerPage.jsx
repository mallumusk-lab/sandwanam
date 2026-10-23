import { useCallback, useEffect, useId, useRef, useState } from "react";
import { branches as branchesApi, cash } from "../../api/endpoints.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { useAsync, useDocumentTitle, useSubmit } from "../../hooks/useAsync.js";
import { formatDateTime, formatDay } from "../../lib/dates.js";
import { newRequestId } from "../../lib/ledger.js";
import { amountError, formatINR, normaliseAmount, subtract } from "../../lib/money.js";
import { Button, Segmented } from "../../ui/controls.jsx";
import { ErrorState, SkeletonRows, useToast } from "../../ui/feedback.jsx";
import { AmountField, SelectField, TextField, focusFirstError } from "../../ui/fields.jsx";
import { Banner, Card, Details, PageHeader, SummaryList } from "../../ui/surfaces.jsx";
import { CloseDayDialog, ReopenDayDialog, VoidEntryDialog } from "./CashDialogs.jsx";
import { CONNECTION_LOST, DayStatus, DifferencePill, EntriesTable, differenceLabel } from "./CashParts.jsx";

// The cash ledger is the branch drawer's own book: every amount is typed in by staff and
// nothing here is linked to loans. Totals and differences always come from the server;
// the browser only previews a difference while a count is being typed.

const DIRECTIONS = [
  { value: "in", label: "Cash in" },
  { value: "out", label: "Cash out" },
];
const EMPTY_ENTRY = { category: "", description: "", reference: "", amount: "" };

function focusErrors(form) {
  requestAnimationFrame(() => focusFirstError(form));
}

function StartDayCard({ overview, headOffice, onSaved }) {
  const toast = useToast();
  const carry = overview.carry_forward;
  const [counted, setCounted] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const [requestId, setRequestId] = useState(newRequestId);
  const formRef = useRef(null);
  const amount = normaliseAmount(counted);
  const difference = amount === null ? null : subtract(amount, carry.amount);

  const [submit, pending] = useSubmit(async () => {
    const problem = amountError(counted, { label: "Cash in hand", allowZero: true });
    if (problem) {
      setError(problem);
      focusErrors(formRef.current);
      return;
    }
    setError("");
    setNotice("");
    try {
      const fresh = await cash.startDay({
        ...(headOffice ? { branch: overview.branch } : {}),
        opening_counted: amount,
        request_id: requestId,
      });
      toast.success("Day started", `Opening count ${formatINR(amount)} · ${differenceLabel(difference)}`);
      setRequestId(newRequestId());
      onSaved(fresh);
    } catch (err) {
      if (err.status === 0) {
        setUncertain(true);
        setNotice(CONNECTION_LOST);
      } else {
        setError(err.message);
        focusErrors(formRef.current);
      }
    }
  });

  return (
    <Card title="Start the day">
      <form ref={formRef} className="stack" noValidate onSubmit={(event) => { event.preventDefault(); submit(); }}>
        {notice ? <Banner tone="warning" role="alert">{notice}</Banner> : null}
        <p>
          {carry.from_day
            ? `Carried forward from ${formatDay(carry.from_day)}: ${formatINR(carry.amount)}`
            : `No earlier closed day, so the carry forward is ${formatINR(carry.amount)}.`}
        </p>
        <AmountField label="Cash in hand now (counted)" value={counted} readOnly={uncertain} error={error}
          hint="Count the drawer before the first cash movement of the day." onChange={(e) => setCounted(e.target.value)} />
        <p className="cash-preview" aria-live="polite">
          {difference === null ? "Enter the counted amount to compare it with the carry forward." : (
            <>Compared with the carry forward: <DifferencePill value={difference} /></>
          )}
        </p>
        <div className="form-actions">
          <Button type="submit" variant="primary" icon="check" loading={pending}>Start the day</Button>
        </div>
      </form>
    </Card>
  );
}

function AddEntryCard({ day, categories, suggestions, onSaved }) {
  const toast = useToast();
  const listId = useId();
  const [direction, setDirection] = useState("in");
  const [form, setForm] = useState(EMPTY_ENTRY);
  const [errors, setErrors] = useState({});
  const [notice, setNotice] = useState(null);
  const [uncertain, setUncertain] = useState(false);
  const [requestId, setRequestId] = useState(newRequestId);
  const formRef = useRef(null);
  const choices = categories.filter((c) => c.direction === direction || c.direction === "any");
  const isOther = form.category === "other";

  const set = (field) => (event) => setForm((f) => ({ ...f, [field]: event.target.value }));
  const changeDirection = (value) => {
    if (uncertain) return;
    setDirection(value);
    setForm((f) => (categories.some((c) => c.key === f.category && (c.direction === value || c.direction === "any")) ? f : { ...f, category: "" }));
  };

  const [submit, pending] = useSubmit(async () => {
    const description = form.description.trim();
    const reference = form.reference.trim();
    const problems = {
      category: form.category ? "" : "Choose a category.",
      description: isOther && !description ? "Describe what this cash was for." : description.length > 255 ? "Keep the description to 255 characters." : "",
      reference: reference.length > 40 ? "Keep the reference to 40 characters." : "",
      amount: amountError(form.amount, { label: "Amount" }),
    };
    if (Object.values(problems).some(Boolean)) {
      setErrors(problems);
      focusErrors(formRef.current);
      return;
    }
    setErrors({});
    setNotice(null);
    const amount = normaliseAmount(form.amount);
    try {
      const fresh = await cash.addEntry(day.id, {
        direction,
        category: form.category,
        ...(description ? { description } : {}),
        ...(reference ? { reference } : {}),
        amount,
        request_id: requestId,
      });
      const label = categories.find((c) => c.key === form.category)?.label ?? form.category;
      toast.success(direction === "in" ? "Cash in recorded" : "Cash out recorded", `${formatINR(amount)} · ${description || label}`);
      setForm(EMPTY_ENTRY);
      setUncertain(false);
      setRequestId(newRequestId());
      onSaved(fresh);
    } catch (err) {
      if (err.status === 0) {
        setUncertain(true);
        setNotice({ tone: "warning", text: CONNECTION_LOST });
        return;
      }
      const fields = err.fieldErrors?.() ?? {};
      const known = Object.keys(fields).filter((key) => key in EMPTY_ENTRY);
      if (known.length) {
        setErrors(Object.fromEntries(known.map((key) => [key, fields[key]])));
        focusErrors(formRef.current);
      } else {
        setNotice({ tone: "danger", text: err.message });
      }
    }
  });

  return (
    <Card title="Add entry">
      <form ref={formRef} className="stack" noValidate onSubmit={(event) => { event.preventDefault(); submit(); }}>
        {notice ? <Banner tone={notice.tone} role="alert">{notice.text}</Banner> : null}
        <Segmented label="Cash in or out" options={DIRECTIONS} value={direction} onChange={changeDirection} />
        <div className="grid grid-tight">
          <SelectField label="Category" value={form.category} onChange={set("category")} error={errors.category} disabled={uncertain}>
            <option value="">Choose…</option>
            {choices.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
          </SelectField>
          <AmountField label="Amount" value={form.amount} onChange={set("amount")} error={errors.amount} readOnly={uncertain} />
        </div>
        <TextField label="Description" optional={!isOther} value={form.description} maxLength={255} list={listId}
          onChange={set("description")} error={errors.description} readOnly={uncertain} autoComplete="off"
          hint={isOther ? "Required for Other: say what the cash was for." : "For example, who was paid or what for."} />
        <datalist id={listId}>
          {suggestions.map((text) => <option key={text} value={text} />)}
        </datalist>
        <TextField label="Reference" optional value={form.reference} maxLength={40} onChange={set("reference")}
          error={errors.reference} readOnly={uncertain} autoComplete="off" hint="A bill or loan number, if there is one." />
        <div className="form-actions">
          <Button type="submit" variant="primary" icon="plus" loading={pending}>
            {direction === "in" ? "Record cash in" : "Record cash out"}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function TodayCard({ overview, onSaved, onChanged }) {
  const day = overview.today_day;
  const open = day.status === "open";
  const [dialog, setDialog] = useState(null);
  const close = () => setDialog(null);

  return (
    <Card title={`Today · ${formatDay(day.day)}`}
      actions={(
        <>
          <DayStatus day={day} />
          {open ? <Button variant="primary" icon="lock" onClick={() => setDialog({ type: "close" })}>Close the day</Button> : null}
          {!open && overview.can_reopen ? <Button icon="refresh" onClick={() => setDialog({ type: "reopen" })}>Reopen</Button> : null}
        </>
      )}>
      <div className="stack">
        <SummaryList rows={[
          { label: "Carried forward", value: formatINR(day.carried_forward) },
          { label: "Opening counted", value: formatINR(day.opening_counted) },
          { label: "Opening difference", value: <DifferencePill value={day.opening_difference} /> },
          { label: "Cash in", value: formatINR(day.cash_in) },
          { label: "Cash out", value: formatINR(day.cash_out) },
          { label: open ? "Cash in drawer now" : "Expected at closing", value: formatINR(day.expected), total: true },
        ]} />
        {open ? null : <ClosedDetails day={day} />}
        <p className="muted">Started by {day.opened_by} at {formatDateTime(day.opened_at)}.</p>
        <EntriesTable caption="Today's cash movements" entries={day.entries}
          onVoid={open ? (entry) => setDialog({ type: "void", entry }) : undefined} />
      </div>
      {dialog?.type === "void" ? <VoidEntryDialog entry={dialog.entry} onClose={close} onSaved={onSaved} /> : null}
      {dialog?.type === "close" ? <CloseDayDialog day={day} onClose={close} onSaved={onSaved} onChanged={onChanged} /> : null}
      {dialog?.type === "reopen" ? <ReopenDayDialog day={day} onClose={close} onSaved={onSaved} /> : null}
    </Card>
  );
}

function ClosedDetails({ day }) {
  return (
    <div className="stack stack-sm">
      {day.closed_automatically ? (
        <Banner tone="warning" title="Closed automatically (not counted)">
          Nobody counted the drawer, so the expected figure was used as the closing count.
        </Banner>
      ) : null}
      <Details items={[
        ["Counted at closing", formatINR(day.closing_counted)],
        ["Closing difference", <DifferencePill key="d" value={day.closing_difference} />],
        ["Closed by", day.closed_by],
        ["Closed at", formatDateTime(day.closed_at)],
      ]} />
    </div>
  );
}

function HistoryCard({ history }) {
  const [expanded, setExpanded] = useState(() => new Set());
  const toggle = (id) => setExpanded((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });

  return (
    <Card title="Last 14 days">
      {history.length === 0 ? (
        <p className="muted">No earlier days yet. Each day is kept for 14 days.</p>
      ) : (
        <ul className="cash-history">
          {history.map((day) => {
            const isOpen = expanded.has(day.id);
            const panelId = `cash-day-${day.id}`;
            return (
              <li key={day.id} className="cash-history-day">
                <h3 className="cash-history-heading">
                  <Button variant="ghost" icon={isOpen ? "chevronDown" : "chevronRight"} aria-expanded={isOpen} aria-controls={panelId}
                    onClick={() => toggle(day.id)}>
                    {formatDay(day.day)}
                    <span className="visually-hidden">{` · ${day.entries.length} cash movement${day.entries.length === 1 ? "" : "s"}`}</span>
                  </Button>
                  <DayStatus day={day} />
                </h3>
                <Details items={[
                  ["Opening counted", formatINR(day.opening_counted)],
                  ["Cash in", formatINR(day.cash_in)],
                  ["Cash out", formatINR(day.cash_out)],
                  ["Closing counted", formatINR(day.closing_counted)],
                  ["Difference", <DifferencePill key="d" value={day.closing_difference} />],
                ]} />
                <div id={panelId} className="cash-history-entries" hidden={!isOpen}>
                  <div className="stack stack-sm">
                    {day.closed_automatically ? <p className="muted">Closed automatically (not counted).</p> : null}
                    <p className="muted">
                      Carried forward {formatINR(day.carried_forward)} · opening difference {differenceLabel(day.opening_difference)}
                      {day.closed_by ? ` · closed by ${day.closed_by} at ${formatDateTime(day.closed_at)}` : ""}
                    </p>
                    <EntriesTable caption={`Cash movements on ${formatDay(day.day)}`} entries={day.entries} />
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

/** Everything below the header, drawn from one server overview (exported for tests). */
export function CashLedgerView({ overview, headOffice = false, onSaved, onChanged }) {
  const day = overview.today_day;
  return (
    <div className="stack stack-lg">
      <p className="muted">
        {overview.branch_name} ({overview.branch}) · today is {formatDay(overview.today)}
      </p>
      {day ? (
        <TodayCard overview={overview} onSaved={onSaved} onChanged={onChanged} />
      ) : (
        <StartDayCard key={overview.branch} overview={overview} headOffice={headOffice} onSaved={onSaved} />
      )}
      {day?.status === "open" ? (
        <AddEntryCard key={day.id} day={day} categories={overview.categories} suggestions={overview.suggestions} onSaved={onSaved} />
      ) : null}
      <HistoryCard history={overview.history} />
    </div>
  );
}

/** Head office picks one branch: a drawer always belongs to a single branch. */
function BranchSelect({ value, onChange }) {
  const { data, error } = useAsync((signal) => branchesApi.list({ signal }), []);
  const list = data ?? [];
  return (
    <SelectField label="Branch" value={value} onChange={(e) => onChange(e.target.value)}
      hint={error ? "The branch list could not be loaded." : undefined}>
      {value === "" ? <option value="">Choose a branch</option> : null}
      {value && !list.some((b) => b.code === value) ? <option value={value}>{value}</option> : null}
      {list.map((b) => <option key={b.code} value={b.code}>{b.name} ({b.code})</option>)}
    </SelectField>
  );
}

export default function CashLedgerPage() {
  useDocumentTitle("Cash ledger");
  const { user, branch } = useAuth();
  const headOffice = Boolean(user.is_head_office);
  const [picked, setPicked] = useState(() => branch || user.branch || "");
  const query = headOffice ? picked : undefined;
  const { data, error, reload } = useAsync((signal) => cash.overview(query, { signal }), [query]);
  // Every write answers with the fresh overview; it is shown until the next load replaces it.
  const [written, setWritten] = useState(null);
  useEffect(() => setWritten(null), [data]);
  const overview = written ?? data;

  const refresh = useCallback(async () => {
    try {
      setWritten(await cash.overview(query));
    } catch {
      reload();
    }
  }, [query, reload]);

  const pick = (code) => {
    setWritten(null);
    setPicked(code);
  };

  return (
    <div className="page">
      <PageHeader title="Cash ledger"
        description="Cash drawer for this branch: count at the start, record every cash movement, count and close at the end. Kept for 14 days."
        actions={headOffice ? <BranchSelect value={picked} onChange={pick} /> : null} />
      {error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !overview ? (
        <SkeletonRows rows={4} label="Loading cash ledger" />
      ) : (
        <CashLedgerView overview={overview} headOffice={headOffice} onSaved={setWritten} onChanged={refresh} />
      )}
    </div>
  );
}
