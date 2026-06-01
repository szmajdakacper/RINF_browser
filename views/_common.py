"""Wspolne pomocnicze funkcje dla widokow Streamlit."""
from __future__ import annotations
import pandas as pd
import streamlit as st

from rinf.models import Parameter


def params_to_dataframe(params: list[Parameter]) -> pd.DataFrame:
    """Konwertuje liste obiektow Parameter na DataFrame do wyswietlania."""
    rows = []
    for p in params:
        rows.append({
            "Grupa": p.group_pl,
            "RINF": p.rinf_index or "",
            "ID": p.id,
            "Nazwa": p.name_pl,
            "Wartosc": p.display,
            "IsApplicable": p.is_applicable,
            "Surowa wartosc": p.value or "",
            "OptionalValue": p.optional_value or "",
            "Set": p.set_context or "",
            "Jednostka": p.unit or "",
            "Opis": p.description or "",
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Sortuj po grupie i RINF
    return df.sort_values(["Grupa", "RINF"]).reset_index(drop=True)


def render_params_table(params: list[Parameter], key: str | None = None, hide_empty: bool = False) -> None:
    """Renderuje pelna tabele parametrow z filtrem grupy."""
    df = params_to_dataframe(params)
    if df.empty:
        st.info("Brak parametrow.")
        return
    if hide_empty:
        df = df[df["Wartosc"].astype(str).str.strip() != ""]
    # Filtr grupy
    groups = sorted(df["Grupa"].unique())
    selected = st.multiselect("Grupy parametrow:", groups, default=groups, key=key)
    df = df[df["Grupa"].isin(selected)]
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Grupa": st.column_config.TextColumn(width="medium"),
            "RINF": st.column_config.TextColumn(width="small"),
            "ID": st.column_config.TextColumn(width="small"),
            "Nazwa": st.column_config.TextColumn(width="large"),
            "Wartosc": st.column_config.TextColumn(width="medium"),
            "IsApplicable": st.column_config.TextColumn(width="small"),
            "Surowa wartosc": st.column_config.TextColumn(width="small"),
            "OptionalValue": st.column_config.TextColumn(width="medium"),
            "Set": st.column_config.TextColumn(width="medium"),
            "Jednostka": st.column_config.TextColumn(width="small"),
            "Opis": st.column_config.TextColumn(width="large"),
        },
    )


def require_dataset():
    """Sprawdza czy dataset jest wczytany, zwraca go lub konczy widok."""
    ds = st.session_state.get("rinf_dataset")
    if ds is None:
        st.info("Wczytaj plik RINF w widoku 'Plik' (sidebar po lewej).")
        st.stop()
    return ds
