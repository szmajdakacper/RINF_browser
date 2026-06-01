"""Widok startowy: upload pliku + statystyki ogolne."""
from __future__ import annotations
import streamlit as st
import pandas as pd

from rinf.parser import parse_rinf


@st.cache_resource(show_spinner="Parsowanie pliku RINF...")
def load_dataset_cached(source_bytes: bytes | None, source_path: str | None):
    if source_bytes is not None:
        return parse_rinf(source_bytes)
    if source_path:
        return parse_rinf(source_path)
    return None


def render():
    st.header("Plik RINF")

    st.markdown("""
Aplikacja **RINF Browser** wyswietla wszystkie dane z pliku RINF (Register of Infrastructure):
punkty eksploatacyjne, odcinki linii, tory, perony, tunele, bocznice, parametry techniczne (ETCS, GSM-R, hamowanie, elektryfikacja, ...).
""")

    # Wykryj domyslna sciezke: szukaj pliku XML w katalogu aplikacji
    from pathlib import Path as _Path
    _app_dir = _Path(__file__).resolve().parent.parent
    _candidates = sorted(_app_dir.glob("*rinf*.xml")) + sorted(_app_dir.glob("RINF*.xml"))
    _default = str(_candidates[0]) if _candidates else ""

    col1, col2 = st.columns([2, 1])
    with col1:
        upload = st.file_uploader("Wybierz plik XML RINF", type=["xml"])
    with col2:
        default_path = st.text_input(
            "lub sciezka do pliku",
            value=st.session_state.get("rinf_path", _default),
        )

    c1, c2 = st.columns(2)
    if c1.button("Wczytaj", type="primary"):
        try:
            if upload is not None:
                ds = load_dataset_cached(upload.getvalue(), None)
            elif default_path:
                ds = load_dataset_cached(None, default_path)
                st.session_state["rinf_path"] = default_path
            else:
                st.warning("Wybierz plik lub podaj sciezke.")
                return
            st.session_state["rinf_dataset"] = ds
            st.success(f"Wczytano. OPs: {len(ds.operational_points)}, SOLs: {len(ds.sections_of_line)}")
        except Exception as e:
            st.error(f"Blad parsowania: {e}")
            raise

    if c2.button("Wyczysc"):
        st.session_state.pop("rinf_dataset", None)
        st.cache_resource.clear()
        st.rerun()

    ds = st.session_state.get("rinf_dataset")
    if ds is None:
        st.info("Wczytaj plik aby zobaczyc statystyki.")
        return

    st.divider()
    st.subheader("Statystyki")

    m = st.columns(5)
    m[0].metric("Punkty eksploatacyjne", len(ds.operational_points))
    m[1].metric("Odcinki linii (SOL)", len(ds.sections_of_line))
    m[2].metric("Linie kolejowe", len(ds.sol_by_line))
    total_len = sum((s.length_km or 0) for s in ds.sections_of_line)
    m[3].metric("Sumaryczna dlugosc", f"{total_len:.1f} km")
    total_params = sum(
        sum(len(t.parameters) for t in s.tracks) for s in ds.sections_of_line
    )
    m[4].metric("Parametrow SOL", f"{total_params:,}".replace(",", " "))

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Najdluzsze linie**")
        rows = []
        for lid, sols in ds.sol_by_line.items():
            total = sum(s.length_km or 0 for s in sols)
            rows.append({"Linia": lid, "Numer PL": sols[0].line_number_pl if sols else "", "Liczba odcinkow": len(sols), "Dlugosc [km]": round(total, 3)})
        df = pd.DataFrame(rows).sort_values("Dlugosc [km]", ascending=False).head(20)
        st.dataframe(df, use_container_width=True, hide_index=True)
    with c2:
        st.markdown("**Typy punktow eksploatacyjnych**")
        from collections import Counter
        c = Counter(op.op_type_label for op in ds.operational_points)
        df_op = pd.DataFrame(c.most_common(), columns=["Typ", "Liczba"])
        st.dataframe(df_op, use_container_width=True, hide_index=True)

    st.divider()
    st.caption(f"Plik: {ds.source_path or '(z uploadu)'} | hash: {ds.source_hash[:8]} | kraj: {ds.member_state_code} v{ds.member_state_version}")
