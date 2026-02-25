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


    @staticmethod
    def _safe_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


        is_past = "landed" in status_text or "arrived" in status_text

        return FlightView(
            fr24_id=self._safe_str(data.get("id") or data.get("flight_id") or "") or "unknown",

            scheduled_duration_min=duration_min,
            is_past=is_past,
        )

    @staticmethod
