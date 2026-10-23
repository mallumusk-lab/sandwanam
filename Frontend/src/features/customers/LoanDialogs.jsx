import { useEffect, useMemo, useState } from "react";
import { loans } from "../../api/endpoints.js";
import { itemsError } from "../../lib/items.js";
import { newRequestId } from "../../lib/ledger.js";
import { amountError, compare, formatINR, normaliseAmount, subtract } from "../../lib/money.js";
import { Button } from "../../ui/controls.jsx";
import { ErrorState, SkeletonRows } from "../../ui/feedback.jsx";
import { AmountField, CheckboxField, focusFirstError } from "../../ui/fields.jsx";
import { Icon } from "../../ui/Icon.jsx";
import { Modal } from "../../ui/Modal.jsx";
import { Banner, SummaryList } from "../../ui/surfaces.jsx";
import { ItemsEditor } from "../loans/ItemsEditor.jsx";

const CONNECTION_LOST =
  "The connection dropped before the server replied, so this may already be saved. Press the button again: it is safe and is never recorded twice.";

function focusErrorIn(formId) {
  requestAnimationFrame(() => focusFirstError(document.getElementById(formId)));
}

function SuccessPanel({ title, children, receiptId, onDone }) {
  return (
    <div className="success-panel" role="status">
      <div className="state-icon"><Icon name="checkCircle" /></div>
      <h3>{title}</h3>
      {children}
      <div className="cluster">
        {receiptId ? (
          <Button variant="primary" icon="printer" to={`/print/entry/${receiptId}`} data-autofocus>Print receipt</Button>
        ) : null}
        <Button onClick={onDone}>Done</Button>
      </div>
    </div>
  );
}

function OutstandingSummary({ outstanding, label = "Outstanding today" }) {
  return (
    <SummaryList
      rows={[
        { label: "Principal", value: formatINR(outstanding.principal) },
        { label: `Interest (${outstanding.period_days} day${outstanding.period_days === 1 ? "" : "s"} this period)`, value: formatINR(outstanding.interest) },
        outstanding.compoundings_due ? { label: "Annual compounding applied", value: `${outstanding.compoundings_due}×` } : null,
        { label, value: formatINR(outstanding.total), total: true },
      ]}
    />
  );
}

/**
 * Days 1-7 of a loan (the server's `first_week`): payments reduce principal, and 7 days' interest
 * on the highest principal is charged at closing or from day 8. Amounts come from the server.
 */
export function FirstWeekBanner({ outstanding, closing = false }) {
  if (closing) {
    return (
      <Banner tone="info">
        Closing in the first 7 days charges 7 days' interest on the highest principal
        {outstanding.window_peak ? ` (${formatINR(outstanding.window_peak)})` : ""}.
      </Banner>
    );
  }
  return (
    <Banner tone="info">
      In the first 7 days a payment reduces the principal. 7 days' interest on the highest principal
      ({formatINR(outstanding.first_week_interest)}) is charged when the loan is closed or from day 8.
    </Banner>
  );
}

// Dialogs are mounted only while open, so their state always starts fresh from props.

/** Record a payment (mode "collect") or add principal (mode "topup"). */
export function PostingDialog({ mode, loan, open, onClose, onPosted }) {
  const collect = mode === "collect";
  const [amount, setAmount] = useState("");
  const [outstanding, setOutstanding] = useState(loan.outstanding);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState(null);
  const [requestId, setRequestId] = useState(newRequestId);
  const [uncertain, setUncertain] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (pending) return;
    const problem = amountError(amount, { label: collect ? "Payment amount" : "Additional principal" });
    if (problem) {
      setError(problem);
      focusErrorIn("posting-form");
      return;
    }
    if (collect && compare(normaliseAmount(amount), outstanding.total) >= 0) {
      setError(`That settles the whole amount due (${formatINR(outstanding.total)}). Use "Close loan" instead, so the pledged items are released.`);
      focusErrorIn("posting-form");
      return;
    }
    setPending(true);
    setError("");
    try {
      const body = {
        amount: normaliseAmount(amount),
        request_id: requestId,
        expected_total: outstanding.total,
      };
      const response = collect ? await loans.collect(loan.loan_number, body) : await loans.topUp(loan.loan_number, body);
      setResult(response);
      onPosted();
    } catch (err) {
      if (err.code === "outstanding_changed") {
        setOutstanding(err.details.outstanding);
        setNotice("The amount due changed since this window opened (for example, a new day started). Check it and submit again.");
        setRequestId(newRequestId());
      } else if (err.status === 0) {
        setUncertain(true);
        setNotice(CONNECTION_LOST);
      } else {
        setError(err.message);
        focusErrorIn("posting-form");
      }
    } finally {
      setPending(false);
    }
  };

  const title = collect ? "Record a payment" : "Add principal";
  const firstWeek = Boolean(outstanding?.first_week);
  return (
    <Modal open={open} onClose={onClose} busy={pending} focusKey={result ? "done" : "form"}
      title={result ? title : `${title} · ${loan.loan_number}`}
      description={result ? undefined : collect
        ? firstWeek ? "The whole payment reduces the principal." : "Interest due is settled first; the rest reduces the principal."
        : "Interest due so far stays owed; the new amount starts earning interest."}
      footer={result ? null : (
        <>
          <Button onClick={onClose} disabled={pending}>Cancel</Button>
          <Button type="submit" form="posting-form" variant="primary" loading={pending}>{collect ? "Record payment" : "Add principal"}</Button>
        </>
      )}>
      {result ? (
        <SuccessPanel title={collect ? "Payment recorded" : "Principal added"} receiptId={result.statement_id} onDone={onClose}>
          <p>{formatINR(normaliseAmount(amount))} for loan {loan.loan_number}.</p>
          {result.replayed ? <p className="muted">It had already been saved when the connection dropped; nothing was recorded twice.</p> : null}
        </SuccessPanel>
      ) : (
        <form id="posting-form" className="stack" onSubmit={submit} noValidate>
          {notice ? <Banner tone="warning" role="alert">{notice}</Banner> : null}
          {collect && firstWeek ? <FirstWeekBanner outstanding={outstanding} /> : null}
          <OutstandingSummary outstanding={outstanding} />
          <AmountField label={collect ? "Amount received" : "Additional principal"} value={amount} readOnly={uncertain}
            onChange={(e) => setAmount(e.target.value)} error={error} data-autofocus />
        </form>
      )}
    </Modal>
  );
}

export function CloseLoanDialog({ loan, open, onClose, onClosed }) {
  const [quote, setQuote] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [received, setReceived] = useState("");
  const [writeOff, setWriteOff] = useState(false);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState(null);
  const [requestId, setRequestId] = useState(newRequestId);
  const [attempt, setAttempt] = useState(0);
  const [uncertain, setUncertain] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setLoadError(null);
    loans
      .closingQuote(loan.loan_number, { signal: controller.signal })
      .then((q) => {
        setQuote(q);
        setReceived(q.total);
      })
      .catch((err) => !controller.signal.aborted && setLoadError(err));
    return () => controller.abort();
  }, [loan.loan_number, attempt]);

  const amount = normaliseAmount(received);
  const remaining = useMemo(
    () => (quote && amount !== null && compare(amount, quote.total) <= 0 ? subtract(quote.total, amount) : null),
    [quote, amount],
  );
  const shortfall = remaining !== null && compare(remaining, "0") > 0;

  const submit = async (event) => {
    event.preventDefault();
    if (pending || !quote) return;
    const problem = amountError(received, { label: "Amount received", allowZero: true, max: quote.total });
    if (problem || (shortfall && !writeOff)) {
      setError(problem || `Confirm the write-off of ${formatINR(remaining)} or collect the full amount.`);
      focusErrorIn("close-form");
      return;
    }
    setPending(true);
    setError("");
    try {
      const response = await loans.close(loan.loan_number, {
        amount_received: amount,
        write_off_remaining: shortfall,
        expected_total: quote.total,
        request_id: requestId,
      });
      setResult(response);
      onClosed();
    } catch (err) {
      if (err.code === "outstanding_changed") {
        setQuote(err.details.outstanding);
        setReceived(err.details.outstanding.total);
        setRequestId(newRequestId());
        setError("The closing amount changed. Check the new amount and confirm again.");
      } else if (err.status === 0) {
        setUncertain(true);
        setError(CONNECTION_LOST);
      } else {
        setError(err.message);
        focusErrorIn("close-form");
      }
    } finally {
      setPending(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} busy={pending} title={`Close loan ${loan.loan_number}`}
      focusKey={result ? "done" : loadError ? "error" : quote ? "form" : "loading"}
      description={result ? undefined : "Collect the closing amount and return the pledged items."}
      footer={result || !quote ? null : (
        <>
          <Button onClick={onClose} disabled={pending}>Cancel</Button>
          <Button type="submit" form="close-form" variant={shortfall ? "danger" : "primary"} loading={pending}>
            {shortfall ? "Close and write off" : "Close loan"}
          </Button>
        </>
      )}>
      {result ? (
        <SuccessPanel title="Loan closed" receiptId={result.statement_id} onDone={onClose}>
          <p>Return the pledged items: {loan.items_text}.</p>
          {!result.statement_id ? <p className="muted">Nothing was owed, so no receipt was created.</p> : null}
        </SuccessPanel>
      ) : loadError ? (
        <ErrorState error={loadError} onRetry={() => setAttempt((n) => n + 1)} />
      ) : !quote ? (
        <SkeletonRows rows={3} label="Working out the closing amount" />
      ) : (
        <form id="close-form" className="stack" onSubmit={submit} noValidate>
          <OutstandingSummary outstanding={quote} label="Closing amount" />
          {quote.first_week ? <FirstWeekBanner outstanding={quote} closing /> : null}
          <AmountField label="Amount received" value={received} readOnly={uncertain}
            onChange={(e) => { setReceived(e.target.value); setError(""); }} error={error} data-autofocus />
          {shortfall ? (
            <CheckboxField checked={writeOff} disabled={uncertain} onChange={(e) => setWriteOff(e.target.checked)}
              label={`Write off the remaining ${formatINR(remaining)}`}
              hint="The loan will be closed with this amount recorded as written off. This can't be undone." />
          ) : null}
        </form>
      )}
    </Modal>
  );
}

export function EditItemsDialog({ loan, open, onClose, onSaved }) {
  const [items, setItems] = useState(loan.items);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  const save = async () => {
    const problem = itemsError(items);
    if (problem) {
      setError(problem);
      requestAnimationFrame(() => focusFirstError(document.querySelector(".modal")));
      return;
    }
    setPending(true);
    try {
      await loans.setItems(loan.loan_number, items);
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} busy={pending} size="lg" title={`Pledged items · ${loan.loan_number}`} focusKey="items"
      description="Changing the item list doesn't affect the amount owed."
      footer={
        <>
          <Button onClick={onClose} disabled={pending}>Cancel</Button>
          <Button variant="primary" loading={pending} onClick={save}>Save items</Button>
        </>
      }>
      <ItemsEditor items={items} onChange={(next) => { setItems(next); setError(""); }} error={error} />
    </Modal>
  );
}
