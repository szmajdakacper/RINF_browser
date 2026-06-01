"""Widok odcinkow linii - SOL z wszystkimi parametrami (per kierunek)."""
from __future__ import annotations
import streamlit as st
import pandas as pd

from views._common import require_dataset, render_params_table


def _sols_dataframe(ds) -> pd.DataFrame:
    rows = []
    for s in ds.sections_of_line:
        start = ds.op_by_id.get(s.op_start_id)
        end = ds.op_by_id.get(s.op_end_id)
        rows.append({
            "Linia ID": s.line_id,
            "Nr PL": s.line_number_pl,
            "Poczatek": start.name if start else s.op_start_id,
            "Start OPID": s.op_start_id,
            "Koniec": end.name if end else s.op_end_id,
            "End OPID": s.op_end_id,
            "Dlugosc [km]": s.length_km,
            "Natura": s.nature_label,
            "Tory": len(s.tracks),
        })
    return pd.DataFrame(rows)


def render():
    st.header("Odcinki linii (SOL)")
    ds = require_dataset()

    if "sols_df" not in st.session_state or st.session_state.get("sols_df_hash") != ds.source_hash:
        st.session_state["sols_df"] = _sols_dataframe(ds)
        st.session_state["sols_df_hash"] = ds.source_hash
    df = st.session_state["sols_df"]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        f_line = st.text_input("Nr linii zawiera").strip().lower()
    with c2:
        f_start = st.text_input("Poczatek zawiera").strip().lower()
    with c3:
        f_end = st.text_input("Koniec zawiera").strip().lower()
    with c4:
        f_minlen = st.number_input("Min. dlugosc [km]", value=0.0, step=0.5)

    filt = df.copy()
    if f_line:
        filt = filt[filt["Linia ID"].str.lower().str.contains(f_line, na=False) | filt["Nr PL"].str.contains(f_line, na=False)]
    if f_start:
        filt = filt[filt["Poczatek"].str.lower().str.contains(f_start, na=False)]
    if f_end:
        filt = filt[filt["Koniec"].str.lower().str.contains(f_end, na=False)]
    if f_minlen > 0:
        filt = filt[filt["Dlugosc [km]"].fillna(0) >= f_minlen]

    st.caption(f"Znaleziono: {len(filt)} z {len(df)} odcinkow")
    st.dataframe(filt, use_container_width=True, hide_index=True, height=300)

    if len(filt) == 0:
        return

    options = filt.index.tolist()
    labels = {i: f"{filt.loc[i, 'Linia ID']}: {filt.loc[i, 'Poczatek']} → {filt.loc[i, 'Koniec']} ({filt.loc[i, 'Dlugosc [km]']} km)" for i in options}
    sel = st.selectbox("Wybierz odcinek do podgladu", options, format_func=lambda i: labels[i])
    sol = ds.sections_of_line[sel]

    st.divider()
    start_op = ds.op_by_id.get(sol.op_start_id)
    end_op = ds.op_by_id.get(sol.op_end_id)
    st.subheader(f"{sol.line_id} | {start_op.name if start_op else sol.op_start_id} → {end_op.name if end_op else sol.op_end_id}")

    # Naglowek
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**Linia (RINF):** `{sol.line_id}`")
    c1.markdown(f"**Numer (PL):** {sol.line_number_pl}")
    c1.markdown(f"**Zarzadca (IM):** {sol.im_code}")
    c2.markdown(f"**Natura odcinka:** {sol.nature_label} (kod {sol.nature_code})")
    c2.markdown(f"**Dlugosc:** {sol.length_km} km")
    c3.markdown(f"**Waznosc od:** {sol.validity_start}")
    c3.markdown(f"**Waznosc do:** {sol.validity_end}")

    # Zakladki: tor po torze
    if not sol.tracks:
        st.info("Brak torow.")
        return

    tab_names = [f"Tor {t.identification} - {t.direction_label}" for t in sol.tracks]
    tab_names.append("Wszystkie tunele")
    tab_names.append("LocationPoint")
    tab_names.append("Raw")
    tabs = st.tabs(tab_names)

    for i, t in enumerate(sol.tracks):
        with tabs[i]:
            st.caption(f"Identyfikator toru: {t.identification} | kierunek RINF: {t.direction_code} ({t.direction_label})")
            st.caption(f"Waznosc: {t.validity_start} → {t.validity_end}  |  Parametrow: {len(t.parameters)}  |  Tuneli: {len(t.tunnels)}  |  LocationPoint: {len(t.location_points)}")
            render_params_table(t.parameters, key=f"sol_{sel}_track_{i}")

    # Wszystkie tunele
    with tabs[len(sol.tracks)]:
        all_tunnels = [(t.identification, tu) for t in sol.tracks for tu in t.tunnels]
        if not all_tunnels:
            st.info("Brak tuneli na tym odcinku.")
        for trk_id, tu in all_tunnels:
            with st.expander(f"Tunel {tu.identification} (tor {trk_id})"):
                if tu.start:
                    st.caption(f"Poczatek: km {tu.start.kilometer}, lat {tu.start.latitude}, lon {tu.start.longitude}")
                if tu.end:
                    st.caption(f"Koniec: km {tu.end.kilometer}, lat {tu.end.latitude}, lon {tu.end.longitude}")
                render_params_table(tu.parameters, key=f"sol_{sel}_tunnel_{tu.identification}_{trk_id}")

    # LocationPoint
    with tabs[len(sol.tracks) + 1]:
        rows = []
        for t in sol.tracks:
            for lp in t.location_points:
                rows.append({"Tor": t.identification, "km": lp.kilometer, "Lat": lp.latitude, "Lon": lp.longitude})
        if not rows:
            st.info("Brak LocationPoint dla tego odcinka.")
        else:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=300)

    # Raw
    with tabs[len(sol.tracks) + 2]:
        st.json({
            "line_id": sol.line_id,
            "line_number_pl": sol.line_number_pl,
            "im_code": sol.im_code,
            "nature": (sol.nature_code, sol.nature_label),
            "op_start_id": sol.op_start_id,
            "op_end_id": sol.op_end_id,
            "length_km": sol.length_km,
            "tracks": [{"id": t.identification, "direction": t.direction_label, "params": len(t.parameters)} for t in sol.tracks],
        })
