from __future__ import annotations

import os
from typing import Dict, Any, List

import streamlit as st
import pandas as pd

from rinf_parser import parse_rinf_xml


st.set_page_config(page_title="RINF – Przeglądarka", layout="wide")

# Utrwalenie danych między rerunami
if "rinf_data" not in st.session_state:
	st.session_state["rinf_data"] = None


def format_op_summary(op: Dict[str, Any]) -> str:
	name = op.get("nazwa") or "(bez nazwy)"
	code = op.get("kod") or ""
	type_pl = op.get("typ_punktu") or ""
	return f"{name} [{code}] – {type_pl}" if type_pl else f"{name} [{code}]"


def render_operational_point_details(op: Dict[str, Any]) -> None:
	st.subheader("Szczegóły punktu eksploatacyjnego")
	col1, col2, col3 = st.columns(3)
	with col1:
		st.metric("Nazwa", op.get("nazwa") or "")
		st.metric("Kod (PL)", op.get("kod") or "")
		st.metric("Typ", op.get("typ_punktu") or "")
	with col2:
		wsp = op.get("wspolrzedne") or {}
		st.metric("Szerokość geo.", str(wsp.get("szerokosc") or ""))
		st.metric("Długość geo.", str(wsp.get("dlugosc") or ""))
	with col3:
		lin = op.get("lokalizacja_liniowa") or {}
		st.metric("Kilometr", str(lin.get("kilometr") or ""))
		st.metric("Identyfikator linii", lin.get("identyfikator_linii") or "")

	st.markdown("---")
	st.markdown("### Tory i perony")
	tracks: List[Dict[str, Any]] = op.get("tory") or []
	if not tracks:
		st.info("Brak danych o torach dla tego punktu.")
		return
	for t in tracks:
		with st.expander(f"Tor: {t.get('tor')}"):
			params = t.get("parametry") or {}
			st.write({
				"Rozstaw toru [mm]": params.get("rozstaw_toru_mm"),
			})
			plats = t.get("perony") or []
			if plats:
				st.write("Perony:")
				for i, p in enumerate(plats, start=1):
					st.write({
						"Nr": i,
						"Długość peronu [m]": p.get("dlugosc_peronu_m"),
						"Wysokość peronu [mm]": p.get("wysokosc_peronu_mm"),
					})
			else:
				st.caption("Brak informacji o peronach")


def render_section_of_line(sol: Dict[str, Any]) -> None:
	with st.expander(f"{sol.get('id_linii')} | {sol.get('start_nazwa') or sol.get('start_kod')} → {sol.get('koniec_nazwa') or sol.get('koniec_kod')} ({sol.get('dlugosc_km')} km)"):
		col1, col2, col3 = st.columns(3)
		with col1:
			st.metric("Identyfikator linii", sol.get("id_linii") or "")
			st.metric("Zarządca (IM)", sol.get("im") or "")
		with col2:
			st.metric("Początek", (sol.get("start_nazwa") or sol.get("start_kod") or ""))
			st.metric("Koniec", (sol.get("koniec_nazwa") or sol.get("koniec_kod") or ""))
		with col3:
			st.metric("Długość [km]", str(sol.get("dlugosc_km") or ""))

		tracks: List[Dict[str, Any]] = sol.get("tory") or []
		for t in tracks:
			params = t.get("parametry") or {}
			st.write({
				"Id toru": t.get("identyfikator"),
				"Rozstaw toru [mm]": params.get("ITP_NomGauge"),
				"Prędkość maks. [km/h]": params.get("IPP_MaxSpeed"),
				"Kategoria linii": params.get("IPP_LineCat"),
				"System trakcyjny": params.get("ECS_SystemType"),
			})


@st.cache_data(show_spinner=False)
def load_data(upload_bytes: bytes | None, path: str | None) -> Dict[str, Any]:
	if upload_bytes is not None:
		return parse_rinf_xml(upload_bytes)
	if path and os.path.exists(path):
		with open(path, "rb") as f:
			return parse_rinf_xml(f.read())
	return {}


def main() -> None:
	st.title("RINF – Przeglądarka danych")
	st.caption("Wczytaj plik XML RINF i przeglądaj punkty eksploatacyjne oraz odcinki linii. Wszystkie etykiety po polsku.")

	with st.sidebar:
		st.header("Wczytywanie pliku")
		upload = st.file_uploader("Wybierz plik XML RINF", type=["xml"]) 
		default_path = st.text_input("lub podaj ścieżkę do pliku XML", value="RINF-PL_2025_7_2_15_47_rinf_008.xml")
		parse_btn = st.button("Wczytaj dane")
		clear_btn = st.button("Wyczyść wczytane dane")

	data: Dict[str, Any] | None = st.session_state.get("rinf_data")
	if parse_btn:
		try:
			upload_bytes = upload.getvalue() if upload is not None else None
			new_data = load_data(upload_bytes, default_path)
			if new_data:
				st.session_state["rinf_data"] = new_data
				data = new_data
			else:
				st.warning("Nie wybrano pliku ani nie znaleziono ścieżki.")
		except Exception as e:
			st.error(f"Błąd parsowania: {e}")
	if clear_btn:
		st.session_state["rinf_data"] = None
		data = None

	if not data:
		st.info("Wczytaj plik po lewej, aby zobaczyć dane.")
		return

	tab1, tab2 = st.tabs(["Punkty eksploatacyjne", "Odcinki linii"]) 

	with tab1:
		ops: List[Dict[str, Any]] = data.get("operational_points", [])
		# Lista wyboru po nazwie
		labels = [format_op_summary(op) for op in ops]
		idx = st.selectbox("Wybierz punkt", options=list(range(len(labels))), format_func=lambda i: labels[i] if labels else "", index=0 if labels else None)
		if labels:
			render_operational_point_details(ops[idx])

	with tab2:
		sols: List[Dict[str, Any]] = data.get("sections_of_line", [])
		st.subheader("Odcinki linii")

		# Filtrowanie
		fc1, fc2, fc3 = st.columns(3)
		with fc1:
			f_line = st.text_input("Filtr: id linii zawiera", "").strip().lower()
		with fc2:
			f_start = st.text_input("Filtr: początek zawiera", "").strip().lower()
		with fc3:
			f_end = st.text_input("Filtr: koniec zawiera", "").strip().lower()

		filtered: List[Dict[str, Any]] = []
		for s in sols:
			line_ok = f_line in (s.get("id_linii") or "").lower()
			start_text = (s.get("start_nazwa") or s.get("start_kod") or "").lower()
			end_text = (s.get("koniec_nazwa") or s.get("koniec_kod") or "").lower()
			start_ok = f_start in start_text
			end_ok = f_end in end_text
			if line_ok and start_ok and end_ok:
				filtered.append(s)

		# Sortowanie po początku/końcu
		filtered = sorted(filtered, key=lambda x: ((x.get("start_nazwa") or x.get("start_kod") or ""), (x.get("koniec_nazwa") or x.get("koniec_kod") or "")))

		# Paginacja
		pc1, pc2, pc3 = st.columns([1,1,2])
		with pc1:
			size = st.slider("Rozmiar strony", 10, 500, 100, step=10)
		with pc2:
			total = max(len(filtered), 1)
			max_pages = (total + size - 1) // size
			page = st.number_input("Strona", min_value=1, max_value=max_pages, value=1)

		start_idx = (int(page) - 1) * int(size)
		end_idx = min(start_idx + int(size), len(filtered))
		page_items = filtered[start_idx:end_idx]

		# Widok tabelaryczny bieżącej strony
		summary_rows: List[Dict[str, Any]] = []
		for s in page_items:
			summary_rows.append({
				"Id linii": s.get("id_linii"),
				"Początek": s.get("start_nazwa") or s.get("start_kod"),
				"Koniec": s.get("koniec_nazwa") or s.get("koniec_kod"),
				"Długość [km]": s.get("dlugosc_km"),
			})
		if summary_rows:
			st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

		if page_items:
			idx = st.selectbox("Wybierz odcinek ze strony", options=list(range(len(page_items))), format_func=lambda i: f"{page_items[i].get('id_linii')} | {page_items[i].get('start_nazwa') or page_items[i].get('start_kod')} → {page_items[i].get('koniec_nazwa') or page_items[i].get('koniec_kod')}" if page_items else "")
			render_section_of_line(page_items[int(idx)])


if __name__ == "__main__":
	main()


