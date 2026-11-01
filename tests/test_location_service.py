from services.location_service import Location, LocationService


def _offline() -> LocationService:
    svc = LocationService()
    svc.enabled = False  # never hit Nominatim in tests
    return svc


def test_location_is_resolved():
    assert not Location().is_resolved
    assert Location(city="Bhopal").is_resolved
    assert Location(lat=0.0, lng=0.0).is_resolved  # 0.0 is a valid coordinate


def test_resolve_city_offline_normalises_text():
    loc = _offline().resolve_city("  bhopal ")
    assert loc.city == "Bhopal"
    assert loc.source == "typed"
    assert loc.lat is None


def test_from_whatsapp_missing_coordinates_returns_empty():
    svc = _offline()
    assert not svc.from_whatsapp({}).is_resolved
    assert not svc.from_whatsapp({"latitude": 12.0}).is_resolved


def test_from_whatsapp_coerces_and_tags_source():
    loc = _offline().from_whatsapp({"latitude": "23.25", "longitude": "77.41"})
    assert (loc.lat, loc.lng, loc.source) == (23.25, 77.41, "whatsapp")


def test_to_dict_round_trip():
    d = Location(city="Pune", state="Maharashtra").to_dict()
    assert d["city"] == "Pune" and d["state"] == "Maharashtra" and d["country"] == "India"
