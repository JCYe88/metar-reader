# METAR Reader

A Flask web application that fetches live METAR weather reports for any airport and decodes them from cryptic aviation shorthand into plain, readable English.

**Example output for KSFO:**
> *Clear and mild at 62.6°F (17°C), winds from the West (280°) at 12 mph, visibility 10+ miles (excellent).*

![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python) ![Flask](https://img.shields.io/badge/Flask-3.0-lightgrey?logo=flask)

---

## What is a METAR?

A METAR (Meteorological Aerodrome Report) is a standardized weather observation used in aviation. They look like this:

```
KSFO 251756Z 28010KT 10SM FEW006 OVC025 16/09 A2999 RMK AO2 SLP156
```

METAR Reader decodes every field into plain English and displays it in a clean, easy-to-read format.

## Features

- Look up current weather for any airport worldwide using its ICAO or IATA code
- Decodes wind direction, speed, and gusts — with a visual compass
- Decodes visibility, sky layers with cloud altitudes, and active weather (rain, snow, fog, thunderstorms, etc.)
- Decodes temperature, dew point, and altimeter pressure
- Generates a one-sentence plain-English weather summary
- Accepts 3-letter US codes (e.g. `SFO`, `LAX`) and automatically maps them to ICAO format
- Shows the raw METAR string alongside the decoded output

## Data Source

Live METAR data is fetched from the [Aviation Weather Center API](https://aviationweather.gov/api/data/metar), operated by NOAA. No API key is required.

## Installation

**Requirements:** Python 3.8+

### 1. Clone the repository

```bash
git clone https://github.com/JCYe88/metar-reader.git
cd metar-reader
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the application

```bash
python app.py
```

Then open your browser and go to **http://localhost:5001**.

## Running Tests

```bash
pytest tests/ -v
```

65 tests cover the METAR parser, summary generator, and all Flask API endpoints. The test suite uses mocked API responses so no network connection is required.

## Usage

1. Type an airport code into the search box (e.g. `KSFO`, `KJFK`, `EGLL`, or US shorthand like `SFO`)
2. Press **Get Weather** or hit Enter
3. Read the plain-English summary and expanded weather details

## Airport Code Formats

| Format | Example | Description |
|--------|---------|-------------|
| ICAO (4-letter) | `KSFO` | Standard international format — works globally |
| IATA (3-letter US) | `SFO` | Common US format — automatically converted to ICAO |

Non-US airports may require the full ICAO code (e.g. `EGLL` for London Heathrow, `RJTT` for Tokyo Haneda).

## Project Structure

```
metar-reader/
├── app.py               # Flask application and METAR parser
├── requirements.txt     # Python dependencies
├── templates/
│   └── index.html       # Single-page frontend (no external dependencies)
├── tests/
│   └── test_app.py      # pytest unit and route tests
└── venv/                # Virtual environment (not committed)
```

## License

MIT
