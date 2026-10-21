import { forwardRef, useId } from "react";
import { Icon } from "./Icon.jsx";

function describedBy(...ids) {
  const value = ids.filter(Boolean).join(" ");
  return value || undefined;
}

/** Label + control + hint + error, wired together for assistive technology. */
function FieldShell({ id, label, hint, error, optional, children, className = "" }) {
  return (
    <div className={`field ${className}`}>
      <label className="field-label" htmlFor={id}>
        {label}
        {optional ? <span className="optional"> (optional)</span> : null}
      </label>
      {children}
      {hint ? (
        <p className="field-hint" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className="field-error" id={`${id}-error`}>
          <Icon name="alertCircle" />
          <span>{error}</span>
        </p>
      ) : null}
    </div>
  );
}

function useFieldIds(id, hint, error, affixes = []) {
  const generated = useId();
  const fieldId = id ?? generated;
  return {
    fieldId,
    aria: {
      "aria-invalid": error ? true : undefined,
      "aria-describedby": describedBy(...affixes.map((a) => a && `${fieldId}-${a}`), hint && `${fieldId}-hint`, error && `${fieldId}-error`),
    },
  };
}

export const TextField = forwardRef(function TextField(
  { id, label, hint, error, optional, className, prefix, suffix, ...input },
  ref,
) {
  const { fieldId, aria } = useFieldIds(id, hint, error, [prefix && "prefix", suffix && "suffix"]);
  const control = <input ref={ref} id={fieldId} className="input" required={!optional || undefined} {...aria} {...input} />;
  return (
    <FieldShell id={fieldId} label={label} hint={hint} error={error} optional={optional} className={className}>
      {prefix || suffix ? (
        <div className="affix">
          {prefix ? <span className="affix-prefix" id={`${fieldId}-prefix`}>{prefix}</span> : null}
          {control}
          {suffix ? <span className="affix-suffix" id={`${fieldId}-suffix`}>{suffix}</span> : null}
        </div>
      ) : (
        control
      )}
    </FieldShell>
  );
});

export const AmountField = forwardRef(function AmountField(props, ref) {
  return <TextField ref={ref} inputMode="decimal" autoComplete="off" prefix="₹" {...props} />;
});

export const WeightField = forwardRef(function WeightField(props, ref) {
  return <TextField ref={ref} inputMode="decimal" autoComplete="off" suffix="g" {...props} />;
});

export const DateField = forwardRef(function DateField(props, ref) {
  return <TextField ref={ref} type="date" {...props} />;
});

export const SelectField = forwardRef(function SelectField(
  { id, label, hint, error, optional, className, children, ...select },
  ref,
) {
  const { fieldId, aria } = useFieldIds(id, hint, error);
  return (
    <FieldShell id={fieldId} label={label} hint={hint} error={error} optional={optional} className={className}>
      <select ref={ref} id={fieldId} className="select" {...aria} {...select}>
        {children}
      </select>
    </FieldShell>
  );
});

export const TextareaField = forwardRef(function TextareaField(
  { id, label, hint, error, optional, className, ...textarea },
  ref,
) {
  const { fieldId, aria } = useFieldIds(id, hint, error);
  return (
    <FieldShell id={fieldId} label={label} hint={hint} error={error} optional={optional} className={className}>
      <textarea ref={ref} id={fieldId} className="textarea" required={!optional || undefined} {...aria} {...textarea} />
    </FieldShell>
  );
});

export function CheckboxField({ id, label, hint, error, checked, onChange, ...rest }) {
  const { fieldId, aria } = useFieldIds(id, hint, error);
  return (
    <div className="field">
      <label className="check" htmlFor={fieldId}>
        <input id={fieldId} type="checkbox" checked={checked} onChange={onChange} {...aria} {...rest} />
        <span>{label}</span>
      </label>
      {hint ? <p className="field-hint" id={`${fieldId}-hint`}>{hint}</p> : null}
      {error ? (
        <p className="field-error" id={`${fieldId}-error`}>
          <Icon name="alertCircle" />
          <span>{error}</span>
        </p>
      ) : null}
    </div>
  );
}

/** Focus the first invalid control after a failed submit (WCAG 3.3.1). */
export function focusFirstError(form) {
  const invalid = form?.querySelector('[aria-invalid="true"]');
  invalid?.focus();
}
