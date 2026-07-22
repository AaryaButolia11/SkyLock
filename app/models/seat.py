from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base

class Seat(Base):
    __tablename__ = "seats"

    id = Column(Integer, primary_key=True, index=True)
    flight_id = Column(Integer, ForeignKey("flights.id"), nullable=False)
    seat_number = Column(String, nullable=False)          # e.g. "12A"
    seat_class = Column(String, nullable=False, default="economy")
    is_booked = Column(Boolean, default=False, nullable=False)

    flight = relationship("Flight", back_populates="seats")
    booking = relationship("Booking", back_populates="seat", uselist=False)

    __table_args__ = (
        UniqueConstraint("flight_id", "seat_number", name="uq_flight_seat"),
    )