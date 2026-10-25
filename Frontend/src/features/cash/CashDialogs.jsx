import { useState } from "react";
import { cash } from "../../api/endpoints.js";
import { amountError, compare, formatINR, normaliseAmount, subtract } from "../../lib/money.js";
import { Button } from "../../ui/controls.jsx";
import { useToast } from "../../ui/feedback.jsx";
import { AmountField, TextField, focusFirstError } from "../../ui/fields.jsx";
import { ConfirmDialog, Modal } from "../../ui/Modal.jsx";
import { Banner, SummaryList } from "../../ui/surfaces.jsx";
import { CONNECTION_LOST, differenceLabel } from "./CashParts.jsx";

// Dialogs are mounted only while open, so their state always starts fresh from props.

function focusErrorIn(formId) {
  requestAnimationFrame(() => focusFirstError(document.getElementById(formId)));
}

export function VoidEntryDialog({ entry, onClose, onSaved }) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (pending) return;
    const text = reason.trim();
    if (text.length < 3 || text.length > 255) {
      setError("Give a reason of 3 to 255 characters, for example \"entered twice\".");
      focusErrorIn("cash-void-form");
      return;
    }
    setPending(true);
    setError("");
    try {
      const overview = await cash.voidEntry(entry.id, text);
      toast.success("Entry voided", `${formatINR(entry.amount)} · ${entry.category_label}`);
      onSaved(overview);
      onClose();
    } catch (err) {
      setError(err.status === 0 ? CONNECTION_LOST : err.message);
      focusErrorIn("cash-void-form");
    } finally {
      setPending(false);
    }
  };

  return (
    <Modal open onClose={onClose} busy={pending} title="Void this entry"
      description="The entry stays on the list, struck through, and no longer counts. Nothing is deleted."
      footer={(
        <>
          <Button onClick={onClose} disabled={pending}>Cancel</Button>
          <Button type="submit" form="cash-void-form" variant="danger" loading={pending}>Void entry</Button>
        </>
      )}>
      <form id="cash-void-form" className="stack" onSubmit={submit} noValidate>
        <SummaryList rows={[
          { label: entry.direction === "in" ? "Cash in" : "Cash out", value: formatINR(entry.amount) },
          { label: "Category", value: entry.category_label },
          entry.description ? { label: "Description", value: entry.description } : null,
        ]} />
        <TextField label="Reason" value={reason} maxLength={255} data-autofocus onChange={(e) => setReason(e.target.value)} error={error}
          hint={'Why this entry is wrong, for example "entered twice".'} />
      </form>
    </Modal>
  );
}

/** Count the drawer and lock the day. The expected figure comes from the server. */
export function CloseDayDialog({ day, onClose, onSaved, onChanged }) {
  const toast = useToast();
  const [counted, setCounted] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState(false);

  const amount = normaliseAmount(counted);
  const difference = amount === null ? null : subtract(amount, day.expected);

  const submit = async (event) => {
    event.preventDefault();
    if (pending) return;
    const problem = amountError(counted, { label: "Cash counted", allowZero: true });
    if (problem) {
      setError(problem);
      focusErrorIn("cash-close-form");
      return;
    }
    setPending(true);
    setError("");
    try {
      const overview = await cash.closeDay(day.id, { closing_counted: amount, expected_total: day.expected });
      toast.success("Day closed", `Counted ${formatINR(amount)} · ${differenceLabel(difference)}`);
      onSaved(overview);
      onClose();
    } catch (err) {
      if (err.code === "cash_changed") {
        setNotice("The expected cash in the drawer has changed since this dialog was opened (an entry was added or voided). Review the updated figure and confirm again.");
        await onChanged();
      } else if (err.status === 0) {
        setNotice(CONNECTION_LOST);
      } else {
        setError(err.message);
        focusErrorIn("cash-close-form");
      }
    } finally {
      setPending(false);
    }
  };

  return (
    <Modal open onClose={onClose} busy={pending} title="Close the day"
      description="Count the cash in the drawer. Closing locks the day; head office can reopen it today."
      footer={(
        <>
          <Button onClick={onClose} disabled={pending}>Cancel</Button>
          <Button type="submit" form="cash-close-form" variant="primary" loading={pending}>Close the day</Button>
        </>
      )}>
      <form id="cash-close-form" className="stack" onSubmit={submit} noValidate>
        {notice ? <Banner tone="warning" role="alert">{notice}</Banner> : null}
        <SummaryList rows={[
          { label: "Opening counted", value: formatINR(day.opening_counted) },
          { label: "Cash in", value: formatINR(day.cash_in) },
          { label: "Cash out", value: formatINR(day.cash_out) },
          { label: "Expected in drawer", value: formatINR(day.expected), total: true },
        ]} />
        <AmountField label="Cash in drawer (counted)" value={counted} onChange={(e) => setCounted(e.target.value)} error={error}
          data-autofocus />
        <p className="cash-preview" aria-live="polite">
          {difference === null ? "Enter the counted amount to see the difference." : `Difference: ${differenceLabel(difference)}`}
          {difference !== null && compare(difference, "0") !== 0 ? " The difference is saved with the day." : ""}
        </p>
      </form>
    </Modal>
  );
}

export function ReopenDayDialog({ day, onClose, onSaved }) {
  const toast = useToast();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  const confirm = async () => {
    if (pending) return;
    setPending(true);
    setError("");
    try {
      const overview = await cash.reopenDay(day.id);
      toast.success("Day reopened", "Entries can be added again. Close the day once more when done.");
      onSaved(overview);
      onClose();
    } catch (err) {
      setError(err.status === 0 ? CONNECTION_LOST : err.message);
    } finally {
      setPending(false);
    }
  };

  return (
    <ConfirmDialog open title="Reopen today's cash day?" confirmLabel="Reopen the day" busy={pending} onConfirm={confirm} onCancel={onClose}>
      <div className="stack">
        <p>The closing count is cleared and staff can record entries again. Close the day again when done — a day left open is closed automatically overnight.</p>
        {error ? <Banner tone="danger">{error}</Banner> : null}
      </div>
    </ConfirmDialog>
  );
}
