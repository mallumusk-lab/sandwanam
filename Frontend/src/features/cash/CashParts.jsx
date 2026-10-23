import { formatDateTime } from "../../lib/dates.js";
import { compare, formatINR, subtract } from "../../lib/money.js";
import { Button } from "../../ui/controls.jsx";
import { DataTable } from "../../ui/DataTable.jsx";
import { Pill } from "../../ui/surfaces.jsx";

export const CONNECTION_LOST =
  "The connection dropped before the server replied, so this may already be saved. Press the button again: it is safe and is never recorded twice.";

/**
 * A counted-minus-expected figure in words: "Matches", "Excess ₹x" or "Shortage ₹x".
 * Display only; the server stores the real differences.
 */
export function differenceLabel(difference) {
  if (difference === null || difference === undefined || difference === "") return "—";
  const sign = compare(difference, "0");
  if (sign === 0) return "Matches";
  return sign > 0 ? `Excess ${formatINR(difference)}` : `Shortage ${formatINR(subtract("0", difference))}`;
}

const DIFFERENCE_TONES = { 0: "success", 1: "warning", [-1]: "danger" };

/** The difference as a pill: the words carry the meaning, the colour only repeats it. */
export function DifferencePill({ value }) {
  if (value === null || value === undefined || value === "") return "—";
  return <Pill tone={DIFFERENCE_TONES[compare(value, "0")]}>{differenceLabel(value)}</Pill>;
}

export function DirectionPill({ direction }) {
  return direction === "in" ? <Pill tone="success">Cash in</Pill> : <Pill tone="warning">Cash out</Pill>;
}

export function DayStatus({ day }) {
  if (day.status === "open") return <Pill tone="info">Open</Pill>;
  return day.closed_automatically ? <Pill tone="warning">Closed automatically</Pill> : <Pill>Closed</Pill>;
}

/** Voided entries stay on the list, struck through and labelled, and don't count. */
function struck(entry, content) {
  return entry.voided ? <s className="cash-voided">{content}</s> : content;
}

/**
 * One day's cash movements, oldest first. `onVoid` is passed only while the day is open.
 */
export function EntriesTable({ entries, onVoid, caption }) {
  const columns = [
    { key: "at", header: "Time", render: (e) => struck(e, formatDateTime(e.at)) },
    { key: "direction", header: "In / out", render: (e) => <DirectionPill direction={e.direction} /> },
    { key: "category", header: "Category", render: (e) => struck(e, e.category_label) },
    { key: "description", header: "Description", render: (e) => struck(e, e.description ?? "—") },
    { key: "reference", header: "Reference", render: (e) => struck(e, e.reference ?? "—") },
    { key: "amount", header: "Amount", numeric: true, render: (e) => struck(e, formatINR(e.amount)) },
    { key: "by", header: "Recorded by", render: (e) => e.recorded_by },
    {
      key: "status",
      header: "Status",
      render: (e) =>
        e.voided ? (
          <span className="cash-void-note">
            <Pill tone="danger">Voided</Pill>
            <span>{e.void_reason}</span>
            <span className="muted">{[e.voided_by, formatDateTime(e.voided_at)].filter(Boolean).join(" · ")}</span>
          </span>
        ) : onVoid ? (
          <Button size="sm" variant="ghost" icon="x" onClick={() => onVoid(e)}>
            Void<span className="visually-hidden"> entry of {formatINR(e.amount)}, {e.category_label}</span>
          </Button>
        ) : (
          "Recorded"
        ),
    },
  ];
  return (
    <DataTable
      caption={caption}
      columns={columns}
      rows={entries}
      rowKey={(e) => e.id}
      empty={<p className="muted">No cash movements recorded.</p>}
    />
  );
}
