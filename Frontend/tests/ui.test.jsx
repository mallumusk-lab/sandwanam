import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { StaticRouter } from "react-router-dom/server";
import { BarList, ColumnChart, compactRupees } from "../src/ui/charts.jsx";
import { Button, IconButton, Pagination, Segmented } from "../src/ui/controls.jsx";
import { DataTable } from "../src/ui/DataTable.jsx";
import { EmptyState, ErrorState, ToastProvider } from "../src/ui/feedback.jsx";
import { AmountField, CheckboxField, SelectField, TextField } from "../src/ui/fields.jsx";
import { ICON_NAMES, Icon } from "../src/ui/Icon.jsx";
import { Stepper } from "../src/ui/surfaces.jsx";

const render = (node) => renderToStaticMarkup(<StaticRouter location="/">{node}</StaticRouter>);

function attr(html, name) {
  return [...html.matchAll(new RegExp(`${name}="([^"]*)"`, "g"))].map((m) => m[1]);
}

test("text fields associate label, hint and error", () => {
  const html = render(<TextField label="Mobile number" hint="10 digits" error="Enter a valid number" value="" onChange={() => {}} />);
  const [id] = attr(html, "id");
  assert.equal(attr(html, "for")[0], id);
  assert.match(html, /aria-invalid="true"/);
  const describedBy = attr(html, "aria-describedby")[0].split(" ");
  assert.ok(describedBy.includes(`${id}-hint`) && describedBy.includes(`${id}-error`));
  assert.match(html, /required=""/);
});

test("optional fields are marked and not required", () => {
  const html = render(<AmountField label="Amount" optional value="" onChange={() => {}} />);
  assert.match(html, /\(optional\)/);
  assert.doesNotMatch(html, /required=""/);
  assert.match(html, /inputMode="decimal"/);
  assert.doesNotMatch(render(<SelectField label="Branch" value="" onChange={() => {}}><option>A</option></SelectField>), /aria-invalid/);
  assert.match(render(<CheckboxField label="Write off" checked={false} onChange={() => {}} />), /type="checkbox"/);
});

test("busy buttons stay focusable and announce their state", () => {
  const html = render(<Button loading>Save</Button>);
  assert.match(html, /aria-busy="true"/);
  assert.match(html, /aria-disabled="true"/);
  assert.doesNotMatch(html, /disabled=""/);
  assert.match(render(<Button to="/x">Go</Button>), /<a[^>]+href="\/x"/);
});

test("icon-only buttons have an accessible name; icons are hidden", () => {
  const html = render(<IconButton icon="trash" label="Remove ring" />);
  assert.match(html, /aria-label="Remove ring"/);
  assert.match(html, /aria-hidden="true"/);
  for (const name of ICON_NAMES) assert.match(render(<Icon name={name} />), /<svg/);
  assert.match(render(<Icon name="info" title="Information" />), /role="img"/);
  assert.throws(() => render(<Icon name="does-not-exist" />));
});

test("tables use header scope and label stacked cells", () => {
  const html = render(<DataTable columns={[{ key: "a", header: "Name" }, { key: "b", header: "Amount", numeric: true }]} rows={[{ a: "X", b: "1" }]} caption="Rows" />);
  assert.match(html, /<caption>Rows<\/caption>/);
  assert.equal(attr(html, "scope").length, 2);
  assert.match(html, /data-label="Amount" class="num"/);
  assert.match(render(<DataTable columns={[]} rows={[]} empty={<p>Nothing</p>} />), /Nothing/);
});

test("tables can add a full-width detail row under a row", () => {
  const columns = [{ key: "a", header: "Name" }, { key: "b", header: "Amount", numeric: true }, { key: "c", header: "Note" }];
  const rows = [{ id: 1, a: "X", b: "1" }, { id: 2, a: "Y", b: "2" }];
  const html = render(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} detail={(r) => (r.id === 1 ? <p>Working for X</p> : null)} />);
  assert.match(html, /<tr class="has-detail">[\s\S]*?<\/tr><tr class="table-detail"><td colSpan="3"><p>Working for X<\/p><\/td><\/tr>/);
  assert.equal((html.match(/table-detail/g) ?? []).length, 1, "no detail row when detail() returns nothing");
  assert.equal((html.match(/<tr>/g) ?? []).length, 2, "header row and the row without detail stay plain");
  const plain = render(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} />);
  assert.doesNotMatch(plain, /has-detail|table-detail|colSpan/);
});

test("segmented controls are a labelled radio group", () => {
  const html = render(<Segmented label="Period" value="b" onChange={() => {}} options={[{ value: "a", label: "A" }, { value: "b", label: "B" }]} />);
  assert.match(html, /<legend class="visually-hidden">Period<\/legend>/);
  assert.equal(attr(html, "type").filter((t) => t === "radio").length, 2);
  assert.match(html, /checked=""/);
});

test("unit affixes are announced with the field", () => {
  const html = render(<TextField label="Interest rate" suffix="% p.a." value="" onChange={() => {}} />);
  const [id] = attr(html, "id");
  assert.ok(attr(html, "aria-describedby")[0].split(" ").includes(`${id}-suffix`));
  assert.match(html, new RegExp(`id="${id}-suffix">% p.a.<`));
});

test("pager buttons stay focusable at the ends", () => {
  const html = render(<Pagination page={1} pageSize={10} total={35} onPage={() => {}} />);
  assert.match(html, /aria-disabled="true"/);
  assert.doesNotMatch(html, /disabled=""/);
});

test("toasts render inside always-present live regions", () => {
  const html = renderToStaticMarkup(<ToastProvider><p>app</p></ToastProvider>);
  assert.match(html, /role="alert"/);
  assert.match(html, /role="status" aria-live="polite"/);
});

test("pagination, stepper and states", () => {
  assert.match(render(<Pagination page={2} pageSize={10} total={35} onPage={() => {}} />), /Showing 11–20 of 35/);
  assert.equal(render(<Pagination page={1} pageSize={10} total={0} onPage={() => {}} />), "");
  const stepper = render(<Stepper steps={["One", "Two", "Three"]} current={1} />);
  assert.match(stepper, /aria-current="step"/);
  assert.match(stepper, /\(completed\)/);
  assert.match(render(<ErrorState error={{ message: "Boom" }} onRetry={() => {}} />), /role="alert"[\s\S]*Boom[\s\S]*Try again/);
  assert.match(render(<EmptyState title="Nothing here" />), /Nothing here/);
});

test("charts keep identity out of colour alone and provide a table", () => {
  const html = render(
    <ColumnChart title="Flows" series={[{ key: "a", label: "Disbursed", color: "red" }, { key: "b", label: "Collected", color: "blue" }]}
      data={[{ label: "Jan", a: "1000", b: "500" }, { label: "Feb", a: "0", b: "250" }]} />,
  );
  assert.match(html, /class="chart-legend"[\s\S]*Disbursed[\s\S]*Collected/);
  assert.match(html, /<summary>View as table<\/summary>/);
  assert.match(html, /aria-label="Jan: Disbursed ₹1,000.00, Collected ₹500.00"/);
  assert.match(render(<BarList title="Aging" rows={[{ label: "0–30 days", value: 3 }]} format={(v) => `${v} loans`} />), /3 loans/);
  assert.equal(compactRupees("150000"), "₹1.5L");
});

/** The declarations of one rule in components.css, found by its exact selector text. */
function cssRule(css, selector) {
  const start = css.indexOf(`${selector} {`);
  assert.ok(start >= 0, `no rule for ${selector}`);
  return css.slice(start + selector.length + 2, css.indexOf("}", start));
}

test("phone layout: charts, bars, stacked tables, dialogs and tiles keep content inside the screen", () => {
  const css = readFileSync(join(process.cwd(), "src", "ui", "components.css"), "utf8");
  // A <figure> has a 40px side margin by default, which pushed charts past the card edge.
  assert.match(cssRule(css, ".chart"), /width: 100%; margin: 0;/);
  // The bar fill is a <span>: without display:block its width is ignored and no bar shows.
  assert.match(cssRule(css, ".hbar-fill"), /display: block;/);
  // Visually hidden header text is positioned; the wrapper must contain it, or the page scrolls sideways.
  assert.match(cssRule(css, ".table-wrap"), /position: relative;[\s\S]*overflow-x: auto;/);
  const stacked = css.slice(css.indexOf("@media screen and (max-width: 720px)"));
  assert.match(stacked, /\.table-stack caption \{ display: block; \}/, "captions span the stacked table instead of one word per line");
  assert.match(stacked, /\.table-stack td, \.table-stack tbody th \{ display: flex;/, "row headers stack like cells");
  // Long text values in a summary wrap instead of widening a dialog; amounts keep their width.
  assert.match(cssRule(css, ".summary-list dd"), /flex-shrink: 0; max-width: 65%; white-space: normal; overflow-wrap: break-word;/);
  // A grid item's minimum width is its content; the cash history day must let its table scroll inside.
  assert.match(cssRule(css, ".cash-history-day"), /grid-template-columns: minmax\(0, 1fr\);/);
  // Narrow KPI tiles shrink the figure so crore amounts stay inside the tile.
  assert.match(css, /@supports \(width: 1cqi\) \{\s*\.kpi \{ container-type: inline-size; \}\s*\.kpi-value \{ font-size: min\(var\(--text-xl\), 12cqi\); \}/);
});
