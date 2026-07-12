"""
travel_search_tool.py — stub coded tools for uc_travel_booking demo.
No external API calls. Generates plausible-looking flight/hotel/booking
data so the full AAOSA network can run without any cloud dependencies.
"""

import hashlib
import logging
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

logger = logging.getLogger(__name__)


def _short_hash(seed: str, length: int = 5) -> str:
    """Deterministic short numeric hash from a seed string."""
    return str(int(hashlib.md5(seed.encode()).hexdigest(), 16))[:length]


# ---------------------------------------------------------------------------
# Flight Search
# ---------------------------------------------------------------------------

_AIRLINES = [
    ("United Airlines", "UA"),
    ("Delta Air Lines", "DL"),
    ("American Airlines", "AA"),
    ("British Airways", "BA"),
    ("Air Canada", "AC"),
    ("Lufthansa", "LH"),
]

_CABIN_MULTIPLIERS = {"economy": 1.0, "business": 3.2, "first": 7.5}
_BASE_PRICE_PER_HOUR = 85  # USD per flying hour, economy


class FlightSearchTool(CodedTool):
    """Stub flight search — returns 3 simulated flight options."""

    async def async_invoke(
        self,
        args: Dict[str, Any],
        sly_data: Dict[str, Any],
    ) -> Union[Dict[str, Any], str]:
        origin         = args.get("origin", "Unknown")
        destination    = args.get("destination", "Unknown")
        departure_date = args.get("departure_date", "2026-01-01")
        return_date    = args.get("return_date", "one-way")
        passengers     = int(args.get("passengers", 1))
        cabin_class    = str(args.get("cabin_class", "economy")).lower()

        logger.debug("FlightSearchTool: %s → %s on %s", origin, destination, departure_date)

        multiplier = _CABIN_MULTIPLIERS.get(cabin_class, 1.0)
        seed = f"{origin}{destination}{departure_date}"

        options = [
            {
                "duration_hours": 8.5,
                "stops": 0,
                "airline_idx": 0,
                "price_base": 480,
            },
            {
                "duration_hours": 11.0,
                "stops": 1,
                "airline_idx": 2,
                "price_base": 310,
            },
            {
                "duration_hours": 9.5,
                "stops": 0,
                "airline_idx": 3,
                "price_base": 560,
            },
        ]

        flights = []
        for i, opt in enumerate(options):
            airline_name, airline_code = _AIRLINES[opt["airline_idx"]]
            flight_num  = f"{airline_code}{_short_hash(seed + str(i), 4)}"
            price_pp    = round(opt["price_base"] * multiplier)
            total       = price_pp * passengers
            dep_hour    = 7 + i * 4
            arr_hour    = (dep_hour + int(opt["duration_hours"])) % 24

            flights.append({
                "flight_id":       f"FL-{str(i+1).zfill(3)}",
                "airline":         airline_name,
                "flight_number":   flight_num,
                "origin":          origin,
                "destination":     destination,
                "departure_time":  f"{departure_date}T{dep_hour:02d}:00",
                "arrival_time":    f"{departure_date}T{arr_hour:02d}:00",
                "duration_hours":  opt["duration_hours"],
                "stops":           opt["stops"],
                "cabin_class":     cabin_class,
                "price_per_person": price_pp,
                "total_price":     total,
                "currency":        "USD",
            })

        return {
            "status": "ok",
            "flights": flights,
            "search_params": {
                "origin": origin,
                "destination": destination,
                "departure_date": departure_date,
                "return_date": return_date,
                "passengers": passengers,
                "cabin_class": cabin_class,
            },
            "note": "FlightSearchTool stub — simulated results for demo",
        }


# ---------------------------------------------------------------------------
# Hotel Search
# ---------------------------------------------------------------------------

_HOTEL_TEMPLATES = {
    "budget": [
        {"name": "Comfort Inn Downtown", "stars": 3, "neighbourhood": "City Centre", "base_price": 89},
        {"name": "Holiday Inn Express", "stars": 3, "neighbourhood": "Airport Area",  "base_price": 75},
        {"name": "Premier Inn",           "stars": 3, "neighbourhood": "Suburb",       "base_price": 82},
    ],
    "mid-range": [
        {"name": "Marriott Courtyard",   "stars": 4, "neighbourhood": "Business District", "base_price": 175},
        {"name": "Hilton Garden Inn",    "stars": 4, "neighbourhood": "City Centre",        "base_price": 195},
        {"name": "Hyatt Place",          "stars": 4, "neighbourhood": "Waterfront",         "base_price": 210},
    ],
    "luxury": [
        {"name": "The Ritz-Carlton",     "stars": 5, "neighbourhood": "Premium District",  "base_price": 550},
        {"name": "Four Seasons Hotel",   "stars": 5, "neighbourhood": "City Centre",        "base_price": 620},
        {"name": "St. Regis",            "stars": 5, "neighbourhood": "Harbourfront",        "base_price": 490},
    ],
}

_AMENITIES_BY_STARS = {
    3: ["Free WiFi", "Breakfast included", "Free parking"],
    4: ["Free WiFi", "Fitness centre", "Swimming pool", "Restaurant"],
    5: ["Free WiFi", "Spa & wellness", "Rooftop bar", "Concierge", "Fine dining"],
}


def _nights_between(check_in: str, check_out: str) -> int:
    try:
        from datetime import date
        d1 = date.fromisoformat(check_in)
        d2 = date.fromisoformat(check_out)
        delta = (d2 - d1).days
        return max(delta, 1)
    except Exception:
        return 3


class HotelSearchTool(CodedTool):
    """Stub hotel search — returns 3 simulated hotel options."""

    async def async_invoke(
        self,
        args: Dict[str, Any],
        sly_data: Dict[str, Any],
    ) -> Union[Dict[str, Any], str]:
        city      = args.get("city", "Unknown")
        check_in  = args.get("check_in",  "2026-01-01")
        check_out = args.get("check_out", "2026-01-04")
        guests    = int(args.get("guests", 1))
        category  = str(args.get("category", "mid-range")).lower()

        if category not in _HOTEL_TEMPLATES:
            category = "mid-range"

        nights    = _nights_between(check_in, check_out)
        templates = _HOTEL_TEMPLATES[category]

        logger.debug("HotelSearchTool: %s %s (%d nights) %s", city, category, nights, check_in)

        hotels = []
        for i, tmpl in enumerate(templates):
            hotel_id    = f"HTL-{str(i+1).zfill(3)}"
            price_night = tmpl["base_price"]
            total       = price_night * nights
            stars       = tmpl["stars"]
            rating      = round(3.8 + i * 0.2, 1)

            hotels.append({
                "hotel_id":      hotel_id,
                "name":          tmpl["name"],
                "category":      category,
                "stars":         stars,
                "city":          city,
                "neighbourhood": tmpl["neighbourhood"],
                "price_per_night": price_night,
                "total_price":   total,
                "currency":      "USD",
                "nights":        nights,
                "check_in":      check_in,
                "check_out":     check_out,
                "rating":        rating,
                "amenities":     _AMENITIES_BY_STARS.get(stars, ["Free WiFi"]),
            })

        return {
            "status": "ok",
            "hotels": hotels,
            "search_params": {
                "city": city,
                "check_in": check_in,
                "check_out": check_out,
                "guests": guests,
                "category": category,
                "nights": nights,
            },
            "note": "HotelSearchTool stub — simulated results for demo",
        }


# ---------------------------------------------------------------------------
# Booking Confirmation
# ---------------------------------------------------------------------------

class BookingConfirmTool(CodedTool):
    """Stub booking confirmation — returns a simulated booking reference."""

    async def async_invoke(
        self,
        args: Dict[str, Any],
        sly_data: Dict[str, Any],
    ) -> Union[Dict[str, Any], str]:
        flight_id  = args.get("flight_id",  "FL-001")
        hotel_id   = args.get("hotel_id",   "HTL-001")
        passengers = int(args.get("passengers", 1))
        guest_name = args.get("guest_name", "Guest")

        logger.debug("BookingConfirmTool: flight=%s hotel=%s pax=%d", flight_id, hotel_id, passengers)

        seed        = f"{flight_id}{hotel_id}{passengers}"
        ref_num     = _short_hash(seed, 5)
        booking_ref = f"TRV-2026-{ref_num}"

        flight_conf  = f"FLT-{_short_hash(flight_id + 'f', 7)}"
        hotel_conf   = f"HTL-{_short_hash(hotel_id  + 'h', 7)}"

        # Plausible stub costs
        flight_total = passengers * 480
        hotel_total  = 175 * 3
        grand_total  = flight_total + hotel_total

        return {
            "status":           "confirmed",
            "booking_ref":      booking_ref,
            "guest_name":       guest_name,
            "flight_id":        flight_id,
            "hotel_id":         hotel_id,
            "passengers":       passengers,
            "flight_confirmation": flight_conf,
            "hotel_confirmation":  hotel_conf,
            "total_flight_cost":   flight_total,
            "total_hotel_cost":    hotel_total,
            "grand_total":         grand_total,
            "currency":            "USD",
            "next_steps": [
                "Check in online 24 hours before departure at airline website",
                "Bring passport or government-issued ID for hotel and flight check-in",
                "Download the airline app for real-time flight updates",
            ],
            "note": "BookingConfirmTool stub — simulated confirmation for demo",
        }
