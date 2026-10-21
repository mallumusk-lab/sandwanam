import { useEffect, useId, useRef, useState } from "react";
import { formatINR } from "../lib/money.js";

const COMPACT = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });
const DEFAULT_WIDTH = 640;
const MIN_WIDTH = 280;
const HEIGHT = 240;
const PAD = { top: 16, right: 8, bottom: 28, left: 52 };
const BAR_MAX = 24;
const GAP = 2;

export function compactRupees(value) {
  return `₹${COMPACT.format(Number(value) || 0)}`;
}

function niceCeiling(value) {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((m) => m * magnitude >= value);
  return step * magnitude;
}

/** Column with a 4px rounded data end and a square baseline. */
function columnPath(x, y, width, height) {
  const r = Math.min(4, width / 2, height);
  const bottom = y + height;
  return `M${x},${bottom}V${y + r}Q${x},${y} ${x + r},${y}H${x + width - r}Q${x + width},${y} ${x + width},${y + r}V${bottom}Z`;
}

/**
 * Grouped column chart for a few series over a few periods.
 * series: [{ key, label, color }]; data: [{ label, [key]: value }]
 */
function useWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(MIN_WIDTH, Math.round(entry.contentRect.width))));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

export function ColumnChart({ title, series, data, format = formatINR }) {
  const [active, setActive] = useState(null);
  const tableId = useId();
  const [plotRef, WIDTH] = useWidth();
  const plotWidth = WIDTH - PAD.left - PAD.right;
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;
  const max = niceCeiling(Math.max(0, ...data.flatMap((row) => series.map((s) => Number(row[s.key]) || 0))));
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  const band = plotWidth / Math.max(1, data.length);
  const barWidth = Math.min(BAR_MAX, (band * 0.6 - GAP * (series.length - 1)) / series.length);
  const groupWidth = barWidth * series.length + GAP * (series.length - 1);
  const yOf = (value) => PAD.top + plotHeight - (value / max) * plotHeight;

  return (
    <figure className="chart" aria-label={title}>
      <ul className="chart-legend">
        {series.map((s) => (
          <li key={s.key}>
            <span className="chart-swatch" style={{ background: s.color }} aria-hidden="true" />
            {s.label}
          </li>
        ))}
      </ul>
      <div className="chart-plot" ref={plotRef}>
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="group" aria-labelledby={`${tableId}-caption`}>
          {ticks.map((tick) => (
            <g key={tick}>
              <line className="chart-grid" x1={PAD.left} x2={WIDTH - PAD.right} y1={yOf(tick)} y2={yOf(tick)} />
              <text className="chart-axis" x={PAD.left - 8} y={yOf(tick) + 4} textAnchor="end">
                {compactRupees(tick)}
              </text>
            </g>
          ))}
          {data.map((row, index) => {
            const groupX = PAD.left + band * index + (band - groupWidth) / 2;
            return (
              <g key={row.label}>
                {series.map((s, si) => {
                  const value = Number(row[s.key]) || 0;
                  const y = yOf(value);
                  const height = PAD.top + plotHeight - y;
                  return height > 0 ? (
                    <path key={s.key} d={columnPath(groupX + si * (barWidth + GAP), y, barWidth, height)} style={{ fill: s.color }} />
                  ) : null;
                })}
                <text className="chart-axis" x={PAD.left + band * index + band / 2} y={HEIGHT - 8} textAnchor="middle">
                  {row.label}
                </text>
                <rect
                  x={PAD.left + band * index}
                  y={PAD.top}
                  width={band}
                  height={plotHeight}
                  fill="transparent"
                  tabIndex={0}
                  aria-label={`${row.label}: ${series.map((s) => `${s.label} ${format(row[s.key])}`).join(", ")}`}
                  onMouseEnter={() => setActive(index)}
                  onMouseLeave={() => setActive(null)}
                  onFocus={() => setActive(index)}
                  onBlur={() => setActive(null)}
                />
              </g>
            );
          })}
        </svg>
        {active !== null ? (
          <div
            className="chart-tooltip"
            style={{ left: `${((PAD.left + band * active + band / 2) / WIDTH) * 100}%` }}
            aria-hidden="true"
          >
            <strong>{data[active].label}</strong>
            {series.map((s) => (
              <span key={s.key}>
                <span className="chart-swatch" style={{ background: s.color }} /> {s.label}: {format(data[active][s.key])}
              </span>
            ))}
          </div>
        ) : null}
      </div>
      <details className="chart-table">
        <summary>View as table</summary>
        <table className="table">
          <caption id={`${tableId}-caption`}>{title}</caption>
          <thead>
            <tr>
              <th scope="col">Period</th>
              {series.map((s) => (
                <th key={s.key} scope="col" className="num">{s.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.label}>
                <th scope="row">{row.label}</th>
                {series.map((s) => (
                  <td key={s.key} className="num">{format(row[s.key])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

/** Single-series horizontal bars with the value at each bar's tip (no legend needed). */
export function BarList({ title, rows, format = (v) => v }) {
  const max = Math.max(1, ...rows.map((row) => Number(row.value) || 0));
  return (
    <figure className="chart stack stack-sm" aria-label={title}>
      {rows.map((row) => (
        <div className="hbar" key={row.label}>
          <span>{row.label}</span>
          <span className="hbar-track" aria-hidden="true">
            <span className="hbar-fill" style={{ width: `${((Number(row.value) || 0) / max) * 100}%` }} />
          </span>
          <span className="num">{format(row.value)}</span>
        </div>
      ))}
    </figure>
  );
}
