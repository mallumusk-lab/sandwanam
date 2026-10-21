import { useEffect, useState } from "react";
import { settings } from "../../api/endpoints.js";
import { useAsync, useDocumentTitle } from "../../hooks/useAsync.js";
import { formatDateTime } from "../../lib/dates.js";
import { amountError, formatINR, normaliseAmount } from "../../lib/money.js";
import { Button } from "../../ui/controls.jsx";
import { ErrorState, SkeletonRows, useToast } from "../../ui/feedback.jsx";
import { AmountField } from "../../ui/fields.jsx";
import { Card, Details, PageHeader } from "../../ui/surfaces.jsx";

export default function SettingsPage() {
  useDocumentTitle("Gold rate");
  const toast = useToast();
  const { data, error, reload } = useAsync((signal) => settings.goldRate({ signal }), []);
  const [value, setValue] = useState("");
  const [problem, setProblem] = useState("");
  const [pending, setPending] = useState(false);
  const current = data?.gold_rate;

  useEffect(() => {
    if (current) setValue(current.per_gram);
  }, [current]);

  const save = async (event) => {
    event.preventDefault();
    const issue = amountError(value, { label: "Gold rate" });
    if (issue) return setProblem(issue);
    setPending(true);
    setProblem("");
    try {
      await settings.setGoldRate(normaliseAmount(value));
      toast.success("Gold rate updated", `${formatINR(normaliseAmount(value))} per gram`);
      reload();
    } catch (err) {
      setProblem(err.message);
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="page narrow">
      <PageHeader title="Gold rate" description="Used for loan-to-value figures on the dashboard. Update it each morning." />
      <div className="stack stack-lg">
        <Card title="Current rate">
          {error ? <ErrorState error={error} onRetry={reload} /> : !data ? <SkeletonRows rows={2} /> : current ? (
            <Details items={[["Per gram", formatINR(current.per_gram)], ["Updated", formatDateTime(current.updated_at)], ["By", current.updated_by]]} />
          ) : (
            <p className="muted">No rate has been set yet.</p>
          )}
        </Card>
        <Card title="Set today's rate">
          <form className="stack" onSubmit={save} noValidate>
            <AmountField label="Rate per gram" value={value} onChange={(e) => setValue(e.target.value)} error={problem}
              hint="The rate your branches lend against, per gram of net weight." />
            <div className="form-actions"><Button type="submit" variant="primary" loading={pending}>Save rate</Button></div>
          </form>
        </Card>
      </div>
    </div>
  );
}
