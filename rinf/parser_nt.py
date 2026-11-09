"""Importer RINF z pliku RDF N-Triples (ontologia ERA, http://data.europa.eu/949/).

Nowy eksport PLK (np. ``PLK_RINF_20260903_002.nt``) zawiera te same obiekty co
stary XML (OP, odcinki, tory, perony, bocznice, tunele), ale zapisane jako graf
RDF. Ten modul buduje z niego dokladnie te same dataclasses co parser XML,
tlumaczac wlasciwosci ERA na dotychczasowe identyfikatory parametrow
(np. ``era:maximumPermittedSpeed`` -> ``IPP_MaxSpeed``). Dzieki temu widoki,
mapa i formularz zgodnosci dzialaja bez zmian.

Zasady:
- ``era:notApplicable``   -> IsApplicable="N"   (n/d)
- ``era:notYetAvailable`` -> IsApplicable="NYA" (brak danych)
- parametr z dotychczasowego XML, ktorego nie ma w pliku RDF -> "NYA"
  (brak danych) z adnotacja w polu ``set_context``,
- wlasciwosci ERA bez odpowiednika w XML -> parametry o ID ``ERA:<nazwa>``.

Plik czytany jest linia po linii (bez rdflib) - 240 MB w kilkanascie sekund.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import IO, Iterable, Union

from .dictionary import enrich_param, op_type_label_pl, decode_enum
from .parser import LINE_NUM_RE, _file_hash, _to_float
from .models import (
    GeoPoint, RailwayLocation, Parameter, Platform, Tunnel,
    OPTrack, OPSiding, OperationalPoint,
    SOLTrack, SectionOfLine, RINFDataset,
)

ERA = "http://data.europa.eu/949/"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
WGS = "http://www.w3.org/2003/01/geo/wgs84_pos#"

_TRIPLE_RE = re.compile(r'^<([^>]*)>\s+<([^>]*)>\s+(.*?)\s*\.\s*$')
_LITERAL_RE = re.compile(r'^"(.*)"(?:\^\^<[^>]*>|@[A-Za-z0-9-]+)?$', re.S)
_GRAD_RE = re.compile(r"^\s*([+-]?)(\d+(?:\.\d+)?)\(([+-]?)(\d+(?:\.\d+)?)\)\s*$")
_DATE_IN_NAME_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})")

# Adnotacja (kolumna "Set" w trybie technicznym) dla parametrow nieobecnych w RDF
MISSING_NOTE = "brak w pliku RDF"

# Predykaty, ktorych nie potrzebujemy - nie trzymamy ich w pamieci
_SKIP_PREDICATES = {
    ERA + "inCountry",
    ERA + "canonicalURI",
    "http://www.w3.org/2000/01/rdf-schema#label",
    "http://www.opengis.net/ont/geosparql#hasGeometry",
    "http://www.opengis.net/ont/geosparql#asWKT",
}

# Parametry bez odpowiednika w RDF, ktore w XML wystepowaly tylko na torach z ETCS
_ETCS_ONLY = {"CPE_OptionalFunctions"}

# Wlasciwosci strukturalne (nie sa parametrami)
_STRUCTURAL = {
    "a", "isPartOf", "hasPart", "netReference", "infrastructureManager",
    "trackId", "trackDirection", "platformId", "sidingId", "tunnelIdentification",
    "etcs", "notApplicable", "notYetAvailable", "uopid", "opName", "opType",
    "primaryLocation", "referenceBorderPoint",
}

# ---------------------------------------------------------------------------
# Mapowanie: dotychczasowe ID parametru XML -> (zrodlo, wlasciwosc ERA)
#   zrodlo "self" = wezel toru/peronu/..., "etcs" = podpiety obiekt era:ETCS
#   None = brak odpowiednika w RDF (zawsze "brak danych")
# Kolejnosc i komplet ID odpowiada parametrom wystepujacym w starym XML.
# ---------------------------------------------------------------------------

OPTRACK_MAP: dict[str, tuple[str, str] | None] = {
    "IDE_ECVerification":  ("self", "verificationINF"),
    "IDE_EIDemonstration": ("self", "demonstrationINF"),
    "ILL_Gauging":         ("self", "gaugingProfile"),
    "IPP_FreightCorridor": ("self", "freightCorridor"),
    "IPP_LineCat":         ("self", "lineCategory"),
    # Stara klasa TEN-T (4 kody) nie da sie jednoznacznie odtworzyc z nowych
    # wlasciwosci tentNetworkLevel + typeOfTraffic - pokazujemy je osobno.
    "IPP_TENClass":        None,
    "ITP_NomGauge":        ("self", "wheelSetGauge"),
}

PLATFORM_MAP: dict[str, tuple[str, str] | None] = {
    "IPL_AreaBoardingAid":         None,
    "IPL_AssistanceStartingTrain": None,
    "IPL_Height":                  ("self", "platformHeight"),
    "IPL_Length":                  ("self", "lengthOfPlatform"),
    "IPL_TENClass":                ("self", "tenClassification"),
}

TUNNEL_MAP: dict[str, tuple[str, str] | None] = {
    "ITU_CrossSectionArea": ("self", "crossSectionArea"),
    "ITU_ECVerification":   ("self", "verificationSRT"),
    "ITU_EIDemonstration":  ("self", "demonstrationSRT"),
    "ITU_EmergencyPlan":    ("self", "hasEmergencyPlan"),
    "ITU_FireCatReq":       ("self", "rollingStockFireCategory"),
    "ITU_Length":           ("self", "lengthOfTunnel"),
    "ITU_NatFireCatReq":    ("self", "nationalRollingStockFireCategory"),
    "ITU_TSITunnel":        ("self", "complianceInfTsi"),
}

SIDING_MAP: dict[str, tuple[str, str] | None] = {
    "ECS_MaxStandstillCurrent": None,
    "IDE_ECVerification":       ("self", "verificationINF"),
    "IDE_EIDemonstration":      ("self", "demonstrationINF"),
    "ILL_Gradient":             None,
    "ILL_MinRadHorzCurve":      ("self", "minimumHorizontalRadius"),
    "ILL_MinRadVertCurve":      None,
    "IPP_Length":               None,
    "IPP_TENClass":             None,
    "ITS_ElectricShoreSupply":  ("self", "hasElectricShoreSupply"),
    "ITS_ExternalCleaning":     ("self", "hasExternalCleaning"),
    "ITS_Refuelling":           ("self", "hasRefuelling"),
    "ITS_SandRestocking":       ("self", "hasSandRestocking"),
    "ITS_ToiletDischarge":      ("self", "hasToiletDischarge"),
    "ITS_WaterRestocking":      ("self", "hasWaterRestocking"),
}

SOLTRACK_MAP: dict[str, tuple[str, str] | None] = {
    "CBP_MaxBrakeDist":              ("self", "maximumBrakingDistance"),
    "CCD_TSITrainDetection":         ("self", "hasTSITrainDetection"),
    "CDE_ECVerification":            None,
    "CEI_TSIMagneticFields":         ("self", "tsiMagneticFields"),
    "CEI_TSITractionHarmonics":      ("self", "tsiTractionHarmonics"),
    "CLD_ETCSSituation":             ("self", "etcsDegradedSituation"),
    "CLD_OtherProtectControlWarn":   ("self", "otherTrainProtection"),
    "COP_Tilting":                   None,
    "CPE_Baseline":                  ("etcs", "etcsBaseline"),
    "CPE_Infill":                    ("etcs", "etcsInfill"),
    "CPE_InfillLineSide":            ("etcs", "etcsInfillLineAccess"),
    "CPE_Level":                     ("etcs", "etcsLevelType"),
    "CPE_MVersion":                  ("etcs", "etcsMVersion"),
    "CPE_NatApplication":            ("etcs", "hasEtcsNationalPacket44"),
    "CPE_OptionalFunctions":         None,
    "CPE_RestrictionsConditions":    ("etcs", "hasETCSRestrictionsConditions"),
    "CPE_SystemCompatibility":       ("etcs", "etcsSystemCompatibility"),
    "CPO_LegacyTrainProtection":     ("self", "protectionLegacySystem"),
    "CRG_AdditionalnetworkInfo":     None,
    "CRG_GPRSAreaOfImpl":            ("self", "gprsImplementationArea"),
    "CRG_GPRSForETCS":               ("self", "gprsForETCS"),
    "CRG_GSMRNoCoverage":            ("self", "gsmRNoCoverage"),
    "CRG_Needof555":                 ("self", "usesGroup555"),
    "CRG_OptionalFunctions":         ("self", "gsmROptionalFunctions"),
    "CRG_RadioCompData":             ("self", "dataRadioCompatible"),
    "CRG_RadioCompVoice":            ("self", "voiceRadioCompatible"),
    "CRG_RoamingAgreement":          None,
    "CRG_RoamingPublic":             ("self", "publicNetworkRoaming"),
    "CRG_RoamingPublicDetails":      ("self", "publicNetworkRoamingDetails"),
    "CRG_Version":                   None,
    "CRS_Installed":                 ("self", "legacyRadioSystem"),
    "CTD_DetectionSystem":           ("self", "trainDetectionSystemType"),
    "CTD_FlangeLubeRules":           None,
    "CTD_MaxDistConsecutiveAxles":   None,
    "CTD_MaxDistEndTrainFirstAxle":  None,
    "CTD_MaxFlangeHeight":           None,
    "CTD_MaxImpedanceWheelset":      None,
    "CTD_MaxSandOutput":             None,
    "CTD_MinAxleLoad":               None,
    "CTD_MinAxleLoadByVehicleCat":   None,
    "CTD_MinDistConsecutiveAxles":   None,
    "CTD_MinDistFirstLastAxles":     None,
    "CTD_MinFlangeHeight":           None,
    "CTD_MinFlangeThickness":        None,
    "CTD_MinRimWidth":               None,
    "CTD_MinWheelDiameter":          None,
    "CTD_SandDriverOverride":        None,
    "CTD_TSICompositeBrakeBlocks":   None,
    "CTD_TSIFerroWheelMat":          None,
    "CTD_TSIMaxDistConsecutiveAxles": None,
    "CTD_TSIMaxImpedanceWheelset":   None,
    "CTD_TSIMetalConstruction":      None,
    "CTD_TSIMetalFree":              None,
    "CTD_TSIRSTShuntImpedance":      None,
    "CTD_TSISand":                   None,
    "CTD_TSISandCharacteristics":    None,
    "CTD_TSIShuntDevices":           None,
    "CTS_SwitchProtectControlWarn":  ("self", "switchProtectControlWarning"),
    "CTS_SwitchRadioSystem":         ("self", "switchRadioSystem"),
    "ECS_MaxStandstillCurrent":      ("self", "maxCurrentStandstillPantograph"),
    "ECS_MaxTrainCurrent":           ("self", "maxTrainCurrent"),
    "ECS_MaxWireHeight":             ("self", "maximumContactWireHeight"),
    "ECS_MinWireHeight":             ("self", "minimumContactWireHeight"),
    "ECS_RegenerativeBraking":       None,
    "ECS_SystemType":                ("self", "contactLineSystemType"),
    "ECS_VoltFreq":                  ("self", "energySupplySystem"),
    "EDE_ECVerification":            ("self", "verificationENE"),
    "EDE_EIDemonstration":           ("self", "demonstrationENE"),
    "EOS_InfoPhase":                 None,
    "EOS_InfoSystem":                None,
    "EOS_Phase":                     ("self", "hasPhaseSeparation"),
    "EOS_System":                    ("self", "hasSystemSeparation"),
    "EPA_NumRaisedSpeed":            None,
    "EPA_OtherHeads":                ("self", "otherPantographHead"),
    "EPA_StripMaterial":             ("self", "contactStripMaterial"),
    "EPA_TSIHeads":                  None,
    "ERS_AutoDropRequired":          ("self", "automaticDroppingDeviceRequired"),
    "ERS_ContactForce":              ("self", "permittedContactForce"),
    "ERS_PowerLimitOnBoard":         ("self", "currentLimitationRequired"),
    "IDE_ECVerification":            ("self", "verificationINF"),
    "IDE_EIDemonstration":           ("self", "demonstrationINF"),
    "IHS_AccelerationLevelCrossing": ("self", "accelerationLevelCrossing"),
    "IHS_FlangeLubeForbidden":       ("self", "flangeLubeForbidden"),
    "IHS_HABDExist":                 ("self", "hasHotAxleBoxDetector"),
    "IHS_LevelCrossing":             None,
    "IHS_QuietRoute":                ("self", "isQuietRoute"),
    "ILL_Gauging":                   ("self", "gaugingProfile"),
    "ILL_GradProfile":               ("self", "gradientProfile"),
    "ILL_MinRadHorzCurve":           ("self", "minimumHorizontalRadius"),
    "ILL_ProfileNumSemiTrailers":    ("self", "profileNumberSemiTrailers"),
    "ILL_ProfileNumSwapBodies":      ("self", "profileNumberSwapBodies"),
    "ILR_EddyCurrentBrakes":         ("self", "eddyCurrentBraking"),
    "ILR_MagneticBrakes":            ("self", "magneticBraking"),
    "ILR_MaxDeceleration":           None,
    "IPP_FreightCorridor":           ("self", "freightCorridor"),
    "IPP_HSLMCompliant":             ("self", "highSpeedLoadModelCompliance"),
    "IPP_LineCat":                   ("self", "lineCategory"),
    "IPP_LoadCap":                   None,
    "IPP_MaxAltitude":               ("self", "maximumAltitude"),
    "IPP_MaxSpeed":                  ("self", "maximumPermittedSpeed"),
    "IPP_SevereClimateCon":          ("self", "hasSevereWeatherConditions"),
    "IPP_TENClass":                  None,
    "IPP_TempRange":                 ("self", "temperatureRange"),
    "ISC_MinWheelDiaFixObtuseCrossings": ("self", "minimumWheelDiameter"),
    "ISC_TSISwitchCrossing":         None,
    "ITP_Ballast":                   ("self", "hasBallast"),
    "ITP_CantDeficiency":            ("self", "cantDeficiency"),
    "ITP_NomGauge":                  ("self", "wheelSetGauge"),
    "ITP_RailInclination":           ("self", "railInclination"),
}


# ---------------------------------------------------------------------------
# Wczytanie trojek
# ---------------------------------------------------------------------------

class _Uri(str):
    """Odroznienie adresu URI od literalu (oba przechowywane jako str)."""
    __slots__ = ()


def _short(u: str) -> str:
    if u.startswith(ERA):
        return u[len(ERA):]
    if u.startswith(WGS):
        return u[len(WGS):]
    if u == RDF_TYPE:
        return "a"
    return u


_ESCAPE_RE = re.compile(r'\\(u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|.)')
_SIMPLE_ESCAPES = {"t": "\t", "n": "\n", "r": "\r", "b": "\b", "f": "\f", '"': '"', "'": "'", "\\": "\\"}


def _unescape(s: str) -> str:
    """Sekwencje ucieczki N-Triples (\\uXXXX, \\", \\n, ...)."""
    if "\\" not in s:
        return s

    def repl(m: re.Match) -> str:
        e = m.group(1)
        if e[0] in "uU" and len(e) > 1:
            return chr(int(e[1:], 16))
        return _SIMPLE_ESCAPES.get(e, e)

    return _ESCAPE_RE.sub(repl, s)


def _load_graph(lines: Iterable[str]) -> dict[str, dict[str, list]]:
    """Zwraca {podmiot: {predykat: [obiekty]}} (URI ERA skrocone)."""
    g: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    intern: dict[str, str] = {}
    for ln in lines:
        if ln[:1] == "﻿":          # BOM (np. plik z TextIO otwartego jako utf-8)
            ln = ln[1:]
        if not ln or ln[0] != "<":
            continue
        m = _TRIPLE_RE.match(ln)
        if not m:
            continue
        s, p, o = m.groups()
        if p in _SKIP_PREDICATES or s.startswith(ERA + "geometry/"):
            continue
        p = intern.setdefault(p, _short(p))
        if o.startswith("<"):
            ov = o[1:-1]
            ov = _Uri(intern.setdefault(ov, _short(ov)))
        else:
            lm = _LITERAL_RE.match(o)
            if not lm:
                continue
            ov = _unescape(lm.group(1))
        g[_short(s)][p].append(ov)
    return g


# ---------------------------------------------------------------------------
# Pomocnicze
# ---------------------------------------------------------------------------

def _first(node: dict | None, pred: str):
    if not node:
        return None
    vals = node.get(pred)
    return vals[0] if vals else None


def _types(node: dict | None) -> set[str]:
    return set(node.get("a", ())) if node else set()


def _last_segment(uri: str) -> str:
    return uri.rstrip("/").rsplit("/", 1)[-1]


def _im_code(node: dict) -> str:
    im = _first(node, "infrastructureManager")
    if not im:
        return ""
    return _last_segment(im).split("_")[0]


def _optional_values() -> dict[str, dict[str, str]]:
    path = Path(__file__).parent.parent / "data" / "nt_optional_values.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_gradient(v: str) -> str:
    """'-0.7(8.985)' -> '-0.7(+8.985)' - format jak w starym XML."""
    m = _GRAD_RE.match(v)
    if not m:
        return v
    gs, g, ks, k = m.groups()
    return f"{gs or '+'}{g}({ks or '+'}{k})"


class _Builder:
    def __init__(self, g: dict[str, dict[str, list]]):
        self.g = g
        self.optional = _optional_values()

    # --- wartosci ---------------------------------------------------------
    def _value(self, raw, param_id: str) -> tuple[str, str | None]:
        if isinstance(raw, _Uri):
            code = _last_segment(raw)
            node = self.g.get(raw)
            if raw.startswith("document/") and node:
                url = _first(node, "documentUrl")
                return code, (str(url) if url else None)
            if node and "linesideDistanceIndicationFrequency" in node:
                desc = (
                    f"co {_first(node, 'linesideDistanceIndicationFrequency')} m, "
                    f"wygląd {_last_segment(_first(node, 'linesideDistanceIndicationAppearance') or '?')}, "
                    f"położenie {_last_segment(_first(node, 'linesideDistanceIndicationPositioning') or '?')}"
                )
                return code, desc
            return code, self.optional.get(param_id, {}).get(code)
        s = str(raw)
        if s == "true":
            return "Y", None
        if s == "false":
            return "N", None
        if param_id == "ILL_GradProfile":
            s = _normalize_gradient(s)
        return s, None

    def _params_for(self, pid: str, src_node: dict, pred: str) -> list[Parameter]:
        out = []
        for raw in src_node.get(pred, ()):
            v, ov = self._value(raw, pid)
            out.append(self._param(pid, "Y", v, ov))
        if out:
            return out
        if pred in src_node.get("notApplicable", ()):
            return [self._param(pid, "N")]
        if pred in src_node.get("notYetAvailable", ()):
            return [self._param(pid, "NYA")]
        # Wlasciwosc nie wystepuje dla tego elementu (parametr warunkowy, np.
        # szczegoly ETCS na torze bez ETCS) - tak jak w XML: parametr pomijamy.
        return []

    @staticmethod
    def _param(pid: str, applicable: str, value: str | None = None,
               optional: str | None = None, note: str | None = None) -> Parameter:
        p = Parameter(id=pid, is_applicable=applicable, value=value,
                      optional_value=optional, set_context=note)
        enrich_param(p)
        return p

    def build_params(self, node: dict, mapping: dict, etcs: dict | None = None) -> list[Parameter]:
        params: list[Parameter] = []
        used_self: set[str] = set()
        used_etcs: set[str] = set()
        has_etcs = bool(etcs and etcs.get("etcsLevelType"))
        for pid, src in mapping.items():
            if src is None:
                if pid in _ETCS_ONLY and not has_etcs:
                    continue
                params.append(self._param(pid, "NYA", note=MISSING_NOTE))
                continue
            where, pred = src
            target = node if where == "self" else (etcs or {})
            (used_self if where == "self" else used_etcs).add(pred)
            if pid == "CPE_Level" and not has_etcs:
                # Brak ETCS na torze: zgodnosc ETCS i M_version oznaczone jako n/d
                if "etcsSystemCompatibility" in target.get("notApplicable", ()):
                    params.append(self._param(pid, "N"))
                    continue
            params.extend(self._params_for(pid, target, pred))
        params.extend(self._extra_params(node, used_self))
        if etcs is not None:
            params.extend(self._extra_params(etcs, used_etcs))
        return params

    def _extra_params(self, node: dict, used: set[str]) -> list[Parameter]:
        """Wlasciwosci ERA bez odpowiednika w starym XML -> ID 'ERA:<nazwa>'."""
        out: list[Parameter] = []
        for pred, vals in node.items():
            if pred in _STRUCTURAL or pred in used or "/" in pred or ":" in pred:
                continue
            pid = f"ERA:{pred}"
            for raw in vals:
                v, ov = self._value(raw, pid)
                out.append(self._param(pid, "Y", v, ov))
        for flag, applicable in (("notApplicable", "N"), ("notYetAvailable", "NYA")):
            for pred in node.get(flag, ()):
                pred = str(pred)
                if pred in used or pred in node:
                    continue
                out.append(self._param(f"ERA:{pred}", applicable))
        return out

    # --- lokalizacja ------------------------------------------------------
    def _geo_of_netref(self, ref) -> GeoPoint | None:
        n = self.g.get(ref)
        if not n:
            return None
        lat, lon = _to_float(_first(n, "lat")), _to_float(_first(n, "long"))
        km = None
        lpsc = self.g.get(_first(n, "hasLrsCoordinate"))
        if lpsc:
            kp = self.g.get(_first(lpsc, "kmPost"))
            base = _to_float(_first(kp, "kilometer"))
            off = _to_float(_first(lpsc, "offsetFromKilometricPost")) or 0.0
            if base is not None:
                km = round(base + off / 1000.0, 3)
        if lat is None and lon is None and km is None:
            return None
        return GeoPoint(latitude=lat, longitude=lon, kilometer=km)

    def _railway_location(self, refs: list) -> RailwayLocation | None:
        for ref in refs:
            n = self.g.get(ref)
            lpsc = self.g.get(_first(n, "hasLrsCoordinate")) if n else None
            if not lpsc:
                continue
            kp = self.g.get(_first(lpsc, "kmPost"))
            base = _to_float(_first(kp, "kilometer"))
            off = _to_float(_first(lpsc, "offsetFromKilometricPost")) or 0.0
            lps_uri = _first(kp, "hasLRS")
            line_id = _first(self.g.get(lps_uri), "lineId") if lps_uri else None
            if not line_id and lps_uri:
                line_id = _last_segment(lps_uri).replace("LPS_", "")
            return RailwayLocation(
                kilometer=round(base + off / 1000.0, 3) if base is not None else None,
                national_ident_num=str(line_id) if line_id else None,
            )
        return None

    # --- elementy ---------------------------------------------------------
    def _children(self, node: dict, cls: str) -> list[tuple[str, dict]]:
        out = []
        for uri in node.get("hasPart", ()):
            child = self.g.get(uri)
            if child and cls in _types(child):
                out.append((uri, child))
        return out

    def tunnel(self, node: dict) -> Tunnel:
        start = end = None
        lin = self.g.get(_first(node, "netReference"))
        if lin and "NetLinearReference" in _types(lin):
            start = self._geo_of_netref(_first(lin, "startsAt"))
            end = self._geo_of_netref(_first(lin, "endsAt"))
        return Tunnel(
            im_code=_im_code(node),
            identification=str(_first(node, "tunnelIdentification") or ""),
            start=start,
            end=end,
            parameters=self.build_params(node, TUNNEL_MAP),
        )

    def op_track(self, node: dict) -> OPTrack:
        t = OPTrack(
            im_code=_im_code(node),
            identification=str(_first(node, "trackId") or ""),
            parameters=self.build_params(node, OPTRACK_MAP),
        )
        for _, pe in self._children(node, "PlatformEdge"):
            t.platforms.append(Platform(
                im_code=_im_code(pe),
                identification=str(_first(pe, "platformId") or ""),
                parameters=self.build_params(pe, PLATFORM_MAP),
            ))
        for _, tu in self._children(node, "Tunnel"):
            t.tunnels.append(self.tunnel(tu))
        return t

    def siding(self, node: dict) -> OPSiding:
        return OPSiding(
            im_code=_im_code(node),
            identification=str(_first(node, "sidingId") or ""),
            parameters=self.build_params(node, SIDING_MAP),
        )

    def operational_point(self, node: dict) -> OperationalPoint:
        code = _last_segment(_first(node, "opType") or "")
        # Angielska nazwa typu jak OPType@OptionalValue w XML (np. "passenger stop")
        op_type_optional = self.optional.get("OPType", {}).get(code)
        refs = node.get("netReference", [])
        primary = self.g.get(_first(node, "primaryLocation"))
        geo = None
        for ref in ([_first(primary, "netReference")] if primary else []) + list(refs):
            if ref:
                g = self._geo_of_netref(ref)
                if g and g.latitude is not None:
                    geo = GeoPoint(latitude=g.latitude, longitude=g.longitude)
                    break
        op = OperationalPoint(
            name=str(_first(node, "opName") or ""),
            unique_id=str(_first(node, "uopid") or ""),
            taf_tap=str(_first(primary, "primaryLocationCode")) if primary and _first(primary, "primaryLocationCode") else None,
            op_type_code=code,
            op_type_optional=op_type_optional,
            op_type_label=op_type_label_pl(code, op_type_optional),
            geographic=geo,
            railway_location=self._railway_location(refs),
        )
        for _, tr in self._children(node, "RunningTrack"):
            op.tracks.append(self.op_track(tr))
        for _, sg in self._children(node, "Siding"):
            op.sidings.append(self.siding(sg))
        return op

    def sol_track(self, node: dict) -> SOLTrack:
        direction_code = _last_segment(_first(node, "trackDirection") or "")
        etcs = self.g.get(_first(node, "etcs"))
        t = SOLTrack(
            identification=str(_first(node, "trackId") or ""),
            direction_code=direction_code,
            direction_label=decode_enum("SOLTrackDirection", direction_code) or direction_code,
            parameters=self.build_params(node, SOLTRACK_MAP, etcs or {}),
        )
        for _, tu in self._children(node, "Tunnel"):
            t.tunnels.append(self.tunnel(tu))
        return t

    def section_of_line(self, node: dict) -> SectionOfLine:
        lps_uri = _first(node, "nationalLine")
        line_id = str(_first(self.g.get(lps_uri), "lineId") or "") if lps_uri else ""
        if not line_id and lps_uri:
            line_id = _last_segment(lps_uri).replace("LPS_", "")
        m = LINE_NUM_RE.match(line_id)
        nat_code = _last_segment(_first(node, "solNature") or "")

        def _uopid(op_uri):
            if not op_uri:
                return ""
            return str(_first(self.g.get(op_uri), "uopid") or _last_segment(op_uri).replace("OP_", ""))

        sol = SectionOfLine(
            im_code=_im_code(node),
            line_id=line_id,
            line_number_pl=(m.group(2).lstrip("0") or "0") if m else "",
            nature_code=nat_code,
            nature_label=decode_enum("SOLNature", nat_code) or nat_code,
            op_start_id=_uopid(_first(node, "opStart")),
            op_end_id=_uopid(_first(node, "opEnd")),
            length_km=_to_float(_first(node, "lengthOfSectionOfLine")),
        )
        for _, tr in self._children(node, "RunningTrack"):
            sol.tracks.append(self.sol_track(tr))
        return sol


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def _date_from_name(name: str | None) -> date | None:
    if not name:
        return None
    m = _DATE_IN_NAME_RE.search(Path(name).name)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parse_rinf_nt(source: Union[str, Path, bytes, IO], name: str | None = None) -> RINFDataset:
    """Wczytuje plik RINF w formacie N-Triples (ERA) i zwraca dataset z indeksami."""
    ds = RINFDataset(member_state_code="PL", member_state_version="RDF (ERA)", source_format="RDF")
    if isinstance(source, (str, Path)):
        ds.source_path = str(source)
        ds.source_hash = _file_hash(str(source))
        with open(source, encoding="utf-8-sig") as fh:
            g = _load_graph(fh)
        name = name or str(source)
    elif isinstance(source, (bytes, bytearray)):
        ds.source_hash = hashlib.md5(source).hexdigest()
        g = _load_graph(io.TextIOWrapper(io.BytesIO(source), encoding="utf-8-sig"))
    else:
        g = _load_graph(io.TextIOWrapper(source, encoding="utf-8-sig") if isinstance(source.read(0), bytes) else source)
    ds.data_date = _date_from_name(name)

    b = _Builder(g)
    for node in g.values():
        types = _types(node)
        if "OperationalPoint" in types:
            ds.operational_points.append(b.operational_point(node))
        elif "SectionOfLine" in types:
            ds.sections_of_line.append(b.section_of_line(node))
    ds.build_indexes()
    return ds
