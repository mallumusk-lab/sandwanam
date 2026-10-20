import { useId, useState } from "react";
import { ITEM_TYPES, addItem, totalQuantity } from "../../lib/items.js";
import { Button, IconButton } from "../../ui/controls.jsx";
import { Icon } from "../../ui/Icon.jsx";

const OTHER = "__other__";

/** Pledged items: pick a type (or type a name), set quantities, remove lines. */
export function ItemsEditor({ items, onChange, error }) {
  const ids = useId();
  const [type, setType] = useState(ITEM_TYPES[0]);
  const [custom, setCustom] = useState("");
  const [qty, setQty] = useState("1");
  const [localError, setLocalError] = useState("");

  const add = () => {
    const name = type === OTHER ? custom.trim() : type;
    const quantity = Number(qty);
    if (!name) return setLocalError("Type the item name.");
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 999) return setLocalError("Quantity must be 1 to 999.");
    setLocalError("");
    onChange(addItem(items, name, quantity));
    setCustom("");
    setQty("1");
  };

  // These inputs sit inside the loan form: Enter adds the item instead of submitting the loan.
  const addOnEnter = (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      add();
    }
  };

  const change = (index, delta) =>
    onChange(items.map((item, i) => (i === index ? { ...item, qty: Math.min(999, Math.max(1, item.qty + delta)) } : item)));

  const shownError = localError || error;
  return (
    <fieldset className="stack stack-sm" aria-describedby={shownError ? `${ids}-error` : undefined}>
      <legend>Pledged items</legend>
      <div className="grid grid-tight">
        <div className="field">
          <label className="field-label" htmlFor={`${ids}-type`}>Item</label>
          <select id={`${ids}-type`} className="select" value={type} onChange={(e) => setType(e.target.value)}
            aria-invalid={shownError ? true : undefined} aria-describedby={shownError ? `${ids}-error` : undefined}>
            {ITEM_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
            <option value={OTHER}>Other…</option>
          </select>
        </div>
        {type === OTHER ? (
          <div className="field">
            <label className="field-label" htmlFor={`${ids}-custom`}>Item name</label>
            <input id={`${ids}-custom`} className="input" maxLength={60} value={custom} onChange={(e) => setCustom(e.target.value)}
              onKeyDown={addOnEnter} />
          </div>
        ) : null}
        <div className="field">
          <label className="field-label" htmlFor={`${ids}-qty`}>Quantity</label>
          <input id={`${ids}-qty`} className="input" inputMode="numeric" value={qty}
            onChange={(e) => setQty(e.target.value.replace(/\D/g, "").slice(0, 3))} onKeyDown={addOnEnter} />
        </div>
        <div className="field">
          <span className="field-label" aria-hidden="true">&nbsp;</span>
          <Button icon="plus" onClick={add}>Add item</Button>
        </div>
      </div>
      {items.length ? (
        <ul className="item-list">
          {items.map((item, index) => (
            <li key={item.name}>
              <span className="item-name">{item.name}</span>
              <span className="cluster cluster-sm">
                <IconButton icon="minus" label={`One fewer ${item.name}`} disabled={item.qty <= 1} onClick={() => change(index, -1)} />
                <span className="num" aria-live="polite" aria-label={`${item.qty} ${item.name}`}>{item.qty}</span>
                <IconButton icon="plus" label={`One more ${item.name}`} onClick={() => change(index, 1)} />
                <IconButton icon="trash" label={`Remove ${item.name}`} onClick={() => onChange(items.filter((_, i) => i !== index))} />
              </span>
            </li>
          ))}
          <li className="item-total">
            <span>Total items</span>
            <strong className="num">{totalQuantity(items)}</strong>
          </li>
        </ul>
      ) : (
        <p className="field-hint">No items added yet.</p>
      )}
      {shownError ? (
        <p className="field-error" id={`${ids}-error`}>
          <Icon name="alertCircle" />
          <span>{shownError}</span>
        </p>
      ) : null}
    </fieldset>
  );
}
