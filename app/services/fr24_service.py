from __future__ import annotations

from typing import Any

from app.schemas import FlightFilter, FlightView


class FR24ServiceError(RuntimeError):
    pass


class FR24Service:
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
        normalized = [self._to_view(raw) for raw in flights]
        filtered = [f for f in normalized if self._match_filters(f, filters)]
        return filtered[:limit]

    @staticmethod
    def _safe_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _to_view(self, raw: Any) -> FlightView:
        data = raw if isinstance(raw, dict) else getattr(raw, "__dict__", {})
        departure_city = data.get("origin_city") or data.get("airport_origin_city")
        arrival_city = data.get("destination_city") or data.get("airport_destination_city")
        departure_airport = data.get("origin_airport_iata") or data.get("airport_origin_code_iata")
        arrival_airport = data.get("destination_airport_iata") or data.get("airport_destination_code_iata")
        duration_min = self._extract_duration_min(data)
        status_text = (data.get("status") or "").lower()
        is_past = "landed" in status_text or "arrived" in status_text

        return FlightView(
            fr24_id=self._safe_str(data.get("id") or data.get("flight_id") or "") or "unknown",
            flight_number=self._safe_str(data.get("number") or data.get("flight") or data.get("flight_number")),
            callsign=self._safe_str(data.get("callsign")),
            airline=self._safe_str(data.get("airline_name") or data.get("airline_icao")),
            aircraft_icao=self._safe_str(data.get("aircraft_code") or data.get("aircraft_icao")),
            departure_airport=self._safe_str(departure_airport),
            departure_city=self._safe_str(departure_city),
            departure_country=self._safe_str(data.get("origin_country") or data.get("airport_origin_country_name")),
            arrival_airport=self._safe_str(arrival_airport),
            arrival_city=self._safe_str(arrival_city),
            arrival_country=self._safe_str(
                data.get("destination_country") or data.get("airport_destination_country_name")
            ),
            scheduled_duration_min=duration_min,
            is_past=is_past,
        )

    @staticmethod
    def _extract_duration_min(data: dict[str, Any]) -> int | None:
        departure_ts = data.get("time_scheduled") or data.get("scheduled_departure")
        arrival_ts = data.get("time_estimated") or data.get("scheduled_arrival")
        if isinstance(departure_ts, (int, float)) and isinstance(arrival_ts, (int, float)):
            delta = int((arrival_ts - departure_ts) // 60)
            return delta if delta > 0 else None
        duration = data.get("duration")
        if isinstance(duration, (int, float)):
            return int(duration // 60) if duration > 500 else int(duration)
        return None

    @staticmethod
    def _match_filters(flight: FlightView, filters: FlightFilter) -> bool:
        def contains(source: str | None, expected: str | None) -> bool:
            if not expected:
                return True
            if not source:
                return False
            return expected.lower() in source.lower()

        if filters.min_duration_h is not None:
            if flight.scheduled_duration_min is None or flight.scheduled_duration_min < filters.min_duration_h * 60:
                return False

        if filters.max_duration_h is not None:
            if flight.scheduled_duration_min is None or flight.scheduled_duration_min > filters.max_duration_h * 60:
                return False

        if not contains(flight.departure_country, filters.departure_country):
            return False
        if not (
            contains(flight.departure_city, filters.departure_city_or_airport)
            or contains(flight.departure_airport, filters.departure_city_or_airport)
        ):
            return False
        if not contains(flight.arrival_country, filters.arrival_country):
            return False
        if not (
            contains(flight.arrival_city, filters.arrival_city_or_airport)
            or contains(flight.arrival_airport, filters.arrival_city_or_airport)
        ):
            return False
        if not contains(flight.arrival_airport, filters.arrival_airport):
            return False
        if not contains(flight.aircraft_icao, filters.aircraft_icao):
            return False
        if not contains(flight.airline, filters.airline):
            return False

        return True

