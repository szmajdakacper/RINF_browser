"""Widok punktow eksploatacyjnych - pelne dane OP."""
from __future__ import annotations
import streamlit as st
import pandas as pd

from views._common import require_dataset, render_params_table


def _ops_dataframe(ds) -> pd.DataFrame:
    rows = []
    for op in ds.operational_points:
        geo = op.geographic or None
        rl = op.railway_location or None
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
            "Bocznice": len(op.sidings),
        })
    return pd.DataFrame(rows)


def render():
    st.header("Punkty eksploatacyjne (OP)")
    ds = require_dataset()

    if "ops_df" not in st.session_state or st.session_state.get("ops_df_hash") != ds.source_hash:
        st.session_state["ops_df"] = _ops_dataframe(ds)
        st.session_state["ops_df_hash"] = ds.source_hash
    df = st.session_state["ops_df"]

    c1, c2, c3 = st.columns(3)
    with c1:
        f_name = st.text_input("Nazwa zawiera").strip().lower()
    with c2:
        f_id = st.text_input("UniqueOPID zawiera").strip().upper()
    with c3:
        f_type = st.selectbox("Typ", ["(wszystkie)"] + sorted(df["Typ"].dropna().unique().tolist()))

    filt = df.copy()
    if f_name:
        filt = filt[filt["Nazwa"].str.lower().str.contains(f_name, na=False)]
    if f_id:
        filt = filt[filt["UniqueOPID"].str.contains(f_id, na=False)]
    if f_type and f_type != "(wszystkie)":
        filt = filt[filt["Typ"] == f_type]

    st.caption(f"Znaleziono: {len(filt)} z {len(df)} punktow")
    st.dataframe(filt, use_container_width=True, hide_index=True, height=300)

    if len(filt) == 0:
        return

    options = filt["UniqueOPID"].tolist()
    labels = {row["UniqueOPID"]: f"{row['Nazwa']} ({row['UniqueOPID']})" for _, row in filt.iterrows()}
    selected_uid = st.selectbox("Wybierz OP do podgladu szczegolow", options, format_func=lambda u: labels[u])

    op = ds.op_by_id.get(selected_uid)
    if op is None:
        return

    st.divider()
    st.subheader(f"{op.name} [{op.unique_id}]")

    tab_basic, tab_tracks, tab_sidings, tab_sols, tab_raw = st.tabs([
        "Dane podstawowe", f"Tory ({len(op.tracks)})", f"Bocznice ({len(op.sidings)})", "Odcinki SOL", "Raw"
    ])

    with tab_basic:
        col1, col2, col3 = st.columns(3)
        col1.markdown(f"**Nazwa:** {op.name}")
        col1.markdown(f"**UniqueOPID:** `{op.unique_id}`")
        col1.markdown(f"**TAF/TAP:** {op.taf_tap or '—'}")
        col1.markdown(f"**Typ:** {op.op_type_label} (kod {op.op_type_code})")
        if op.geographic:
            col2.markdown(f"**Szerokosc geo.:** {op.geographic.latitude}")
            col2.markdown(f"**Dlugosc geo.:** {op.geographic.longitude}")
        if op.railway_location:
            col3.markdown(f"**Linia (NationalIdentNum):** {op.railway_location.national_ident_num}")
            col3.markdown(f"**Kilometraz:** {op.railway_location.kilometer}")
        col3.markdown(f"**Waznosc od:** {op.validity_start}")
        col3.markdown(f"**Waznosc do:** {op.validity_end}")

    with tab_tracks:
        if not op.tracks:
            st.info("Brak torow operacyjnych.")
        # Wybierz tor (zamiast zagniezdzonych expanderow)
        track_labels = [
            f"Tor {t.identification}  -  {len(t.parameters)} par., {len(t.platforms)} peronow, {len(t.tunnels)} tuneli"
            for t in op.tracks
        ]
        if op.tracks:
            idx_t = st.selectbox("Wybierz tor:", list(range(len(op.tracks))), format_func=lambda i: track_labels[i], key="op_track_sel")
            t = op.tracks[idx_t]
            st.caption(f"IM: {t.im_code}  |  Identyfikator: {t.identification}  |  Waznosc: {t.validity_start} → {t.validity_end}")
            sub_tabs = st.tabs([
                "Parametry toru",
                f"Perony ({len(t.platforms)})",
                f"Tunele ({len(t.tunnels)})",
            ])
            with sub_tabs[0]:
                render_params_table(t.parameters, key=f"op_track_{idx_t}_params")
            with sub_tabs[1]:
                if not t.platforms:
                    st.info("Brak peronow.")
                for j, pl in enumerate(t.platforms):
                    st.markdown(f"#### Peron {pl.identification}  (IM {pl.im_code})")
                    st.caption(f"Waznosc: {pl.validity_start} → {pl.validity_end}  |  Parametrow: {len(pl.parameters)}")
                    render_params_table(pl.parameters, key=f"op_track_{idx_t}_plat_{j}")
                    st.divider()
            with sub_tabs[2]:
                if not t.tunnels:
                    st.info("Brak tuneli.")
                for j, tu in enumerate(t.tunnels):
                    st.markdown(f"#### Tunel {tu.identification}  (IM {tu.im_code})")
                    st.caption(f"Waznosc: {tu.validity_start} → {tu.validity_end}  |  Parametrow: {len(tu.parameters)}")
                    render_params_table(tu.parameters, key=f"op_track_{idx_t}_tun_{j}")
                    st.divider()

    with tab_sidings:
        if not op.sidings:
            st.info("Brak bocznic.")
        for i, s in enumerate(op.sidings):
            with st.expander(f"Bocznica {s.identification} (IM {s.im_code})  -  {len(s.parameters)} parametrow"):
                st.caption(f"Waznosc: {s.validity_start} → {s.validity_end}")
                render_params_table(s.parameters, key=f"op_siding_{i}")

    with tab_sols:
        sols = ds.op_to_sols.get(op.unique_id, [])
        st.markdown(f"Punkt nalezy do **{len(sols)}** odcinkow linii (jako start lub koniec).")
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
                "Dlugosc [km]": s.length_km,
                "Tory": len(s.tracks),
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with tab_raw:
        st.markdown("Surowe dane (dataclass dump):")
        st.json({
            "name": op.name,
            "unique_id": op.unique_id,
            "taf_tap": op.taf_tap,
            "op_type_code": op.op_type_code,
            "op_type_label": op.op_type_label,
            "tracks_count": len(op.tracks),
            "sidings_count": len(op.sidings),
        }, expanded=False)
