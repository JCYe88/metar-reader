# METAR Reader

Flask web app that fetches live METAR aviation weather reports and decodes them into plain English.

## Architecture

Single-file Flask app (`app.py`) with no database. All logic is pure Python functions:

- `parse_metar(raw)` — tokenizes and decodes a raw METAR string into a structured dict
- `build_summary(parsed)` — converts the parsed dict into a human-readable sentence
- `GET /` — serves the search UI (`templates/index.html`)
- `GET /metar?code=<ICAO>` — fetches from aviationweather.gov and returns JSON

3-letter IATA codes (e.g. `SFO`) are automatically retried with a `K` prefix (`KSFO`).

## Running the app

```bash
source venv/bin/activate
python app.py          # starts on http://localhost:5001
```

## Running tests

```bash
source venv/bin/activate
pytest                 # all tests
pytest -v              # verbose
pytest tests/test_app.py::TestParseMetarWind   # single class
```

Tests never hit the network — `requests.get` is mocked in all route tests.

## Code quality

```bash
source venv/bin/activate
black app.py tests/        # auto-format (line length 88)
black --check app.py tests/ # check without modifying
flake8 app.py tests/       # lint (E203 suppressed for Black compatibility)
mypy app.py tests/         # type checking (strict on app.py; relaxed on tests/)
```

Config files: `.flake8`, `mypy.ini`. Black has no config file — its defaults are used.

## Dependencies

Managed via `requirements.txt`. Install with:

```bash
pip install -r requirements.txt
```

Key packages: `flask`, `requests`, `pytest`, `flake8`, `mypy`, `types-requests`.

## External data source

Live METAR data comes from:
```
https://aviationweather.gov/api/data/metar?ids=<ICAO>
```
No API key required. Timeout is 10 seconds.
