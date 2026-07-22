from pydantic import BaseModel
from datetime import datetime


class PassengerInput(BaseModel):
    full_name: str
    age: int
    gender: str
    meal_preference: str = "veg"


class PassengerOut(BaseModel):
    full_name: str
    age: int
    gender: str
    meal_preference: str

    class Config:
        from_attributes = True


class SeatLockRequest(BaseModel):
    flight_id: int
    seat_id: int


class SeatLockResponse(BaseModel):
    seat_id: int
    locked: bool
    expires_in_seconds: int


class BookingConfirmRequest(BaseModel):
    flight_id: int
    seat_id: int
    passenger: PassengerInput


class PaymentOut(BaseModel):
    id: int
    amount: float
    status: str

    class Config:
        from_attributes = True


class BookingOut(BaseModel):
    id: int
    flight_id: int
    seat_id: int
    status: str
    booked_at: datetime

    class Config:
        from_attributes = True


class RefundOut(BaseModel):
    id: int
    amount: float
    reason: str | None
    status: str
    refunded_at: datetime

    class Config:
        from_attributes = True

    
class FlightSummaryOut(BaseModel):
    flight_number: str
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime

    class Config:
        from_attributes = True
        
class BookingDetailOut(BookingOut):
    payment: PaymentOut | None = None
    refund: RefundOut | None = None
    passenger: PassengerOut | None = None
    flight: FlightSummaryOut | None = None

class GroupLockRequest(BaseModel):
    flight_id: int
    seat_ids: list[int]
    
class GroupBookingRequest(BaseModel):
    flight_id: int
    seat_ids: list[int]
    passengers: list[PassengerInput]


class GroupBookingOut(BaseModel):
    bookings: list[BookingDetailOut]
    total_amount: float