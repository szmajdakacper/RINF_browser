"""Parser RINF XML - lxml iterparse, pelne pokrycie schematu."""
from __future__ import annotations
import hashlib
import io
import re
from datetime import date
from pathlib import Path
from typing import IO, Iterable, Union

from lxml import etree

from .dictionary import enrich_param, op_type_label_pl, decode_enum
from .models import (
    GeoPoint, RailwayLocation, Parameter, Platform, Tunnel,
    OPTrack, OPSiding, OperationalPoint,
    SOLTrack, SectionOfLine, RINFDataset,
)

LINE_NUM_RE = re.compile(r"PL(\d{4})(\d{3})$")


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _to_float(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _build_param(elem) -> Parameter:
    p = Parameter(
        id=elem.get("ID") or "",
        is_applicable=elem.get("IsApplicable") or "",
        value=elem.get("Value"),
        optional_value=elem.get("OptionalValue"),
        set_context=elem.get("Set"),
    )
    enrich_param(p)
    return p


def _build_geo(elem) -> GeoPoint | None:
    if elem is None:
        return None
    return GeoPoint(
        latitude=_to_float(elem.get("Latitude")),
        longitude=_to_float(elem.get("Longitude")),
        kilometer=_to_float(elem.get("Kilometer")),
    )


def _build_railway_loc(elem) -> RailwayLocation | None:
    if elem is None:
        return None
    return RailwayLocation(
        kilometer=_to_float(elem.get("Kilometer")),
        national_ident_num=elem.get("NationalIdentNum"),
    )


def _build_platform(plat_elem) -> Platform:
    pl = Platform(
        validity_start=_parse_date(plat_elem.get("ValidityDateStart")),
        validity_end=_parse_date(plat_elem.get("ValidityDateEnd")),
        im_code=(plat_elem.find("OPTrackPlatformIMCode").get("Value") if plat_elem.find("OPTrackPlatformIMCode") is not None else ""),
        identification=(plat_elem.find("OPTrackPlatformIdentification").get("Value") if plat_elem.find("OPTrackPlatformIdentification") is not None else ""),
    )
    for p in plat_elem.findall("OPTrackPlatformParameter"):
        pl.parameters.append(_build_param(p))
    return pl


def _build_op_tunnel(tun_elem) -> Tunnel:
    t = Tunnel(
        validity_start=_parse_date(tun_elem.get("ValidityDateStart")),
        validity_end=_parse_date(tun_elem.get("ValidityDateEnd")),
        im_code=(tun_elem.find("OPTrackTunnelIMCode").get("Value") if tun_elem.find("OPTrackTunnelIMCode") is not None else ""),
        identification=(tun_elem.find("OPTrackTunnelIdentification").get("Value") if tun_elem.find("OPTrackTunnelIdentification") is not None else ""),
    )
    for p in tun_elem.findall("OPTrackTunnelParameter"):
        t.parameters.append(_build_param(p))
    return t


def _build_sol_tunnel(tun_elem) -> Tunnel:
    t = Tunnel(
        validity_start=_parse_date(tun_elem.get("ValidityDateStart")),
        validity_end=_parse_date(tun_elem.get("ValidityDateEnd")),
        im_code=(tun_elem.find("SOLTunnelIMCode").get("Value") if tun_elem.find("SOLTunnelIMCode") is not None else ""),
        identification=(tun_elem.find("SOLTunnelIdentification").get("Value") if tun_elem.find("SOLTunnelIdentification") is not None else ""),
        start=_build_geo(tun_elem.find("SOLTunnelStart")),
        end=_build_geo(tun_elem.find("SOLTunnelEnd")),
    )
    for p in tun_elem.findall("SOLTunnelParameter"):
        t.parameters.append(_build_param(p))
    return t


def _build_op_track(track_elem) -> OPTrack:
    t = OPTrack(
        validity_start=_parse_date(track_elem.get("ValidityDateStart")),
        validity_end=_parse_date(track_elem.get("ValidityDateEnd")),
        im_code=(track_elem.find("OPTrackIMCode").get("Value") if track_elem.find("OPTrackIMCode") is not None else ""),
        identification=(track_elem.find("OPTrackIdentification").get("Value") if track_elem.find("OPTrackIdentification") is not None else ""),
    )
    for p in track_elem.findall("OPTrackParameter"):
        t.parameters.append(_build_param(p))
    for plat in track_elem.findall("OPTrackPlatform"):
        t.platforms.append(_build_platform(plat))
    for tun in track_elem.findall("OPTrackTunnel"):
        t.tunnels.append(_build_op_tunnel(tun))
    return t


def _build_op_siding(siding_elem) -> OPSiding:
    s = OPSiding(
        validity_start=_parse_date(siding_elem.get("ValidityDateStart")),
        validity_end=_parse_date(siding_elem.get("ValidityDateEnd")),
        im_code=(siding_elem.find("OPSidingIMCode").get("Value") if siding_elem.find("OPSidingIMCode") is not None else ""),
        identification=(siding_elem.find("OPSidingIdentification").get("Value") if siding_elem.find("OPSidingIdentification") is not None else ""),
    )
    for p in siding_elem.findall("OPSidingParameter"):
        s.parameters.append(_build_param(p))
    return s


def _build_op(elem) -> OperationalPoint:
    name = elem.find("OPName").get("Value") if elem.find("OPName") is not None else ""
    uid = elem.find("UniqueOPID").get("Value") if elem.find("UniqueOPID") is not None else ""
    taf_el = elem.find("OPTafTapCode")
    taf = taf_el.get("Value") if taf_el is not None else None
    op_type_el = elem.find("OPType")
    code = op_type_el.get("Value") if op_type_el is not None else ""
    optional = op_type_el.get("OptionalValue") if op_type_el is not None else None
    op = OperationalPoint(
        name=name,
        unique_id=uid,
        taf_tap=taf,
        op_type_code=code,
        op_type_label=op_type_label_pl(code, optional),
        geographic=_build_geo(elem.find("OPGeographicLocation")),
        railway_location=_build_railway_loc(elem.find("OPRailwayLocation")),
        validity_start=_parse_date(elem.get("ValidityDateStart")),
        validity_end=_parse_date(elem.get("ValidityDateEnd")),
    )
    for t in elem.findall("OPTrack"):
        op.tracks.append(_build_op_track(t))
    for s in elem.findall("OPSiding"):
        op.sidings.append(_build_op_siding(s))
    return op


def _build_sol_track(track_elem) -> SOLTrack:
    tid_el = track_elem.find("SOLTrackIdentification")
    tdir_el = track_elem.find("SOLTrackDirection")
    direction_code = tdir_el.get("Value") if tdir_el is not None else ""
    direction_label = decode_enum("SOLTrackDirection", direction_code) or direction_code
    t = SOLTrack(
        identification=(tid_el.get("Value") if tid_el is not None else ""),
        direction_code=direction_code,
        direction_label=direction_label,
        validity_start=_parse_date(track_elem.get("ValidityDateStart")),
        validity_end=_parse_date(track_elem.get("ValidityDateEnd")),
    )
    for p in track_elem.findall("SOLTrackParameter"):
        # Pomijamy LocationPoint, ktore lapiemy osobno
        t.parameters.append(_build_param(p))
    for lp in track_elem.iter("LocationPoint"):
        t.location_points.append(GeoPoint(
            latitude=_to_float(lp.get("Latitude")),
            longitude=_to_float(lp.get("Longitude")),
            kilometer=_to_float(lp.get("Kilometer")),
        ))
    for tun in track_elem.findall("SOLTunnel"):
        t.tunnels.append(_build_sol_tunnel(tun))
    return t


def _build_sol(elem) -> SectionOfLine:
    line_id = elem.find("SOLLineIdentification").get("Value") if elem.find("SOLLineIdentification") is not None else ""
    line_num_pl = ""
    m = LINE_NUM_RE.match(line_id)
    if m:
        line_num_pl = m.group(2).lstrip("0") or "0"
    nat_el = elem.find("SOLNature")
    nat_code = nat_el.get("Value") if nat_el is not None else ""
    nat_label = (nat_el.get("OptionalValue") if nat_el is not None else None) or decode_enum("SOLNature", nat_code) or nat_code
    sol = SectionOfLine(
        im_code=(elem.find("SOLIMCode").get("Value") if elem.find("SOLIMCode") is not None else ""),
        line_id=line_id,
        line_number_pl=line_num_pl,
        nature_code=nat_code,
        nature_label=nat_label,
        op_start_id=(elem.find("SOLOPStart").get("Value") if elem.find("SOLOPStart") is not None else ""),
        op_end_id=(elem.find("SOLOPEnd").get("Value") if elem.find("SOLOPEnd") is not None else ""),
        length_km=_to_float(elem.find("SOLLength").get("Value") if elem.find("SOLLength") is not None else None),
        validity_start=_parse_date(elem.get("ValidityDateStart")),
        validity_end=_parse_date(elem.get("ValidityDateEnd")),
    )
    for t in elem.findall("SOLTrack"):
        sol.tracks.append(_build_sol_track(t))
    return sol


def _fast_iter(context):
    """Standardowy idiom lxml: po przetworzeniu elementu zwalniamy pamiec."""
    for event, elem in context:
        yield event, elem
        elem.clear()
        while elem.getprevious() is not None:
            del elem.getparent()[0]


def parse_rinf(source: Union[str, Path, bytes, IO]) -> RINFDataset:
    """Wczytuje plik RINF i zwraca pelny dataset z indeksami.

    source: sciezka, bajty lub plikopodobny obiekt.
    """
    ds = RINFDataset()
    if isinstance(source, (str, Path)):
        source_path = str(source)
        ds.source_path = source_path
        ds.source_hash = _file_hash(source_path)
        fh = source_path
    elif isinstance(source, (bytes, bytearray)):
        ds.source_hash = hashlib.md5(source).hexdigest()
        fh = io.BytesIO(source)
    else:
        fh = source

    context = etree.iterparse(fh, events=("end",), tag=("MemberStateCode", "OperationalPoint", "SectionOfLine"))
    for _, elem in _fast_iter(context):
        if elem.tag == "MemberStateCode":
            ds.member_state_code = elem.get("Code") or ""
            ds.member_state_version = elem.get("Version") or ""
        elif elem.tag == "OperationalPoint":
            ds.operational_points.append(_build_op(elem))
        elif elem.tag == "SectionOfLine":
            ds.sections_of_line.append(_build_sol(elem))

    ds.build_indexes()
    return ds


def _file_hash(path: str) -> str:
    """MD5 z pierwszych 1 MB pliku + rozmiar - szybki cache key."""
    h = hashlib.md5()
    size = Path(path).stat().st_size
    with open(path, "rb") as f:
        h.update(f.read(1024 * 1024))
    h.update(str(size).encode())
    return h.hexdigest()
