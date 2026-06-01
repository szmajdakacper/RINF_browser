"""Widok punktów eksploatacyjnych — pełne dane OP."""
from __future__ import annotations
import streamlit as st
import pandas as pd

from views._common import require_dataset, render_params_table


def _ops_dataframe(ds) -> pd.DataFrame:
    rows = []
    for op in ds.operational_points:
        geo = op.geographic or None
        rl = op.railway_location or None
        # Liczba peronów = suma platformów po wszystkich torach
        platforms_count = sum(len(t.platforms) for t in op.tracks)
        rows.append({
            "Nazwa": op.name,
            "UniqueOPID": op.unique_id,
            "TAF/TAP": op.taf_tap or "",
            "Typ": op.op_type_label,
            "Lat": geo.latitude if geo else None,
            "Lon": geo.longitude if geo else None,
            "Linia (Nat.)": rl.national_ident_num if rl else "",
            "km": rl.kilometer if rl else None,
            "Tory": len(op.tracks),
            "Perony": platforms_count,
            "Bocznice": len(op.sidings),
        })
    return pd.DataFrame(rows)


def _quick_metrics(op, ds):
    """Pasek metryk na górze szczegółów OP."""
    platforms_count = sum(len(t.platforms) for t in op.tracks)
    sols_count = len(ds.op_to_sols.get(op.unique_id, []))

    # Zakres długości peronów
    plat_lens = []
    plat_heights = []
    for t in op.tracks:
        for pl in t.platforms:
            for p in pl.parameters:
                if p.id == "IPL_Length" and p.value:
                    try:
                        plat_lens.append(int(p.value))
                    except ValueError:
                        pass
                if p.id == "IPL_Height" and p.value:
                    try:
                        plat_heights.append(int(p.value))
                    except ValueError:
                        pass

    cols = st.columns(5)
    cols[0].metric("Tory", len(op.tracks))
    cols[1].metric("Perony", platforms_count)
    cols[2].metric("Bocznice", len(op.sidings))
    cols[3].metric("Odcinków SOL", sols_count)
    if plat_lens:
        cols[4].metric("Perony — długość", f"{min(plat_lens)}–{max(plat_lens)} m")


def _mini_map(op):
    """Mała mapka folium z markerem na pozycji OP."""
    if not (op.geographic and op.geographic.latitude and op.geographic.longitude):
        return
    try:
        import folium
        from streamlit_folium import st_folium
        m = folium.Map(location=[op.geographic.latitude, op.geographic.longitude], zoom_start=13, tiles="OpenStreetMap")
        folium.Marker(
            location=[op.geographic.latitude, op.geographic.longitude],
            popup=op.name,
            tooltip=op.name,
            icon=folium.Icon(color="blue", icon="train", prefix="fa"),
        ).add_to(m)
        st_folium(m, height=280, returned_objects=[], key=f"map_{op.unique_id}")
    except ImportError:
        st.caption("Mapa wymaga `streamlit-folium`.")


def render():
    st.header("📍 Punkty eksploatacyjne (OP)")
    ds = require_dataset()

    if "ops_df" not in st.session_state or st.session_state.get("ops_df_hash") != ds.source_hash:
        st.session_state["ops_df"] = _ops_dataframe(ds)
        st.session_state["ops_df_hash"] = ds.source_hash
    df = st.session_state["ops_df"]

    c1, c2, c3 = st.columns(3)
    with c1:
        f_name = st.text_input(
            "Nazwa zawiera",
            value=st.session_state.get("filter_op_name", ""),
            key="filter_op_name",
        ).strip().lower()
    with c2:
        f_id = st.text_input("UniqueOPID zawiera").strip().upper()
    with c3:
        types_avail = ["(wszystkie)"] + sorted(df["Typ"].dropna().unique().tolist())
        f_type = st.selectbox("Typ", types_avail)

    filt = df.copy()
    if f_name:
        filt = filt[filt["Nazwa"].str.lower().str.contains(f_name, na=False)]
    if f_id:
        filt = filt[filt["UniqueOPID"].str.contains(f_id, na=False)]
    if f_type and f_type != "(wszystkie)":
        filt = filt[filt["Typ"] == f_type]

    st.caption(f"Znaleziono: **{len(filt)}** z {len(df)} punktów")

    # Tabela z możliwością wyboru wiersza (kliknięcie)
    event = st.dataframe(
        filt,
        use_container_width=True,
        hide_index=True,
        height=350,
        on_select="rerun",
        selection_mode="single-row",
        key="op_table_select",
    )

    selected_uid = None
    if event and event.selection and event.selection.rows:
        idx = event.selection.rows[0]
        selected_uid = filt.iloc[idx]["UniqueOPID"]
    elif len(filt) > 0:
        # Fallback: jeśli nic nie wybrane, pokaż pierwszy
        st.info("👆 Kliknij wiersz w tabeli, aby zobaczyć szczegóły OP.")
        return

    if not selected_uid:
        return

    op = ds.op_by_id.get(selected_uid)
    if op is None:
        return

    st.divider()
    st.subheader(f"🏛️ {op.name}  ·  `{op.unique_id}`")
    _quick_metrics(op, ds)

    tab_basic, tab_tracks, tab_sidings, tab_sols, tab_raw = st.tabs([
        "Dane podstawowe",
        f"Tory ({len(op.tracks)})",
        f"Bocznice ({len(op.sidings)})",
        f"Odcinki SOL ({len(ds.op_to_sols.get(op.unique_id, []))})",
        "Raw",
    ])

    with tab_basic:
        col1, col2 = st.columns([1, 1])
        with col1:
            st.markdown(f"**Nazwa:** {op.name}")
            st.markdown(f"**UniqueOPID:** `{op.unique_id}`")
            st.markdown(f"**TAF/TAP:** {op.taf_tap or '—'}")
            st.markdown(f"**Typ:** {op.op_type_label} (kod {op.op_type_code})")
            if op.railway_location:
                st.markdown(f"**Linia (NationalIdentNum):** `{op.railway_location.national_ident_num}`")
                st.markdown(f"**Kilometraż:** {op.railway_location.kilometer}")
            st.markdown(f"**Ważność od:** {op.validity_start}")
            if op.validity_end and op.validity_end.year < 3000:
                st.markdown(f"**Ważność do:** {op.validity_end}")
        with col2:
            if op.geographic and op.geographic.latitude:
                st.markdown(f"**Szerokość geo.:** {op.geographic.latitude}")
                st.markdown(f"**Długość geo.:** {op.geographic.longitude}")
                _mini_map(op)

    with tab_tracks:
        if not op.tracks:
            st.info("Brak torów operacyjnych.")
        else:
            track_labels = [
                f"Tor {t.identification}  ·  {len(t.parameters)} par., {len(t.platforms)} peronów, {len(t.tunnels)} tuneli"
                for t in op.tracks
            ]
            idx_t = st.selectbox("Wybierz tor:", list(range(len(op.tracks))), format_func=lambda i: track_labels[i], key="op_track_sel")
            t = op.tracks[idx_t]
            st.caption(f"IM: {t.im_code}  |  Identyfikator: {t.identification}  |  Ważność: {t.validity_start} → {t.validity_end}")

            sub_tabs = st.tabs([
                "Parametry toru",
                f"Perony ({len(t.platforms)})",
                f"Tunele ({len(t.tunnels)})",
            ])
            with sub_tabs[0]:
                render_params_table(t.parameters, key=f"op_track_{idx_t}_params")
            with sub_tabs[1]:
                if not t.platforms:
                    st.info("Brak peronów.")
                for j, pl in enumerate(t.platforms):
                    st.markdown(f"#### Peron {pl.identification}  (IM {pl.im_code})")
                    st.caption(f"Ważność: {pl.validity_start} → {pl.validity_end}  |  Parametrów: {len(pl.parameters)}")
                    render_params_table(pl.parameters, key=f"op_track_{idx_t}_plat_{j}")
                    st.divider()
            with sub_tabs[2]:
                if not t.tunnels:
                    st.info("Brak tuneli.")
                for j, tu in enumerate(t.tunnels):
                    st.markdown(f"#### Tunel {tu.identification}  (IM {tu.im_code})")
                    st.caption(f"Ważność: {tu.validity_start} → {tu.validity_end}  |  Parametrów: {len(tu.parameters)}")
                    render_params_table(tu.parameters, key=f"op_track_{idx_t}_tun_{j}")
                    st.divider()

    with tab_sidings:
        if not op.sidings:
            st.info("Brak bocznic.")
        else:
            siding_labels = [
                f"Bocznica {s.identification}  ·  {len(s.parameters)} parametrów"
                for s in op.sidings
            ]
            idx_s = st.selectbox("Wybierz bocznicę:", list(range(len(op.sidings))), format_func=lambda i: siding_labels[i], key="op_siding_sel")
            s = op.sidings[idx_s]
            st.caption(f"IM: {s.im_code}  |  Ważność: {s.validity_start} → {s.validity_end}")
            render_params_table(s.parameters, key=f"op_siding_{idx_s}")

    with tab_sols:
        sols = ds.op_to_sols.get(op.unique_id, [])
        if not sols:
            st.info("Punkt nie pojawia się w żadnym odcinku SOL.")
        else:
            st.markdown(f"Punkt należy do **{len(sols)}** odcinków linii (jako początek lub koniec).")
            rows = []
            for s in sols:
                other_id = s.op_end_id if s.op_start_id == op.unique_id else s.op_start_id
                other = ds.op_by_id.get(other_id)
                other_name = other.name if other else other_id
                direction = "→" if s.op_start_id == op.unique_id else "←"
                rows.append({
                    "Linia": s.line_id,
                    "Nr PL": s.line_number_pl,
                    "Kierunek": direction,
                    "Drugi OP": other_name,
                    "Drugi OPID": other_id,
                    "Długość [km]": s.length_km,
                    "Tory": len(s.tracks),
                })
            sols_df = pd.DataFrame(rows)
            st.dataframe(sols_df, use_container_width=True, hide_index=True)

            # Akcja: przejdź do widoku odcinków z preselekcją linii
            with st.expander("🔗 Otwórz wybraną linię w widoku odcinków"):
                sel_line = st.selectbox("Linia", sorted({s.line_number_pl for s in sols if s.line_number_pl}), key="op_to_sol_line")
                if st.button("Przejdź do widoku odcinków", key="op_to_sol_btn"):
                    st.session_state["filter_sol_line"] = sel_line
                    st.session_state["nav_target"] = "Odcinki linii"
                    st.rerun()

    with tab_raw:
        st.json({
            "name": op.name,
            "unique_id": op.unique_id,
            "taf_tap": op.taf_tap,
            "op_type_code": op.op_type_code,
            "op_type_label": op.op_type_label,
            "tracks_count": len(op.tracks),
            "sidings_count": len(op.sidings),
            "validity_start": str(op.validity_start) if op.validity_start else None,
            "validity_end": str(op.validity_end) if op.validity_end else None,
        }, expanded=False)
