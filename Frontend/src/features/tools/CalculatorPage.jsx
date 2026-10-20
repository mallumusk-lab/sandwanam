import { useMemo, useState } from "react";
import { useDocumentTitle } from "../../hooks/useAsync.js";
import { addMonths, formatDay, isValidDay, todayIST } from "../../lib/dates.js";
import { dailyInterest, monthlyRate, quote } from "../../lib/interest.js";
import { amountError, formatINR, normaliseAmount, subtract } from "../../lib/money.js";
import { rateError, tenureError } from "../../lib/validation.js";
import { Button } from "../../ui/controls.jsx";
import { AmountField, DateField, TextField } from "../../ui/fields.jsx";
import { Banner, Card, PageHeader, SummaryList } from "../../ui/surfaces.jsx";
import { Fields, Letterhead, Signatures } from "../../print/printing.jsx";
import { useLetterhead } from "./useLetterhead.js";

const CHECKPOINTS = [1, 3, 6, 12];

export default function CalculatorPage() {
  useDocumentTitle("Loan calculator");
  const letterhead = useLetterhead();
  const [form, setForm] = useState({ principal: "", rate: "18", tenure: "12", start: todayIST(), name: "", phone: "" });
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const errors = {
    principal: form.principal ? amountError(form.principal, { label: "Loan amount" }) : "",
    rate: rateError(form.rate),
    tenure: tenureError(form.tenure),
    start: isValidDay(form.start) ? "" : "Enter a valid date.",
  };
  const ready = form.principal && !Object.values(errors).some(Boolean);

  const result = useMemo(() => {
    if (!ready) return null;
    const principal = normaliseAmount(form.principal);
    const rate = normaliseAmount(form.rate);
    const tenure = Number(form.tenure);
    const maturity = addMonths(form.start, tenure);
    const months = [...new Set([...CHECKPOINTS.filter((m) => m < tenure), tenure])];
    return {
      principal, rate, tenure, maturity,
      perDay: dailyInterest(principal, rate),
      perMonth: monthlyRate(rate),
      atMaturity: quote({ principal, rate, start: form.start, asOf: maturity }),
      schedule: months.map((m) => ({ months: m, date: addMonths(form.start, m), ...quote({ principal, rate, start: form.start, asOf: addMonths(form.start, m) }) })),
    };
  }, [ready, form.principal, form.rate, form.tenure, form.start]);

  return (
    <div className="page">
      <div className="no-print">
      <PageHeader title="Loan calculator" description="Estimate the interest on a gold loan using the same rules as the ledger."
        actions={result ? <Button icon="printer" onClick={() => window.print()}>Print estimate</Button> : null} />
      </div>
      <div className="grid no-print">
        <Card title="Loan details">
          <form className="stack" onSubmit={(e) => e.preventDefault()} noValidate>
            <AmountField label="Loan amount" value={form.principal} onChange={set("principal")} error={errors.principal} />
            <TextField label="Interest rate" inputMode="decimal" suffix="% p.a." value={form.rate} onChange={set("rate")} error={errors.rate} />
            <TextField label="Tenure" inputMode="numeric" suffix="months" value={form.tenure} onChange={set("tenure")} error={errors.tenure} />
            <DateField label="Loan date" value={form.start} onChange={set("start")} error={errors.start} />
            <TextField label="Customer name" optional value={form.name} onChange={set("name")} hint="Only for the printed estimate." />
            <TextField label="Phone" optional type="tel" value={form.phone} onChange={set("phone")} />
          </form>
        </Card>
        <Card title="Estimate">
          {result ? (
            <div className="stack" aria-live="polite">
              <SummaryList rows={[
                { label: "Interest per day", value: formatINR(result.perDay) },
                { label: "Equivalent monthly rate", value: `${result.perMonth} % a month` },
                { label: `Interest by ${formatDay(result.maturity)}`, value: formatINR(result.atMaturity.totalInterest) },
                result.atMaturity.compoundings ? { label: "Compounded into principal", value: formatINR(subtract(result.atMaturity.principal, result.principal)) } : null,
                { label: "Total to repay at the end of the tenure", value: formatINR(result.atMaturity.total), total: true },
              ]} />
              <table className="table">
                <caption>Amount due if the loan is closed after</caption>
                <thead><tr><th scope="col">After</th><th scope="col">Date</th><th scope="col" className="num">Interest</th><th scope="col" className="num">Total due</th></tr></thead>
                <tbody>
                  {result.schedule.map((row) => (
                    <tr key={row.months}>
                      <th scope="row">{row.months} month{row.months === 1 ? "" : "s"}</th>
                      <td>{formatDay(row.date)}</td>
                      <td className="num">{formatINR(row.totalInterest)}</td>
                      <td className="num">{formatINR(row.total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Banner tone="info">Estimate only, assuming no payments. Days are counted including the loan date, and interest compounds once a year.</Banner>
            </div>
          ) : (
            <p className="muted">Enter the loan amount to see the estimate.</p>
          )}
        </Card>
      </div>
      {result ? (
        <div className="print-only">
          <article className="sheet">
            <Letterhead branch={letterhead} title="Loan estimate" />
            <Fields rows={[
              ["Customer", form.name || "—"], ["Phone", form.phone || "—"], ["Loan date", formatDay(form.start)],
              ["Loan amount", formatINR(result.principal)], ["Interest rate", `${result.rate} % p.a.`], ["Tenure", `${result.tenure} months`],
              ["Interest per day", formatINR(result.perDay)], ["Interest for the tenure", formatINR(result.atMaturity.totalInterest)],
              result.atMaturity.compoundings ? ["Of which compounded", formatINR(subtract(result.atMaturity.principal, result.principal))] : null,
              ["Maturity date", formatDay(result.maturity)],
            ]} />
            <div className="sheet-total"><span>Total to repay at maturity</span><strong>{formatINR(result.atMaturity.total)}</strong></div>
            <Signatures left="Customer" />
          </article>
        </div>
      ) : null}
    </div>
  );
}
