"""Widok diagnostyczny — surowy XML / trójki RDF wybranego OP lub SOL."""
from __future__ import annotations
import re
import streamlit as st
from lxml import etree

from views._common import require_dataset


_ERA = "http://data.europa.eu/949/"
_MAX_TRIPLES = 3000


def _iter_xml(path: str, tag: str):
    """iterparse ze zwalnianiem pamięci przetworzonych elementów."""
    for _, elem in etree.iterparse(path, events=("end",), tag=tag):
        yield elem
        elem.clear()
        while elem.getprevious() is not None:
            del elem.getparent()[0]


def _attr(elem, child: str) -> str | None:
    el = elem.find(child)
    return el.get("Value") if el is not None else None


@st.cache_data(show_spinner="Szukanie w pliku XML...", max_entries=32)
def _find_op_in_xml(path: str, source_hash: str, opid: str) -> str | None:
    try:
        for elem in _iter_xml(path, "OperationalPoint"):
            if _attr(elem, "UniqueOPID") == opid:
                return etree.tostring(elem, pretty_print=True).decode("utf-8", errors="replace")
    except Exception as e:
        return f"<!-- Błąd: {e} -->"
    return None


@st.cache_data(show_spinner="Szukanie w pliku XML...", max_entries=32)
def _find_sol_in_xml(path: str, source_hash: str, line_id: str, op_start: str, op_end: str) -> str | None:
    try:
        for elem in _iter_xml(path, "SectionOfLine"):
            if (_attr(elem, "SOLLineIdentification") == line_id
                    and _attr(elem, "SOLOPStart") == op_start
                    and _attr(elem, "SOLOPEnd") == op_end):
                return etree.tostring(elem, pretty_print=True).decode("utf-8", errors="replace")
    except Exception as e:
        return f"<!-- Błąd: {e} -->"
    return None


@st.cache_data(show_spinner="Szukanie trójek w pliku RDF...", max_entries=32)
def _find_triples_nt(path: str, source_hash: str, kind: str, key: str) -> str | None:
    """Trójki N-Triples dotyczące elementu (URI ERA skrócone do ``era:``).

    kind="OP":  podmioty z identyfikatorem OP (``.../OP_PL02587``, ``TR_PL02587_...``),
                z pominięciem obiektów odcinków (SOL);
    kind="SOL": podmioty zawierające klucz ``<linia>_<OP start>_<OP koniec>``.
    """
    if kind == "OP":
        rx = re.compile(rf"[/_]{re.escape(key)}(?:_|$)")
        matches = lambda s: "SOL" not in s and rx.search(s) is not None  # noqa: E731
    else:
        matches = lambda s: key in s  # noqa: E731

    out: list[str] = []
    with open(path, encoding="utf-8-sig") as f:
        for ln in f:
            end = ln.find(">")
            if end > 0 and matches(ln[1:end]):
                out.append(ln.rstrip().replace(_ERA, "era:"))
    if not out:
        return None
    out.sort()
    if len(out) > _MAX_TRIPLES:
        out = out[:_MAX_TRIPLES] + [f"# ... przycięto: pokazano {_MAX_TRIPLES} z {len(out)} trójek"]
    return "\n".join(out)


def _show(txt: str | None, language: str) -> None:
    if txt:
        st.code(txt, language=language)
    else:
        st.warning("Nie znaleziono.")


def render():
    st.header("🔧 Surowe dane (diagnostyka)")
    ds = require_dataset()

    if not ds.source_path:
        st.warning("Plik był wczytany z uploadu — brak ścieżki na dysku. Wczytaj plik przez ścieżkę.")
        return

    is_rdf = ds.source_format == "RDF"
    if is_rdf:
        st.caption("Źródło RDF: pokazywane są trójki N-Triples dotyczące wybranego elementu "
                   "(prefiks `era:` = http://data.europa.eu/949/).")
    button_label = "Pokaż trójki RDF" if is_rdf else "Pokaż XML"
    language = "turtle" if is_rdf else "xml"

    mode = st.radio("Typ elementu:", ["OperationalPoint", "SectionOfLine"], horizontal=True)

    if mode == "OperationalPoint":
        opid = st.selectbox("UniqueOPID:", [op.unique_id for op in ds.operational_points])
        if st.button(button_label):
            if is_rdf:
                txt = _find_triples_nt(ds.source_path, ds.source_hash, "OP", opid)
            else:
                txt = _find_op_in_xml(ds.source_path, ds.source_hash, opid)
            _show(txt, language)
    else:
        labels = [f"{s.line_id}: {s.op_start_id} → {s.op_end_id}" for s in ds.sections_of_line]
        sel = st.selectbox("Odcinek:", range(len(labels)), format_func=labels.__getitem__)
        if st.button(button_label):
            sol = ds.sections_of_line[sel]
            if is_rdf:
                key = f"{sol.line_id}_{sol.op_start_id}_{sol.op_end_id}"
                txt = _find_triples_nt(ds.source_path, ds.source_hash, "SOL", key)
            else:
                txt = _find_sol_in_xml(ds.source_path, ds.source_hash, sol.line_id, sol.op_start_id, sol.op_end_id)
            _show(txt, language)
