from app.redis_client import redis

LOCK_TTL_SECONDS = 300  # 5 minutes


def _lock_key(flight_id: int, seat_id: int) -> str:
    return f"seat_lock:{flight_id}:{seat_id}"


def acquire_seat_lock(flight_id: int, seat_id: int, user_id: int) -> bool:
    """
    Attempts to lock a seat for a user. Returns True if lock acquired,
    False if another user already holds it.
    Uses Redis SET with NX (only set if not exists) + EX (auto-expiry).
    """
    key = _lock_key(flight_id, seat_id)
    result = redis.set(key, str(user_id), nx=True, ex=LOCK_TTL_SECONDS)
    return result is not None


def get_seat_lock_owner(flight_id: int, seat_id: int) -> str | None:
    key = _lock_key(flight_id, seat_id)
    return redis.get(key)

def get_seat_lock_owners_bulk(flight_id: int, seat_ids: list[int]) -> dict:
    """
    Checks lock status for many seats in ONE Redis round trip instead of one per seat.
    Returns {seat_id: owner_user_id_or_None}.
    """
    if not seat_ids:
        return {}
    keys = [_lock_key(flight_id, sid) for sid in seat_ids]
    values = redis.mget(*keys)  # unpack the list — mget takes *args, not a single list
    return {sid: values[i] for i, sid in enumerate(seat_ids)}


def release_seat_lock(flight_id: int, seat_id: int, user_id: int) -> None:
    """
    Only releases the lock if it's actually owned by this user —
    prevents accidentally releasing someone else's lock.
    """
    key = _lock_key(flight_id, seat_id)
    owner = redis.get(key)
    if owner == str(user_id):
        redis.delete(key)
def is_seat_locked(flight_id: int, seat_id: int) -> bool:
    return get_seat_lock_owner(flight_id, seat_id) is not None
'''
SET key value NX EX 300 is atomic in Redis — "set this key only if it doesn't already exist, and expire it in 300 seconds" happens as one indivisible operation. If two users hit acquire_seat_lock at the exact same millisecond, Redis guarantees only one SET succeeds. This is the textbook distributed-lock pattern (Redlock is the more advanced multi-node version of this idea).
Why not just check-then-set in Python? Because "check if locked" then "set if not locked" as two separate steps has a race condition window between them — two requests could both pass the check before either sets the lock. NX collapses check+set into one atomic Redis operation, closing that window entirely.
EX 300 — auto-expiry. If a user locks a seat then abandons the booking (closes tab, whatever), the lock self-destructs after 5 minutes instead of the seat being stuck locked forever.
Ownership check in release_seat_lock — without this, User B could accidentally release User A's still-valid lock by calling release on the same seat.

'''
