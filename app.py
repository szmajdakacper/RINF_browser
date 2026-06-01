"""RINF Browser — aplikacja Streamlit pokazująca wszystkie dane z pliku RINF."""
from __future__ import annotations
import streamlit as st

from views import home, operational_points, sections, parameter_browser, raw_xpath, line_compatibility


st.set_page_config(
    page_title="RINF Browser — pełna przeglądarka",
    page_icon="🚆",
    layout="wide",
    initial_sidebar_state="expanded",
)


VIEWS = {
    "📁 Plik / Statystyki":     home.render,
    "📍 Punkty eksploatacyjne": operational_points.render,
    "🛤️ Odcinki linii":         sections.render,
    "📚 Parametry RINF":        parameter_browser.render,
    "📄 Formularz zgodności":   line_compatibility.render,
    "🔧 Surowy XML":            raw_xpath.render,
}


def _try_render_map():
    try:
        from views import map_view
        return map_view.render
    except ImportError as e:
        def _stub():
            st.error(
                f"Mapa wymaga `streamlit-folium` i `folium`. Brak: {e}\n\n"
                "Zainstaluj: `pip install streamlit-folium folium`."
            )
        return _stub


VIEWS["🗺️ Mapa"] = _try_render_map()


# Mapowanie pełnych nazw → te same (do nawigacji)
NAV_ALIAS = {
    "Punkty eksploatacyjne": "📍 Punkty eksploatacyjne",
    "Odcinki linii":         "🛤️ Odcinki linii",
    "Mapa":                  "🗺️ Mapa",
    "Formularz zgodności":   "📄 Formularz zgodności",
    "Parametry RINF":        "📚 Parametry RINF",
}


def _global_search(ds):
    """Wyszukiwarka w sidebarze — szuka po nazwie OP / numerze linii."""
    query = st.sidebar.text_input("🔎 Szybkie wyszukiwanie", placeholder="np. Leszno albo 271")
    if not query:
        return
    q = query.strip().lower()

    # Spróbuj jako numer linii
    if q.isdigit():
        line_id = f"PL0051{int(q):03d}"
        if line_id in ds.sol_by_line:
            st.sidebar.success(f"✓ Znaleziono linię {q}")
            if st.sidebar.button(f"Otwórz linię {q} w odcinkach", use_container_width=True):
                st.session_state["filter_sol_line"] = q
                st.session_state["nav_target"] = "Odcinki linii"
                st.rerun()
            if st.sidebar.button(f"Pokaż linię {q} na mapie", use_container_width=True):
                st.session_state["filter_map_line"] = q
                st.session_state["nav_target"] = "Mapa"
                st.rerun()
            return

    # Szukanie po nazwie OP
    matches = [op for op in ds.operational_points if q in op.name.lower()][:10]
    if matches:
        st.sidebar.success(f"✓ Znaleziono {len(matches)} OP")
        for op in matches:
            if st.sidebar.button(f"📍 {op.name} ({op.unique_id})", key=f"goto_{op.unique_id}", use_container_width=True):
                st.session_state["filter_op_name"] = op.name
                st.session_state["nav_target"] = "Punkty eksploatacyjne"
                st.rerun()
    else:
        st.sidebar.warning("Brak dopasowań.")


def main():
    st.sidebar.title("🚆 RINF Browser")
    st.sidebar.caption("Pełna przeglądarka danych RINF")

    # Nawigacja — szanuj nav_target (ustawione przez inne widoki)
    keys = list(VIEWS.keys())
    target = st.session_state.pop("nav_target", None)
    default_idx = 0
    if target and target in NAV_ALIAS:
        target_full = NAV_ALIAS[target]
        if target_full in keys:
            default_idx = keys.index(target_full)
            # Wymuś radio na właściwy widok
            st.session_state["sidebar_choice"] = target_full

    choice = st.sidebar.radio("Widok", keys, key="sidebar_choice", index=default_idx)

    st.sidebar.divider()
    ds = st.session_state.get("rinf_dataset")
    if ds is not None:
        st.sidebar.success(f"📊 {len(ds.operational_points):,} OP, {len(ds.sections_of_line):,} SOL".replace(",", " "))
        _global_search(ds)
        st.sidebar.divider()
        st.sidebar.caption(f"Plik: `{ds.source_hash[:10]}`")
    else:
        st.sidebar.info("Wczytaj plik w widoku 'Plik / Statystyki'.")

    VIEWS[choice]()


if __name__ == "__main__":
    main()
