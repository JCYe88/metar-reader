"""
METAR Reader — Flask web application.

Fetches live METAR weather reports from aviationweather.gov and decodes
them from cryptic aviation shorthand into plain English.
"""

import re
from typing import Any

import requests
from flask import Flask, render_template, request, jsonify
from flask.typing import ResponseReturnValue

app = Flask(__name__)

# 16-point compass rose used to convert wind degrees to a cardinal direction.
WIND_DIRECTIONS = [
    'North', 'NNE', 'NE', 'ENE',
    'East', 'ESE', 'SE', 'SSE',
    'South', 'SSW', 'SW', 'WSW',
    'West', 'WNW', 'NW', 'NNW',
]

# METAR two-letter descriptor codes that modify a weather phenomenon
# (e.g. "SH" = shower, "TS" = thunderstorm, "FZ" = freezing).
WEATHER_DESCRIPTORS = {
    'MI': 'shallow', 'BC': 'patchy', 'PR': 'partial',
    'DR': 'drifting', 'BL': 'blowing', 'SH': 'shower',
    'TS': 'thunderstorm', 'FZ': 'freezing',
}

# METAR two-letter phenomenon codes mapped to plain English.
WEATHER_PHENOMENA = {
    'DZ': 'drizzle', 'RA': 'rain', 'SN': 'snow',
    'SG': 'snow grains', 'IC': 'ice crystals', 'PL': 'ice pellets',
    'GR': 'hail', 'GS': 'small hail', 'UP': 'unknown precipitation',
    'BR': 'mist', 'FG': 'fog', 'FU': 'smoke', 'VA': 'volcanic ash',
    'DU': 'dust', 'SA': 'sand', 'HZ': 'haze', 'PO': 'dust whirls',
    'SQ': 'squalls', 'FC': 'funnel cloud', 'SS': 'sandstorm', 'DS': 'dust storm',
}

# Sky condition codes mapped to (short label, plain English description).
SKY_CONDITIONS = {
    'SKC': ('Clear', 'clear'), 'CLR': ('Clear', 'clear'),
    'NSC': ('Clear', 'no significant clouds'),
    'FEW': ('Few Clouds', 'a few clouds'),
    'SCT': ('Partly Cloudy', 'scattered clouds'),
    'BKN': ('Mostly Cloudy', 'broken cloud cover'),
    'OVC': ('Overcast', 'overcast'),
    'VV': ('Sky Obscured', 'sky obscured'),
}


def degrees_to_cardinal(deg: float) -> str:
    """Convert a wind direction in degrees (0–360) to a cardinal direction string."""
    return WIND_DIRECTIONS[round(deg / 22.5) % 16]


def c_to_f(c: float) -> float:
    """Convert Celsius to Fahrenheit, rounded to one decimal place."""
    return round(c * 9 / 5 + 32, 1)


def parse_temp_token(token: str) -> int:
    """
    Parse a METAR temperature token into an integer Celsius value.

    METAR uses 'M' as a minus sign (e.g. 'M05' → -5).
    """
    return -int(token[1:]) if token.startswith('M') else int(token)


def decode_weather_token(token: str) -> str | None:
    """
    Decode a single METAR present-weather token into a plain English phrase.

    A token is composed of up to three parts:
      - An optional intensity prefix: '-' (light) or '+' (heavy)
      - An optional descriptor (e.g. 'SH' for shower, 'TS' for thunderstorm)
      - One or more phenomenon codes (e.g. 'RA' for rain, 'SN' for snow)

    Returns a human-readable string, or None if the token contains no
    recognisable phenomena.
    """
    intensity = ''
    if token.startswith('-'):
        intensity = 'light '
        token = token[1:]
    elif token.startswith('+'):
        intensity = 'heavy '
        token = token[1:]

    vicinity = ''
    if token.startswith('VC'):
        vicinity = ' in the vicinity'
        token = token[2:]

    descriptor = ''
    for code, label in WEATHER_DESCRIPTORS.items():
        if token.startswith(code):
            descriptor = label + ' '
            token = token[len(code):]
            break

    phenomena = []
    while len(token) >= 2:
        code = token[:2]
        if code in WEATHER_PHENOMENA:
            phenomena.append(WEATHER_PHENOMENA[code])
            token = token[2:]
        else:
            break

    if not phenomena:
        return None
    return intensity + descriptor + ' and '.join(phenomena) + vicinity


def parse_metar(raw: str) -> dict[str, Any]:
    """
    Parse a raw METAR string into a structured dictionary.

    Handles the following METAR fields in order:
      - Report type (METAR / SPECI)
      - Station identifier
      - Observation timestamp (DDHHMMZ)
      - AUTO / COR modifier
      - Wind (direction, speed, optional gust; KT / MPS / KMH)
      - Variable wind direction range (dddVddd)
      - CAVOK or visibility (SM / metric)
      - Runway Visual Range (skipped)
      - Present weather phenomena
      - Sky conditions with altitude (FEW / SCT / BKN / OVC / VV)
      - Temperature and dew point
      - Altimeter setting (A = inHg, Q = hPa)
      - Remarks (everything after 'RMK')

    Args:
        raw: The raw METAR string.

    Returns:
        A dictionary containing parsed fields. Fields that are not present
        in the report are set to None (or empty list for weather/sky).
    """
    raw = raw.strip()
    result: dict[str, Any] = {
        'raw': raw,
        'station': None,
        'time': None,
        'auto': False,
        'wind': None,
        'wind_variable': None,
        'visibility': None,
        'rvr': [],
        'weather': [],
        'sky': [],
        'temperature': None,
        'dewpoint': None,
        'altimeter': None,
        'remarks': None,
    }

    # Remarks follow 'RMK' and are not formally decoded — store as raw text.
    main, _, remarks = raw.partition(' RMK ')
    if remarks:
        result['remarks'] = remarks

    tokens = main.split()
    if not tokens:
        return result

    idx = 0

    # Report type word is optional and carries no decoded value.
    if tokens[idx] in ('METAR', 'SPECI'):
        idx += 1

    # Station identifier: 3–4 uppercase alphanumeric characters (ICAO code).
    if idx < len(tokens) and re.match(r'^[A-Z0-9]{3,4}$', tokens[idx]):
        result['station'] = tokens[idx]
        idx += 1

    # Timestamp format: DDHHMMZ (day-of-month, hour, minute, UTC).
    if idx < len(tokens) and re.match(r'^\d{6}Z$', tokens[idx]):
        t = tokens[idx]
        result['time'] = {'day': int(t[0:2]), 'hour': int(t[2:4]), 'minute': int(t[4:6])}
        idx += 1

    # AUTO indicates a fully automated station with no human observer.
    if idx < len(tokens) and tokens[idx] in ('AUTO', 'COR', 'RTD'):
        result['auto'] = tokens[idx] == 'AUTO'
        idx += 1

    # Wind: format is (VRB|ddd)(ss[s])(Ggg[g])(KT|MPS|KMH).
    # '00000KT' means calm; 'VRB' means direction is variable.
    if idx < len(tokens):
        wm = re.match(r'^(VRB|\d{3})(\d{2,3})(?:G(\d{2,3}))?(KT|MPS|KMH)$', tokens[idx])
        if wm:
            direction = wm.group(1)
            speed_raw, gust_raw, unit = wm.group(2), wm.group(3), wm.group(4)
            speed = int(speed_raw)
            gust = int(gust_raw) if gust_raw else None

            def to_mph(val: float) -> int:
                """Convert wind speed from the reported unit to mph."""
                if unit == 'KT':
                    return round(val * 1.15078)
                elif unit == 'MPS':
                    return round(val * 2.23694)
                else:  # KMH
                    return round(val * 0.621371)

            speed_mph = to_mph(speed)
            gust_mph = to_mph(gust) if gust else None

            if direction == '000' and speed == 0:
                result['wind'] = {'calm': True, 'description': 'Calm'}
            elif direction == 'VRB':
                desc = f"Variable at {speed_mph} mph"
                if gust_mph:
                    desc += f", gusting to {gust_mph} mph"
                result['wind'] = {
                    'calm': False, 'description': desc,
                    'speed_mph': speed_mph, 'gust_mph': gust_mph,
                }
            else:
                deg = int(direction)
                cardinal = degrees_to_cardinal(deg)
                desc = f"from the {cardinal} ({deg}°) at {speed_mph} mph"
                if gust_mph:
                    desc += f", gusting to {gust_mph} mph"
                result['wind'] = {
                    'calm': False, 'description': desc,
                    'degrees': deg, 'cardinal': cardinal,
                    'speed_mph': speed_mph, 'gust_mph': gust_mph,
                }
            idx += 1

        # Variable wind range token (e.g. '280V350') follows the main wind group
        # when direction varies more than 60° at speeds above 6 knots.
        if idx < len(tokens) and re.match(r'^\d{3}V\d{3}$', tokens[idx]):
            m = re.match(r'^(\d{3})V(\d{3})$', tokens[idx])
            assert m
            result['wind_variable'] = f"{m.group(1)}° to {m.group(2)}°"
            idx += 1

    # CAVOK (Ceiling And Visibility OK) replaces visibility + sky groups when
    # visibility ≥ 10 km, no cloud below 5,000 ft, and no significant weather.
    if idx < len(tokens) and tokens[idx] == 'CAVOK':
        result['visibility'] = {'raw': 'CAVOK', 'description': '10+ km — ceiling and visibility OK'}
        result['sky'] = [
            {'code': 'CAVOK', 'label': 'Clear',
             'description': 'no significant clouds below 5,000 ft'}
        ]
        idx += 1
    else:
        # Visibility: US reports use statute miles (SM); international use metres.
        if idx < len(tokens):
            tok = tokens[idx]
            if re.match(r'^\d+/\d+SM$', tok):
                # Fractional SM value, e.g. '1/4SM'
                num, denom = tok.replace('SM', '').split('/')
                vis = float(num) / float(denom)
                result['visibility'] = {'miles': vis, 'description': f"{vis:.2f} miles"}
                idx += 1
            elif (re.match(r'^\d+$', tok)
                  and idx + 1 < len(tokens)
                  and re.match(r'^\d+/\d+SM$', tokens[idx + 1])):
                # Mixed whole + fraction, e.g. '1 1/2SM'
                whole = int(tok)
                num, denom = tokens[idx + 1].replace('SM', '').split('/')
                vis = whole + float(num) / float(denom)
                result['visibility'] = {'miles': vis, 'description': f"{vis:.1f} miles"}
                idx += 2
            elif re.match(r'^\d+SM$', tok):
                # Whole-number SM value, e.g. '10SM'
                vis = int(tok.replace('SM', ''))
                desc = f"{vis}+ miles (excellent)" if vis >= 10 else f"{vis} miles"
                result['visibility'] = {'miles': vis, 'description': desc}
                idx += 1
            elif re.match(r'^\d{4}$', tok):
                # Metric visibility in metres (international format), e.g. '9999'
                meters = int(tok)
                km = meters / 1000
                miles = meters / 1609.34
                desc = (
                    "10+ km (excellent)" if meters >= 9999
                    else f"{km:.1f} km ({miles:.1f} miles)"
                )
                result['visibility'] = {'km': km, 'description': desc}
                idx += 1

        # Runway Visual Range groups (e.g. 'R28L/2400FT') — skip, not decoded.
        while idx < len(tokens) and re.match(r'^R\d{2}[LCR]?/', tokens[idx]):
            idx += 1

        # Present weather: optional intensity prefix, optional descriptor, one or
        # more phenomenon codes. Multiple groups may appear (e.g. '-RA FZFG').
        wx_pat = re.compile(
            r'^(\+|-|VC)?(MI|BC|PR|DR|BL|SH|TS|FZ)?'
            r'(DZ|RA|SN|SG|IC|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PO|SQ|FC|SS|DS)+$'
        )
        while idx < len(tokens) and wx_pat.match(tokens[idx]):
            decoded = decode_weather_token(tokens[idx])
            if decoded:
                result['weather'].append(decoded)
            idx += 1

        # Sky condition groups: coverage code + altitude in hundreds of feet +
        # optional CB (cumulonimbus) or TCU (towering cumulus) suffix.
        sky_pat = re.compile(r'^(SKC|CLR|NSC|FEW|SCT|BKN|OVC|VV)(\d{3})?(CB|TCU)?$')
        while idx < len(tokens) and sky_pat.match(tokens[idx]):
            m = sky_pat.match(tokens[idx])
            assert m
            code, alt_raw, cb = m.group(1), m.group(2), m.group(3)
            label, description = SKY_CONDITIONS.get(code, (code, code.lower()))
            entry = {'code': code, 'label': label, 'description': description}
            if alt_raw:
                alt_ft = int(alt_raw) * 100
                entry['altitude_ft'] = alt_ft
                entry['description'] = f"{description} at {alt_ft:,} ft"
            if cb == 'CB':
                entry['description'] += ' with cumulonimbus (thunderstorm clouds)'
            elif cb == 'TCU':
                entry['description'] += ' with towering cumulus'
            result['sky'].append(entry)
            idx += 1

    # Temperature / dew point: TT/DD in Celsius; 'M' prefix means negative.
    if idx < len(tokens):
        tm = re.match(r'^(M?\d+)/(M?\d+)?$', tokens[idx])
        if tm:
            temp_c = parse_temp_token(tm.group(1))
            result['temperature'] = {'celsius': temp_c, 'fahrenheit': c_to_f(temp_c)}
            if tm.group(2):
                dew_c = parse_temp_token(tm.group(2))
                result['dewpoint'] = {'celsius': dew_c, 'fahrenheit': c_to_f(dew_c)}
            idx += 1

    # Altimeter: 'A' prefix = inches of mercury (×100); 'Q' prefix = hectopascals.
    if idx < len(tokens):
        am = re.match(r'^(A|Q)(\d{4})$', tokens[idx])
        if am:
            a_type, a_val = am.group(1), int(am.group(2))
            if a_type == 'A':
                inhg = a_val / 100
                hpa = round(inhg * 33.8639)
            else:
                hpa = a_val
                inhg = round(hpa / 33.8639, 2)
            result['altimeter'] = {
                'inHg': inhg, 'hPa': hpa,
                'description': f"{inhg:.2f} inHg ({hpa} hPa)",
            }
            idx += 1

    return result


def build_summary(p: dict[str, Any]) -> str:
    """
    Build a single plain-English weather summary sentence from parsed METAR data.

    Args:
        p: The dictionary returned by parse_metar().

    Returns:
        A human-readable string describing current conditions, e.g.
        "Clear and mild at 72.5°F (22°C), winds from the West at 8 mph,
        visibility 10+ miles (excellent)."
    """
    # Determine overall sky condition from the worst layer reported.
    sky_codes = [s['code'] for s in p['sky']]
    if 'OVC' in sky_codes or 'VV' in sky_codes:
        sky_word = 'Overcast'
    elif 'BKN' in sky_codes:
        sky_word = 'Mostly cloudy'
    elif 'SCT' in sky_codes:
        sky_word = 'Partly cloudy'
    elif 'FEW' in sky_codes:
        sky_word = 'Mostly clear'
    elif any(c in sky_codes for c in ('SKC', 'CLR', 'NSC', 'CAVOK')):
        sky_word = 'Clear'
    else:
        sky_word = None

    # Map temperature to a colloquial feel word.
    temp_word = ''
    if p['temperature']:
        f = p['temperature']['fahrenheit']
        if f >= 95:
            temp_word = 'extremely hot'
        elif f >= 85:
            temp_word = 'hot'
        elif f >= 75:
            temp_word = 'warm'
        elif f >= 60:
            temp_word = 'mild'
        elif f >= 45:
            temp_word = 'cool'
        elif f >= 32:
            temp_word = 'cold'
        else:
            temp_word = 'freezing'

    # Opening clause combines sky and feel (e.g. "Clear and mild").
    opening = ''
    if sky_word and temp_word:
        opening = f"{sky_word} and {temp_word}"
    elif sky_word:
        opening = sky_word
    elif temp_word:
        opening = temp_word.capitalize()

    temp_detail = ''
    if p['temperature']:
        f = p['temperature']['fahrenheit']
        c = p['temperature']['celsius']
        temp_detail = f"{f}°F ({c}°C)"

    wx_clause = ', '.join(p['weather']) if p['weather'] else ''

    if p['wind']:
        wind_clause = 'winds calm' if p['wind']['calm'] else f"winds {p['wind']['description']}"
    else:
        wind_clause = ''

    vis_clause = f"visibility {p['visibility']['description']}" if p['visibility'] else ''

    # Assemble clauses into one flowing sentence.
    sentence_parts = []
    if opening and temp_detail:
        sentence_parts.append(f"{opening} at {temp_detail}")
    elif opening:
        sentence_parts.append(opening)
    elif temp_detail:
        sentence_parts.append(temp_detail)

    if wx_clause:
        sentence_parts.append(f"with {wx_clause}")
    if wind_clause:
        sentence_parts.append(wind_clause)
    if vis_clause:
        sentence_parts.append(vis_clause)

    if not sentence_parts:
        return 'No decoded weather available.'

    full = sentence_parts[0] + (
        (', ' + ', '.join(sentence_parts[1:])) if len(sentence_parts) > 1 else ''
    ) + '.'
    return full[0].upper() + full[1:]


@app.route('/')
def index() -> ResponseReturnValue:
    """Serve the main search page."""
    return render_template('index.html')


@app.route('/metar')
def get_metar() -> ResponseReturnValue:
    """
    Fetch and decode a METAR for the given airport code.

    Query parameters:
        code: ICAO or IATA airport code (3–4 characters).
              Three-letter US codes (e.g. 'SFO') are automatically retried
              with a 'K' prefix ('KSFO') if the first request returns no data.

    Returns:
        JSON with keys: airport, raw, parsed, summary — or an error message.
    """
    code = request.args.get('code', '').strip().upper()
    if not code:
        return jsonify({'error': 'Please enter an airport code.'}), 400
    if not re.match(r'^[A-Z0-9]{3,4}$', code):
        return jsonify({'error': 'Airport codes are 3–4 letters (e.g. KHIO, SFO, LAX).'}), 400

    # Build a list of codes to attempt. US IATA codes (3 letters) are retried
    # with a 'K' prefix to form the ICAO equivalent (e.g. SFO → KSFO).
    codes_to_try = [code]
    if len(code) == 3 and code.isalpha():
        codes_to_try.append('K' + code)

    try:
        raw = ''
        used_code = code
        for attempt in codes_to_try:
            url = f"https://aviationweather.gov/api/data/metar?ids={attempt}"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            raw = resp.text.strip()
            if raw:
                used_code = attempt
                break
        code = used_code
    except requests.exceptions.Timeout:
        return jsonify({'error': 'The weather service timed out. Please try again.'}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Could not reach the weather service: {e}'}), 502

    if not raw:
        return jsonify(
            {'error': f'No METAR data found for {code}. Check the airport code and try again.'}
        ), 404

    # The API may return multiple lines; take the first non-empty one.
    raw_line = next((ln.strip() for ln in raw.splitlines() if ln.strip()), '')
    if not raw_line:
        return jsonify({'error': f'No METAR data found for {code}.'}), 404

    parsed = parse_metar(raw_line)
    summary = build_summary(parsed)

    return jsonify({'airport': code, 'raw': raw_line, 'parsed': parsed, 'summary': summary})


if __name__ == '__main__':
    app.run(debug=True, port=5001)
