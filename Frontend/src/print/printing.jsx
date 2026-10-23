import { forwardRef } from "react";
import { useNavigate } from "react-router-dom";
import { formatDay, todayIST } from "../lib/dates.js";
import { Button } from "../ui/controls.jsx";
import { Icon } from "../ui/Icon.jsx";
import "./print.css";

/** Back, the title and Print; extra actions (such as Share) sit beside Print. */
export function PrintToolbar({ title, children }) {
  const navigate = useNavigate();
  return (
    <div className="print-toolbar no-print">
      <Button icon="arrowLeft" onClick={() => navigate(-1)}>Back</Button>
      <h1 className="print-toolbar-title">{title}</h1>
      <div className="cluster">
        {children}
        <Button variant="primary" icon="printer" onClick={() => window.print()}>Print</Button>
      </div>
    </div>
  );
}

/** The letterhead's text lines (shared with the PDF drawing in receiptCanvas.js). */
export function letterheadText(branch) {
  return {
    name: branch?.legal_name ?? branch?.name ?? "Gold Loan Desk",
    address: branch?.address || "",
    contact: branch?.email || branch?.phone
      ? [branch.email && `Email: ${branch.email}`, branch.phone && `Phone: ${branch.phone}`].filter(Boolean).join("  ·  ")
      : "",
  };
}

export function Letterhead({ branch, title, date = todayIST() }) {
  const text = letterheadText(branch);
  return (
    <header className="letterhead">
      {branch?.logo ? <img src={branch.logo} alt="" className="letterhead-logo" /> : null}
      <div className="letterhead-text">
        <p className="letterhead-name">{text.name}</p>
        {text.address ? <p>{text.address}</p> : null}
        {text.contact ? <p>{text.contact}</p> : null}
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

export const OFFICE_SEAL = "Office seal";

export function Signatures({ left = "Customer signature", right = "Authorised signatory" }) {
  return (
    <div className="signatures">
      <div>{left}</div>
      <div>{OFFICE_SEAL}</div>
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

/**
 * One printed copy, drawn from a plain description (see `loanSheet` / `entrySheet`), so the
 * screen, the printout and the shared PDF (receiptCanvas.js) all show the same thing.
 */
export const Sheet = forwardRef(function Sheet({ sheet }, ref) {
  return (
    <article ref={ref} className="sheet" aria-label={`${sheet.copy} copy`}>
      <Letterhead branch={sheet.letterhead} title={sheet.title} date={sheet.date} />
      <Fields rows={sheet.fields} />
      {sheet.total ? (
        <div className="sheet-total">
          <span>{sheet.total.label}</span>
          <strong>{sheet.total.value}</strong>
        </div>
      ) : null}
      {sheet.terms ? <Terms /> : null}
      <Signatures {...sheet.signatures} />
    </article>
  );
});
