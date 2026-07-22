"""
Dynamic fare calculation based on:
  1. Great-circle distance between origin/destination airports (haversine)
  2. Seat class multiplier (business costs more than economy)
  3. Time-of-day surcharge (peak departure hours cost more)

This replaces the old flat "economy = 4999, business = 12999" pricing.
"""

import math
from datetime import datetime

# Approximate lat/lon for major Indian airports.
# Matches the airport codes used in the frontend dropdowns and seed script.
AIRPORT_COORDS = {
    "DEL": (28.5562, 77.1000),   # Delhi
    "BOM": (19.0896, 72.8656),   # Mumbai
    "BLR": (13.1986, 77.7066),   # Bengaluru
    "MAA": (12.9941, 80.1709),   # Chennai
    "CCU": (22.6547, 88.4467),   # Kolkata
    "HYD": (17.2403, 78.4294),   # Hyderabad
    "AMD": (23.0772, 72.6347),   # Ahmedabad
    "PNQ": (18.5822, 73.9197),   # Pune
    "GOI": (15.3800, 73.8310),   # Goa
    "COK": (10.1520, 76.4019),   # Kochi
    "JAI": (26.8242, 75.8122),   # Jaipur
    "LKO": (26.7606, 80.8893),   # Lucknow
    "IXC": (30.6735, 76.7885),   # Chandigarh
    "GAU": (26.1061, 91.5859),   # Guwahati
    "PAT": (25.5913, 85.0880),   # Patna
    "BBI": (20.2444, 85.8178),   # Bhubaneswar
    "TRV": (8.4821, 76.9200),    # Thiruvananthapuram
    "VNS": (25.4524, 82.8593),   # Varanasi
    "IDR": (22.7218, 75.8011),   # Indore
    "NAG": (21.0922, 79.0472),   # Nagpur
    "RPR": (21.1804, 81.7388),   # Raipur
    "SXR": (33.9871, 74.7742),   # Srinagar
    "IXJ": (32.6891, 74.8374),   # Jammu
    "ATQ": (31.7096, 74.7973),   # Amritsar
}

BASE_FARE = 1200.0          # flat starting fare, covers airport fees etc.
RATE_PER_KM = 6.2           # economy ₹ per km
BUSINESS_MULTIPLIER = 2.3   # business class costs 2.3x economy for the same route
PEAK_SURCHARGE = 0.18       # +18% during peak hours
PEAK_HOURS = set(list(range(6, 10)) + list(range(17, 21)))  # 6-9am, 5-8pm


def get_distance_km(origin: str, destination: str) -> float:
    """Great-circle (haversine) distance between two airport codes, in km."""
    if origin not in AIRPORT_COORDS or destination not in AIRPORT_COORDS:
        return 800.0  # sane fallback for any airport not in our table

    lat1, lon1 = AIRPORT_COORDS[origin]
    lat2, lon2 = AIRPORT_COORDS[destination]

    R = 6371.0  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 1)


def calculate_fare(
    origin: str,
    destination: str,
    seat_class: str,
    departure_time: datetime,
) -> float:
    """
    Fare = base + (distance * per-km rate), scaled by class multiplier,
    plus a peak-hour surcharge based on departure time.
    """
    distance = get_distance_km(origin, destination)

    fare = BASE_FARE + (distance * RATE_PER_KM)

    if seat_class == "business":
        fare *= BUSINESS_MULTIPLIER

    if departure_time.hour in PEAK_HOURS:
        fare *= (1 + PEAK_SURCHARGE)

    return round(fare, 2)