from __future__ import annotations

import io
from typing import Dict, Any, List, Optional, Union
import xml.etree.ElementTree as ET


# Mapy pomocnicze tłumaczeń i wartości
OP_TYPE_PL: Dict[str, str] = {
	"passenger stop": "przystanek pasażerski",
	"station": "stacja",
	"halt": "przystanek osobowy",
	"yard": "stacja rozrządowa",
	"junction": "posterunek odgałęźny",
	"freight terminal": "terminal towarowy",
}

GAUGE_CODE_TO_MM: Dict[str, str] = {
	# Często w RINF Value="30" odpowiada 1435 mm (rozstaw normalny)
	"30": "1435",
	# Możliwe inne kody (użyjemy OptionalValue jeśli jest dostępne)
}


def _get_attr(elem: Optional[ET.Element], attr: str, default: Optional[str] = None) -> Optional[str]:
	if elem is None:
		return default
	return elem.get(attr, default)


def _text_or_none(value: Optional[str]) -> Optional[str]:
	if value is None:
		return None
	value = value.strip()
	return value if value else None


def _to_float(value: Optional[str]) -> Optional[float]:
	try:
		return float(value) if value is not None and value != "" else None
	except ValueError:
		return None


def _pl_type_from_elem(op_type_elem: Optional[ET.Element]) -> Optional[str]:
	if op_type_elem is None:
		return None
	# Preferuj opisowy OptionalValue, inaczej użyj Value i spróbuj mapować
	optional = _get_attr(op_type_elem, "OptionalValue")
	if optional:
		return OP_TYPE_PL.get(optional, optional)
	val = _get_attr(op_type_elem, "Value")
	return OP_TYPE_PL.get(val or "", val)


def _extract_op_track(track_elem: ET.Element) -> Dict[str, Any]:
	track_id = _get_attr(track_elem.find("OPTrackIdentification"), "Value")
	# Parametry toru (wybierzmy kilka kluczowych, np. rozstaw)
	gauge_mm: Optional[str] = None
	for p in track_elem.findall("OPTrackParameter"):
		pid = _get_attr(p, "ID")
		if pid == "ITP_NomGauge":
			gauge_mm = _get_attr(p, "OptionalValue") or GAUGE_CODE_TO_MM.get(_get_attr(p, "Value", ""), _get_attr(p, "Value"))
			break

	# Perony (długość i wysokość)
	platforms: List[Dict[str, Optional[Union[str, float]]]] = []
	for plat in track_elem.findall("OPTrackPlatform"):
		length_val: Optional[float] = None
		height_val: Optional[float] = None
		for pp in plat.findall("OPTrackPlatformParameter"):
			pid = _get_attr(pp, "ID")
			if pid == "IPL_Length":
				length_val = _to_float(_get_attr(pp, "Value"))
			elif pid == "IPL_Height":
				height_val = _to_float(_get_attr(pp, "Value"))
		platforms.append({
			"dlugosc_peronu_m": length_val,
			"wysokosc_peronu_mm": height_val,
		})

	return {
		"tor": track_id,
		"parametry": {
			"rozstaw_toru_mm": gauge_mm,
		},
		"perony": platforms,
	}


def _parse_operational_point(elem: ET.Element) -> Dict[str, Any]:
	name = _get_attr(elem.find("OPName"), "Value")
	code = _get_attr(elem.find("UniqueOPID"), "Value")
	ptype = _pl_type_from_elem(elem.find("OPType"))
	op_geo = elem.find("OPGeographicLocation")
	lat = _to_float(_get_attr(op_geo, "Latitude"))
	lon = _to_float(_get_attr(op_geo, "Longitude"))
	op_rloc = elem.find("OPRailwayLocation")
	km = _to_float(_get_attr(op_rloc, "Kilometer"))
	nid = _get_attr(op_rloc, "NationalIdentNum")

	tracks: List[Dict[str, Any]] = []
	for t in elem.findall("OPTrack"):
		tracks.append(_extract_op_track(t))

	return {
		"nazwa": name,
		"kod": code,
		"typ_punktu": ptype,
		"wspolrzedne": {
			"szerokosc": lat,
			"dlugosc": lon,
		},
		"lokalizacja_liniowa": {
			"kilometr": km,
			"identyfikator_linii": nid,
		},
		"tory": tracks,
	}


def _extract_sol_track(track_elem: ET.Element) -> Dict[str, Any]:
	track_id = _get_attr(track_elem.find("SOLTrackIdentification"), "Value")
	params: Dict[str, Any] = {}
	for p in track_elem.findall("SOLTrackParameter"):
		pid = _get_attr(p, "ID")
		val = _get_attr(p, "OptionalValue") or _get_attr(p, "Value") or _get_attr(p, "Set")
		if pid in {"ITP_NomGauge", "IPP_MaxSpeed", "IPP_LineCat", "ECS_SystemType"}:
			# Specjalne traktowanie rozstawu
			if pid == "ITP_NomGauge" and not _get_attr(p, "OptionalValue"):
				val = GAUGE_CODE_TO_MM.get(_get_attr(p, "Value", ""), _get_attr(p, "Value"))
			params[pid] = val
	return {
		"identyfikator": track_id,
		"parametry": params,
	}


def _parse_section_of_line(elem: ET.Element) -> Dict[str, Any]:
	im_code = _get_attr(elem.find("SOLIMCode"), "Value")
	line_id = _get_attr(elem.find("SOLLineIdentification"), "Value")
	start_code = _get_attr(elem.find("SOLOPStart"), "Value")
	end_code = _get_attr(elem.find("SOLOPEnd"), "Value")
	length_km = _to_float(_get_attr(elem.find("SOLLength"), "Value"))
	tracks: List[Dict[str, Any]] = []
	for t in elem.findall("SOLTrack"):
		tracks.append(_extract_sol_track(t))
	return {
		"im": im_code,
		"id_linii": line_id,
		"start_kod": start_code,
		"koniec_kod": end_code,
		"dlugosc_km": length_km,
		"tory": tracks,
	}


def parse_rinf_xml(source: Union[str, bytes, io.BytesIO]) -> Dict[str, Any]:
	"""Parsuje plik XML RINF i zwraca słownik z listami punktów i odcinków.

	Parametr `source` może być ścieżką do pliku, bajtami lub plikopodobnym obiektem.
	"""
	if isinstance(source, (bytes, bytearray)):
		fh: Union[str, io.BytesIO] = io.BytesIO(source)
	elif isinstance(source, io.BytesIO):
		fh = source
	else:
		fh = str(source)

	operational_points: List[Dict[str, Any]] = []
	sections_of_line: List[Dict[str, Any]] = []
	opid_to_name: Dict[str, str] = {}

	# iterparse dla niskiego zużycia pamięci
	context = ET.iterparse(fh, events=("end",))
	for event, elem in context:
		tag = elem.tag
		# Brak przestrzeni nazw w dostarczonym pliku – używamy tagów wprost
		if tag == "OperationalPoint":
			op = _parse_operational_point(elem)
			operational_points.append(op)
			if op.get("kod") and op.get("nazwa"):
				opid_to_name[op["kod"]] = op["nazwa"]
			# Zwolnij pamięć
			elem.clear()
		elif tag == "SectionOfLine":
			so = _parse_section_of_line(elem)
			sections_of_line.append(so)
			elem.clear()

	# Uzupełnij nazwy punktów dla odcinków
	for so in sections_of_line:
		so["start_nazwa"] = opid_to_name.get(so.get("start_kod", ""))
		so["koniec_nazwa"] = opid_to_name.get(so.get("koniec_kod", ""))

	# Posortuj punkty po nazwie
	operational_points.sort(key=lambda x: (x.get("nazwa") or ""))

	return {
		"operational_points": operational_points,
		"sections_of_line": sections_of_line,
	}



