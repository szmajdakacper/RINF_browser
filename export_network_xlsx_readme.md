# export_network_xlsx.py — eksport sieci RINF do XLSX

Samodzielny skrypt konwertujący plik RINF-PL (XML) do pliku XLSX importowanego
przez aplikację organizatora oferty przewozów. Korzysta z parsera strumieniowego
projektu (`rinf/parser.py`), więc bez problemu przetwarza pełny plik ~100 MB.

## Uruchomienie

```powershell
python export_network_xlsx.py <plik_rinf.xml> [plik_wyjsciowy.xlsx] [--check]
```

Przykłady:

```powershell
# domyślna nazwa wyjścia: siec_kolejowa_<nazwa_zrodla>.xlsx obok pliku źródłowego
python export_network_xlsx.py RINF-PL_2026_3_12d_rinf.xml

# własna nazwa wyjścia + weryfikacja pliku po zapisie
python export_network_xlsx.py RINF-PL_2026_3_12d_rinf.xml siec.xlsx --check
```

Wymagania jak dla całej aplikacji (`pip install -r requirements.txt`) —
skrypt używa `lxml` i `openpyxl`.

## Co zawiera plik wyjściowy

Jeden plik XLSX z dokładnie dwoma arkuszami. Zwykłe wiersze — bez formuł
i tabel Excela (tylko nagłówki są pogrubione), więc można ręcznie dopisywać
wiersze linii innych zarządców (np. DSDiK) ze `zrodlo=RECZNE`.

### Arkusz `punkty` — jeden wiersz na OperationalPoint

| Kolumna | Źródło w RINF | Przykład |
|---|---|---|
| `kod` | UniqueOPID | PL02587 |
| `nazwa` | OPName | Wrocław Główny |
| `typ` | OPType OptionalValue (surowy tekst) | station |
| `szerokosc` | OPGeographicLocation Latitude (WGS84) | 51.098 |
| `dlugosc` | OPGeographicLocation Longitude (bez „+") | 17.036 |
| `nr_linii` | numer krajowy z OPRailwayLocation NationalIdentNum | 273 |
| `km` | OPRailwayLocation Kilometer | 1.7 |
| `zarzadca` | stała | PLK |
| `zrodlo` | stała | RINF |

### Arkusz `odcinki` — jeden wiersz na SectionOfLine

| Kolumna | Źródło w RINF | Przykład |
|---|---|---|
| `punkt_a` | SOLOPStart | PL02587 |
| `punkt_b` | SOLOPEnd | PL02600 |
| `dlugosc_m` | SOLLength [km] × 1000, zaokrąglone do całkowitych metrów | 4567 |
| `nr_linii` | numer krajowy z SOLLineIdentification | 273 |
| `zarzadca` | stała | PLK |
| `zrodlo` | stała | RINF |

Numer krajowy linii wyciągany jest z identyfikatora `PL0051NNN`
(prefiks PL + kod zarządcy 0051 + 3-cyfrowy numer linii).

## Reguły spójności (importer jest all-or-nothing)

Skrypt egzekwuje reguły, których naruszenie odrzuciłoby cały plik:

1. **Unikalny `kod`** — jeśli XML zawiera duplikaty OP (różne okresy ważności),
   zostaje rekord aktualnie obowiązujący (najpóźniejszy `ValidityDateEnd`;
   brak daty = bezterminowo).
2. **Spójność odcinków z punktami** — każdy `punkt_a`/`punkt_b` musi występować
   w arkuszu `punkty`. Punkty bez współrzędnych są pomijane, a razem z nimi
   ich odcinki (liczby pominiętych wypisywane na konsolę).
3. **`dlugosc_m` > 0** — odcinki z pustym/zerowym `SOLLength` są pomijane.
4. **Brak duplikatów odcinków** — ta sama para punktów (w obu kierunkach!)
   i ten sam `nr_linii` = duplikat; zostaje rekord aktualnie obowiązujący.

Współrzędne zapisywane są jako liczby z kropką dziesiętną, bez wiodącego „+".

## Podsumowanie i weryfikacja

Po zapisie skrypt wypisuje: liczbę punktów i odcinków, liczbę unikalnych
numerów linii oraz ile rekordów pominięto (bez współrzędnych / bez długości /
duplikaty).

Z flagą `--check` skrypt dodatkowo **otwiera zapisany plik na nowo**
i niezależnie sprawdza nazwy arkuszy, nagłówki oraz reguły 1–4.
Przy naruszeniu wypisuje błędy i kończy się kodem wyjścia `1`
(bez naruszeń: `OK - reguly 1-4 spelnione`, kod `0`).

Przykładowy wynik dla pliku RINF-PL 2026:

```
Sparsowano: 4249 OP, 4946 SOL

Zapisano siec_kolejowa_RINF-PL_2026_3_12d_rinf.xlsx
  punkty:  4249
  odcinki: 4943
  unikalne numery linii: 662
Pominieto:
  punkty bez wspolrzednych:       0
  duplikaty punktow (kod):        0
  odcinki bez dlugosci (<=0):     3
  odcinki z pominietym punktem:   0
  duplikaty odcinkow (para+linia): 0
```
