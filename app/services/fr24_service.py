from __future__ import annotations

from time import monotonic
from typing import Any

import requests

from app.schemas import FlightFilter, FlightView


class FR24ServiceError(RuntimeError):
    pass


class FR24Service:
    COUNTRY_ALIASES = {
        "россия": "russia",
        "рф": "russia",
        "турция": "turkey",
        "германия": "germany",
        "франция": "france",
        "италия": "italy",
        "испания": "spain",
        "китай": "china",
        "япония": "japan",
        "оаэ": "united arab emirates",
        "сша": "united states",
        "великобритания": "united kingdom",
    }

    FEED_URL = "https://data-cloud.flightradar24.com/zones/fcgi/feed.js"
    DETAILS_URL = "https://data-live.flightradar24.com/clickhandler/"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.library_api: Any | None = None

        # Резервный вариант через библиотеку, если прямые endpoints недоступны.
        for module_name in ("FlightRadar24", "FlightRadarAPI"):
            try:
                mod = __import__(module_name, fromlist=["FlightRadar24API"])
                self.library_api = getattr(mod, "FlightRadar24API")()
                break
            except Exception:
                continue

    def search(self, filters: FlightFilter, limit: int = 100) -> list[FlightView]:
        has_duration_filter = filters.min_duration_h is not None or filters.max_duration_h is not None
        needs_details_for_matching = any(
            [
                bool(filters.departure_country),
                bool(filters.departure_city_or_airport),
                bool(filters.arrival_country),
                bool(filters.arrival_airport),
            ]
        )

        deadline = monotonic() + (35.0 if has_duration_filter and not needs_details_for_matching else 25.0)

        flights = self._get_live_flights()
        candidates: list[Any] = []
        for raw in flights:
            base_view = self._to_view(raw)
            # На этапе prefilter нельзя жёстко фильтровать по полям,
            # которые часто появляются только в details (ICAO аэропорта/страны/города).
            if self._match_prefilter(base_view, filters):
                candidates.append(raw)

        result: list[FlightView] = []
        scan_limit = (
            max(limit * 12, 1200)
            if needs_details_for_matching
            else (max(limit * 8, 800) if has_duration_filter else max(limit * 4, 220))
        )

        for raw in candidates[:scan_limit]:
            if monotonic() > deadline:
                break

            details = self._get_flight_details(raw)
            view = self._to_view(raw, details)
            if self._match_filters(view, filters):
                result.append(view)
                if len(result) >= limit:
                    break

        return result

    def _get_live_flights(self) -> list[Any]:
        try:
            params = {
                "bounds": "90,-90,-180,180",
                "faa": "1",
                "satellite": "1",
                "mlat": "1",
                "flarm": "1",
                "adsb": "1",
                "gnd": "1",
                "air": "1",
                "vehicles": "0",
                "estimated": "1",
                "maxage": "14400",
                "gliders": "1",
                "stats": "0",
            }
            resp = self.session.get(self.FEED_URL, params=params, timeout=12)
            resp.raise_for_status()
            payload = resp.json()

            flights: list[dict[str, Any]] = []
            for key, value in payload.items():
                if not isinstance(value, list) or len(value) < 17:
                    continue
                flights.append(
                    {
                        "id": key,
                        "aircraft_code": value[8],
                        "registration": value[9],
                        "timestamp": value[10],
                        "origin_airport_iata": value[11],
                        "destination_airport_iata": value[12],
                        "number": value[13],
                        "callsign": value[16],
                    }
                )
            return flights
        except Exception:
            if self.library_api is None:
                raise FR24ServiceError("Не удалось получить live рейсы из FlightRadar24")
            return self.library_api.get_flights()

    def _get_flight_details(self, raw: Any) -> dict[str, Any] | None:
        flight_id = None
        if isinstance(raw, dict):
            flight_id = raw.get("id") or raw.get("flight_id")
        else:
            flight_id = getattr(raw, "id", None)

        if flight_id:
            try:
                resp = self.session.get(self.DETAILS_URL, params={"flight": flight_id}, timeout=8)
                resp.raise_for_status()
                data = resp.json()
                return data if isinstance(data, dict) else None
            except Exception:
                pass

        if self.library_api is not None:
            try:
                return self.library_api.get_flight_details(raw)
            except Exception:
                return None
        return None

    @staticmethod
    def _safe_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _to_view(self, raw: Any, details: dict[str, Any] | None = None) -> FlightView:
        data = raw if isinstance(raw, dict) else getattr(raw, "__dict__", {})
        details = details or {}

        airport = self._as_dict(details.get("airport"))
        dep_detail = self._as_dict(airport.get("origin"))
        arr_detail = self._as_dict(airport.get("destination"))

        dep_pos = self._as_dict(dep_detail.get("position"))
        arr_pos = self._as_dict(arr_detail.get("position"))
        dep_region = self._as_dict(dep_pos.get("region"))
        arr_region = self._as_dict(arr_pos.get("region"))
        dep_country_obj = self._as_dict(dep_pos.get("country"))
        arr_country_obj = self._as_dict(arr_pos.get("country"))
        dep_code = self._as_dict(dep_detail.get("code"))
        arr_code = self._as_dict(arr_detail.get("code"))

        dep_iata = data.get("origin_airport_iata") or data.get("airport_origin_code_iata") or dep_code.get("iata")
        arr_iata = data.get("destination_airport_iata") or data.get("airport_destination_code_iata") or arr_code.get("iata")
        dep_icao = data.get("origin_airport_icao") or data.get("airport_origin_code_icao") or dep_code.get("icao")
        arr_icao = data.get("destination_airport_icao") or data.get("airport_destination_code_icao") or arr_code.get("icao")

        departure_city = data.get("origin_city") or data.get("airport_origin_city") or dep_region.get("city")
        arrival_city = data.get("destination_city") or data.get("airport_destination_city") or arr_region.get("city")

        airline = self._as_dict(details.get("airline"))
        airline_code = self._as_dict(airline.get("code"))
        airline_name = data.get("airline_name") or airline.get("name")
        airline_icao = data.get("airline_icao") or airline_code.get("icao")
        airline_iata = data.get("airline_iata") or airline_code.get("iata")
        airline_field = " ".join([item for item in [airline_name, airline_icao, airline_iata] if item]) or None

        dep_country = data.get("origin_country") or data.get("airport_origin_country_name") or dep_country_obj.get("name")
        arr_country = data.get("destination_country") or data.get("airport_destination_country_name") or arr_country_obj.get("name")

        identification = self._as_dict(details.get("identification"))
        identification_number = self._as_dict(identification.get("number"))

        aircraft = self._as_dict(details.get("aircraft"))
        aircraft_model = self._as_dict(aircraft.get("model"))

        status = self._as_dict(details.get("status"))
        duration_min = self._extract_duration_min(data, details)
        status_text = (data.get("status") or status.get("text") or "").lower()
        is_past = "landed" in status_text or "arrived" in status_text

        return FlightView(
            fr24_id=self._safe_str(data.get("id") or data.get("flight_id") or "") or "unknown",
            flight_number=self._safe_str(
                data.get("number")
                or data.get("flight")
                or data.get("flight_number")
                or identification_number.get("default")
            ),
            callsign=self._safe_str(data.get("callsign") or identification.get("callsign")),
            airline=self._safe_str(airline_field),
            aircraft_icao=self._safe_str(data.get("aircraft_code") or data.get("aircraft_icao") or aircraft_model.get("code")),
            departure_airport=self._safe_str(dep_iata),
            departure_airport_icao=self._safe_str(dep_icao),
            departure_city=self._safe_str(departure_city),
            departure_country=self._safe_str(dep_country),
            arrival_airport=self._safe_str(arr_iata),
            arrival_airport_icao=self._safe_str(arr_icao),
            arrival_city=self._safe_str(arrival_city),
            arrival_country=self._safe_str(arr_country),
            scheduled_duration_min=duration_min,
            is_past=is_past,
        )

    @staticmethod
    def _extract_duration_min(data: dict[str, Any], details: dict[str, Any] | None = None) -> int | None:
        details = details or {}

        def normalize_ts(value: Any) -> int | None:
            if isinstance(value, dict):
                value = value.get("timestamp") or value.get("time")
            if not isinstance(value, (int, float)):
                return None
            if value > 10_000_000_000:
                value = value / 1000
            return int(value)

        time_obj = details.get("time") if isinstance(details.get("time"), dict) else {}
        scheduled = time_obj.get("scheduled") if isinstance(time_obj.get("scheduled"), dict) else {}

        departure_ts = scheduled.get("departure") or data.get("time_scheduled") or data.get("scheduled_departure")
        arrival_ts = scheduled.get("arrival") or data.get("time_estimated") or data.get("scheduled_arrival")

        departure_ts_norm = normalize_ts(departure_ts)
        arrival_ts_norm = normalize_ts(arrival_ts)

        if departure_ts_norm is not None and arrival_ts_norm is not None:
            delta = int((arrival_ts_norm - departure_ts_norm) // 60)
            return delta if delta > 0 else None

        real = time_obj.get("real") if isinstance(time_obj.get("real"), dict) else {}
        dep_real = normalize_ts(real.get("departure"))
        arr_real = normalize_ts(real.get("arrival"))
        if dep_real is not None and arr_real is not None:
            delta = int((arr_real - dep_real) // 60)
            return delta if delta > 0 else None

        duration = data.get("duration")
        if isinstance(duration, (int, float)):
            return int(duration // 60) if duration > 1000 else int(duration)

        other = time_obj.get("other") if isinstance(time_obj.get("other"), dict) else {}
        for key in ("eta", "duration", "delay"):
            value = other.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return int(value // 60) if value > 1000 else int(value)

        return None

    @classmethod
    def _norm_country(cls, value: str | None) -> str | None:
        if not value:
            return None
        lower = value.lower().strip()
        return cls.COUNTRY_ALIASES.get(lower, lower)

    @staticmethod
    def _contains(source: str | None, expected: str | None) -> bool:
        if not expected:
            return True
        if not source:
            return False
        return expected.lower() in source.lower()

    @classmethod
    def _match_prefilter(cls, flight: FlightView, filters: FlightFilter) -> bool:
        # Prefilter only by fields that are usually present in the live feed.
        if filters.aircraft_icao and not cls._contains(flight.aircraft_icao, filters.aircraft_icao):
            return False

        if filters.airline and not (
            cls._contains(flight.airline, filters.airline)
            or cls._contains(flight.callsign, filters.airline)
            or cls._contains(flight.flight_number, filters.airline)
        ):
            return False

        return True

    @classmethod
    def _match_filters(cls, flight: FlightView, filters: FlightFilter, skip_duration: bool = False) -> bool:
        if not skip_duration and filters.min_duration_h is not None:
            if flight.scheduled_duration_min is None or flight.scheduled_duration_min < filters.min_duration_h * 60:
                return False

        if not skip_duration and filters.max_duration_h is not None:
            if flight.scheduled_duration_min is None or flight.scheduled_duration_min > filters.max_duration_h * 60:
                return False

        expected_dep_country = cls._norm_country(filters.departure_country)
        expected_arr_country = cls._norm_country(filters.arrival_country)
        flight_dep_country = cls._norm_country(flight.departure_country)
        flight_arr_country = cls._norm_country(flight.arrival_country)

        if expected_dep_country and not cls._contains(flight_dep_country, expected_dep_country):
            return False
        if not (
            cls._contains(flight.departure_city, filters.departure_city_or_airport)
            or cls._contains(flight.departure_airport, filters.departure_city_or_airport)
            or cls._contains(flight.departure_airport_icao, filters.departure_city_or_airport)
        ):
            return False
        if expected_arr_country and not cls._contains(flight_arr_country, expected_arr_country):
            return False
        if not (
            cls._contains(flight.arrival_airport, filters.arrival_airport)
            or cls._contains(flight.arrival_airport_icao, filters.arrival_airport)
        ):
            return False
        if not cls._contains(flight.aircraft_icao, filters.aircraft_icao):
            return False
        if filters.airline and not (
            cls._contains(flight.airline, filters.airline)
            or cls._contains(flight.callsign, filters.airline)
            or cls._contains(flight.flight_number, filters.airline)
        ):
            return False

        return True
