"""Widok startowy: upload pliku + statystyki ogólne."""
from __future__ import annotations
from pathlib import Path
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


def _detect_validity_range(ds):
    """Znajduje minimalną i maksymalną datę ValidityDateStart wśród elementów."""
    dates = set()
    for op in ds.operational_points:
        if op.validity_start:
            dates.add(op.validity_start)
        for t in op.tracks:
            if t.validity_start:
                dates.add(t.validity_start)
    for s in ds.sections_of_line:
        if s.validity_start:
            dates.add(s.validity_start)
        for t in s.tracks:
            if t.validity_start:
                dates.add(t.validity_start)
    if not dates:
        return None, None
    return min(dates), max(dates)


def render():
    st.header("📁 Plik RINF")

    st.markdown("""
**RINF Browser** wyświetla wszystkie dane z pliku RINF (Register of Infrastructure):
punkty eksploatacyjne, odcinki linii, tory, perony, tunele, bocznice oraz
parametry techniczne (ETCS, GSM-R, hamowanie, elektryfikacja, …).
""")

    # Wyszukaj domyślny plik XML w katalogu aplikacji
    app_dir = Path(__file__).resolve().parent.parent
    candidates = sorted(app_dir.glob("*rinf*.xml")) + sorted(app_dir.glob("RINF*.xml"))
    default = str(candidates[0]) if candidates else ""

    col1, col2 = st.columns([2, 1])
    with col1:
        upload = st.file_uploader("Wybierz plik XML RINF", type=["xml"])
    with col2:
        default_path = st.text_input(
            "lub ścieżka do pliku",
            value=st.session_state.get("rinf_path", default),
        )

    c1, c2 = st.columns(2)
    if c1.button("Wczytaj", type="primary", use_container_width=True):
        try:
            if upload is not None:
                ds = load_dataset_cached(upload.getvalue(), None)
            elif default_path:
                ds = load_dataset_cached(None, default_path)
                st.session_state["rinf_path"] = default_path
            else:
                st.warning("Wybierz plik lub podaj ścieżkę.")
                return
            st.session_state["rinf_dataset"] = ds
            st.success(f"✓ Wczytano: {len(ds.operational_points)} OP, {len(ds.sections_of_line)} odcinków")
        except Exception as e:
            st.error(f"Błąd parsowania: {e}")
            raise

    if c2.button("Wyczyść", use_container_width=True):
        st.session_state.pop("rinf_dataset", None)
        st.cache_resource.clear()
        st.rerun()

    ds = st.session_state.get("rinf_dataset")
    if ds is None:
        st.info("👈 Wczytaj plik, aby zobaczyć statystyki.")
        return

    # Banner walidacji
    vstart, vend = _detect_validity_range(ds)
    if vstart:
        st.success(
            f"📅 **Data ważności danych:** od {vstart.isoformat()}"
            + (f" do {vend.isoformat()}" if vend and vend.year < 3000 else "")
            + f"   |   Kraj: **{ds.member_state_code}** v{ds.member_state_version}"
        )

    st.divider()
    st.subheader("📊 Statystyki ogólne")

    m = st.columns(5)
    m[0].metric("Punkty eksploatacyjne", f"{len(ds.operational_points):,}".replace(",", " "))
    m[1].metric("Odcinki linii (SOL)", f"{len(ds.sections_of_line):,}".replace(",", " "))
    m[2].metric("Linie kolejowe", len(ds.sol_by_line))
    total_len = sum((s.length_km or 0) for s in ds.sections_of_line)
    m[3].metric("Sumaryczna długość", f"{total_len:,.1f} km".replace(",", " "))
    total_params = sum(
        sum(len(t.parameters) for t in s.tracks) for s in ds.sections_of_line
    )
    m[4].metric("Parametrów SOL", f"{total_params:,}".replace(",", " "))

    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**🚆 Najdłuższe linie kolejowe**")
        rows = []
        for lid, sols in ds.sol_by_line.items():
            total = sum(s.length_km or 0 for s in sols)
            rows.append({
                "Linia": lid,
                "Nr PL": sols[0].line_number_pl if sols else "",
                "Odcinki": len(sols),
                "Długość [km]": round(total, 3),
            })
        df_lines = pd.DataFrame(rows).sort_values("Długość [km]", ascending=False).head(20)
        st.dataframe(df_lines, use_container_width=True, hide_index=True, height=400)

    with c2:
        st.markdown("**📍 Typy punktów eksploatacyjnych**")
        from collections import Counter
        c = Counter(op.op_type_label for op in ds.operational_points)
        df_op = pd.DataFrame(c.most_common(), columns=["Typ", "Liczba"])
        st.dataframe(df_op, use_container_width=True, hide_index=True, height=400)

    st.divider()
    st.caption(f"Plik: {ds.source_path or '(z uploadu)'}   |   hash: `{ds.source_hash[:10]}`")
