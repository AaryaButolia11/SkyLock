from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.services.seat_lock import get_seat_lock_owners_bulk
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime,date
from app.services.pricing import calculate_fare
from app.database import get_db
from app.models.flight import Flight
from app.models.seat import Seat
from app.schemas.flight import FlightCreate, FlightOut, FlightDetailOut
from app.auth.dependencies import get_current_admin
from app.models.user import User
from app.services.seat_lock import is_seat_locked

router = APIRouter(prefix="/flights", tags=["flights"])


@router.post("/", response_model=FlightOut, status_code=status.HTTP_201_CREATED)
async def create_flight(
    flight_in: FlightCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    new_flight = Flight(
        flight_number=flight_in.flight_number,
        origin=flight_in.origin,
        destination=flight_in.destination,
        departure_time=flight_in.departure_time,
        arrival_time=flight_in.arrival_time,
        total_seats=flight_in.total_seats,
    )
    db.add(new_flight)
    await db.flush()  # get new_flight.id before commit

    # auto-generate seats: e.g. rows 1-N, seats A-F per row (economy)
    seat_letters = ["A", "B", "C", "D", "E", "F"]
    seats_created = 0
    row = 1
    while seats_created < flight_in.total_seats:
        for letter in seat_letters:
            if seats_created >= flight_in.total_seats:
                break
            seat = Seat(
                flight_id=new_flight.id,
                seat_number=f"{row}{letter}",
                seat_class="business" if row <= 2 else "economy",
            )
            db.add(seat)
            seats_created += 1
        row += 1

    await db.commit()
    invalidate_flights_cache()
    await db.refresh(new_flight)
    return new_flight

from app.services.pricing import calculate_fare

from app.services.cache import _flights_cache_key, get_cached_flights, set_cached_flights, invalidate_flights_cache

@router.get("/", response_model=list[FlightOut])
async def list_flights(
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    departure_date: Optional[date] = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    cache_key = _flights_cache_key(origin, destination, departure_date, limit, offset)
    cached = get_cached_flights(cache_key)
    if cached is not None:
        return cached

    query = select(Flight)
    if origin:
        query = query.where(Flight.origin.ilike(origin))
    if destination:
        query = query.where(Flight.destination.ilike(destination))
    if departure_date:
        query = query.where(
            Flight.departure_time >= datetime.combine(departure_date, datetime.min.time()),
            Flight.departure_time < datetime.combine(departure_date, datetime.max.time()),
        )
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    flights = result.scalars().all()
    for f in flights:
        f.price = calculate_fare(f.origin, f.destination, "economy", f.departure_time)

    serialized = [FlightOut.model_validate(f).model_dump() for f in flights]
    set_cached_flights(cache_key, serialized)
    return flights


from app.services.seat_lock import is_seat_locked

@router.get("/{flight_id}", response_model=FlightDetailOut)
async def get_flight(flight_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Flight)
        .options(selectinload(Flight.seats))
        .where(Flight.id == flight_id)
    )
    flight = result.scalar_one_or_none()
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")

    # attach live lock status per seat (Redis check, not stored in Postgres)

    seat_ids = [s.id for s in flight.seats]
    lock_owners = get_seat_lock_owners_bulk(flight_id, seat_ids)

    for seat in flight.seats:
        seat.is_locked = lock_owners.get(seat.id) is not None
        seat.price = calculate_fare(flight.origin, flight.destination, seat.seat_class, flight.departure_time)    
    return flight

'''
create_flight is protected by Depends(get_current_admin) — only an admin JWT can create flights.
It auto-generates seats (rows of 6, first 2 rows business) so you don't manually create dozens of seat records per flight.
db.flush() pushes the INSERT to Postgres and gets back new_flight.id without committing yet — needed because seats need flight_id before we commit everything together as one transaction.
selectinload(Flight.seats) — this is important. Without it, accessing flight.seats triggers a separate lazy-load query per flight (the N+1 problem), which can fail entirely in async SQLAlchemy since lazy loading doesn't work well outside a sync context. selectinload eagerly fetches seats in one extra query up front.
'''

'''
Add from datetime import datetime to the existing imports at top too (you likely already have date and Optional needed now).

Why ilike not ==: case-insensitive matching — "del" and "DEL" both match origin "DEL". Real users don't reliably match case.

Why the date range instead of ==: departure_time is a full timestamp; comparing == departure_date would only match flights departing at exactly midnight. Range query correctly captures "any flight departing sometime on this date."

Test: GET /flights?origin=DEL&destination=BOM&departure_date=2026-08-01
'''
