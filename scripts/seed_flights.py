"""
Seeds sample flights across major Indian airport routes + auto-generates seats.
Safe to re-run — skips any flight_number that already exists.

Usage:
    python -m scripts.seed_flights
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.flight import Flight
from app.models.seat import Seat

# Matches the INDIAN_AIRPORTS list used in the frontend dropdowns
SAMPLE_FLIGHTS = [
    {"flight_number": "SK101", "origin": "DEL", "destination": "BOM", "total_seats": 18, "hours_from_now": 12},
    {"flight_number": "SK102", "origin": "BOM", "destination": "DEL", "total_seats": 18, "hours_from_now": 16},
    {"flight_number": "SK201", "origin": "DEL", "destination": "BLR", "total_seats": 24, "hours_from_now": 20},
    {"flight_number": "SK202", "origin": "BLR", "destination": "DEL", "total_seats": 24, "hours_from_now": 26},
    {"flight_number": "SK301", "origin": "BOM", "destination": "BLR", "total_seats": 18, "hours_from_now": 14},
    {"flight_number": "SK302", "origin": "BLR", "destination": "BOM", "total_seats": 18, "hours_from_now": 30},
    {"flight_number": "SK401", "origin": "DEL", "destination": "MAA", "total_seats": 30, "hours_from_now": 18},
    {"flight_number": "SK402", "origin": "MAA", "destination": "DEL", "total_seats": 30, "hours_from_now": 34},
    {"flight_number": "SK501", "origin": "BOM", "destination": "CCU", "total_seats": 24, "hours_from_now": 22},
    {"flight_number": "SK502", "origin": "CCU", "destination": "BOM", "total_seats": 24, "hours_from_now": 38},
    {"flight_number": "SK601", "origin": "HYD", "destination": "DEL", "total_seats": 18, "hours_from_now": 15},
    {"flight_number": "SK602", "origin": "DEL", "destination": "HYD", "total_seats": 18, "hours_from_now": 40},
    {"flight_number": "SK701", "origin": "BLR", "destination": "GOI", "total_seats": 12, "hours_from_now": 10},
    {"flight_number": "SK702", "origin": "GOI", "destination": "BLR", "total_seats": 12, "hours_from_now": 44},
    {"flight_number": "SK801", "origin": "BOM", "destination": "AMD", "total_seats": 12, "hours_from_now": 9},
    {"flight_number": "SK802", "origin": "AMD", "destination": "BOM", "total_seats": 12, "hours_from_now": 48},
    {"flight_number": "SK901", "origin": "DEL", "destination": "JAI", "total_seats": 12, "hours_from_now": 8},
    {"flight_number": "SK902", "origin": "JAI", "destination": "DEL", "total_seats": 12, "hours_from_now": 52},
    {"flight_number": "SK1001", "origin": "COK", "destination": "BOM", "total_seats": 18, "hours_from_now": 24},
    {"flight_number": "SK1002", "origin": "BOM", "destination": "COK", "total_seats": 18, "hours_from_now": 56},
    {"flight_number": "SK1101", "origin": "PNQ", "destination": "DEL", "total_seats": 18, "hours_from_now": 13},
    {"flight_number": "SK1102", "origin": "DEL", "destination": "PNQ", "total_seats": 18, "hours_from_now": 60},
    {"flight_number": "SK1201", "origin": "CCU", "destination": "GAU", "total_seats": 12, "hours_from_now": 17},
    {"flight_number": "SK1202", "origin": "GAU", "destination": "CCU", "total_seats": 12, "hours_from_now": 64},
    {"flight_number": "SK1301", "origin": "LKO", "destination": "DEL", "total_seats": 12, "hours_from_now": 11},
    {"flight_number": "SK1302", "origin": "DEL", "destination": "LKO", "total_seats": 12, "hours_from_now": 68},
    {"flight_number": "SK1401", "origin": "BLR", "destination": "TRV", "total_seats": 18, "hours_from_now": 19},
    {"flight_number": "SK1402", "origin": "TRV", "destination": "BLR", "total_seats": 18, "hours_from_now": 72},
    {"flight_number": "SK1501", "origin": "IXC", "destination": "BOM", "total_seats": 12, "hours_from_now": 21},
    {"flight_number": "SK1502", "origin": "BOM", "destination": "IXC", "total_seats": 12, "hours_from_now": 76},
]

SEAT_LETTERS = ["A", "B", "C", "D", "E", "F"]


async def seed():
    async with AsyncSessionLocal() as db:
        created, skipped = 0, 0

        for f in SAMPLE_FLIGHTS:
            existing = await db.execute(
                select(Flight).where(Flight.flight_number == f["flight_number"])
            )
            if existing.scalar_one_or_none():
                print(f"Skipping {f['flight_number']} — already exists")
                skipped += 1
                continue

            departure = datetime.now(timezone.utc) + timedelta(hours=f["hours_from_now"])
            arrival = departure + timedelta(hours=2)

            flight = Flight(
                flight_number=f["flight_number"],
                origin=f["origin"],
                destination=f["destination"],
                departure_time=departure,
                arrival_time=arrival,
                total_seats=f["total_seats"],
            )
            db.add(flight)
            await db.flush()  # get flight.id before adding seats

            seats_created = 0
            row = 1
            while seats_created < f["total_seats"]:
                for letter in SEAT_LETTERS:
                    if seats_created >= f["total_seats"]:
                        break
                    db.add(Seat(
                        flight_id=flight.id,
                        seat_number=f"{row}{letter}",
                        seat_class="business" if row <= 2 else "economy",
                    ))
                    seats_created += 1
                row += 1

            print(f"Seeded {f['flight_number']} ({f['origin']} -> {f['destination']}) with {f['total_seats']} seats")
            created += 1

        await db.commit()
    print(f"\nSeeding complete — {created} created, {skipped} skipped.")


if __name__ == "__main__":
    asyncio.run(seed())