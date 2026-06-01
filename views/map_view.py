"""Widok mapy — OP + odcinki SOL."""
from __future__ import annotations
import streamlit as st
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

from views._common import require_dataset


def render():
    st.header("🗺️ Mapa")
    ds = require_dataset()

    c1, c2, c3 = st.columns(3)
    with c1:
        # Filtr linii — dwa formaty
        f_line = st.text_input(
            "Nr linii (np. 271)",
            value=st.session_state.get("filter_map_line", ""),
            key="filter_map_line",
            help="Wpisz numer polski (np. 271) lub pełny ID RINF (np. PL0051271). Mapa pokaże punkty operacyjne i przebieg.",
        ).strip()
    with c2:
        op_type_filter = st.selectbox(
            "Typ OP:",
            ["(wszystkie)"] + sorted({op.op_type_label for op in ds.operational_points if op.op_type_label}),
        )
    with c3:
        show_lp = st.checkbox(
            "Pokaż precyzyjny przebieg (LocationPoint)",
            value=False,
            help="Pokazuje punkty pośrednie zarejestrowane wzdłuż linii — może spowolnić mapę",
        )

    # Skonwertuj filtr linii na ID RINF
    line_id_filter = None
    if f_line:
        if f_line.isdigit():
            line_id_filter = f"PL0051{int(f_line):03d}"
        else:
            line_id_filter = f_line.upper()

    # Domyślny widok: cała Polska
    m = folium.Map(location=[52.0, 19.5], zoom_start=6, tiles="OpenStreetMap")

    cluster = MarkerCluster(name="Punkty eksploatacyjne").add_to(m)

    ops_to_show = [
        op for op in ds.operational_points
        if op.geographic and op.geographic.latitude and op.geographic.longitude
        and (op_type_filter == "(wszystkie)" or op.op_type_label == op_type_filter)
    ]

    if line_id_filter:
        ops_in_line: set[str] = set()
        for sol in ds.sections_of_line:
            if line_id_filter in sol.line_id or sol.line_number_pl == f_line:
                ops_in_line.add(sol.op_start_id)
                ops_in_line.add(sol.op_end_id)
        ops_to_show = [op for op in ops_to_show if op.unique_id in ops_in_line]
        st.caption(f"Filtruje OP po linii **{line_id_filter}** — znaleziono **{len(ops_to_show)}** punktów")
        # Centruj mapę na pierwszym punkcie linii
        if ops_to_show and ops_to_show[0].geographic:
            m.location = [ops_to_show[0].geographic.latitude, ops_to_show[0].geographic.longitude]
            m.options["zoom"] = 10

    for op in ops_to_show[:5000]:
        popup_html = f"<b>{op.name}</b><br>{op.unique_id}<br>Typ: {op.op_type_label}"
        if op.railway_location:
            popup_html += f"<br>Linia: {op.railway_location.national_ident_num} km {op.railway_location.kilometer}"
        folium.Marker(
            location=[op.geographic.latitude, op.geographic.longitude],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=op.name,
            icon=folium.Icon(color="blue", icon="train", prefix="fa"),
        ).add_to(cluster)

    # Linie
    line_grp = folium.FeatureGroup(name="Odcinki linii").add_to(m)
    sols_to_show = ds.sections_of_line
    if line_id_filter:
        sols_to_show = [s for s in ds.sections_of_line if line_id_filter in s.line_id or s.line_number_pl == f_line]

    for sol in sols_to_show:
        s_op = ds.op_by_id.get(sol.op_start_id)
        e_op = ds.op_by_id.get(sol.op_end_id)
        if not (s_op and e_op and s_op.geographic and e_op.geographic):
            continue
        if not (s_op.geographic.latitude and e_op.geographic.latitude):
            continue
        if show_lp and sol.tracks:
            lp = [(p.latitude, p.longitude) for p in sol.tracks[0].location_points if p.latitude and p.longitude]
            if lp:
                points = [(s_op.geographic.latitude, s_op.geographic.longitude), *lp, (e_op.geographic.latitude, e_op.geographic.longitude)]
            else:
                points = [(s_op.geographic.latitude, s_op.geographic.longitude), (e_op.geographic.latitude, e_op.geographic.longitude)]
        else:
            points = [(s_op.geographic.latitude, s_op.geographic.longitude), (e_op.geographic.latitude, e_op.geographic.longitude)]
        folium.PolyLine(
            locations=points,
            tooltip=f"{sol.line_id} | {s_op.name} → {e_op.name} ({sol.length_km} km)",
            color="red", weight=2, opacity=0.6,
        ).add_to(line_grp)

    folium.LayerControl().add_to(m)
    st_folium(m, width=1100, height=700, returned_objects=[])
