import { useState } from "react";
import { loans } from "../../api/endpoints.js";
import { addDays, formatDay, todayIST } from "../../lib/dates.js";
import { Button } from "../../ui/controls.jsx";
import { useToast } from "../../ui/feedback.jsx";
import { DateField } from "../../ui/fields.jsx";
import { Modal } from "../../ui/Modal.jsx";

/** The date the dialog starts on: the date staff set, if still ahead, else a week from today. */
export function defaultFollowUp(loan, today = todayIST()) {
  return loan.follow_up_set && loan.follow_up_date && loan.follow_up_date >= today ? loan.follow_up_date : addDays(today, 7);
}

const dayCount = (n) => `${n} day${n === 1 ? "" : "s"}`;

/** Label and pill tone for a follow-up `days` away (the server's follow_up_days; negative once passed). */
export function followUpStatus(days) {
  if (days > 0) return { label: `Due in ${dayCount(days)}`, tone: "info" };
  if (days === 0) return { label: "Due today", tone: "warning" };
  return { label: `Overdue by ${dayCount(-days)}`, tone: "danger" };
}

/**
 * Schedule the next follow-up on an open loan. `loan` needs loan_number, customer_name,
 * phone, follow_up_date and follow_up_set (due_date is shown when present).
 */
export function FollowUpDialog({ loan, onClose, onSaved }) {
  const toast = useToast();
  const [date, setDate] = useState(() => defaultFollowUp(loan));
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const save = async (value) => {
    setPending(true);
    try {
      await loans.setFollowUp(loan.loan_number, value);
      toast.success(value ? "Follow-up scheduled" : "Follow-up set to the automatic date", `${loan.customer_name} · ${loan.loan_number}`);
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  };
  const contact = [loan.customer_name, loan.phone].filter(Boolean).join(", ");
  return (
    <Modal open onClose={onClose} busy={pending} title={`Follow up · ${loan.loan_number}`}
      description={`${contact}.${loan.due_date ? ` Due ${formatDay(loan.due_date)}.` : ""}`}
      footer={
        <>
          {loan.follow_up_set ? <Button onClick={() => save(null)} disabled={pending}>Use the automatic date</Button> : null}
          <Button variant="primary" loading={pending} onClick={() => (date ? save(date) : setError("Choose a date."))}>Save</Button>
        </>
      }>
      <DateField label="Next follow-up" value={date} min={todayIST()} onChange={(e) => setDate(e.target.value)} error={error} data-autofocus />
    </Modal>
  );
}
