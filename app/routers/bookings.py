from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from app.logging_config import logger
from app.services.pricing import calculate_fare
from app.database import get_db
from app.models.seat import Seat
from app.models.flight import Flight
from app.models.booking import Booking
from app.models.payment import Payment
from app.schemas.booking import (
    SeatLockRequest, SeatLockResponse,
    BookingConfirmRequest, BookingDetailOut,
    GroupLockRequest, GroupBookingRequest, GroupBookingOut,
)
from app.services.email import send_booking_confirmation, send_cancellation_email
from app.models.refund import Refund
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.services.seat_lock import (
    acquire_seat_lock, release_seat_lock, get_seat_lock_owner, LOCK_TTL_SECONDS,
)
from fastapi.responses import Response
from app.services.ticket_pdf import generate_ticket_pdf
from app.models.passenger import Passenger
from app.websocket_manager import manager

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("/lock-seat", response_model=SeatLockResponse)
async def lock_seat(
    req: SeatLockRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Seat).where(Seat.id == req.seat_id, Seat.flight_id == req.flight_id)
    )
    seat = result.scalar_one_or_none()
    if not seat:
        raise HTTPException(status_code=404, detail="Seat not found")

    if seat.is_booked:
        raise HTTPException(status_code=409, detail="Seat already booked")

    acquired = acquire_seat_lock(req.flight_id, req.seat_id, current_user.id)
    if not acquired:
        raise HTTPException(
            status_code=409,
            detail="Seat is currently locked by another user. Try again shortly.",
        )

    # only broadcast once we actually know the lock succeeded — broadcasting
    # unconditionally would tell other viewers a seat is locked even when it isn't
    await manager.broadcast(req.flight_id, {"event": "seat_locked", "seat_id": req.seat_id})

    return SeatLockResponse(
        seat_id=req.seat_id, locked=True, expires_in_seconds=LOCK_TTL_SECONDS
    )


@router.post("/confirm", response_model=BookingDetailOut, status_code=status.HTTP_201_CREATED)
async def confirm_booking(
    req: BookingConfirmRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. verify this user actually holds the lock
    lock_owner = get_seat_lock_owner(req.flight_id, req.seat_id)
    if lock_owner != str(current_user.id):
        raise HTTPException(
            status_code=403,
            detail="You don't hold the lock on this seat (it may have expired).",
        )

    # 2. re-fetch seat with a row lock (DB-level guarantee, defense in depth)
    result = await db.execute(
        select(Seat)
        .where(Seat.id == req.seat_id, Seat.flight_id == req.flight_id)
        .with_for_update()
    )
    seat = result.scalar_one_or_none()
    if not seat:
        raise HTTPException(status_code=404, detail="Seat not found")
    if seat.is_booked:
        raise HTTPException(status_code=409, detail="Seat already booked")

    # 2b. fetch the flight for pricing inputs (route + departure time)
    flight_result = await db.execute(select(Flight).where(Flight.id == req.flight_id))
    flight = flight_result.scalar_one_or_none()
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")

    # 3. calculate fare from distance, seat class, and time of day
    fare_amount = calculate_fare(
        origin=flight.origin,
        destination=flight.destination,
        seat_class=seat.seat_class,
        departure_time=flight.departure_time,
    )

    # 4. create booking + payment + passenger + mark seat booked, all in one transaction
    new_booking = Booking(
        user_id=current_user.id,
        flight_id=req.flight_id,
        seat_id=req.seat_id,
        status="confirmed",
    )
    db.add(new_booking)

    try:
        await db.flush()  # get new_booking.id before commit

        new_passenger = Passenger(
            booking_id=new_booking.id,
            full_name=req.passenger.full_name,
            age=req.passenger.age,
            gender=req.passenger.gender,
            meal_preference=req.passenger.meal_preference,
        )
        db.add(new_passenger)

        new_payment = Payment(
            booking_id=new_booking.id,
            amount=fare_amount,
            status="success",
        )
        db.add(new_payment)

        seat.is_booked = True

        await db.commit()
    except IntegrityError:
        # DB-level unique constraint caught a conflict our app-level check missed
        # (e.g. stale/inconsistent data) — this is the final safety net, not a crash.
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Seat already booked (conflict detected at database level)",
        )

    # 5. release the redis lock — booking is now permanent in postgres
    release_seat_lock(req.flight_id, req.seat_id, current_user.id)
    await manager.broadcast(req.flight_id, {"event": "seat_booked", "seat_id": req.seat_id})

    # 6. re-fetch with payment + refund + passenger + flight eagerly loaded, so response
    #    serialization doesn't trigger an async lazy-load (fails outside a greenlet)
    result = await db.execute(
        select(Booking)
        .options(
            selectinload(Booking.payment),
            selectinload(Booking.refund),
            selectinload(Booking.passenger),
            selectinload(Booking.flight),
        )
        .where(Booking.id == new_booking.id)
    )
    logger.info(f"Booking confirmed: user={current_user.id} flight={req.flight_id} seat={req.seat_id}")
    booking_obj = result.scalar_one()
    background_tasks.add_task(
        send_booking_confirmation, current_user.email, booking_obj, flight, seat, new_payment, new_passenger
    )
    return booking_obj


@router.post("/{booking_id}/cancel", response_model=BookingDetailOut)
async def cancel_booking(
    booking_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your booking")
    if booking.status == "cancelled":
        raise HTTPException(status_code=400, detail="Booking already cancelled")

    seat_result = await db.execute(select(Seat).where(Seat.id == booking.seat_id))
    seat = seat_result.scalar_one_or_none()
    if seat:
        seat.is_booked = False

    booking.status = "cancelled"

    payment_result = await db.execute(select(Payment).where(Payment.booking_id == booking.id))
    payment = payment_result.scalar_one_or_none()

    if payment and payment.status != "refunded":
        payment.status = "refunded"

        new_refund = Refund(
            booking_id=booking.id,
            payment_id=payment.id,
            amount=payment.amount,
            reason="User-requested cancellation",
            status="processed",
        )
        db.add(new_refund)

    await db.commit()
    await manager.broadcast(booking.flight_id, {"event": "seat_released", "seat_id": booking.seat_id})

    result = await db.execute(
        select(Booking)
        .options(
            selectinload(Booking.payment),
            selectinload(Booking.refund),
            selectinload(Booking.passenger),
            selectinload(Booking.flight),
        )
        .where(Booking.id == booking.id)
    )
    logger.info(f"Booking cancelled: booking_id={booking.id} user={current_user.id} refund_amount={payment.amount if payment else 0}")
    booking_obj = result.scalar_one()
    if payment:
        background_tasks.add_task(send_cancellation_email, current_user.email, booking_obj, payment.amount)
    return booking_obj


@router.get("/me", response_model=list[BookingDetailOut])
async def get_my_bookings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Booking)
        .options(
            selectinload(Booking.payment),
            selectinload(Booking.refund),
            selectinload(Booking.passenger),
            selectinload(Booking.flight),
        )
        .where(Booking.user_id == current_user.id)
        .order_by(Booking.booked_at.desc())
    )
    return result.scalars().all()


@router.get("/{booking_id}/ticket")
async def download_ticket(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Booking)
        .options(
            selectinload(Booking.payment),
            selectinload(Booking.refund),
            selectinload(Booking.passenger),
            selectinload(Booking.flight),
        )
        .where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your booking")
    if booking.status != "confirmed":
        raise HTTPException(status_code=400, detail="Ticket only available for confirmed bookings")

    flight_result = await db.execute(select(Flight).where(Flight.id == booking.flight_id))
    flight = flight_result.scalar_one_or_none()
    seat_result = await db.execute(select(Seat).where(Seat.id == booking.seat_id))
    seat = seat_result.scalar_one_or_none()

    pdf_bytes = generate_ticket_pdf(
        booking, flight, seat, booking.payment, current_user.email, passenger=booking.passenger
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=skylock-ticket-{booking.id}.pdf"},
    )


@router.post("/lock-seats", response_model=list[SeatLockResponse])
async def lock_multiple_seats(
    req: GroupLockRequest,  # lock-only schema: just flight_id + seat_ids, no passengers yet
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    responses = []
    locked_so_far = []

    for seat_id in req.seat_ids:
        result = await db.execute(
            select(Seat).where(Seat.id == seat_id, Seat.flight_id == req.flight_id)
        )
        seat = result.scalar_one_or_none()
        if not seat or seat.is_booked:
            # roll back any locks already acquired in this batch
            for sid in locked_so_far:
                release_seat_lock(req.flight_id, sid, current_user.id)
                await manager.broadcast(req.flight_id, {"event": "seat_released", "seat_id": sid})
            raise HTTPException(status_code=409, detail=f"Seat {seat_id} unavailable")

        acquired = acquire_seat_lock(req.flight_id, seat_id, current_user.id)
        if not acquired:
            for sid in locked_so_far:
                release_seat_lock(req.flight_id, sid, current_user.id)
                await manager.broadcast(req.flight_id, {"event": "seat_released", "seat_id": sid})
            raise HTTPException(status_code=409, detail=f"Seat {seat_id} is locked by another user")

        locked_so_far.append(seat_id)
        await manager.broadcast(req.flight_id, {"event": "seat_locked", "seat_id": seat_id})
        responses.append(SeatLockResponse(seat_id=seat_id, locked=True, expires_in_seconds=LOCK_TTL_SECONDS))

    return responses


@router.post("/confirm-group", response_model=GroupBookingOut, status_code=status.HTTP_201_CREATED)
async def confirm_group_booking(
    req: GroupBookingRequest,  # confirm schema: requires passengers matching seat_ids
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if len(req.passengers) != len(req.seat_ids):
        raise HTTPException(status_code=400, detail="Number of passengers must match number of seats")

    # 1. verify user holds every lock in this group
    for seat_id in req.seat_ids:
        owner = get_seat_lock_owner(req.flight_id, seat_id)
        if owner != str(current_user.id):
            raise HTTPException(status_code=403, detail=f"Lock missing/expired for seat {seat_id}")

    flight_result = await db.execute(select(Flight).where(Flight.id == req.flight_id))
    flight = flight_result.scalar_one_or_none()
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")

    # 2. row-lock every seat, verify none got booked in the meantime
    seats = []
    for seat_id in req.seat_ids:
        result = await db.execute(
            select(Seat).where(Seat.id == seat_id, Seat.flight_id == req.flight_id).with_for_update()
        )
        seat = result.scalar_one_or_none()
        if not seat or seat.is_booked:
            await db.rollback()
            raise HTTPException(status_code=409, detail=f"Seat {seat_id} already booked")
        seats.append(seat)

    # 3. create one booking + payment + passenger per seat, all in a single transaction
    created_bookings = []
    total_amount = 0.0

    try:
        for seat, passenger_info in zip(seats, req.passengers):
            fare = calculate_fare(flight.origin, flight.destination, seat.seat_class, flight.departure_time)
            total_amount += fare

            booking = Booking(user_id=current_user.id, flight_id=req.flight_id, seat_id=seat.id, status="confirmed")
            db.add(booking)
            await db.flush()

            payment = Payment(booking_id=booking.id, amount=fare, status="success")
            db.add(payment)

            passenger = Passenger(
                booking_id=booking.id,
                full_name=passenger_info.full_name,
                age=passenger_info.age,
                gender=passenger_info.gender,
                meal_preference=passenger_info.meal_preference,
            )
            db.add(passenger)

            seat.is_booked = True
            created_bookings.append(booking.id)

        await db.commit()
    except IntegrityError:
        await db.rollback()
        for seat_id in req.seat_ids:
            release_seat_lock(req.flight_id, seat_id, current_user.id)
            await manager.broadcast(req.flight_id, {"event": "seat_released", "seat_id": seat_id})
        raise HTTPException(
            status_code=409,
            detail="One or more seats were already booked (conflict detected at database level)",
        )

    for seat_id in req.seat_ids:
        release_seat_lock(req.flight_id, seat_id, current_user.id)
        await manager.broadcast(req.flight_id, {"event": "seat_booked", "seat_id": seat_id})

    result = await db.execute(
        select(Booking)
        .options(
            selectinload(Booking.payment),
            selectinload(Booking.refund),
            selectinload(Booking.passenger),
            selectinload(Booking.flight),
        )
        .where(Booking.id.in_(created_bookings))
    )
    bookings = result.scalars().all()

    logger.info(f"Group booking confirmed: user={current_user.id} flight={req.flight_id} seats={req.seat_ids}")

    return GroupBookingOut(bookings=bookings, total_amount=round(total_amount, 2))


@router.websocket("/ws/{flight_id}")
async def seat_updates_ws(websocket: WebSocket, flight_id: int):
    await manager.connect(flight_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # keep alive; we don't need incoming messages
    except WebSocketDisconnect:
        manager.disconnect(flight_id, websocket)