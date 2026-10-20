import { useNavigate } from "react-router-dom";
import { formatDay, todayIST } from "../lib/dates.js";
import { Button } from "../ui/controls.jsx";
import { Icon } from "../ui/Icon.jsx";
import "./print.css";

/** Print just one sheet of a page (e.g. the application form without the receipts). */
export function printOnly(element) {
  if (!element) return window.print();
  element.classList.add("printing-target");
  document.body.classList.add("printing-section");
  const cleanup = () => {
    element.classList.remove("printing-target");
    document.body.classList.remove("printing-section");
    window.removeEventListener("afterprint", cleanup);
  };
  window.addEventListener("afterprint", cleanup);
  window.print();
  setTimeout(cleanup, 1000);
}

export function PrintToolbar({ title, children }) {
  const navigate = useNavigate();
  return (
    <div className="print-toolbar no-print">
      <Button icon="arrowLeft" onClick={() => navigate(-1)}>Back</Button>
      <h1 className="print-toolbar-title">{title}</h1>
      <div className="cluster">
        {children ?? <Button variant="primary" icon="printer" onClick={() => window.print()}>Print</Button>}
      </div>
    </div>
  );
}

export function Letterhead({ branch, title, date = todayIST() }) {
  return (
    <header className="letterhead">
      {branch?.logo ? <img src={branch.logo} alt="" className="letterhead-logo" /> : null}
      <div className="letterhead-text">
        <p className="letterhead-name">{branch?.legal_name ?? branch?.name ?? "Gold Loan Desk"}</p>
        {branch?.address ? <p>{branch.address}</p> : null}
        {branch?.email || branch?.phone ? (
          <p>{[branch.email && `Email: ${branch.email}`, branch.phone && `Phone: ${branch.phone}`].filter(Boolean).join("  ·  ")}</p>
        ) : null}
      </div>
      <div className="letterhead-doc">
        <p className="letterhead-title">{title}</p>
        <p>Date: {formatDay(date)}</p>
      </div>
    </header>
  );
}

export function CutLine() {
  return (
    <div className="cut-line" aria-hidden="true">
      <Icon name="scissors" />
      <span />
    </div>
  );
}

export function Signatures({ left = "Customer signature", right = "Authorised signatory" }) {
  return (
    <div className="signatures">
      <div>{left}</div>
      <div>Office seal</div>
      <div>{right}</div>
    </div>
  );
}

export const RECEIPT_TERMS = [
  "പണയ ഉരുപ്പടി 6 മാസത്തിനകം തിരികെ എടുത്തു കൊള്ളുകയൊ പലിശ അടച്ചു പണയം പുതുക്കുകയോ ചെയ്യാത്ത പക്ഷം പണയ ഉരുപ്പടി വിലയ്ക്ക് കൊടുത്തു തുക ഈടാക്കുന്നതാണ്",
  "പണയ ഉരുപ്പടികൾ തിരിച്ചെടുക്കുമ്പോൾ ഒരു ദിവസത്തിന് മുമ്പേ പണം അടയ്‌ക്കേണ്ടതാണ്.12 മാസം കഴിഞ്ഞാൽ യാതൊരു അറിയിപ്പും കൂടാതെ ഉരുപ്പടിയെ വിലയ്ക്കു കൊടുത്തു തുക ഈടാക്കുന്നതാണ്.",
  "ഉരുപ്പടി തിരികെ എടുക്കുന്ന സമയത്ത് ഈ രസീത് ഹാജരാക്കണം",
];

export function Terms() {
  return (
    <section className="terms">
      <p className="terms-title">Terms and conditions</p>
      <ul lang="ml">
        {RECEIPT_TERMS.map((term) => <li key={term}>{term}</li>)}
      </ul>
    </section>
  );
}

export function Fields({ rows }) {
  return (
    <dl className="sheet-fields">
      {rows.filter(Boolean).map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}
