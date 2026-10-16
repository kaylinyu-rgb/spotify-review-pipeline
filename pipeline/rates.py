"""Editable price table -> cost. item_cost = billed_units x price_per_unit; total = sum(item_cost).

Billing items are mutually exclusive: input (uncached), cached_input, cache_write, output.
Unknown prices stay unknown (None) - they are never silently turned into zero.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .config import ROOT

DEFAULT_RATES = ROOT / "cost" / "rates.csv"
ITEMS = ("input", "cached_input", "cache_write", "output")


def load_rates(path: Path = DEFAULT_RATES, multiplier: float = 1.0) -> dict:
    rates = {}
    with Path(path).open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            price = r["price_usd"].strip()
            rates[(r["provider"], r["model"], r["item"])] = {
                "price": float(price) * multiplier if price else None, "unit": r["unit"],
                "status": r["status"], "source": r["source_url"], "checked": r["checked_date"]}
    return rates


def per_unit(rate: dict) -> float | None:
    if rate is None or rate["price"] is None:
        return None
    if rate["unit"] == "per_1M_tokens":
        return rate["price"] / 1_000_000
    if rate["unit"] in ("per_call", "per_request", "per_token"):
        return rate["price"]
    raise ValueError("Unknown unit " + rate["unit"])


def cost(provider: str, model: str, usage: dict, rates: dict) -> tuple[float | None, list[dict]]:
    """Return (total or None if any billed item has unknown price, itemised lines)."""
    lines, total, unknown = [], 0.0, False
    for item in ITEMS:
        units = int(usage.get(item, 0) or 0)
        if not units:
            continue
        r = rates.get((provider, model, item))
        pu = per_unit(r)
        if pu is None:
            unknown = True
            lines.append({"item": item, "units": units, "price_per_unit": None, "cost": None})
        else:
            c = units * pu
            total += c
            lines.append({"item": item, "units": units, "price_per_unit": pu, "cost": c})
    return (None if unknown else total), lines


def worst_case(provider, model, input_tokens_est, max_output_tokens, rates) -> float:
    """Reservation for an in-flight call: all input uncached + the full output cap."""
    pin = per_unit(rates.get((provider, model, "input"))) or 0.0
    pout = per_unit(rates.get((provider, model, "output"))) or 0.0
    return input_tokens_est * pin + max_output_tokens * pout
