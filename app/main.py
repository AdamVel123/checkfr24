from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.schemas import FlightFilter
from app.services.cache import FlightCache
from app.services.fr24_service import FR24Service, FR24ServiceError


class FlightFilterRequest(BaseModel):
    min_duration_h: float | None = Field(default=None, ge=0)
    max_duration_h: float | None = Field(default=None, ge=0)
    departure_country: str | None = None
    departure_city_or_airport: str | None = None
    arrival_country: str | None = None
    arrival_city_or_airport: str | None = None
    arrival_airport: str | None = None
    aircraft_icao: str | None = None
    airline: str | None = None
    include_past: bool = False

    def to_domain(self) -> FlightFilter:
        return FlightFilter(**self.model_dump())


app = FastAPI(title="FR24 Flight Finder")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
cache = FlightCache()


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/flights/search")
def search_flights(payload: FlightFilterRequest) -> dict:
    filters = payload.to_domain()
    if not filters.has_any_filter():
        raise HTTPException(status_code=400, detail="Добавьте хотя бы один фильтр для поиска.")

    if filters.min_duration_h is not None and filters.max_duration_h is not None:
        if filters.min_duration_h > filters.max_duration_h:
            raise HTTPException(status_code=400, detail="Минимальная длительность больше максимальной.")

    cache.prune(days=5)

    try:
        service = FR24Service()
        live_flights = service.search(filters)
    except FR24ServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка обработки рейсов: {exc}") from exc

    cache.save(live_flights)

    result = live_flights
    if filters.include_past:
        past = [f for f in cache.get_all() if f.is_past]
        ids = {f.fr24_id for f in result}
        result.extend([f for f in past if f.fr24_id not in ids])

    return {"count": len(result), "flights": [asdict(item) for item in result]}
