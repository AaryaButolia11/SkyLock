from app.models.user import User
from app.models.flight import Flight
from app.models.seat import Seat
from app.models.booking import Booking
from app.models.payment import Payment
from app.models.refund import Refund
from app.models.passenger import Passenger
'''
ForeignKey("flights.id") — this is what makes Seat belong to a Flight. In Postgres this becomes an actual foreign key constraint — the DB itself will reject a seat pointing to a flight that doesn't exist.
relationship(...) — this isn't a DB column, it's a Python-side convenience so you can do flight.seats and get a list of Seat objects, without writing a JOIN yourself.
UniqueConstraint("flight_id", "seat_number") on Seat — guarantees seat "12A" can only exist once per flight at the database level. Combined with booking.seat_id being unique=True, this is one of your two lines of defense against double-booking (Redis lock is the other).
status as a plain String — works fine for a resume project. If you want to flex more, later we can upgrade this to a proper Postgres Enum type — but let's not over-engineer yet.
'''
