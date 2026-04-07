"""Global map component — deck.gl world map with country markers."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from dashboard.components._utils import safe_json_for_script

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "static" / "deck_map.html"

# Drill-down countries with region-level views
DRILL_DOWN_COUNTRIES: tuple[str, ...] = ("MY", "NG", "IN", "ZA")

# Country centroid coordinates (~200 countries)
# Format: {ISO2: {"lat": float, "lng": float, "name": str}}
COUNTRY_COORDS: dict[str, dict[str, Any]] = {
    "AF": {"lat": 33.94, "lng": 67.71, "name": "Afghanistan"},
    "AL": {"lat": 41.15, "lng": 20.17, "name": "Albania"},
    "DZ": {"lat": 28.03, "lng": 1.66, "name": "Algeria"},
    "AO": {"lat": -11.20, "lng": 17.87, "name": "Angola"},
    "AR": {"lat": -38.42, "lng": -63.62, "name": "Argentina"},
    "AM": {"lat": 40.07, "lng": 45.04, "name": "Armenia"},
    "AU": {"lat": -25.27, "lng": 133.78, "name": "Australia"},
    "AT": {"lat": 47.52, "lng": 14.55, "name": "Austria"},
    "AZ": {"lat": 40.14, "lng": 47.58, "name": "Azerbaijan"},
    "BH": {"lat": 26.07, "lng": 50.56, "name": "Bahrain"},
    "BD": {"lat": 23.68, "lng": 90.36, "name": "Bangladesh"},
    "BY": {"lat": 53.71, "lng": 27.95, "name": "Belarus"},
    "BE": {"lat": 50.50, "lng": 4.47, "name": "Belgium"},
    "BJ": {"lat": 9.31, "lng": 2.32, "name": "Benin"},
    "BO": {"lat": -16.29, "lng": -63.59, "name": "Bolivia"},
    "BA": {"lat": 43.92, "lng": 17.68, "name": "Bosnia and Herzegovina"},
    "BW": {"lat": -22.33, "lng": 24.68, "name": "Botswana"},
    "BR": {"lat": -14.24, "lng": -51.93, "name": "Brazil"},
    "BN": {"lat": 4.54, "lng": 114.73, "name": "Brunei"},
    "BG": {"lat": 42.73, "lng": 25.49, "name": "Bulgaria"},
    "BF": {"lat": 12.24, "lng": -1.56, "name": "Burkina Faso"},
    "BI": {"lat": -3.37, "lng": 29.92, "name": "Burundi"},
    "KH": {"lat": 12.57, "lng": 104.99, "name": "Cambodia"},
    "CM": {"lat": 7.37, "lng": 12.35, "name": "Cameroon"},
    "CA": {"lat": 56.13, "lng": -106.35, "name": "Canada"},
    "CF": {"lat": 6.61, "lng": 20.94, "name": "Central African Republic"},
    "TD": {"lat": 15.45, "lng": 18.73, "name": "Chad"},
    "CL": {"lat": -35.68, "lng": -71.54, "name": "Chile"},
    "CN": {"lat": 35.86, "lng": 104.20, "name": "China"},
    "CO": {"lat": 4.57, "lng": -74.30, "name": "Colombia"},
    "CD": {"lat": -4.04, "lng": 21.76, "name": "DR Congo"},
    "CG": {"lat": -0.23, "lng": 15.83, "name": "Congo"},
    "CR": {"lat": 9.75, "lng": -83.75, "name": "Costa Rica"},
    "CI": {"lat": 7.54, "lng": -5.55, "name": "Ivory Coast"},
    "HR": {"lat": 45.10, "lng": 15.20, "name": "Croatia"},
    "CU": {"lat": 21.52, "lng": -77.78, "name": "Cuba"},
    "CY": {"lat": 35.13, "lng": 33.43, "name": "Cyprus"},
    "CZ": {"lat": 49.82, "lng": 15.47, "name": "Czech Republic"},
    "DK": {"lat": 56.26, "lng": 9.50, "name": "Denmark"},
    "DJ": {"lat": 11.83, "lng": 42.59, "name": "Djibouti"},
    "DO": {"lat": 18.74, "lng": -70.16, "name": "Dominican Republic"},
    "EC": {"lat": -1.83, "lng": -78.18, "name": "Ecuador"},
    "EG": {"lat": 26.82, "lng": 30.80, "name": "Egypt"},
    "SV": {"lat": 13.79, "lng": -88.90, "name": "El Salvador"},
    "GQ": {"lat": 1.65, "lng": 10.27, "name": "Equatorial Guinea"},
    "ER": {"lat": 15.18, "lng": 39.78, "name": "Eritrea"},
    "EE": {"lat": 58.60, "lng": 25.01, "name": "Estonia"},
    "SZ": {"lat": -26.52, "lng": 31.47, "name": "Eswatini"},
    "ET": {"lat": 9.15, "lng": 40.49, "name": "Ethiopia"},
    "FI": {"lat": 61.92, "lng": 25.75, "name": "Finland"},
    "FR": {"lat": 46.23, "lng": 2.21, "name": "France"},
    "GA": {"lat": -0.80, "lng": 11.61, "name": "Gabon"},
    "GM": {"lat": 13.44, "lng": -15.31, "name": "Gambia"},
    "GE": {"lat": 42.32, "lng": 43.36, "name": "Georgia"},
    "DE": {"lat": 51.17, "lng": 10.45, "name": "Germany"},
    "GH": {"lat": 7.95, "lng": -1.02, "name": "Ghana"},
    "GR": {"lat": 39.07, "lng": 21.82, "name": "Greece"},
    "GT": {"lat": 15.78, "lng": -90.23, "name": "Guatemala"},
    "GN": {"lat": 9.95, "lng": -9.70, "name": "Guinea"},
    "GW": {"lat": 11.80, "lng": -15.18, "name": "Guinea-Bissau"},
    "GY": {"lat": 4.86, "lng": -58.93, "name": "Guyana"},
    "HT": {"lat": 18.97, "lng": -72.29, "name": "Haiti"},
    "HN": {"lat": 15.20, "lng": -86.24, "name": "Honduras"},
    "HU": {"lat": 47.16, "lng": 19.50, "name": "Hungary"},
    "IS": {"lat": 64.96, "lng": -19.02, "name": "Iceland"},
    "IN": {"lat": 20.59, "lng": 78.96, "name": "India"},
    "ID": {"lat": -0.79, "lng": 113.92, "name": "Indonesia"},
    "IR": {"lat": 32.43, "lng": 53.69, "name": "Iran"},
    "IQ": {"lat": 33.22, "lng": 43.68, "name": "Iraq"},
    "IE": {"lat": 53.14, "lng": -7.69, "name": "Ireland"},
    "IL": {"lat": 31.05, "lng": 34.85, "name": "Israel"},
    "IT": {"lat": 41.87, "lng": 12.57, "name": "Italy"},
    "JM": {"lat": 18.11, "lng": -77.30, "name": "Jamaica"},
    "JP": {"lat": 36.20, "lng": 138.25, "name": "Japan"},
    "JO": {"lat": 30.59, "lng": 36.24, "name": "Jordan"},
    "KZ": {"lat": 48.02, "lng": 66.92, "name": "Kazakhstan"},
    "KE": {"lat": -0.02, "lng": 37.91, "name": "Kenya"},
    "KP": {"lat": 40.34, "lng": 127.51, "name": "North Korea"},
    "KR": {"lat": 35.91, "lng": 127.77, "name": "South Korea"},
    "KW": {"lat": 29.31, "lng": 47.48, "name": "Kuwait"},
    "KG": {"lat": 41.20, "lng": 74.77, "name": "Kyrgyzstan"},
    "LA": {"lat": 19.86, "lng": 102.50, "name": "Laos"},
    "LV": {"lat": 56.88, "lng": 24.60, "name": "Latvia"},
    "LB": {"lat": 33.85, "lng": 35.86, "name": "Lebanon"},
    "LS": {"lat": -29.61, "lng": 28.23, "name": "Lesotho"},
    "LR": {"lat": 6.43, "lng": -9.43, "name": "Liberia"},
    "LY": {"lat": 26.34, "lng": 17.23, "name": "Libya"},
    "LT": {"lat": 55.17, "lng": 23.88, "name": "Lithuania"},
    "LU": {"lat": 49.82, "lng": 6.13, "name": "Luxembourg"},
    "MG": {"lat": -18.77, "lng": 46.87, "name": "Madagascar"},
    "MW": {"lat": -13.25, "lng": 34.30, "name": "Malawi"},
    "MY": {"lat": 4.21, "lng": 101.98, "name": "Malaysia"},
    "ML": {"lat": 17.57, "lng": -4.00, "name": "Mali"},
    "MR": {"lat": 21.01, "lng": -10.94, "name": "Mauritania"},
    "MX": {"lat": 23.63, "lng": -102.55, "name": "Mexico"},
    "MD": {"lat": 47.41, "lng": 28.37, "name": "Moldova"},
    "MN": {"lat": 46.86, "lng": 103.85, "name": "Mongolia"},
    "ME": {"lat": 42.71, "lng": 19.37, "name": "Montenegro"},
    "MA": {"lat": 31.79, "lng": -7.09, "name": "Morocco"},
    "MZ": {"lat": -18.67, "lng": 35.53, "name": "Mozambique"},
    "MM": {"lat": 21.91, "lng": 95.96, "name": "Myanmar"},
    "NA": {"lat": -22.96, "lng": 18.49, "name": "Namibia"},
    "NP": {"lat": 28.39, "lng": 84.12, "name": "Nepal"},
    "NL": {"lat": 52.13, "lng": 5.29, "name": "Netherlands"},
    "NZ": {"lat": -40.90, "lng": 174.89, "name": "New Zealand"},
    "NI": {"lat": 12.87, "lng": -85.21, "name": "Nicaragua"},
    "NE": {"lat": 17.61, "lng": 8.08, "name": "Niger"},
    "NG": {"lat": 9.08, "lng": 8.68, "name": "Nigeria"},
    "MK": {"lat": 41.51, "lng": 21.75, "name": "North Macedonia"},
    "NO": {"lat": 60.47, "lng": 8.47, "name": "Norway"},
    "OM": {"lat": 21.47, "lng": 55.98, "name": "Oman"},
    "PK": {"lat": 30.38, "lng": 69.35, "name": "Pakistan"},
    "PS": {"lat": 31.95, "lng": 35.23, "name": "Palestine"},
    "PA": {"lat": 8.54, "lng": -80.78, "name": "Panama"},
    "PG": {"lat": -6.31, "lng": 143.96, "name": "Papua New Guinea"},
    "PY": {"lat": -23.44, "lng": -58.44, "name": "Paraguay"},
    "PE": {"lat": -9.19, "lng": -75.02, "name": "Peru"},
    "PH": {"lat": 12.88, "lng": 121.77, "name": "Philippines"},
    "PL": {"lat": 51.92, "lng": 19.15, "name": "Poland"},
    "PT": {"lat": 39.40, "lng": -8.22, "name": "Portugal"},
    "QA": {"lat": 25.35, "lng": 51.18, "name": "Qatar"},
    "RO": {"lat": 45.94, "lng": 24.97, "name": "Romania"},
    "RU": {"lat": 61.52, "lng": 105.32, "name": "Russia"},
    "RW": {"lat": -1.94, "lng": 29.87, "name": "Rwanda"},
    "SA": {"lat": 23.89, "lng": 45.08, "name": "Saudi Arabia"},
    "SN": {"lat": 14.50, "lng": -14.45, "name": "Senegal"},
    "RS": {"lat": 44.02, "lng": 21.01, "name": "Serbia"},
    "SL": {"lat": 8.46, "lng": -11.78, "name": "Sierra Leone"},
    "SG": {"lat": 1.35, "lng": 103.82, "name": "Singapore"},
    "SK": {"lat": 48.67, "lng": 19.70, "name": "Slovakia"},
    "SI": {"lat": 46.15, "lng": 14.99, "name": "Slovenia"},
    "SO": {"lat": 5.15, "lng": 46.20, "name": "Somalia"},
    "ZA": {"lat": -30.56, "lng": 22.94, "name": "South Africa"},
    "SS": {"lat": 6.88, "lng": 31.31, "name": "South Sudan"},
    "ES": {"lat": 40.46, "lng": -3.75, "name": "Spain"},
    "LK": {"lat": 7.87, "lng": 80.77, "name": "Sri Lanka"},
    "SD": {"lat": 12.86, "lng": 30.22, "name": "Sudan"},
    "SR": {"lat": 3.92, "lng": -56.03, "name": "Suriname"},
    "SE": {"lat": 60.13, "lng": 18.64, "name": "Sweden"},
    "CH": {"lat": 46.82, "lng": 8.23, "name": "Switzerland"},
    "SY": {"lat": 34.80, "lng": 38.99, "name": "Syria"},
    "TW": {"lat": 23.70, "lng": 120.96, "name": "Taiwan"},
    "TJ": {"lat": 38.86, "lng": 71.28, "name": "Tajikistan"},
    "TZ": {"lat": -6.37, "lng": 34.89, "name": "Tanzania"},
    "TH": {"lat": 15.87, "lng": 100.99, "name": "Thailand"},
    "TL": {"lat": -8.87, "lng": 125.73, "name": "Timor-Leste"},
    "TG": {"lat": 8.62, "lng": 0.82, "name": "Togo"},
    "TT": {"lat": 10.69, "lng": -61.22, "name": "Trinidad and Tobago"},
    "TN": {"lat": 33.89, "lng": 9.54, "name": "Tunisia"},
    "TR": {"lat": 38.96, "lng": 35.24, "name": "Turkey"},
    "TM": {"lat": 38.97, "lng": 59.56, "name": "Turkmenistan"},
    "UG": {"lat": 1.37, "lng": 32.29, "name": "Uganda"},
    "UA": {"lat": 48.38, "lng": 31.17, "name": "Ukraine"},
    "AE": {"lat": 23.42, "lng": 53.85, "name": "United Arab Emirates"},
    "GB": {"lat": 55.38, "lng": -3.44, "name": "United Kingdom"},
    "US": {"lat": 37.09, "lng": -95.71, "name": "United States"},
    "UY": {"lat": -32.52, "lng": -55.77, "name": "Uruguay"},
    "UZ": {"lat": 41.38, "lng": 64.59, "name": "Uzbekistan"},
    "VE": {"lat": 6.42, "lng": -66.59, "name": "Venezuela"},
    "VN": {"lat": 14.06, "lng": 108.28, "name": "Vietnam"},
    "YE": {"lat": 15.55, "lng": 48.52, "name": "Yemen"},
    "ZM": {"lat": -13.13, "lng": 27.85, "name": "Zambia"},
    "ZW": {"lat": -19.02, "lng": 29.15, "name": "Zimbabwe"},
    # Additional countries for broader coverage
    "AD": {"lat": 42.55, "lng": 1.60, "name": "Andorra"},
    "AG": {"lat": 17.06, "lng": -61.80, "name": "Antigua and Barbuda"},
    "BS": {"lat": 25.03, "lng": -77.40, "name": "Bahamas"},
    "BB": {"lat": 13.19, "lng": -59.54, "name": "Barbados"},
    "BZ": {"lat": 17.19, "lng": -88.50, "name": "Belize"},
    "BT": {"lat": 27.51, "lng": 90.43, "name": "Bhutan"},
    "CV": {"lat": 16.00, "lng": -24.01, "name": "Cape Verde"},
    "KM": {"lat": -11.88, "lng": 43.87, "name": "Comoros"},
    "DM": {"lat": 15.41, "lng": -61.37, "name": "Dominica"},
    "FJ": {"lat": -17.71, "lng": 178.07, "name": "Fiji"},
    "GD": {"lat": 12.12, "lng": -61.68, "name": "Grenada"},
    "KI": {"lat": 1.87, "lng": -157.36, "name": "Kiribati"},
    "LI": {"lat": 47.17, "lng": 9.56, "name": "Liechtenstein"},
    "MV": {"lat": 3.20, "lng": 73.22, "name": "Maldives"},
    "MT": {"lat": 35.94, "lng": 14.38, "name": "Malta"},
    "MH": {"lat": 7.13, "lng": 171.18, "name": "Marshall Islands"},
    "MU": {"lat": -20.35, "lng": 57.55, "name": "Mauritius"},
    "FM": {"lat": 7.43, "lng": 150.55, "name": "Micronesia"},
    "MC": {"lat": 43.75, "lng": 7.41, "name": "Monaco"},
    "NR": {"lat": -0.52, "lng": 166.93, "name": "Nauru"},
    "PW": {"lat": 7.51, "lng": 134.58, "name": "Palau"},
    "WS": {"lat": -13.76, "lng": -172.10, "name": "Samoa"},
    "SM": {"lat": 43.94, "lng": 12.46, "name": "San Marino"},
    "ST": {"lat": 0.19, "lng": 6.61, "name": "Sao Tome and Principe"},
    "SC": {"lat": -4.68, "lng": 55.49, "name": "Seychelles"},
    "SB": {"lat": -9.43, "lng": 160.02, "name": "Solomon Islands"},
    "KN": {"lat": 17.36, "lng": -62.78, "name": "Saint Kitts and Nevis"},
    "LC": {"lat": 13.91, "lng": -60.98, "name": "Saint Lucia"},
    "VC": {"lat": 12.98, "lng": -61.29, "name": "Saint Vincent and the Grenadines"},
    "TO": {"lat": -21.18, "lng": -175.20, "name": "Tonga"},
    "TV": {"lat": -7.11, "lng": 177.65, "name": "Tuvalu"},
    "VU": {"lat": -15.38, "lng": 166.96, "name": "Vanuatu"},
    "VA": {"lat": 41.90, "lng": 12.45, "name": "Vatican City"},
    "HK": {"lat": 22.40, "lng": 114.11, "name": "Hong Kong"},
    "MO": {"lat": 22.20, "lng": 113.54, "name": "Macau"},
    "XK": {"lat": 42.60, "lng": 20.90, "name": "Kosovo"},
}


def build_map_data(country_counts: dict[str, int]) -> list[dict[str, Any]]:
    """Convert {country_code: count} to list of dicts with lat/lng for deck.gl.

    Skips country codes not found in COUNTRY_COORDS.
    Coerces count to non-negative int; skips non-numeric or negative values.
    """
    data: list[dict[str, Any]] = []
    for cc, count in country_counts.items():
        coord = COUNTRY_COORDS.get(cc)
        if coord is None:
            continue
        try:
            float_count = float(count)
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(float_count) or float_count < 0:
            continue
        int_count = int(float_count)
        data.append({
            "lat": coord["lat"],
            "lng": coord["lng"],
            "count": int_count,
            "country_code": cc,
            "country_name": coord["name"],
        })
    return data


_DEFAULT_VIEW_STATE = (
    "latitude: 20,\n"
    "        longitude: 30,\n"
    "        zoom: 1.8,"
)


def render_map_html(data: list[dict[str, Any]]) -> str:
    """Render the deck.gl map HTML with injected data.

    Reads the template from dashboard/static/deck_map.html and replaces
    the __DATA__ and __INITIAL_VIEW_STATE__ placeholders.
    """
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    json_blob = safe_json_for_script(data)
    rendered = template.replace("__DATA__", json_blob)
    rendered = rendered.replace("__INITIAL_VIEW_STATE__", _DEFAULT_VIEW_STATE)
    return rendered
