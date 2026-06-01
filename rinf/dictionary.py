"""Wczytywanie slownikow parametrow RINF i mapowanie kodow."""
from __future__ import annotations
import json
from pathlib import Path
from functools import lru_cache

_DATA_DIR = Path(__file__).parent.parent / "data"
_PARAM_FILE = _DATA_DIR / "parameter_dictionary.json"
_ENUM_FILE = _DATA_DIR / "enum_codes.json"


@lru_cache(maxsize=1)
def parameter_dictionary() -> dict[str, dict]:
    """Slownik: XML_ID -> {rinf_index, name_pl, group_pl, unit, description}."""
    if not _PARAM_FILE.exists():
        return {}
    return json.loads(_PARAM_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def enum_codes() -> dict[str, dict[str, str]]:
    """Slownik: parameter_id (lub kategoria) -> {kod: opis_PL}."""
    if not _ENUM_FILE.exists():
        return {}
    return json.loads(_ENUM_FILE.read_text(encoding="utf-8"))


def enrich_param(param) -> None:
    """In-place: wzbogaca obiekt Parameter o pola ze slownika."""
    info = parameter_dictionary().get(param.id, {})
    param.rinf_index = info.get("rinf_index")
    param.name_pl = info.get("name_pl") or param.id
    param.group_pl = info.get("group_pl") or "Inne"
    param.unit = info.get("unit")
    param.description = info.get("description") or ""


def decode_enum(param_id: str, code: str | None) -> str | None:
    """Zwraca opisowa wartosc dla kodu, jezeli mapowanie istnieje."""
    if not code:
        return None
    return enum_codes().get(param_id, {}).get(code)


def op_type_label_pl(code: str | None, optional_value: str | None = None) -> str:
    """Zwraca polska etykiete typu OP."""
    if not code and not optional_value:
        return ""
    pl = decode_enum("OPType", code or "")
    if pl:
        return pl
    return optional_value or code or ""
