from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class FlightFilter:
    min_duration_h: Optional[float] = None
    max_duration_h: Optional[float] = None
    departure_country: Optional[str] = None
    departure_city_or_airport: Optional[str] = None
    arrival_country: Optional[str] = None
    arrival_airport: Optional[str] = None
    aircraft_icao: Optional[str] = None
    airline: Optional[str] = None
    include_past: bool = False

    def has_any_filter(self) -> bool:
        return any(
            [
                self.min_duration_h is not None,
                self.max_duration_h is not None,
                bool(self.departure_country),
                bool(self.departure_city_or_airport),
                bool(self.arrival_country),
                bool(self.arrival_airport),
                bool(self.aircraft_icao),
                bool(self.airline),
            ]
        )


@dataclass(slots=True)
class FlightView:
    fr24_id: str
    flight_number: Optional[str]
    callsign: Optional[str]
    airline: Optional[str]
    aircraft_icao: Optional[str]
    departure_airport: Optional[str]
    departure_airport_icao: Optional[str]
    departure_city: Optional[str]
    departure_country: Optional[str]
    arrival_airport: Optional[str]
    arrival_airport_icao: Optional[str]
    arrival_city: Optional[str]
    arrival_country: Optional[str]
    scheduled_duration_min: Optional[int]
    is_past: bool
