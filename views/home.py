"""Widok startowy: upload pliku + statystyki ogólne."""
from __future__ import annotations
import re
from pathlib import Path
import streamlit as st
import pandas as pd

from rinf.parser import parse_rinf


@st.cache_resource(show_spinner="Parsowanie pliku RINF...")
def load_dataset_cached(source_bytes: bytes | None, source_path: str | None, source_name: str | None = None):
    if source_bytes is not None:
        return parse_rinf(source_bytes, name=source_name)
    if source_path:
        return parse_rinf(source_path)
    return None


_DATE_IN_NAME_RE = re.compile(r"(20\d{2})_?(\d{1,2})_?(\d{1,2})")


def _find_rinf_files(app_dir: Path, suffix: str) -> list[Path]:
    """Pliki z 'rinf' w nazwie (bez względu na wielkość liter) w app_dir i katalogu nadrzędnym."""
    found = []
    for d in (app_dir, app_dir.parent):
        found += [p for p in d.iterdir()
                  if p.is_file() and p.suffix.lower() == suffix and "rinf" in p.name.lower()]
    return found


def _newest_first(paths: list[Path]) -> list[Path]:
    """Sortuje wg daty w nazwie pliku (np. 20260903, 2026_3_12), potem wg daty modyfikacji."""
    def key(p: Path):
        m = _DATE_IN_NAME_RE.search(p.name)
        named = (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (0, 0, 0)
        return (named, p.stat().st_mtime)
    return sorted(paths, key=key, reverse=True)


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

    # Domyślny plik z katalogu aplikacji i katalogu nadrzędnego:
    # najnowszy eksport RDF (.nt), a jeśli go nie ma - najnowszy XML
    app_dir = Path(__file__).resolve().parent.parent
    candidates = _newest_first(_find_rinf_files(app_dir, ".nt")) or _newest_first(_find_rinf_files(app_dir, ".xml"))
    default = str(candidates[0]) if candidates else ""

    col1, col2 = st.columns([2, 1])
    with col1:
        upload = st.file_uploader(
            "Wybierz plik RINF (XML lub RDF N-Triples .nt)", type=["xml", "nt"],
            help="Duże pliki (np. .nt ~240 MB) wygodniej wczytać przez ścieżkę obok.",
        )
    with col2:
        default_path = st.text_input(
            "lub ścieżka do pliku",
            value=st.session_state.get("rinf_path", default),
        )

    c1, c2 = st.columns(2)
    if c1.button("Wczytaj", type="primary", use_container_width=True):
        try:
            if upload is not None:
                ds = load_dataset_cached(upload.getvalue(), None, upload.name)
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
    if ds.source_format == "RDF":
        st.success(
            "🔗 **Źródło: RDF / N-Triples (ontologia ERA)**"
            + (f"   |   Data eksportu (z nazwy pliku): **{ds.data_date.isoformat()}**" if ds.data_date else "")
        )
        st.info(
            "Plik RDF nie zawiera dat ważności ani części parametrów ze starego XML "
            "(np. pojemność ładunkowa, ślizgacze TSI, hamowanie odzyskowe, maks. opóźnienie, "
            "szczegóły detekcji pociągu, długość bocznic). Takie parametry są oznaczone jako "
            "**brak danych** (w trybie technicznym kolumna *Set*: „brak w pliku RDF”). "
            "Parametry dostępne tylko w RDF mają ID z prefiksem `ERA:`."
        )
    elif vstart:
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
