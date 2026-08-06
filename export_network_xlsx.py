"""Eksport sieci RINF do pliku XLSX dla organizatora oferty przewozow.

Uzycie:
    python export_network_xlsx.py <plik_rinf.xml> [plik_wyjsciowy.xlsx] [--check]

Tworzy plik XLSX z dwoma arkuszami:
  punkty  - jeden wiersz na OperationalPoint (kod, nazwa, typ, wspolrzedne,
            nr_linii, km, zarzadca, zrodlo)
  odcinki - jeden wiersz na SectionOfLine (punkt_a, punkt_b, dlugosc_m,
            nr_linii, zarzadca, zrodlo)

Importer po drugiej stronie jest all-or-nothing, wiec skrypt egzekwuje:
  1. unikalny `kod` (z duplikatow OP zostaje rekord z najpozniejszym
     ValidityDateEnd; brak daty = obowiazuje bezterminowo),
  2. kazdy punkt_a/punkt_b wystepuje w arkuszu `punkty` (punkty bez
     wspolrzednych sa pomijane razem ze swoimi odcinkami),
  3. dlugosc_m > 0,
  4. brak duplikatow pary punktow (w obu kierunkach) + nr_linii.

Do pliku mozna recznie dopisywac wiersze innych zarzadcow (zrodlo=RECZNE) -
zapis to zwykle wiersze bez formul i tabel Excela, tylko naglowki sa pogrubione.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from rinf.parser import parse_rinf, LINE_NUM_RE

ZARZADCA = "PLK"
ZRODLO = "RINF"

PUNKTY_HEADERS = ["kod", "nazwa", "typ", "szerokosc", "dlugosc",
                  "nr_linii", "km", "zarzadca", "zrodlo"]
ODCINKI_HEADERS = ["punkt_a", "punkt_b", "dlugosc_m", "nr_linii",
                   "zarzadca", "zrodlo"]


def _validity_key(obj) -> tuple:
    """Klucz sortowania okresow waznosci: pusty ValidityDateEnd = bezterminowo."""
    end = obj.validity_end or date.max
    start = obj.validity_start or date.min
    return (end, start)


def _line_number(national_ident: str | None) -> str:
    """Krajowy numer linii z identyfikatora PL0051NNN (np. '273')."""
    if not national_ident:
        return ""
    m = LINE_NUM_RE.match(national_ident)
    if not m:
        return ""
    return m.group(2).lstrip("0") or "0"


def _has_coords(op) -> bool:
    g = op.geographic
    return g is not None and g.latitude is not None and g.longitude is not None


def build_rows(ds):
    """Zwraca (punkty, odcinki, statystyki) gotowe do zapisu."""
    stats = {
        "op_bez_wspolrzednych": 0,
        "op_duplikaty": 0,
        "sol_bez_dlugosci": 0,
        "sol_brakujacy_punkt": 0,
        "sol_duplikaty": 0,
    }

    # Regula 1: unikalny kod - z duplikatow zostaje najpozniejszy ValidityDateEnd
    best_op: dict[str, object] = {}
    for op in ds.operational_points:
        if not op.unique_id:
            continue
        prev = best_op.get(op.unique_id)
        if prev is None:
            best_op[op.unique_id] = op
        else:
            stats["op_duplikaty"] += 1
            if _validity_key(op) > _validity_key(prev):
                best_op[op.unique_id] = op

    # Regula 2 (czesc pierwsza): punkty bez wspolrzednych odpadaja
    punkty = []
    known_ids: set[str] = set()
    for uid in sorted(best_op):
        op = best_op[uid]
        if not _has_coords(op):
            stats["op_bez_wspolrzednych"] += 1
            continue
        known_ids.add(uid)
        rl = op.railway_location
        punkty.append([
            uid,
            op.name,
            op.op_type_optional or op.op_type_label or op.op_type_code,
            op.geographic.latitude,
            op.geographic.longitude,
            _line_number(rl.national_ident_num if rl else None),
            rl.kilometer if rl else None,
            ZARZADCA,
            ZRODLO,
        ])

    # Odcinki: regula 3 (dlugosc > 0), regula 2 (oba punkty znane),
    # regula 4 (dedup pary punktow w obu kierunkach + nr linii)
    best_sol: dict[tuple, object] = {}
    for sol in ds.sections_of_line:
        if not sol.length_km or sol.length_km <= 0:
            stats["sol_bez_dlugosci"] += 1
            continue
        if sol.op_start_id not in known_ids or sol.op_end_id not in known_ids:
            stats["sol_brakujacy_punkt"] += 1
            continue
        nr = sol.line_number_pl or _line_number(sol.line_id)
        key = (frozenset((sol.op_start_id, sol.op_end_id)), nr)
        prev = best_sol.get(key)
        if prev is None:
            best_sol[key] = sol
        else:
            stats["sol_duplikaty"] += 1
            if _validity_key(sol) > _validity_key(prev):
                best_sol[key] = sol

    odcinki = []
    for sol in sorted(best_sol.values(),
                      key=lambda s: (s.line_number_pl, s.op_start_id, s.op_end_id)):
        odcinki.append([
            sol.op_start_id,
            sol.op_end_id,
            round(sol.length_km * 1000),
            sol.line_number_pl or _line_number(sol.line_id),
            ZARZADCA,
            ZRODLO,
        ])

    return punkty, odcinki, stats


def write_xlsx(path: Path, punkty: list, odcinki: list) -> None:
    wb = Workbook()
    bold = Font(bold=True)

    ws = wb.active
    ws.title = "punkty"
    ws.append(PUNKTY_HEADERS)
    for cell in ws[1]:
        cell.font = bold
    for row in punkty:
        ws.append(row)

    ws2 = wb.create_sheet("odcinki")
    ws2.append(ODCINKI_HEADERS)
    for cell in ws2[1]:
        cell.font = bold
    for row in odcinki:
        ws2.append(row)

    wb.save(path)


def check_xlsx(path: Path) -> list[str]:
    """Otwiera zapisany plik i weryfikuje reguly 1-4. Zwraca liste bledow."""
    errors: list[str] = []
    wb = load_workbook(path, read_only=True)

    if set(wb.sheetnames) != {"punkty", "odcinki"}:
        errors.append(f"arkusze: oczekiwano ['punkty', 'odcinki'], jest {wb.sheetnames}")
        return errors

    rows_p = wb["punkty"].iter_rows(values_only=True)
    header = list(next(rows_p))
    if header != PUNKTY_HEADERS:
        errors.append(f"naglowki 'punkty': {header}")
    kody: set[str] = set()
    for i, row in enumerate(rows_p, start=2):
        kod = row[0]
        if kod in kody:
            errors.append(f"punkty wiersz {i}: zduplikowany kod {kod!r}")
        kody.add(kod)

    rows_o = wb["odcinki"].iter_rows(values_only=True)
    header = list(next(rows_o))
    if header != ODCINKI_HEADERS:
        errors.append(f"naglowki 'odcinki': {header}")
    pary: set[tuple] = set()
    for i, row in enumerate(rows_o, start=2):
        a, b, dl, nr = row[0], row[1], row[2], row[3]
        if a not in kody:
            errors.append(f"odcinki wiersz {i}: punkt_a {a!r} nie wystepuje w 'punkty'")
        if b not in kody:
            errors.append(f"odcinki wiersz {i}: punkt_b {b!r} nie wystepuje w 'punkty'")
        if not isinstance(dl, (int, float)) or dl <= 0:
            errors.append(f"odcinki wiersz {i}: dlugosc_m = {dl!r} (wymagane > 0)")
        key = (frozenset((a, b)), nr)
        if key in pary:
            errors.append(f"odcinki wiersz {i}: duplikat pary {a}-{b} na linii {nr!r}")
        pary.add(key)

    wb.close()
    return errors


def main(argv: list[str]) -> int:
    args = [a for a in argv if a != "--check"]
    do_check = "--check" in argv
    if not args:
        print(__doc__.strip().splitlines()[0])
        print("Uzycie: python export_network_xlsx.py <plik_rinf.xml> "
              "[plik_wyjsciowy.xlsx] [--check]")
        return 2

    src = Path(args[0])
    if not src.is_file():
        print(f"Blad: nie znaleziono pliku {src}")
        return 2
    out = Path(args[1]) if len(args) > 1 else src.with_name(f"siec_kolejowa_{src.stem}.xlsx")

    print(f"Wczytywanie {src} ...")
    ds = parse_rinf(src)
    print(f"Sparsowano: {len(ds.operational_points)} OP, "
          f"{len(ds.sections_of_line)} SOL")

    punkty, odcinki, stats = build_rows(ds)
    write_xlsx(out, punkty, odcinki)

    linie = {row[3] for row in odcinki if row[3]} | {row[5] for row in punkty if row[5]}
    print(f"\nZapisano {out}")
    print(f"  punkty:  {len(punkty)}")
    print(f"  odcinki: {len(odcinki)}")
    print(f"  unikalne numery linii: {len(linie)}")
    print("Pominieto:")
    print(f"  punkty bez wspolrzednych:       {stats['op_bez_wspolrzednych']}")
    print(f"  duplikaty punktow (kod):        {stats['op_duplikaty']}")
    print(f"  odcinki bez dlugosci (<=0):     {stats['sol_bez_dlugosci']}")
    print(f"  odcinki z pominietym punktem:   {stats['sol_brakujacy_punkt']}")
    print(f"  duplikaty odcinkow (para+linia): {stats['sol_duplikaty']}")

    if do_check:
        print(f"\nWeryfikacja {out} ...")
        errors = check_xlsx(out)
        if errors:
            for e in errors[:50]:
                print(f"  BLAD: {e}")
            if len(errors) > 50:
                print(f"  ... i {len(errors) - 50} kolejnych")
            return 1
        print("  OK - reguly 1-4 spelnione")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
