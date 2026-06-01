"""Pomocnicze funkcje formatowania wartosci."""
from __future__ import annotations
from typing import Iterable


def merge_param_values(values: Iterable[str]) -> str:
    """Laczy wartosci tego samego parametru z roznych torow/odcinkow.

    Logika identyczna jak format_value w fill_form.py:
      - jezeli sa konkretne wartosci, n/d / brak danych sa pomijane;
      - TAK/NIE traktowane jako informacyjne, sa zachowywane.
    """
    if not values:
        return ""
    vals = set(values)
    META = {"n/d", "brak danych"}
    concrete = sorted(v for v in vals if v not in META and v not in ("TAK", "NIE"))
    yn = sorted(v for v in vals if v in ("TAK", "NIE"))
    if concrete:
        return "; ".join(concrete + yn)
    if yn:
        return "; ".join(yn)
    if "brak danych" in vals:
        return "brak danych"
    if "n/d" in vals:
        return "n/d"
    return "; ".join(sorted(vals))


def format_km(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.3f} km"
