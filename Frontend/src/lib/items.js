// Pledged items. Structured items ({ name, qty }) are what the API stores.

export const ITEM_TYPES = ["Chain", "Ring", "Bangle", "Necklace", "Earrings", "Coin"];

export function totalQuantity(items) {
  return items.reduce((sum, item) => sum + (Number(item.qty) || 0), 0);
}

export function itemsText(items) {
  return items.map((item) => `${item.name}(${item.qty})`).join(", ");
}

export function itemsError(items) {
  if (!items.length) return "Add at least one pledged item.";
  for (const item of items) {
    if (!String(item.name ?? "").trim()) return "Every item needs a name.";
    const qty = Number(item.qty);
    if (!Number.isInteger(qty) || qty < 1 || qty > 999) return "Quantities must be whole numbers from 1 to 999.";
  }
  return "";
}

/** Add an item, merging with an existing line of the same name. */
export function addItem(items, name, qty = 1) {
  const clean = String(name).trim().replace(/\s+/g, " ");
  const existing = items.findIndex((item) => item.name.toLowerCase() === clean.toLowerCase());
  if (existing >= 0) {
    return items.map((item, index) => (index === existing ? { ...item, qty: Math.min(999, item.qty + qty) } : item));
  }
  return [...items, { name: clean, qty }];
}
