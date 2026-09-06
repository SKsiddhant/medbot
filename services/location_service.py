"""
Location service.

Two inputs we can get:
  * Free-text city ("Bhopal", "Delhi NCR")           — user types it.
  * (lat, lng) coordinates                           — browser geolocation
                                                       or WhatsApp location share.

For coordinates we reverse-geocode via Nominatim (free, no API key).
Result: {city, state, country} — the state is important because it
decides which state government schemes apply (Chiranjeevi in Rajasthan,
Aarogyasri in Telangana, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger


try:
    from geopy.geocoders import Nominatim
    _geocoder = Nominatim(user_agent="medbot-triage/1.0")
    GEOPY_OK = True
except ImportError:                                     # pragma: no cover
    GEOPY_OK = False
    _geocoder = None


# States we have specific scheme mappings for (extend as needed)
KNOWN_STATES = {
    "madhya pradesh", "maharashtra", "karnataka", "tamil nadu",
    "andhra pradesh", "telangana", "kerala", "rajasthan", "gujarat",
    "delhi", "uttar pradesh", "west bengal", "punjab", "haryana",
    "bihar", "odisha", "assam", "chhattisgarh",
}


@dataclass
class Location:
    city: str = ""
    state: str = ""
    country: str = "India"
    lat: float | None = None
    lng: float | None = None
    source: str = "typed"                               # typed | gps | whatsapp

    @property
    def is_resolved(self) -> bool:
        return bool(self.city or (self.lat is not None and self.lng is not None))

    def to_dict(self) -> dict[str, Any]:
        return {
            "city": self.city, "state": self.state, "country": self.country,
            "lat": self.lat, "lng": self.lng, "source": self.source,
        }


class LocationService:
    def __init__(self) -> None:
        self.enabled = GEOPY_OK

    # ------------------------------------------------------------------
    # Reverse geocode: (lat, lng) → city + state
    # ------------------------------------------------------------------
    def resolve_coords(self, lat: float, lng: float, source: str = "gps") -> Location:
        loc = Location(lat=lat, lng=lng, source=source)
        if not self.enabled or _geocoder is None:
            return loc
        try:
            r = _geocoder.reverse((lat, lng), language="en", zoom=10, timeout=8)
            if r and r.raw and "address" in r.raw:
                addr = r.raw["address"]
                loc.city = (
                    addr.get("city") or addr.get("town")
                    or addr.get("village") or addr.get("county") or ""
                )
                loc.state = addr.get("state", "")
                loc.country = addr.get("country", "India")
        except Exception as e:
            logger.warning(f"Reverse geocode failed: {e}")
        return loc

    # ------------------------------------------------------------------
    # Forward geocode: "Bhopal" → (state, lat, lng)
    # Used when user types a city name, so we know the state for schemes.
    # ------------------------------------------------------------------
    def resolve_city(self, city_text: str) -> Location:
        loc = Location(city=city_text.strip().title(), source="typed")
        if not self.enabled or _geocoder is None:
            return loc
        try:
            r = _geocoder.geocode(
                f"{city_text}, India", language="en", timeout=8,
                exactly_one=True, addressdetails=True,
            )
            if r:
                loc.lat, loc.lng = r.latitude, r.longitude
                if r.raw and "address" in r.raw:
                    addr = r.raw["address"]
                    loc.state = addr.get("state", "")
                    loc.city = (
                        addr.get("city") or addr.get("town")
                        or addr.get("village") or loc.city
                    )
        except Exception as e:
            logger.warning(f"Forward geocode failed: {e}")
        return loc

    # ------------------------------------------------------------------
    # Parse WhatsApp location message payload
    # ------------------------------------------------------------------
    def from_whatsapp(self, location_msg: dict[str, Any]) -> Location:
        lat = location_msg.get("latitude")
        lng = location_msg.get("longitude")
        if lat is None or lng is None:
            return Location()
        return self.resolve_coords(float(lat), float(lng), source="whatsapp")


location_service = LocationService()
