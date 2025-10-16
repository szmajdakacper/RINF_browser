## RINF – Przeglądarka danych (Streamlit)

Prosta aplikacja do przeglądania plików XML RINF (Rail Infrastructure Database).

### Wymagania
- Python 3.10+

### Instalacja
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Uruchomienie
```bash
streamlit run app.py
```

Po uruchomieniu otwórz przeglądarkę (adres pokaże się w terminalu). W lewym panelu wczytaj plik XML — możesz:
- wskazać plik przez uploader,
- albo podać ścieżkę (domyślnie ustawiona na plik z katalogu).

### Funkcje
- Zakładka „Punkty eksploatacyjne”: lista punktów (posortowana po nazwie), szczegóły punktu (nazwa, kod PL, typ po polsku, współrzędne, lokalizacja liniowa, tory i perony z długościami i wysokościami).
- Zakładka „Odcinki linii”: odcinki z nazwami punktów start/koniec (jeśli znane), długością [km] i zebranymi parametrami torów.

Wszystkie etykiety w interfejsie są po polsku.

### Pliki
- `app.py` – aplikacja Streamlit
- `rinf_parser.py` – parser RINF XML (bezpieczny pamięciowo, iterparse)
- `requirements.txt` – zależności

### Uwagi
- Parser korzysta z `xml.etree.ElementTree` i szuka tagów wg nazewnictwa widocznego w pliku (np. `OperationalPoint`, `OPName`, `UniqueOPID`, `OPTrackIdentification`, `OPTrackPlatformParameter`, `SectionOfLine`, `SOLOPStart`, `SOLOPEnd`, `SOLLength`).
- Rozstaw toru jest mapowany z `ITP_NomGauge` na mm, jeśli `OptionalValue` jest dostępne; inaczej stosowana jest prosta mapa kod→mm.

