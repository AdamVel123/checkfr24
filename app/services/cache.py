from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from app.schemas import FlightView


class FlightCache:
    def __init__(self, db_path: str = "flights_cache.db") -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS flights_cache (
                    fr24_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    cached_at TEXT NOT NULL
                )
                """
            )

    def save(self, flights: Iterable[FlightView]) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO flights_cache (fr24_id, payload, cached_at)
                VALUES (?, ?, ?)
                ON CONFLICT(fr24_id) DO UPDATE SET
                    payload=excluded.payload,
                    cached_at=excluded.cached_at
                """,
                [
                    (
                        f.fr24_id,
                        json.dumps({k: getattr(f, k) for k in f.__slots__}, ensure_ascii=False),
                        now_iso,
                    )
                    for f in flights
                ],
            )

    def get_all(self) -> list[FlightView]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM flights_cache").fetchall()


        flights: list[FlightView] = []
        for row in rows:
            payload = json.loads(row[0])
            payload.setdefault("departure_airport_icao", None)
            payload.setdefault("arrival_airport_icao", None)
            flights.append(FlightView(**payload))

        return flights


    def prune(self, days: int = 5) -> int:
        threshold = datetime.now(timezone.utc) - timedelta(days=days)
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM flights_cache WHERE cached_at < ?", (threshold.isoformat(),)
            )
            return cursor.rowcount
