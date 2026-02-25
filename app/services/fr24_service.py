from __future__ import annotations

from typing import Any

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

    def __init__(self) -> None:
        try:
            from FlightRadar24 import FlightRadar24API  # type: ignore
        except ImportError as exc:
            raise FR24ServiceError(
                "Не установлена библиотека FlightRadar24API. Установите зависимости из requirements.txt"
            ) from exc

        self.api = FlightRadar24API()

    def search(self, filters: FlightFilter, limit: int = 100) -> list[FlightView]:
        flights = self.api.get_flights()

        candidates: list[Any] = []
        for raw in flights:
            base_view = self._to_view(raw)
            if self._match_filters(base_view, filters, skip_duration=True):
                candidates.append(raw)

        result: list[FlightView] = []
        for raw in candidates[: max(limit * 5, 250)]:
            details: dict[str, Any] | None
            try:
                details = self.api.get_flight_details(raw)
            except Exception:
                details = None

            view = self._to_view(raw, details)
            if self._match_filters(view, filters):
                result.append(view)
                if len(result) >= limit:
                    break

        return result

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

        departure_city = data.get("origin_city") or data.get("airport_origin_city") or dep_region.get("city")
        arrival_city = data.get("destination_city") or data.get("airport_destination_city") or arr_region.get("city")
        departure_airport = data.get("origin_airport_iata") or data.get("airport_origin_code_iata") or dep_code.get("iata")
        arrival_airport = (
            data.get("destination_airport_iata") or data.get("airport_destination_code_iata") or arr_code.get("iata")
        )

        airline = self._as_dict(details.get("airline"))
        airline_code = self._as_dict(airline.get("code"))
        airline_name = data.get("airline_name") or airline.get("name")
        airline_icao = data.get("airline_icao") or airline_code.get("icao")
        airline_iata = data.get("airline_iata") or airline_code.get("iata")
        airline_field = " ".join([item for item in [airline_name, airline_icao, airline_iata] if item]) or None

        dep_country = data.get("origin_country") or data.get("airport_origin_country_name") or dep_country_obj.get("name")
        arr_country = (
            data.get("destination_country") or data.get("airport_destination_country_name") or arr_country_obj.get("name")
        )

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
            departure_airport=self._safe_str(departure_airport),
            departure_city=self._safe_str(departure_city),
            departure_country=self._safe_str(dep_country),
            arrival_airport=self._safe_str(arrival_airport),
            arrival_city=self._safe_str(arrival_city),
            arrival_country=self._safe_str(arr_country),
            scheduled_duration_min=duration_min,
            is_past=is_past,
        )

    @staticmethod
    def _extract_duration_min(data: dict[str, Any], details: dict[str, Any] | None = None) -> int | None:
        details = details or {}

        time_obj = details.get("time") if isinstance(details.get("time"), dict) else {}
        scheduled = time_obj.get("scheduled") if isinstance(time_obj.get("scheduled"), dict) else {}

        departure_ts = scheduled.get("departure") or data.get("time_scheduled") or data.get("scheduled_departure")
        arrival_ts = scheduled.get("arrival") or data.get("time_estimated") or data.get("scheduled_arrival")

        if isinstance(departure_ts, dict):
            departure_ts = departure_ts.get("timestamp") or departure_ts.get("time")
        if isinstance(arrival_ts, dict):
            arrival_ts = arrival_ts.get("timestamp") or arrival_ts.get("time")

        if isinstance(departure_ts, (int, float)) and isinstance(arrival_ts, (int, float)):
            delta = int((arrival_ts - departure_ts) // 60)
            return delta if delta > 0 else None

        duration = data.get("duration")
        if isinstance(duration, (int, float)):
            return int(duration // 60) if duration > 500 else int(duration)

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
        ):
            return False
        if expected_arr_country and not cls._contains(flight_arr_country, expected_arr_country):
            return False
        if not (
            cls._contains(flight.arrival_city, filters.arrival_city_or_airport)
            or cls._contains(flight.arrival_airport, filters.arrival_city_or_airport)
        ):
            return False
        if not cls._contains(flight.arrival_airport, filters.arrival_airport):
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
