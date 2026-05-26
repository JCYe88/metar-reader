"""
Unit and route tests for the METAR Reader application.

Test strategy:
  - Unit tests validate parse_metar(), build_summary(), and helpers in
    isolation using hardcoded METAR strings — no network calls, no Flask.
  - Route tests exercise the /metar endpoint via Flask's test client with
    requests.get mocked so the test suite never hits the real API.
"""

import pytest
from unittest.mock import patch, MagicMock

from app import (
    app,
    parse_metar,
    build_summary,
    decode_weather_token,
    degrees_to_cardinal,
    c_to_f,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Flask test client with testing mode enabled."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def mock_metar_response(metar_string: str) -> MagicMock:
    """Return a mock requests.Response whose .text is the given METAR string."""
    mock = MagicMock()
    mock.text = metar_string
    mock.raise_for_status = MagicMock()
    return mock


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestDegreesToCardinal:
    def test_north(self):
        assert degrees_to_cardinal(0) == "North"

    def test_north_from_360(self):
        assert degrees_to_cardinal(360) == "North"

    def test_south(self):
        assert degrees_to_cardinal(180) == "South"

    def test_east(self):
        assert degrees_to_cardinal(90) == "East"

    def test_west(self):
        assert degrees_to_cardinal(270) == "West"

    def test_northeast(self):
        assert degrees_to_cardinal(45) == "NE"

    def test_southwest(self):
        assert degrees_to_cardinal(225) == "SW"


class TestCelsiusToFahrenheit:
    def test_freezing_point(self):
        assert c_to_f(0) == 32.0

    def test_boiling_point(self):
        assert c_to_f(100) == 212.0

    def test_body_temperature(self):
        assert c_to_f(37) == 98.6

    def test_negative(self):
        assert c_to_f(-40) == -40.0


# ---------------------------------------------------------------------------
# Weather token decoder tests
# ---------------------------------------------------------------------------


class TestDecodeWeatherToken:
    def test_light_rain(self):
        assert decode_weather_token("-RA") == "light rain"

    def test_heavy_snow(self):
        assert decode_weather_token("+SN") == "heavy snow"

    def test_fog(self):
        assert decode_weather_token("FG") == "fog"

    def test_mist(self):
        assert decode_weather_token("BR") == "mist"

    def test_thunderstorm_rain(self):
        assert decode_weather_token("TSRA") == "thunderstorm rain"

    def test_freezing_rain(self):
        assert decode_weather_token("FZRA") == "freezing rain"

    def test_shower_rain(self):
        assert decode_weather_token("SHRA") == "shower rain"

    def test_heavy_thunderstorm_rain(self):
        assert decode_weather_token("+TSRA") == "heavy thunderstorm rain"

    def test_unknown_code_returns_none(self):
        assert decode_weather_token("ZZ") is None


# ---------------------------------------------------------------------------
# parse_metar() unit tests
# ---------------------------------------------------------------------------


class TestParseMetarStation:
    def test_station_parsed(self):
        p = parse_metar("KHIO 251553Z 00000KT 10SM CLR 18/07 A2993")
        assert p["station"] == "KHIO"

    def test_station_with_metar_prefix(self):
        # Some feeds prepend the word METAR before the station ID
        p = parse_metar("METAR KSFO 251756Z 28010KT 10SM CLR 16/09 A2999")
        assert p["station"] == "KSFO"


class TestParseMetarTime:
    def test_time_parsed(self):
        p = parse_metar("KHIO 251553Z 00000KT 10SM CLR 18/07 A2993")
        assert p["time"] == {"day": 25, "hour": 15, "minute": 53}


class TestParseMetarWind:
    def test_calm_wind(self):
        p = parse_metar("KHIO 251553Z 00000KT 10SM CLR 18/07 A2993")
        assert p["wind"]["calm"] is True
        assert p["wind"]["description"] == "Calm"

    def test_directional_wind_knots(self):
        # 280° at 10 knots = ~12 mph
        p = parse_metar("KSFO 251756Z 28010KT 10SM CLR 16/09 A2999")
        assert p["wind"]["calm"] is False
        assert p["wind"]["degrees"] == 280
        assert p["wind"]["cardinal"] == "West"
        assert p["wind"]["speed_mph"] == 12

    def test_wind_with_gust(self):
        p = parse_metar("KJFK 251554Z 04015G25KT 10SM CLR 07/04 A2975")
        assert p["wind"]["speed_mph"] == 17
        assert p["wind"]["gust_mph"] == 29

    def test_variable_wind(self):
        p = parse_metar("KORD 251600Z VRB05KT 10SM CLR 15/05 A2990")
        assert p["wind"]["calm"] is False
        assert "Variable" in p["wind"]["description"]

    def test_variable_wind_range(self):
        p = parse_metar("KBOS 251600Z 28008KT 260V320 10SM CLR 12/04 A2988")
        assert p["wind_variable"] == "260° to 320°"

    def test_auto_station_flag(self):
        p = parse_metar("KSEA 251600Z AUTO 27012KT 10SM CLR 10/02 A2985")
        assert p["auto"] is True


class TestParseMetarVisibility:
    def test_ten_sm(self):
        p = parse_metar("KHIO 251553Z 00000KT 10SM CLR 18/07 A2993")
        assert p["visibility"]["miles"] == 10

    def test_fractional_sm(self):
        p = parse_metar("KJFK 251554Z 04015KT 1/2SM FG 07/04 A2975")
        assert p["visibility"]["miles"] == pytest.approx(0.5)

    def test_mixed_fraction_sm(self):
        p = parse_metar("KORD 251600Z 18010KT 1 1/2SM -RA 10/08 A2985")
        assert p["visibility"]["miles"] == pytest.approx(1.5)

    def test_cavok(self):
        p = parse_metar("EGLL 251550Z 13009KT CAVOK 16/09 Q1013")
        assert "ceiling and visibility OK" in p["visibility"]["description"]
        assert p["sky"][0]["code"] == "CAVOK"

    def test_metric_visibility(self):
        p = parse_metar("EGLL 251550Z 13009KT 9999 FEW020 16/09 Q1013")
        assert p["visibility"]["km"] == pytest.approx(9.999)


class TestParseMetarWeather:
    def test_light_rain(self):
        p = parse_metar("KJFK 251554Z 04015KT 3SM -RA OVC030 07/04 A2975")
        assert "light rain" in p["weather"]

    def test_heavy_snow(self):
        p = parse_metar("KORD 251600Z 18010KT 1SM +SN OVC010 M02/M05 A2970")
        assert "heavy snow" in p["weather"]

    def test_fog(self):
        p = parse_metar("KSFO 060056Z 00000KT 1/4SM FG OVC002 14/14 A2990")
        assert "fog" in p["weather"]

    def test_thunderstorm(self):
        p = parse_metar("KATL 251800Z 21015KT 5SM TSRA BKN040CB 28/22 A2985")
        assert "thunderstorm rain" in p["weather"]

    def test_no_weather(self):
        p = parse_metar("KHIO 251553Z 00000KT 10SM CLR 18/07 A2993")
        assert p["weather"] == []


class TestParseMetarSky:
    def test_clear(self):
        p = parse_metar("KHIO 251553Z 00000KT 10SM CLR 18/07 A2993")
        assert p["sky"][0]["code"] == "CLR"

    def test_few_with_altitude(self):
        p = parse_metar("KSFO 251756Z 28010KT 10SM FEW006 OVC025 16/09 A2999")
        assert p["sky"][0]["code"] == "FEW"
        assert p["sky"][0]["altitude_ft"] == 600

    def test_overcast_with_altitude(self):
        p = parse_metar("KSFO 251756Z 28010KT 10SM FEW006 OVC025 16/09 A2999")
        ovc = next(s for s in p["sky"] if s["code"] == "OVC")
        assert ovc["altitude_ft"] == 2500

    def test_multiple_layers(self):
        p = parse_metar("KSFO 251756Z 28010KT 10SM FEW006 SCT020 OVC040 16/09 A2999")
        assert len(p["sky"]) == 3

    def test_cumulonimbus_flag(self):
        p = parse_metar("KATL 251800Z 21015KT 5SM TSRA BKN040CB 28/22 A2985")
        bkn = next(s for s in p["sky"] if s["code"] == "BKN")
        assert "cumulonimbus" in bkn["description"]


class TestParseMetarTemperature:
    def test_positive_temp(self):
        p = parse_metar("KHIO 251553Z 00000KT 10SM CLR 18/07 A2993")
        assert p["temperature"]["celsius"] == 18
        assert p["temperature"]["fahrenheit"] == pytest.approx(64.4)

    def test_negative_temp(self):
        # M05 = -5°C
        p = parse_metar("PANC 251653Z 18008KT 2SM -SN OVC040 M05/M08 A2940")
        assert p["temperature"]["celsius"] == -5
        assert p["temperature"]["fahrenheit"] == pytest.approx(23.0)

    def test_dewpoint(self):
        p = parse_metar("KHIO 251553Z 00000KT 10SM CLR 18/07 A2993")
        assert p["dewpoint"]["celsius"] == 7

    def test_negative_dewpoint(self):
        p = parse_metar("PANC 251653Z 18008KT 2SM -SN OVC040 M05/M08 A2940")
        assert p["dewpoint"]["celsius"] == -8


class TestParseMetarAltimeter:
    def test_us_altimeter_inhg(self):
        p = parse_metar("KHIO 251553Z 00000KT 10SM CLR 18/07 A2993")
        assert p["altimeter"]["inHg"] == pytest.approx(29.93)
        assert p["altimeter"]["hPa"] == 1014

    def test_international_altimeter_hpa(self):
        p = parse_metar("EGLL 251550Z 13009KT 9999 FEW020 16/09 Q1013")
        assert p["altimeter"]["hPa"] == 1013
        assert p["altimeter"]["inHg"] == pytest.approx(29.91, abs=0.01)


class TestParseMetarRemarks:
    def test_remarks_stored(self):
        p = parse_metar("KHIO 251553Z 00000KT 10SM CLR 18/07 A2993 RMK AO2 SLP133")
        assert "AO2" in p["remarks"]

    def test_no_remarks(self):
        p = parse_metar("KHIO 251553Z 00000KT 10SM CLR 18/07 A2993")
        assert p["remarks"] is None


# ---------------------------------------------------------------------------
# build_summary() tests
# ---------------------------------------------------------------------------


class TestBuildSummary:
    def test_clear_and_mild(self):
        p = parse_metar("KHIO 251553Z 00000KT 10SM CLR 18/07 A2993")
        summary = build_summary(p)
        assert "Clear" in summary
        assert "mild" in summary
        assert "64.4°F" in summary
        assert "calm" in summary.lower()

    def test_overcast_and_cold_with_snow(self):
        p = parse_metar("PANC 251653Z 18008KT 2SM -SN OVC040 M05/M08 A2940")
        summary = build_summary(p)
        assert "Overcast" in summary
        assert "freezing" in summary
        assert "light snow" in summary

    def test_wind_description_in_summary(self):
        p = parse_metar("KSFO 251756Z 28010KT 10SM CLR 16/09 A2999")
        summary = build_summary(p)
        assert "West" in summary
        assert "mph" in summary

    def test_summary_ends_with_period(self):
        p = parse_metar("KHIO 251553Z 00000KT 10SM CLR 18/07 A2993")
        assert build_summary(p).endswith(".")

    def test_summary_starts_with_capital(self):
        p = parse_metar("KHIO 251553Z 00000KT 10SM CLR 18/07 A2993")
        assert build_summary(p)[0].isupper()


# ---------------------------------------------------------------------------
# Flask route tests (requests.get is mocked)
# ---------------------------------------------------------------------------


class TestMetarRoute:
    def test_missing_code_returns_400(self, client):
        resp = client.get("/metar?code=")
        assert resp.status_code == 400

    def test_invalid_code_format_returns_400(self, client):
        resp = client.get("/metar?code=!!")
        assert resp.status_code == 400

    def test_valid_icao_returns_200(self, client):
        with patch("app.requests.get") as mock_get:
            mock_get.return_value = mock_metar_response(
                "KHIO 251553Z 00000KT 10SM CLR 18/07 A2993 RMK AO2"
            )
            resp = client.get("/metar?code=KHIO")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["airport"] == "KHIO"
        assert "summary" in data
        assert "parsed" in data

    def test_empty_api_response_returns_404(self, client):
        with patch("app.requests.get") as mock_get:
            mock_get.return_value = mock_metar_response("")
            resp = client.get("/metar?code=XXXX")
        assert resp.status_code == 404

    def test_iata_code_retried_with_k_prefix(self, client):
        """3-letter IATA code (SFO) should fall back to KSFO when first attempt returns nothing."""  # noqa: E501

        def side_effect(url, timeout):
            mock = MagicMock()
            mock.raise_for_status = MagicMock()
            # Return empty for SFO, real data for KSFO
            mock.text = (
                "" if "ids=SFO" in url else "KSFO 251756Z 28010KT 10SM CLR 16/09 A2999"
            )
            return mock

        with patch("app.requests.get", side_effect=side_effect):
            resp = client.get("/metar?code=SFO")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["airport"] == "KSFO"

    def test_api_timeout_returns_504(self, client):
        import requests as req

        with patch("app.requests.get", side_effect=req.exceptions.Timeout):
            resp = client.get("/metar?code=KHIO")
        assert resp.status_code == 504

    def test_api_connection_error_returns_502(self, client):
        import requests as req

        with patch("app.requests.get", side_effect=req.exceptions.ConnectionError):
            resp = client.get("/metar?code=KHIO")
        assert resp.status_code == 502

    def test_homepage_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
