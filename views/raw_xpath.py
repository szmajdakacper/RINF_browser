"""Widok diagnostyczny — surowy XML wybranego OP lub SOL."""
from __future__ import annotations
import streamlit as st
from lxml import etree

from views._common import require_dataset


def _find_op_in_xml(path: str, opid: str) -> str | None:
    if not path:
        return None
    try:
        for _, elem in etree.iterparse(path, events=("end",), tag="OperationalPoint"):
            uid_el = elem.find("UniqueOPID")
            if uid_el is not None and uid_el.get("Value") == opid:
                return etree.tostring(elem, pretty_print=True).decode("utf-8", errors="replace")
            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]
    except Exception as e:
        return f"<!-- Błąd: {e} -->"
    return None


def render():
    st.header("🔧 Surowy XML (diagnostyka)")
    ds = require_dataset()

    if not ds.source_path:
        st.warning("Plik był wczytany z uploadu — brak ścieżki na dysku do XPath. Wczytaj plik przez ścieżkę.")
        return

    mode = st.radio("Typ elementu:", ["OperationalPoint", "SectionOfLine"], horizontal=True)

    if mode == "OperationalPoint":
        opid = st.selectbox("UniqueOPID:", [op.unique_id for op in ds.operational_points])
        if st.button("Pokaż XML"):
            xml = _find_op_in_xml(ds.source_path, opid)
            if xml:
                st.code(xml, language="xml")
            else:
                st.warning("Nie znaleziono.")
    else:
        opts = [(i, f"{s.line_id}: {s.op_start_id} → {s.op_end_id}") for i, s in enumerate(ds.sections_of_line)]
        sel = st.selectbox("Odcinek:", [i for i, _ in opts], format_func=lambda i: dict(opts)[i])
        if st.button("Pokaż XML"):
            sol = ds.sections_of_line[sel]
            target = None
            for _, elem in etree.iterparse(ds.source_path, events=("end",), tag="SectionOfLine"):
                lid_el = elem.find("SOLLineIdentification")
                s_el = elem.find("SOLOPStart")
                e_el = elem.find("SOLOPEnd")
                if (lid_el is not None and lid_el.get("Value") == sol.line_id
                    and s_el is not None and s_el.get("Value") == sol.op_start_id
                    and e_el is not None and e_el.get("Value") == sol.op_end_id):
                    target = etree.tostring(elem, pretty_print=True).decode("utf-8", errors="replace")
                    elem.clear()
                    break
                elem.clear()
            if target:
                st.code(target, language="xml")
            else:
                st.warning("Nie znaleziono.")
