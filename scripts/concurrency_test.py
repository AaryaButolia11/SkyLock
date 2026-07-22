"""
Fires two simultaneous booking requests at the SAME seat to prove
the locking mechanism prevents double-booking.

Usage:
    python scripts/concurrency_test.py <flight_id> <seat_id> <token_user_a> <token_user_b>
"""

import asyncio
import sys
import httpx

BASE_URL = "http://127.0.0.1:8000"


async def attempt_booking(client: httpx.AsyncClient, token: str, flight_id: int, seat_id: int, label: str):
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"flight_id": flight_id, "seat_id": seat_id}

    lock_resp = await client.post(f"{BASE_URL}/bookings/lock-seat", json=payload, headers=headers)
    print(f"[{label}] lock-seat -> {lock_resp.status_code} {lock_resp.json()}")

    if lock_resp.status_code != 200:
        return

    confirm_resp = await client.post(f"{BASE_URL}/bookings/confirm", json=payload, headers=headers)
    print(f"[{label}] confirm -> {confirm_resp.status_code} {confirm_resp.json()}")


async def main():
    flight_id = int(sys.argv[1])
    seat_id = int(sys.argv[2])
    token_a = sys.argv[3]
    token_b = sys.argv[4]

    async with httpx.AsyncClient() as client:
        # fire both requests at (approximately) the same moment
        await asyncio.gather(
            attempt_booking(client, token_a, flight_id, seat_id, "User A"),
            attempt_booking(client, token_b, flight_id, seat_id, "User B"),
        )


if __name__ == "__main__":
    asyncio.run(main())