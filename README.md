# RINF Browser — pełna przeglądarka danych RINF (Streamlit)

Aplikacja wyświetla **wszystkie dane** z pliku RINF (Register of Infrastructure):
punkty eksploatacyjne, odcinki linii, parametry torów (per kierunek), perony,
bocznice, tunele, parametry techniczne (ETCS, GSM-R, hamowanie, elektryfikacja,
pantograf, detekcja pociągu, …). Wszystkie etykiety i opisy po polsku.

W stosunku do poprzedniej wersji `rinf_browser`:
- pełne pokrycie schematu RINF (~150 ID parametrów, wszystkie atrybuty, daty ważności, `Set`, `LocationPoint`),
- rozróżnienie **n/d** / **brak danych** / **TAK** / **NIE** / wartość konkretna,
- rozróżnienie torów **N (nieparzysty)** / **P (parzysty)** w `SOLTrack`,
- bocznice (`OPSiding`) i tunele (`OPTrackTunnel`, `SOLTunnel`),
- mapa folium z OP i przebiegiem odcinków,
- generator **Formularza zgodności pojazdu z linią** w formacie xlsx,
- numery RINF (1.1.1.x.x.x) i opisy techniczne dla każdego parametru.

## Wymagania
- Python 3.10+
- Pakiety: `streamlit`, `lxml`, `pandas`, `openpyxl`, `streamlit-folium`, `folium`

## Instalacja (Windows / PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Uruchomienie
```powershell
streamlit run app.py
```
W przeglądarce otwiera się aplikacja (URL pokazuje się w terminalu). W panelu po lewej
wybierz widok:

| Widok | Co pokazuje |
|---|---|
| **Plik / Statystyki** | Upload pliku XML + liczniki: OPs, SOLs, najdłuższe linie, typy OP |
| **Punkty eksploatacyjne** | Tabela 4249 OP z filtrowaniem; po wyborze: szczegóły, tory z peronami i tunelami, bocznice, lista odcinków przez OP |
| **Odcinki linii** | Tabela 4946 SOL z filtrowaniem; po wyborze: tor N i tor P osobno, każdy z ~100 parametrami, tunele, LocationPoint |
| **Przeglądarka parametrów** | Słownik wszystkich parametrów RINF + histogram wystąpień |
| **Formularz zgodności** | Generuje xlsx dla wskazanej linii i odcinka (oba kierunki) |
| **Mapa** | OP jako markery z clustering + przebiegi linii (folium) |
| **Surowy XML (diagnostyka)** | Pretty-print fragmentu XML dla wybranego OP/SOL |

## Architektura

```
RINF_app/
├── app.py                      # punkt wejścia, router widoków
├── requirements.txt
├── README.md
│
├── rinf/                       # core (parser, modele, słowniki)
│   ├── models.py               # dataclasses: OperationalPoint, SectionOfLine, OPTrack, ...
│   ├── parser.py               # lxml iterparse, pełne pokrycie XML
│   ├── dictionary.py           # XML_ID → {RINF index, nazwa PL, jednostka, opis}
│   ├── formatters.py           # n/d / NIE / TAK / brak danych
│   └── exports/
│       └── compatibility_form.py   # generator xlsx (Formularz zgodności)
│
├── views/                      # widoki Streamlit
│   ├── home.py
│   ├── operational_points.py
│   ├── sections.py
│   ├── parameter_browser.py
│   ├── map_view.py
│   ├── line_compatibility.py
│   └── raw_xpath.py
│
└── data/                       # zewnętrzne słowniki (edytowalne)
    ├── parameter_dictionary.json    # ~120 ID parametrów RINF
    └── enum_codes.json              # mapowania kodów: OPType, ECS_VoltFreq, CPO_LegacyTrainProtection, ...
```

## Wydajność

- Parser oparty o `lxml.iterparse` z idiomem czyszczenia rodzeństwa — pamięć ~stała niezależnie od rozmiaru XML.
- Pierwsze parsowanie pliku 100 MB: ~5–6 s.
- Kolejne wczytania tego samego pliku: <1 s (cache `@st.cache_resource`).
- Indeksy: `op_by_id`, `op_by_name`, `sol_by_line`, `op_to_sols` — zbudowane raz przy parsowaniu.

## Pokrycie danych vs RINF v0.1

| Element | Liczba w pliku | Pokrycie |
|---|---|---|
| OperationalPoint | 4 249 | wszystkie atrybuty + walidacja |
| OPTafTapCode | 4 249 | tak |
| OPTrack | 12 589 | wszystkie 7 parametrów |
| OPTrackPlatform | 5 806 | wszystkie 5 parametrów |
| OPTrackTunnel | 6 | wszystkie 6 parametrów |
| OPSiding | 9 954 | wszystkie 14 parametrów |
| SectionOfLine | 4 946 | + SOLNature, daty |
| SOLTrack | 7 156 | + SOLTrackDirection, walidacja |
| SOLTrackParameter | 836 829 | **wszystkie 109 ID** |
| SOLTunnel | 33 | wszystkie 8 parametrów |
| LocationPoint | 12 089 | tak |

## Plik źródłowy

Aplikacja testowana z plikiem `RINF-PL_2026_3_12d_rinf (1).xml` (~100 MB, 9195 OP+SOL, 837k parametrów).
