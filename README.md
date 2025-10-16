## RINF – Data Viewer (Streamlit)

Note: The application UI and all labels are in Polish.

### Requirements
- Python 3.10+

### Installation (Windows / PowerShell)
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Run
```bash
streamlit run app.py
```

Open the browser (URL appears in the terminal). In the left sidebar load an XML file — you can:
- choose a file via the uploader, or
- provide a path (defaults to the sample file in this folder).

### Features
- Operational points tab: a list of points (sorted by name) with details such as name, PL code, point type (Polish label), coordinates, linear location, tracks and platforms (length and height).
- Sections of line tab: line segments with start/end point names (if known), length [km], and selected track parameters.

All UI labels in the app are in Polish.

### Files
- `app.py` — Streamlit UI (Polish labels)
- `rinf_parser.py` — RINF XML parser (memory-friendly, iterparse)
- `requirements.txt` — dependencies

### Notes
- The parser uses `xml.etree.ElementTree` and reads tags present in the XML (e.g., `OperationalPoint`, `OPName`, `UniqueOPID`, `OPTrackIdentification`, `OPTrackPlatformParameter`, `SectionOfLine`, `SOLOPStart`, `SOLOPEnd`, `SOLLength`).
- Track gauge is derived from `ITP_NomGauge` to millimetres, using `OptionalValue` when available; otherwise a simple code→mm mapping is applied.

