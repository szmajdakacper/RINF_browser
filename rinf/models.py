"""Modele danych RINF - dataclasses opisujace wszystkie elementy XML."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class GeoPoint:
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    kilometer: Optional[float] = None


@dataclass
class RailwayLocation:
    kilometer: Optional[float] = None
    national_ident_num: Optional[str] = None  # np. "PL0051273"


@dataclass
class Parameter:
    """Pojedynczy parametr RINF.

    Pola surowe pochodza wprost z XML, pola wzbogacone (rinf_index, name_pl,
    group_pl, unit) sa uzupelniane przez dictionary.
    """
    id: str                                    # "CPE_Level"
    is_applicable: str                         # "Y" / "N" / "NYA"
    value: Optional[str] = None
    optional_value: Optional[str] = None
    set_context: Optional[str] = None          # @Set
    # Wzbogacenie ze slownika
    rinf_index: Optional[str] = None           # "1.1.1.3.2.1"
    name_pl: str = ""
    group_pl: str = ""
    unit: Optional[str] = None
    description: str = ""

    @property
    def display(self) -> str:
        """Tekstowa reprezentacja gotowa do prezentacji (n/d, NIE, TAK, ...).

        Logika identyczna jak w fill_form.py:
          IsApplicable=N            -> "n/d"
          IsApplicable=NYA          -> "brak danych"
          IsApplicable=Y Value=Y    -> "TAK"
          IsApplicable=Y Value=N    -> "NIE"
          IsApplicable=Y Value=X    -> "X" lub "X (OptionalValue)"
        """
        if self.is_applicable == "N":
            return "n/d"
        if self.is_applicable == "NYA":
            return "brak danych"
        v = self.value
        ov = self.optional_value
        if v == "Y":
            return "TAK"
        if v == "N":
            return "NIE"
        if v is None and ov is None:
            return self.is_applicable or ""
        if ov and ov != v:
            return f"{v} ({ov})"
        text = v or ""
        if text and self.unit:
            return f"{text} {self.unit}"
        return text


@dataclass
class Platform:
    """OPTrackPlatform - peron na torze stacji."""
    im_code: str = ""
    identification: str = ""
    validity_start: Optional[date] = None
    validity_end: Optional[date] = None
    parameters: list[Parameter] = field(default_factory=list)


@dataclass
class Tunnel:
    """OPTrackTunnel lub SOLTunnel."""
    im_code: str = ""
    identification: str = ""
    validity_start: Optional[date] = None
    validity_end: Optional[date] = None
    start: Optional[GeoPoint] = None
    end: Optional[GeoPoint] = None
    parameters: list[Parameter] = field(default_factory=list)


@dataclass
class OPTrack:
    """OPTrack - tor stacyjny."""
    im_code: str = ""
    identification: str = ""
    validity_start: Optional[date] = None
    validity_end: Optional[date] = None
    parameters: list[Parameter] = field(default_factory=list)
    platforms: list[Platform] = field(default_factory=list)
    tunnels: list[Tunnel] = field(default_factory=list)


@dataclass
class OPSiding:
    """OPSiding - bocznica."""
    im_code: str = ""
    identification: str = ""
    validity_start: Optional[date] = None
    validity_end: Optional[date] = None
    parameters: list[Parameter] = field(default_factory=list)


@dataclass
class OperationalPoint:
    """OperationalPoint - punkt eksploatacyjny (stacja, przystanek, ...)."""
    name: str = ""
    unique_id: str = ""                        # "PL04430"
    taf_tap: Optional[str] = None              # OPTafTapCode
    op_type_code: str = ""                     # "70"
    op_type_label: str = ""                    # "passenger stop" / "przystanek pasazerski"
    geographic: Optional[GeoPoint] = None
    railway_location: Optional[RailwayLocation] = None
    validity_start: Optional[date] = None
    validity_end: Optional[date] = None
    tracks: list[OPTrack] = field(default_factory=list)
    sidings: list[OPSiding] = field(default_factory=list)


@dataclass
class SOLTrack:
    """SOLTrack - tor odcinka linii."""
    identification: str = ""                   # "N" / "P"
    direction_code: str = ""                   # "10" / "20" / "30"
    direction_label: str = ""                  # PL
    validity_start: Optional[date] = None
    validity_end: Optional[date] = None
    parameters: list[Parameter] = field(default_factory=list)
    tunnels: list[Tunnel] = field(default_factory=list)
    location_points: list[GeoPoint] = field(default_factory=list)


@dataclass
class SectionOfLine:
    """SectionOfLine - odcinek linii kolejowej miedzy dwoma OP."""
    im_code: str = ""
    line_id: str = ""                          # "PL0051271"
    line_number_pl: str = ""                   # "271"
    nature_code: str = ""                      # "10"
    nature_label: str = ""                     # "Regular SoL"
    op_start_id: str = ""                      # PL04430
    op_end_id: str = ""                        # PL04451
    length_km: Optional[float] = None
    validity_start: Optional[date] = None
    validity_end: Optional[date] = None
    tracks: list[SOLTrack] = field(default_factory=list)


@dataclass
class RINFDataset:
    """Kompletny sparsowany plik RINF."""
    member_state_code: str = ""
    member_state_version: str = ""
    operational_points: list[OperationalPoint] = field(default_factory=list)
    sections_of_line: list[SectionOfLine] = field(default_factory=list)
    # Indeksy
    op_by_id: dict[str, OperationalPoint] = field(default_factory=dict)
    op_by_name: dict[str, list[OperationalPoint]] = field(default_factory=dict)
    sol_by_line: dict[str, list[SectionOfLine]] = field(default_factory=dict)
    op_to_sols: dict[str, list[SectionOfLine]] = field(default_factory=dict)
    # Metadane
    source_path: str = ""
    source_hash: str = ""

    def build_indexes(self) -> None:
        self.op_by_id = {op.unique_id: op for op in self.operational_points}
        self.op_by_name = {}
        for op in self.operational_points:
            self.op_by_name.setdefault(op.name, []).append(op)
        self.sol_by_line = {}
        self.op_to_sols = {}
        for sol in self.sections_of_line:
            self.sol_by_line.setdefault(sol.line_id, []).append(sol)
            self.op_to_sols.setdefault(sol.op_start_id, []).append(sol)
            self.op_to_sols.setdefault(sol.op_end_id, []).append(sol)
