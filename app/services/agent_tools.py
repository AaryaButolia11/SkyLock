"""
LangChain tools that wrap SkyLock's existing booking logic. Each tool is
bound to a specific request's DB session + authenticated user via closures,
so the LLM never sees or controls user identity directly — it can only act
as that already-authenticated user, same security boundary as the REST API.
"""
from app.logging_config import logger
from datetime import datetime
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.flight import Flight
from app.models.seat import Seat
from app.models.booking import Booking
from app.models.payment import Payment
from app.models.passenger import Passenger
from app.services.pricing import calculate_fare
from app.services.seat_lock import acquire_seat_lock, get_seat_lock_owner, release_seat_lock, LOCK_TTL_SECONDS


def build_tools(db, current_user):

    # ---------- Tool 1: search flights ----------
    class SearchFlightsInput(BaseModel):
        origin: str = Field(description="3-letter origin airport code, e.g. DEL")
        destination: str = Field(description="3-letter destination airport code, e.g. BOM")
        date: str = Field(default="", description="Departure date as YYYY-MM-DD, optional")

    async def search_flights(origin: str, destination: str, date: str = "") -> str:
        query = select(Flight).where(
            Flight.origin.ilike(origin.strip()),
            Flight.destination.ilike(destination.strip()),
        )
        if date:
            try:
                d = datetime.strptime(date, "%Y-%m-%d").date()
                query = query.where(
                    Flight.departure_time >= datetime.combine(d, datetime.min.time()),
                    Flight.departure_time < datetime.combine(d, datetime.max.time()),
                )
            except ValueError:
                pass

        result = await db.execute(query.limit(5))
        flights = result.scalars().all()

        if not flights:
            return "No flights found for that route/date. Try a different date or check the airport codes."

        lines = []
        for f in flights:
            price = calculate_fare(f.origin, f.destination, "economy", f.departure_time)
            lines.append(
                f"- flight_id={f.id}, {f.flight_number}: {f.origin}->{f.destination}, "
                f"departs {f.departure_time.strftime('%Y-%m-%d %H:%M')}, "
                f"economy from ₹{round(price)}"
            )
        return "\n".join(lines)

    # ---------- Tool 2: get seat map ----------
    class GetSeatsInput(BaseModel):
        flight_id: int = Field(description="The flight_id to check seats for")

    async def get_seats(flight_id: int) -> str:
        result = await db.execute(select(Seat).where(Seat.flight_id == flight_id, Seat.is_booked == False))
        seats = result.scalars().all()
        if not seats:
            return "No available seats found on this flight."

        flight_result = await db.execute(select(Flight).where(Flight.id == flight_id))
        flight = flight_result.scalar_one_or_none()
        if not flight:
            return "Flight not found."

        lines = []
        for s in seats[:15]:
            locked = get_seat_lock_owner(flight_id, s.id) is not None
            if locked:
                continue
            price = calculate_fare(flight.origin, flight.destination, s.seat_class, flight.departure_time)
            lines.append(f"- seat_id={s.id}, {s.seat_number} ({s.seat_class}), ₹{round(price)}")

        return "\n".join(lines) if lines else "All visible seats are currently locked by other users — try again shortly."

    # ---------- Tool 3: lock a seat ----------
    class LockSeatInput(BaseModel):
        flight_id: int
        seat_id: int

    async def lock_seat(flight_id: int, seat_id: int) -> str:
        logger.info(f"[AGENT TOOL CALL] lock_seat: user={current_user.id} flight_id={flight_id} seat_id={seat_id}")
        result = await db.execute(select(Seat).where(Seat.id == seat_id, Seat.flight_id == flight_id))
        seat = result.scalar_one_or_none()
        if not seat:
            return "Seat not found."
        if seat.is_booked:
            return "That seat is already booked. Please pick another."

        acquired = acquire_seat_lock(flight_id, seat_id, current_user.id)
        if not acquired:
            return "That seat is currently locked by another user. Please pick another."

        return (
            f"Seat {seat.seat_number} locked for {LOCK_TTL_SECONDS // 60} minutes. "
            f"To complete the booking, I need the passenger's full name, age, gender, "
            f"and meal preference (veg/non_veg/vegan/jain)."
        )

    # ---------- Tool 4: confirm booking ----------
    class BookSeatInput(BaseModel):
        flight_id: int
        seat_id: int
        full_name: str = Field(description="Passenger's full legal name")
        age: int = Field(description="Passenger's age in years")
        gender: str = Field(description="male, female, or other")
        meal_preference: str = Field(default="veg", description="veg, non_veg, vegan, or jain")

    async def book_seat(flight_id: int, seat_id: int, full_name: str, age: int, gender: str, meal_preference: str = "veg") -> str:
        logger.info(
            f"[AGENT TOOL CALL] book_seat: user={current_user.id} flight_id={flight_id} seat_id={seat_id} "
            f"name={full_name!r} age={age} gender={gender} meal={meal_preference}"
        )
        lock_owner = get_seat_lock_owner(flight_id, seat_id)

        if lock_owner != str(current_user.id):
            return "I no longer hold the lock on that seat (it may have expired). Please select a seat again."

        result = await db.execute(
            select(Seat).where(Seat.id == seat_id, Seat.flight_id == flight_id).with_for_update()
        )
        seat = result.scalar_one_or_none()
        if not seat or seat.is_booked:
            return "That seat was just booked by someone else. Please pick a different seat."

        flight_result = await db.execute(select(Flight).where(Flight.id == flight_id))
        flight = flight_result.scalar_one_or_none()
        if not flight:
            return "Flight not found."

        fare = calculate_fare(flight.origin, flight.destination, seat.seat_class, flight.departure_time)

        booking = Booking(user_id=current_user.id, flight_id=flight_id, seat_id=seat_id, status="confirmed")
        db.add(booking)

        try:
            await db.flush()
            db.add(Passenger(booking_id=booking.id, full_name=full_name, age=age, gender=gender, meal_preference=meal_preference))
            db.add(Payment(booking_id=booking.id, amount=fare, status="success"))
            seat.is_booked = True
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return "That seat was booked by someone else at the last moment. Please pick a different seat."

        release_seat_lock(flight_id, seat_id, current_user.id)

        return (
            f"Booking confirmed! Flight {flight.flight_number} ({flight.origin}->{flight.destination}), "
            f"seat {seat.seat_number}, passenger {full_name}, ₹{fare} paid. Booking ID: {booking.id}."
        )

    return [
        StructuredTool.from_function(coroutine=search_flights, name="search_flights", description="Search for flights between two airport codes, optionally on a specific date (YYYY-MM-DD).", args_schema=SearchFlightsInput),
        StructuredTool.from_function(coroutine=get_seats, name="get_available_seats", description="List available seats and their prices for a given flight_id.", args_schema=GetSeatsInput),
        StructuredTool.from_function(coroutine=lock_seat, name="lock_seat", description="Temporarily lock a specific seat before booking. Must be called before book_seat.", args_schema=LockSeatInput),
        StructuredTool.from_function(coroutine=book_seat, name="book_seat", description="Confirm and pay for a locked seat, given passenger details. Only call after lock_seat succeeded and you have collected full_name, age, gender, and meal_preference from the user.", args_schema=BookSeatInput),
    ]