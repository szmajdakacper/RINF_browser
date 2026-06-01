"""Widok generatora formularza zgodności pojazdu z linią."""
from __future__ import annotations
import streamlit as st
from pathlib import Path

from views._common import require_dataset
from rinf.exports.compatibility_form import (
    build_route_form, find_route, TEMPLATE_PATH_DEFAULT
)


def render():
    st.header("📄 Formularz zgodności pojazdu z linią")
    ds = require_dataset()

    st.markdown("""
Wybierz linię, punkt początkowy i końcowy. Aplikacja wyznaczy łańcuch odcinków,
zagreguje parametry dla obu torów (nieparzysty/parzysty) i wygeneruje plik xlsx
wzorowany na **Formularz zgodności.xlsx**.
""")

    c1, _ = st.columns([1, 2])
    with c1:
        f_line = st.text_input(
            "Nr linii (np. 271)",
            value=st.session_state.get("filter_compat_line", "271"),
            key="filter_compat_line",
        ).strip()
    if not f_line:
        st.info("Podaj numer linii.")
        return

    if f_line.isdigit():
        line_id = f"PL0051{int(f_line):03d}"
    else:
        line_id = f_line

    sols_on_line = ds.sol_by_line.get(line_id, [])
    if not sols_on_line:
        st.warning(f"Brak linii {line_id} w pliku RINF.")
        return

    op_ids: set[str] = set()
    for s in sols_on_line:
        op_ids.add(s.op_start_id)
        op_ids.add(s.op_end_id)
    op_options: list[tuple[str, str]] = []
    for oid in op_ids:
        op = ds.op_by_id.get(oid)
        if op:
            op_options.append((oid, f"{op.name} ({oid})"))
    op_options.sort(key=lambda x: x[1])

    # Wstępnie wybrane OP-y (z navigation state)
    default_start = st.session_state.get("filter_compat_start")
    default_end = st.session_state.get("filter_compat_end")
    start_idx = next((i for i, (oid, _) in enumerate(op_options) if oid == default_start), 0)
    end_idx = next((i for i, (oid, _) in enumerate(op_options) if oid == default_end), min(1, len(op_options) - 1))

    c1, c2 = st.columns(2)
    with c1:
        start = st.selectbox(
            "Punkt początkowy",
            [o for o, _ in op_options],
            format_func=lambda o: dict(op_options)[o],
            index=start_idx,
            key="compat_start_sel",
        )
    with c2:
        end = st.selectbox(
            "Punkt końcowy",
            [o for o, _ in op_options],
            format_func=lambda o: dict(op_options)[o],
            index=end_idx,
            key="compat_end_sel",
        )

    tc1, tc2 = st.columns([2, 1])
    with tc1:
        tmpl = st.text_input(
            "Ścieżka do szablonu Formularz zgodności.xlsx",
            value=str(TEMPLATE_PATH_DEFAULT),
        )
    with tc2:
        tmpl_upload = st.file_uploader("lub wgraj szablon", type=["xlsx"], key="tmpl_upload")

    if st.button("Wyznacz trasę i wygeneruj", type="primary", use_container_width=True):
        chain = find_route(ds, line_id, start, end)
        if not chain:
            st.error(f"Nie znaleziono trasy {start} → {end} na linii {line_id}.")
            return
        st.success(f"✓ Trasa: {len(chain)} odcinków, łącznie {sum(s.length_km or 0 for s in chain):.3f} km")

        rows = []
        for s in chain:
            so = ds.op_by_id.get(s.op_start_id)
            eo = ds.op_by_id.get(s.op_end_id)
            rows.append({
                "Odcinek": f"{so.name if so else s.op_start_id} → {eo.name if eo else s.op_end_id}",
                "Długość [km]": s.length_km,
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)

        if tmpl_upload is not None:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
                f.write(tmpl_upload.getvalue())
                template_path = Path(f.name)
        elif tmpl and Path(tmpl).exists():
            template_path = Path(tmpl)
        else:
            st.error(f"Szablon nie istnieje: {tmpl}. Wgraj plik 'Formularz zgodności.xlsx' lub podaj poprawną ścieżkę.")
            return

        files = build_route_form(ds, line_id, start, end, template_path=template_path)
        if not files:
            st.error("Nie udało się wygenerować plików.")
            return

        st.subheader("📥 Pobierz pliki:")
        for tid, (data, fname) in files.items():
            st.download_button(
                label=f"⬇ Tor {tid} — {fname}",
                data=data,
                file_name=fname,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_{tid}",
                use_container_width=True,
            )
