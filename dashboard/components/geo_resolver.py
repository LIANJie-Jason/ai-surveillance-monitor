"""Maps city/region names from articles to admin-1 boundary names in GeoJSON."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models import Article

# Case-insensitive lookup: all keys are lowercase.
# Values are the EXACT admin-1 name from Natural Earth GeoJSON.
REGION_TO_ADMIN1: dict[str, dict[str, str]] = {
    "IN": {
        # Delhi / NCT
        "delhi": "Delhi",
        "new delhi": "Delhi",
        "nct delhi": "Delhi",
        "delhi ncr": "Delhi",
        "national capital region": "Delhi",
        "ncr": "Delhi",
        # Maharashtra (Mumbai, Pune)
        "mumbai": "Maharashtra",
        "bombay": "Maharashtra",
        "maharashtra": "Maharashtra",
        "greater mumbai": "Maharashtra",
        "pune": "Maharashtra",
        "poona": "Maharashtra",
        # Karnataka (Bangalore)
        "bangalore": "Karnataka",
        "bengaluru": "Karnataka",
        "karnataka": "Karnataka",
        "silicon valley of india": "Karnataka",
        # Tamil Nadu (Chennai)
        "chennai": "Tamil Nadu",
        "madras": "Tamil Nadu",
        "tamil nadu": "Tamil Nadu",
        # West Bengal (Kolkata)
        "kolkata": "West Bengal",
        "calcutta": "West Bengal",
        "west bengal": "West Bengal",
        # Telangana (Hyderabad)
        "hyderabad": "Telangana",
        "telangana": "Telangana",
        "cyberabad": "Telangana",
        # Gujarat (Ahmedabad)
        "ahmedabad": "Gujarat",
        "amdavad": "Gujarat",
        "gujarat": "Gujarat",
        # Rajasthan (Jaipur)
        "jaipur": "Rajasthan",
        "rajasthan": "Rajasthan",
        "pink city": "Rajasthan",
        # Uttar Pradesh (Lucknow)
        "lucknow": "Uttar Pradesh",
        "uttar pradesh": "Uttar Pradesh",
        "up": "Uttar Pradesh",
    },
    "MY": {
        # Kuala Lumpur
        "kuala lumpur": "Kuala Lumpur",
        "kl": "Kuala Lumpur",
        "federal territory": "Kuala Lumpur",
        "federal territory of kuala lumpur": "Kuala Lumpur",
        # Pulau Pinang (Penang)
        "penang": "Pulau Pinang",
        "pulau pinang": "Pulau Pinang",
        "george town": "Pulau Pinang",
        "georgetown": "Pulau Pinang",
        # Johor
        "johor bahru": "Johor",
        "jb": "Johor",
        "johor": "Johor",
        # Selangor
        "selangor": "Selangor",
        "shah alam": "Selangor",
        "petaling jaya": "Selangor",
        "pj": "Selangor",
        "subang jaya": "Selangor",
        "klang valley": "Selangor",
        # Sabah
        "sabah": "Sabah",
        "kota kinabalu": "Sabah",
        "kk": "Sabah",
        "north borneo": "Sabah",
        # Sarawak
        "sarawak": "Sarawak",
        "kuching": "Sarawak",
        "sarawak borneo": "Sarawak",
        # Putrajaya
        "putrajaya": "Putrajaya",
        "federal territory of putrajaya": "Putrajaya",
        # Melaka
        "malacca": "Melaka",
        "melaka": "Melaka",
        "malacca city": "Melaka",
    },
    "NG": {
        # Lagos
        "lagos": "Lagos",
        "lagos state": "Lagos",
        "lagos island": "Lagos",
        "victoria island": "Lagos",
        "ikeja": "Lagos",
        "lekki": "Lagos",
        # Federal Capital Territory (Abuja)
        "abuja": "Federal Capital Territory",
        "fct": "Federal Capital Territory",
        "federal capital territory": "Federal Capital Territory",
        # Kano
        "kano": "Kano",
        "kano state": "Kano",
        # Rivers (Port Harcourt)
        "port harcourt": "Rivers",
        "rivers state": "Rivers",
        "rivers": "Rivers",
        "ph": "Rivers",
        # Oyo (Ibadan)
        "ibadan": "Oyo",
        "oyo state": "Oyo",
        "oyo": "Oyo",
        # Kaduna
        "kaduna": "Kaduna",
        "kaduna state": "Kaduna",
        # Enugu
        "enugu": "Enugu",
        "enugu state": "Enugu",
        # Edo (Benin City)
        "benin city": "Edo",
        "edo state": "Edo",
        "edo": "Edo",
        # Borno (Maiduguri)
        "maiduguri": "Borno",
        "borno state": "Borno",
        "borno": "Borno",
        # Sokoto
        "sokoto": "Sokoto",
        "sokoto state": "Sokoto",
    },
    "ZA": {
        # Gauteng (Johannesburg, Pretoria)
        "johannesburg": "Gauteng",
        "joburg": "Gauteng",
        "jozi": "Gauteng",
        "gauteng": "Gauteng",
        "egoli": "Gauteng",
        "sandton": "Gauteng",
        "pretoria": "Gauteng",
        "tshwane": "Gauteng",
        "administrative capital": "Gauteng",
        "jacaranda city": "Gauteng",
        # Western Cape (Cape Town)
        "cape town": "Western Cape",
        "mother city": "Western Cape",
        "western cape": "Western Cape",
        "kaapstad": "Western Cape",
        # KwaZulu-Natal (Durban)
        "durban": "KwaZulu-Natal",
        "ethekwini": "KwaZulu-Natal",
        "kwazulu-natal": "KwaZulu-Natal",
        "kzn": "KwaZulu-Natal",
        # Eastern Cape (Port Elizabeth, East London)
        "port elizabeth": "Eastern Cape",
        "gqeberha": "Eastern Cape",
        "nelson mandela bay": "Eastern Cape",
        "eastern cape": "Eastern Cape",
        "east london": "Eastern Cape",
        "buffalo city": "Eastern Cape",
        # Free State (Bloemfontein)
        "bloemfontein": "Free State",
        "mangaung": "Free State",
        "free state": "Free State",
        "judicial capital": "Free State",
        # Limpopo (Polokwane)
        "polokwane": "Limpopo",
        "pietersburg": "Limpopo",
        "limpopo": "Limpopo",
        # Mpumalanga (Nelspruit)
        "nelspruit": "Mpumalanga",
        "mbombela": "Mpumalanga",
        "mpumalanga": "Mpumalanga",
        # Northern Cape (Kimberley)
        "kimberley": "Northern Cape",
        "northern cape": "Northern Cape",
        "diamond city": "Northern Cape",
    },
}


def resolve_admin1(country_code: str, region_name: str) -> str | None:
    """Resolve a city/region name to its admin-1 boundary name.

    Case-insensitive lookup. Returns None if no mapping found.
    """
    country_map = REGION_TO_ADMIN1.get(country_code)
    if not country_map:
        return None
    return country_map.get(region_name.lower().strip())


def build_admin1_article_counts(
    articles: list[Article],
    country_code: str,
) -> dict[str, int]:
    """Aggregate article counts by admin-1 region name.

    Articles whose country_code does not match, or whose region cannot
    be resolved, are silently skipped.
    """
    counts: dict[str, int] = {}
    for article in articles:
        if not article.region:
            continue
        if article.country_code != country_code:
            continue
        admin1 = resolve_admin1(country_code, article.region)
        if admin1:
            counts[admin1] = counts.get(admin1, 0) + 1
    return counts
