import { useRef, useState } from "react";
import { useDocumentTitle, useFocusOnChange } from "../../hooks/useAsync.js";
import { formatINR, normaliseAmount } from "../../lib/money.js";
import { Button } from "../../ui/controls.jsx";
import { Banner, Card, PageHeader } from "../../ui/surfaces.jsx";
import { CutLine, Fields, Letterhead, Signatures, printOnly } from "../../print/printing.jsx";
import { useLetterhead } from "./useLetterhead.js";

// The group-loan application form. Its contents (including Aadhaar numbers) stay in
// this page's memory only: nothing is saved, sent to the server or put in the URL.
const SECTIONS = [
  { title: "Applicant", fields: [
    ["applicantName", "അപേക്ഷകയുടെ പേര്"], ["applicantBirth", "ജനന തിയതി / വയസ്"], ["applicantAadhaar", "ആധാർ നമ്പർ"],
    ["applicantIdCard", "ID കാർഡ് നമ്പർ"], ["applicantMobile", "മോബൈൽ നമ്പർ"], ["applicantAddress", "മേൽവിലാസം"],
  ] },
  { title: "Spouse", fields: [
    ["spouseName", "ഭർത്താവിൻ്റെ പേര്"], ["spouseBirth", "ജനന തിയതി / വയസ്"], ["spouseAadhaar", "ആധാർ നമ്പർ"],
    ["spouseIdCard", "ID കാർഡ് നമ്പർ"], ["spouseMobile", "മോബൈൽ നമ്പർ"], ["spouseAddress", "മേൽവിലാസം"],
  ] },
  { title: "Group and branch", fields: [
    ["memberName", "അപേക്ഷകയുടെ പേര്"], ["childName", "മകൾ / മകൻ പേര്"], ["memberAadhaar", "ആധാർ നമ്പർ"],
    ["groupName", "ഗ്രൂപ്പിൻ്റെ പേര്"], ["groupNumber", "ഗ്രൂപ്പ് നമ്പർ"], ["customerNumber", "കസ്റ്റമർ നമ്പർ"],
    ["loanAmount", "അപേക്ഷിക്കുന്ന വായ്‌പ തുക"], ["weeklyInstalment", "പ്രതിവാര തിരിച്ചടവ് തുക"],
  ] },
  { title: "Loan", fields: [
    ["loanSpouse", "ഭർത്താവിൻ്റെ പേര്"], ["rationCard", "റേഷൻ കാർഡ് നമ്പർ"], ["loanNeed", "വായ്‌പ ആവശ്യം"],
    ["loanTerms", "ലോൺ വ്യവസ്ഥ"], ["loanDate", "വായ്‌പ എടുത്ത തിയതി"], ["repaymentDate", "തിരിച്ചടവ് തിയതി"],
    ["loanPeriod", "വായ്‌പ കാലാവധി"], ["totalRepayment", "ആകെ തിരിച്ചടവ് തുക"],
  ] },
  { title: "Purpose and membership", fields: [
    ["purpose", "ഉദ്ദേശ്യം"], ["purposeGroupNumber", "ഗ്രൂപ്പ് നമ്പർ"], ["membershipNumber", "മെമ്പർഷിപ് നമ്പർ"],
    ["membershipCustomerNumber", "കസ്റ്റമർ നമ്പർ"],
  ] },
];
const ALL_FIELDS = SECTIONS.flatMap((s) => s.fields);
const empty = () => Object.fromEntries(ALL_FIELDS.map(([key]) => [key, ""]));

function SheetTable({ form, keys }) {
  const labels = Object.fromEntries(ALL_FIELDS);
  return (
    <table className="sheet-table" lang="ml">
      <tbody>
        {keys.map((key) => (
          <tr key={key}><th scope="row">{labels[key]}</th><td lang="en">{form[key] || " "}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

function money(value) {
  const amount = normaliseAmount(value);
  return amount ? formatINR(amount) : value || "—";
}

export default function ApplicationFormPage() {
  useDocumentTitle("Application form");
  const letterhead = useLetterhead();
  const [form, setForm] = useState(empty);
  const [preview, setPreview] = useState(false);
  const application = useRef(null);
  const office = useRef(null);
  const customer = useRef(null);
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const heading = useFocusOnChange(preview);

  if (preview) {
    const receipt = (copy, ref) => (
      <article className="sheet" ref={ref} aria-label={`${copy} copy`}>
        <Letterhead branch={letterhead} title={`Loan application · ${copy} copy`} />
        <Fields rows={[
          ["Name", form.applicantName], ["Phone", form.applicantMobile], ["Address", form.applicantAddress],
          ["Loan amount", money(form.loanAmount)], ["Weekly instalment", money(form.weeklyInstalment)], ["Tenure", form.loanPeriod],
        ]} />
        <Signatures />
      </article>
    );
    return (
      <div className="print-page">
        <div className="print-toolbar no-print">
          <Button icon="arrowLeft" onClick={() => setPreview(false)}>Edit form</Button>
          <h1 className="print-toolbar-title" ref={heading} tabIndex={-1}>Application form preview</h1>
          <div className="cluster">
            <Button icon="printer" onClick={() => printOnly(application.current)}>Application</Button>
            <Button icon="printer" onClick={() => printOnly(office.current)}>Office copy</Button>
            <Button icon="printer" onClick={() => printOnly(customer.current)}>Customer copy</Button>
          </div>
        </div>
        <div className="sheets">
          <article className="sheet" ref={application} aria-label="Application">
            <Letterhead branch={letterhead} title="Loan application form" />
            <div className="form-sheet-grid">
              <SheetTable form={form} keys={SECTIONS[0].fields.map(([k]) => k)} />
              <SheetTable form={form} keys={SECTIONS[1].fields.map(([k]) => k)} />
            </div>
            <section className="form-sheet-section">
              <h3 lang="ml">വായ്‌പ വിവരങ്ങൾ</h3>
              <div className="form-sheet-grid">
                <SheetTable form={form} keys={["memberName", "childName", "memberAadhaar", "groupName", "groupNumber", "customerNumber"]} />
                <SheetTable form={form} keys={["loanSpouse", "rationCard", "loanNeed", "loanTerms", "loanPeriod", "totalRepayment"]} />
              </div>
              <div className="form-sheet-grid">
                <SheetTable form={form} keys={["loanAmount", "weeklyInstalment", "loanDate", "repaymentDate"]} />
                <SheetTable form={form} keys={["purpose", "purposeGroupNumber", "membershipNumber", "membershipCustomerNumber"]} />
              </div>
            </section>
            <section className="form-sheet-section" lang="ml">
              <h3>ശുപാർശ</h3>
              <p>
                തിയതികളിൽ നടന്ന ഗ്രൂപ്പ് യോഗത്തിൻ്റെയും വായ്‌പ കരാറിലെ മറ്റു അംഗങ്ങളുടെയും സമ്മതപ്രകാരം ശ്രീമതി{" "}
                <strong lang="en">{form.applicantName || "________"}</strong> ക്ക് വായ്‌പ നൽകുവാൻ സെൻ്റർ അധികാരികൾ എന്ന നിലയിൽ ഞങ്ങൾ അധികാരം നൽകുന്നു.
                പ്രസ്‌തുത വ്യക്തി എന്തെങ്കിലും കാരണവശാൽ വായ്‌പ തവണ തുകകൾ തിരിച്ച് അടയ്ക്കാത്ത പക്ഷം സെൻ്ററിലെ എല്ലാ അംഗങ്ങളും ചേർന്ന്
                വായ്‌പ തിരിച്ചടയ്ക്കാൻ പ്രോത്സാഹിപ്പിച്ചു വായ്‌പ അടപ്പിക്കും. അല്ലെങ്കിൽ ഗ്രൂപ്പ് ഉത്തരവാദിത്വത്തിൽ ഞങ്ങൾ എല്ലാവരും ചേർന്ന്
                വായ്‌പ തിരിച്ചടയ്ക്കുമെന്ന് ഇതിനാൽ ഉറപ്പു തരുന്നു.
              </p>
              <div className="signatures signatures-4">
                <div>പ്രസിഡന്റ്</div><div>സെക്രട്ടറി</div><div>ഗ്രൂപ്പ് ലീഡർ</div><div>ഗ്രൂപ്പ് അംഗം</div>
              </div>
            </section>
          </article>
          {receipt("Office", office)}
          <CutLine />
          {receipt("Customer", customer)}
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div ref={heading} tabIndex={-1}>
        <PageHeader title="Application form" description="Fill in the group-loan application, then preview and print it." />
      </div>
      <form className="stack stack-lg" onSubmit={(e) => { e.preventDefault(); setPreview(true); }} noValidate>
        <Banner tone="info">Nothing on this form is saved. Print it before leaving the page.</Banner>
        {SECTIONS.map((section) => (
          <Card key={section.title} title={section.title}>
            <fieldset className="grid grid-tight">
              <legend className="visually-hidden">{section.title}</legend>
              {section.fields.map(([key, label]) => (
                <div className="field" key={key}>
                  <label className="field-label" htmlFor={`form-${key}`} lang="ml">{label}</label>
                  <input id={`form-${key}`} className="input" maxLength={60} autoComplete="off" value={form[key]} onChange={set(key)} />
                </div>
              ))}
            </fieldset>
          </Card>
        ))}
        <div className="form-actions">
          <Button onClick={() => setForm(empty())}>Clear form</Button>
          <Button type="submit" variant="primary" icon="printer">Preview and print</Button>
        </div>
      </form>
    </div>
  );
}
