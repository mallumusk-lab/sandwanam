"""Pledged items.

Structured items ({"name", "qty"}) stored in `loan_data.items` are the source of truth.
The legacy text column `particulars` ("Chain(1), Ring(2)") is kept for display and is
written with ", " between items. The legacy writers used both "," and ", ", so the
parser accepts either, plus the oldest "2 Ring" style.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

_ITEM = re.compile(r"^(?P<name>.+?)\s*\((?P<qty>\d+)\)$")
_QTY_FIRST = re.compile(r"^(?P<qty>\d+)\s+(?P<name>\D.*)$")  # oldest format: "2 Ring"
MAX_ITEMS = 50
MAX_NAME = 60
MAX_QTY = 999


@dataclass(frozen=True)
class Item:
    name: str
    qty: int

    def as_dict(self) -> dict:
        return {"name": self.name, "qty": self.qty}


class ItemsError(ValueError):
    pass


def parse_legacy(text: str | None) -> list[Item]:
    if not text:
        return []
    items: list[Item] = []
    for part in text.split(","):
        chunk = part.strip()
        if not chunk:
            continue
        match = _ITEM.match(chunk) or _QTY_FIRST.match(chunk)
        if match:
            items.append(Item(match["name"].strip(), max(1, int(match["qty"]))))
        else:
            items.append(Item(chunk, 1))
    return items


def to_display(items: Iterable[Item]) -> str:
    return ", ".join(f"{item.name}({item.qty})" for item in items)


def total_quantity(items: Iterable[Item]) -> int:
    return sum(item.qty for item in items)


def validate(raw: Sequence[object]) -> list[Item]:
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ItemsError("Add at least one pledged item.")
    if len(raw) > MAX_ITEMS:
        raise ItemsError(f"A loan can have at most {MAX_ITEMS} item lines.")
    items: list[Item] = []
    for entry in raw:
        if isinstance(entry, Item):
            name, qty = entry.name, entry.qty
        elif isinstance(entry, dict):
            name, qty = entry.get("name"), entry.get("qty")
        else:
            raise ItemsError("Each item needs a name and a quantity.")
        if not isinstance(name, str) or not name.strip():
            raise ItemsError("Each item needs a name.")
        name = " ".join(name.split())
        if len(name) > MAX_NAME or not name.isprintable():
            raise ItemsError(f"Item names must be printable and at most {MAX_NAME} characters.")
        if isinstance(qty, bool) or not isinstance(qty, int) or not 1 <= qty <= MAX_QTY:
            raise ItemsError(f"Quantities must be whole numbers from 1 to {MAX_QTY}.")
        items.append(Item(name, qty))
    return items
