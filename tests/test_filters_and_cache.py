from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.schemas import FlightFilter, FlightView
from app.services.cache import FlightCache
from app.services.fr24_service import FR24Service


def test_has_any_filter_false_when_empty() -> None:
    assert FlightFilter().has_any_filter() is False


def test_has_any_filter_true_with_one_filter() -> None:
    assert FlightFilter(arrival_country="Turkey").has_any_filter() is True


def test_match_filters_aircraft_and_airline() -> None:
    flight = FlightView(
        fr24_id="1",
        flight_number="SU100",
        callsign="AFL100",
        airline="Aeroflot",
        aircraft_icao="B738",
        departure_airport="SVO",
        departure_city="Moscow",
        departure_country="Russia",
        arrival_airport="AYT",
        arrival_city="Antalya",
        arrival_country="Turkey",
        scheduled_duration_min=180,
        is_past=False,
    )

    filters = FlightFilter(aircraft_icao="b738", airline="aero", min_duration_h=2, max_duration_h=4)

    assert FR24Service._match_filters(flight, filters) is True


def test_cache_prune(tmp_path) -> None:
    cache = FlightCache(str(tmp_path / "cache.db"))

    flight = FlightView(
        fr24_id="x1",
        flight_number=None,
        callsign=None,
        airline=None,
        aircraft_icao=None,
        departure_airport=None,
        departure_city=None,
        departure_country=None,
        arrival_airport=None,
        arrival_city=None,
        arrival_country=None,
        scheduled_duration_min=None,
        is_past=True,
    )
    cache.save([flight])

    old = (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()
    with cache._connect() as conn:
        conn.execute("UPDATE flights_cache SET cached_at = ?", (old,))

    removed = cache.prune(days=5)
    assert removed == 1
    assert cache.get_all() == []


def test_match_filters_country_alias_ru() -> None:
    flight = FlightView(
        fr24_id="2",
        flight_number="SU101",
        callsign="AFL101",
        airline="Aeroflot AFL SU",
        aircraft_icao="B738",
        departure_airport="SVO",
        departure_city="Moscow",
        departure_country="Russia",
        arrival_airport="LED",
        arrival_city="Saint Petersburg",
        arrival_country="Russia",
        scheduled_duration_min=95,
        is_past=False,
    )

    filters = FlightFilter(departure_country="Россия")
    assert FR24Service._match_filters(flight, filters) is True


def test_match_filters_airline_by_callsign_prefix() -> None:
    flight = FlightView(
        fr24_id="3",
        flight_number="SU1200",
        callsign="AFL1200",
        airline="Aeroflot AFL SU",
        aircraft_icao="B738",
        departure_airport="SVO",
        departure_city="Moscow",
        departure_country="Russia",
        arrival_airport="AER",
        arrival_city="Sochi",
        arrival_country="Russia",
        scheduled_duration_min=150,
        is_past=False,
    )

    filters = FlightFilter(airline="AFL")
    assert FR24Service._match_filters(flight, filters) is True


def test_to_view_handles_none_nested_detail_objects() -> None:
    service = object.__new__(FR24Service)
    raw = {
        "id": "f1",
        "callsign": "AFL123",
        "airline_name": "Aeroflot",
        "aircraft_code": "B738",
    }
    details = {
        "airport": {"origin": None, "destination": None},
        "status": None,
        "airline": {"name": "Aeroflot"},
    }

    view = service._to_view(raw, details)
    assert view.fr24_id == "f1"
    assert view.callsign == "AFL123"
    assert view.departure_city is None
    assert view.arrival_city is None
