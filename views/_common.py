"""Wspólne pomocnicze funkcje dla widoków Streamlit."""
from __future__ import annotations
import pandas as pd
import streamlit as st

from rinf.models import Parameter


# Pełna lista technicznych kolumn (ukryte domyślnie)
TECH_COLUMNS = ["IsApplicable", "Surowa wartość", "OptionalValue", "Set"]


def params_to_dataframe(params: list[Parameter]) -> pd.DataFrame:
    """Konwertuje listę obiektów Parameter na DataFrame do wyświetlania."""
    rows = []
    for p in params:
        rows.append({
            "Grupa": p.group_pl,
            "RINF": p.rinf_index or "",
            "ID": p.id,
            "Nazwa": p.name_pl,
            "Wartość": p.display,
            "Jednostka": p.unit or "",
            "Opis": p.description or "",
            "IsApplicable": p.is_applicable,
            "Surowa wartość": p.value or "",
            "OptionalValue": p.optional_value or "",
            "Set": p.set_context or "",
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["Grupa", "RINF"]).reset_index(drop=True)


def _style_value(val: str) -> str:
    """Kolorowanie tekstu w komórce 'Wartość' wg semantyki."""
    if not isinstance(val, str) or not val:
        return ""
    v = val.strip()
    if v == "n/d":
        return "color: #999999; font-style: italic;"
    if v == "brak danych":
        return "color: #b58900; font-style: italic;"
    if v == "TAK":
        return "color: #2e7d32; font-weight: bold;"
    if v == "NIE":
        return "color: #c62828; font-weight: bold;"
    if v.startswith("TAK") or v.startswith("NIE"):
        return "color: #c62828; font-weight: bold;" if v.startswith("NIE") else "color: #2e7d32; font-weight: bold;"
    return "font-weight: 600;"   # konkretna wartość


def render_params_table(
    params: list[Parameter],
    key: str | None = None,
    show_filters: bool = True,
) -> None:
    """Renderuje pełną tabelę parametrów z filtrem grupy i toggle 'pokaż wszystkie'."""
    df = params_to_dataframe(params)
    if df.empty:
        st.info("Brak parametrów.")
        return

    # Toggle pod tabelą: pokazać n/d? pokazać techniczne kolumny?
    if show_filters:
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            show_na = st.checkbox("Pokaż n/d", value=False, key=f"{key}_show_na", help="Pokaż parametry oznaczone jako 'nie dotyczy'")
        with c2:
            show_tech = st.checkbox("Tryb techniczny", value=False, key=f"{key}_show_tech", help="Pokaż surowe wartości XML, IsApplicable, Set, OptionalValue")
        with c3:
            groups = sorted(df["Grupa"].unique())
            selected = st.multiselect("Grupy:", groups, default=groups, key=f"{key}_groups")
        df = df[df["Grupa"].isin(selected)]
    else:
        show_na = False
        show_tech = False

    if not show_na:
        df = df[df["Wartość"].astype(str).str.strip() != "n/d"]

    if not show_tech:
        df = df.drop(columns=[c for c in TECH_COLUMNS if c in df.columns])

    if df.empty:
        st.caption("Brak wyników po zastosowaniu filtrów.")
        return

    # Styl: kolorowanie kolumny "Wartość"
    styled = df.style.map(_style_value, subset=["Wartość"])

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Grupa": st.column_config.TextColumn(width="medium"),
            "RINF": st.column_config.TextColumn(width="small"),
            "ID": st.column_config.TextColumn(width="small"),
            "Nazwa": st.column_config.TextColumn(width="large"),
            "Wartość": st.column_config.TextColumn(width="medium"),
            "Jednostka": st.column_config.TextColumn(width="small"),
            "Opis": st.column_config.TextColumn(width="large"),
            "IsApplicable": st.column_config.TextColumn(width="small"),
            "Surowa wartość": st.column_config.TextColumn(width="small"),
            "OptionalValue": st.column_config.TextColumn(width="medium"),
            "Set": st.column_config.TextColumn(width="medium"),
        },
    )
    st.caption(f"Wyświetlono {len(df)} parametrów" + (" (n/d ukryte)" if not show_na else "") + (" — tryb techniczny" if show_tech else ""))


def require_dataset():
    """Sprawdza czy dataset jest wczytany, zwraca go lub kończy widok."""
    ds = st.session_state.get("rinf_dataset")
    if ds is None:
        st.info("Wczytaj plik RINF w widoku 'Plik / Statystyki' (sidebar po lewej).")
        st.stop()
    return ds
