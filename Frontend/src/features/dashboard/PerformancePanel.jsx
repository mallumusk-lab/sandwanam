import { useState } from "react";
import { dashboard } from "../../api/endpoints.js";
import { useAsync } from "../../hooks/useAsync.js";
import { periodPreset, todayIST } from "../../lib/dates.js";
import { Segmented } from "../../ui/controls.jsx";
import { ErrorState, Skeleton } from "../../ui/feedback.jsx";
import { DateField } from "../../ui/fields.jsx";
import { Card } from "../../ui/surfaces.jsx";
import { DetailDialog, METRICS } from "./DetailDialog.jsx";

const PRESETS = [
  { value: "today", label: "Today" },
  { value: "week", label: "7 days" },
  { value: "month", label: "This month" },
  { value: "fy", label: "This financial year" },
  { value: "custom", label: "Custom" },
];
const SHOWN = [
  "new_customers",
  "new_loans",
  "disbursed",
  "total_collected",
  "interest_collected",
  "principal_collected",
  "closures",
  "compounded",
  "written_off",
  "gold_pledged",
];

export function KpiButton({ label, value, meta, onClick }) {
  return (
    <button type="button" className="kpi" onClick={onClick}>
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
      {meta ? <span className="kpi-meta">{meta}</span> : null}
      <span className="visually-hidden">. Show details.</span>
    </button>
  );
}

export function PerformancePanel({ branch }) {
  const today = todayIST();
  const [preset, setPreset] = useState("month");
  const [custom, setCustom] = useState(periodPreset("month", today));
  const [detail, setDetail] = useState(null);
  const period = preset === "custom" ? custom : periodPreset(preset, today);
  const valid = period.from && period.to && period.from <= period.to && period.to <= today;
  const { data, error, reload } = useAsync(
    (signal) => (valid ? dashboard.performance({ branch, from: period.from, to: period.to }, { signal }) : Promise.resolve(null)),
    [branch, period.from, period.to, valid],
  );

  return (
    <Card title="Performance" actions={<Segmented label="Period" options={PRESETS} value={preset} onChange={setPreset} />}>
      <div className="stack">
        {preset === "custom" ? (
          <div className="grid grid-tight">
            <DateField label="From" value={custom.from} max={today} onChange={(e) => setCustom((c) => ({ ...c, from: e.target.value }))} />
            <DateField label="To" value={custom.to} max={today} onChange={(e) => setCustom((c) => ({ ...c, to: e.target.value }))}
              error={valid ? "" : "Choose a start date on or before the end date, and not in the future."} />
          </div>
        ) : null}
        {error ? (
          <ErrorState error={error} onRetry={reload} />
        ) : (
          <div className="grid grid-tight" aria-busy={!data}>
            {SHOWN.map((key) =>
              data ? (
                <KpiButton key={key} label={METRICS[key].title} value={METRICS[key].value(data)} meta={METRICS[key].meta?.(data)}
                  onClick={() => setDetail(key)} />
              ) : (
                <div className="kpi" key={key}><Skeleton width="60%" /><Skeleton height="1.75rem" /></div>
              ),
            )}
          </div>
        )}
      </div>
      {detail ? <DetailDialog metric={detail} period={period} branch={branch} onClose={() => setDetail(null)} /> : null}
    </Card>
  );
}
