"""Slownik wszystkich parametrow RINF + histogram wystapien."""
from __future__ import annotations
import streamlit as st
import pandas as pd
from collections import Counter

from views._common import require_dataset
from rinf.dictionary import parameter_dictionary, enum_codes


def render():
    st.header("Przegladarka parametrow RINF")
    ds = require_dataset()

    pd_dict = parameter_dictionary()
    rows = []
    for pid, info in pd_dict.items():
        rows.append({
            "Grupa": info.get("group_pl") or "",
            "RINF": info.get("rinf_index") or "",
            "ID": pid,
            "Nazwa": info.get("name_pl") or pid,
            "Jednostka": info.get("unit") or "",
            "Opis": info.get("description") or "",
        })
    df = pd.DataFrame(rows).sort_values(["Grupa", "RINF"]).reset_index(drop=True)

    st.markdown(f"Slownik zawiera **{len(df)}** parametrow RINF.")
    groups = sorted(df["Grupa"].unique())
    selected = st.multiselect("Filtr grup:", groups, default=groups)
    flt = df[df["Grupa"].isin(selected)]
    st.dataframe(flt, use_container_width=True, hide_index=True, height=400)

    st.divider()
    st.subheader("Analiza wystapien wybranego parametru")

    pid = st.selectbox("Wybierz parametr (XML ID):", sorted(df["ID"].tolist()))
    if not pid:
        return

    # Zlicz wystapienia w SOL i OP
    sol_values: list[str] = []
    op_values: list[str] = []
    for s in ds.sections_of_line:
        for t in s.tracks:
            for p in t.parameters:
                if p.id == pid:
                    sol_values.append(p.display)
    for op in ds.operational_points:
        for t in op.tracks:
            for p in t.parameters:
                if p.id == pid:
                    op_values.append(p.display)
        for sid in op.sidings:
            for p in sid.parameters:
                if p.id == pid:
                    op_values.append(p.display)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Wystapienia w SOLTrackParameter:** {len(sol_values)}")
        c = Counter(sol_values)
        if c:
            top = pd.DataFrame(c.most_common(50), columns=["Wartosc", "Liczba"])
            st.dataframe(top, use_container_width=True, hide_index=True)
    with c2:
        st.markdown(f"**Wystapienia w OP (track + siding):** {len(op_values)}")
        c = Counter(op_values)
        if c:
            top = pd.DataFrame(c.most_common(50), columns=["Wartosc", "Liczba"])
            st.dataframe(top, use_container_width=True, hide_index=True)

    # Pokaz slownik enum jezeli istnieje
    enums = enum_codes().get(pid)
    if enums:
        st.markdown(f"**Slownik kodow `{pid}`:**")
        st.dataframe(pd.DataFrame(enums.items(), columns=["Kod", "Opis"]), use_container_width=True, hide_index=True)
