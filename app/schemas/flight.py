from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class FlightCreate(BaseModel):
    flight_number: str
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    total_seats: int


class SeatOut(BaseModel):
    id: int
    seat_number: str
    seat_class: str
    is_booked: bool
    is_locked: bool = False
    price: float = 0.0

    class Config:
        from_attributes = True
        
class FlightOut(BaseModel):
    id: int
    flight_number: str
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    total_seats: int
    price: float = 0.0   # economy starting price, computed on the fly

    class Config:
        from_attributes = True


class FlightDetailOut(FlightOut):
    seats: list[SeatOut] = []
    
    
    '''Why FlightDetailOut extends FlightOut: the list view (GET /flights) doesn't need every seat nested in each result — that's wasteful. The single-flight view (GET /flights/{id}) does. Reusing via inheritance avoids duplicating fields.'''
    