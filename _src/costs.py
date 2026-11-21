"""Cost arithmetic on the stated annual prices, without guessing missing plans."""
from __future__ import annotations

from decimal import Decimal


def annual_cost(first: str, later: str, years: int) -> str:
    if years < 1:
        raise ValueError('need at least one year')
    total = Decimal(first.removeprefix('$')) + (years - 1) * Decimal(later.removeprefix('$'))
    return f'${total:.2f}'


def planned_cost(years: int, updates: bool) -> str:
    if years < 1:
        raise ValueError('need at least one year')
    return f'${39 + (19 * (years - 1) if updates else 0):.2f}'
