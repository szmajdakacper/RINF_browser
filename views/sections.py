"""Widok odcinków linii — SOL z wszystkimi parametrami (per kierunek)."""
from __future__ import annotations
import streamlit as st
import pandas as pd

from views._common import require_dataset, render_params_table


def _sols_dataframe(ds) -> pd.DataFrame:
    rows = []
    for s in ds.sections_of_line:
        start = ds.op_by_id.get(s.op_start_id)
        end = ds.op_by_id.get(s.op_end_id)
        # Wyciągnij V_max z pierwszego toru
        vmax = ""
        voltage = ""
        for t in s.tracks:
            for p in t.parameters:
                if p.id == "IPP_MaxSpeed" and p.value:
                    vmax = p.value
                if p.id == "ECS_VoltFreq" and p.value:
                    voltage = p.value
            if vmax:
                break
        rows.append({
            "Linia ID": s.line_id,
            "Nr PL": s.line_number_pl,
            "Początek": start.name if start else s.op_start_id,
            "Koniec": end.name if end else s.op_end_id,
            "Długość [km]": s.length_km,
            "V_max": vmax,
            "Zasilanie": voltage,
            "Tory": len(s.tracks),
            "Natura": s.nature_label,
        })
    return pd.DataFrame(rows)


def _quick_sol_summary(sol, ds):
    """Streszczenie kluczowych parametrów odcinka — pasek u góry."""
    # Zbierz wybrane parametry z dowolnego toru (zazwyczaj identyczne)
    vmax = lcat = volt = sys_type = etcs_lvl = etcs_comp = klasa_b = gsmr = brake_dist = ""
    for t in sol.tracks:
        for p in t.parameters:
            if p.id == "IPP_MaxSpeed":
                vmax = p.display
            elif p.id == "IPP_LoadCap":
                lcat = p.display
            elif p.id == "ECS_VoltFreq":
                volt = p.display
            elif p.id == "ECS_SystemType":
                sys_type = p.display
            elif p.id == "CPE_Level":
                etcs_lvl = p.display
            elif p.id == "CPE_SystemCompatibility":
                etcs_comp = p.display
            elif p.id == "CPO_LegacyTrainProtection":
                klasa_b = p.display
            elif p.id == "CRG_RadioCompVoice":
                gsmr = p.display
            elif p.id == "CBP_MaxBrakeDist":
                brake_dist = p.display

    # Wyświetl 2 wiersze metryk
    cols = st.columns(5)
    cols[0].metric("V max", vmax or "—")
    cols[1].metric("Kategoria linii", lcat or "—")
    cols[2].metric("Zasilanie", volt or "—")
    cols[3].metric("Maks. droga ham.", brake_dist or "—")
    cols[4].metric("Tory", len(sol.tracks))

    cols = st.columns(5)
    cols[0].metric("ETCS", etcs_lvl if etcs_lvl and etcs_lvl != "n/d" else "—")
    cols[1].metric("GSM-R głos", gsmr if gsmr and gsmr != "n/d" else "—")
    cols[2].metric("Klasa B", klasa_b if klasa_b and klasa_b != "n/d" else "—")
    cols[3].metric("Tunele", sum(len(t.tunnels) for t in sol.tracks))
    cols[4].metric("Geo punkty", sum(len(t.location_points) for t in sol.tracks))


def render():
    st.header("🛤️ Odcinki linii (SOL)")
    ds = require_dataset()

    if "sols_df" not in st.session_state or st.session_state.get("sols_df_hash") != ds.source_hash:
        st.session_state["sols_df"] = _sols_dataframe(ds)
        st.session_state["sols_df_hash"] = ds.source_hash
    df = st.session_state["sols_df"]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        f_line = st.text_input(
            "Nr linii zawiera",
            value=st.session_state.get("filter_sol_line", ""),
            key="filter_sol_line",
        ).strip().lower()
    with c2:
        f_start = st.text_input("Początek zawiera").strip().lower()
    with c3:
        f_end = st.text_input("Koniec zawiera").strip().lower()
    with c4:
        f_minlen = st.number_input("Min. długość [km]", value=0.0, step=1.0)

    filt = df.copy()
    if f_line:
        filt = filt[filt["Linia ID"].str.lower().str.contains(f_line, na=False) | filt["Nr PL"].str.contains(f_line, na=False)]
    if f_start:
        filt = filt[filt["Początek"].str.lower().str.contains(f_start, na=False)]
    if f_end:
        filt = filt[filt["Koniec"].str.lower().str.contains(f_end, na=False)]
    if f_minlen > 0:
        filt = filt[filt["Długość [km]"].fillna(0) >= f_minlen]

    st.caption(f"Znaleziono: **{len(filt)}** z {len(df)} odcinków")

    event = st.dataframe(
        filt,
        use_container_width=True,
        hide_index=True,
        height=350,
        on_select="rerun",
        selection_mode="single-row",
        key="sol_table_select",
    )

    selected_idx = None
    if event and event.selection and event.selection.rows:
        selected_idx = filt.index[event.selection.rows[0]]

    if selected_idx is None:
        if len(filt) > 0:
            st.info("👆 Kliknij wiersz w tabeli, aby zobaczyć szczegóły odcinka.")
        return

    sol = ds.sections_of_line[selected_idx]
    start_op = ds.op_by_id.get(sol.op_start_id)
    end_op = ds.op_by_id.get(sol.op_end_id)

    st.divider()
    st.subheader(f"🚆 Linia {sol.line_number_pl}: {start_op.name if start_op else sol.op_start_id} → {end_op.name if end_op else sol.op_end_id}")

    _quick_sol_summary(sol, ds)

    # Akcja: pokaż na mapie
    c_act = st.columns([1, 1, 4])
    with c_act[0]:
        if st.button("🗺️ Pokaż linię na mapie", key="show_on_map"):
            st.session_state["filter_map_line"] = sol.line_number_pl
            st.session_state["nav_target"] = "Mapa"
            st.rerun()
    with c_act[1]:
        if st.button("📄 Formularz zgodności", key="show_compat"):
            st.session_state["filter_compat_line"] = sol.line_number_pl
            st.session_state["filter_compat_start"] = sol.op_start_id
            st.session_state["filter_compat_end"] = sol.op_end_id
            st.session_state["nav_target"] = "Formularz zgodności"
            st.rerun()

    st.divider()

    # Nagłówek
    with st.expander("ℹ️ Dane administracyjne odcinka", expanded=False):
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**Linia (RINF):** `{sol.line_id}`")
        c1.markdown(f"**Numer (PL):** {sol.line_number_pl}")
        c1.markdown(f"**Zarządca (IM):** {sol.im_code}")
        c2.markdown(f"**Natura odcinka:** {sol.nature_label} (kod {sol.nature_code})")
        c2.markdown(f"**Długość:** {sol.length_km} km")
        c3.markdown(f"**Ważność od:** {sol.validity_start}")
        c3.markdown(f"**Ważność do:** {sol.validity_end}")

    if not sol.tracks:
        st.info("Brak torów na tym odcinku.")
        return

    tab_names = [f"Tor {t.identification} — {t.direction_label}" for t in sol.tracks]
    tab_names.append(f"Tunele ({sum(len(t.tunnels) for t in sol.tracks)})")
    tab_names.append(f"Lokalizacja (LocationPoint, {sum(len(t.location_points) for t in sol.tracks)})")
    tab_names.append("Raw")
    tabs = st.tabs(tab_names)

    for i, t in enumerate(sol.tracks):
        with tabs[i]:
            st.caption(
                f"Identyfikator toru: **{t.identification}**  |  "
                f"Kierunek RINF: **{t.direction_code}** ({t.direction_label})  |  "
                f"Parametrów: **{len(t.parameters)}**  |  "
                f"Tuneli: {len(t.tunnels)}  |  "
                f"Punktów geo: {len(t.location_points)}"
            )
            render_params_table(t.parameters, key=f"sol_{selected_idx}_track_{i}")

    # Tunele
    with tabs[len(sol.tracks)]:
        all_tunnels = [(t.identification, tu) for t in sol.tracks for tu in t.tunnels]
        if not all_tunnels:
            st.info("Brak tuneli na tym odcinku.")
        else:
            tun_labels = [f"Tor {trk_id}: Tunel {tu.identification}" for trk_id, tu in all_tunnels]
            idx_tu = st.selectbox("Wybierz tunel:", list(range(len(all_tunnels))), format_func=lambda i: tun_labels[i], key=f"sol_{selected_idx}_tun_sel")
            trk_id, tu = all_tunnels[idx_tu]
            if tu.start:
                st.caption(f"**Początek:** km {tu.start.kilometer}, lat {tu.start.latitude}, lon {tu.start.longitude}")
            if tu.end:
                st.caption(f"**Koniec:** km {tu.end.kilometer}, lat {tu.end.latitude}, lon {tu.end.longitude}")
            render_params_table(tu.parameters, key=f"sol_{selected_idx}_tunnel_{idx_tu}")

    # LocationPoint
    with tabs[len(sol.tracks) + 1]:
        rows = []
        for t in sol.tracks:
            for lp in t.location_points:
                rows.append({"Tor": t.identification, "km": lp.kilometer, "Szerokość": lp.latitude, "Długość": lp.longitude})
        if not rows:
            st.info("Brak punktów LocationPoint dla tego odcinka.")
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
