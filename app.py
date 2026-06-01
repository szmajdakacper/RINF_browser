"""RINF Browser - aplikacja Streamlit pokazujaca wszystkie dane z pliku RINF."""
from __future__ import annotations
import streamlit as st

# Import widokow
from views import home, operational_points, sections, parameter_browser, raw_xpath, line_compatibility


st.set_page_config(
    page_title="RINF Browser - pelna przegladarka",
    layout="wide",
    initial_sidebar_state="expanded",
)


VIEWS = {
    "Plik / Statystyki": home.render,
    "Punkty eksploatacyjne": operational_points.render,
    "Odcinki linii": sections.render,
    "Przegladarka parametrow": parameter_browser.render,
    "Formularz zgodnosci": line_compatibility.render,
    "Surowy XML (diagnostyka)": raw_xpath.render,
}


def _try_render_map():
    try:
        from views import map_view
        return map_view.render
    except ImportError as e:
        def _stub():
            st.error(f"Mapa wymaga `streamlit-folium` i `folium`. Brak: {e}\n\nZainstaluj: `pip install streamlit-folium folium`.")
        return _stub


VIEWS["Mapa"] = _try_render_map()


def main():
    st.sidebar.title("RINF Browser")
    st.sidebar.caption("Pelna przegladarka danych RINF (PL)")
    choice = st.sidebar.radio("Widok", list(VIEWS.keys()), index=0)
    st.sidebar.divider()
    ds = st.session_state.get("rinf_dataset")
    if ds is not None:
        st.sidebar.success(f"Wczytano: {len(ds.operational_points)} OP, {len(ds.sections_of_line)} SOL")
    else:
        st.sidebar.info("Nie wczytano pliku - przejdz do 'Plik / Statystyki'.")

    VIEWS[choice]()


if __name__ == "__main__":
    main()
