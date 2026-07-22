
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    flight_id = Column(Integer, ForeignKey("flights.id"), nullable=False)
    seat_id = Column(Integer, ForeignKey("seats.id"), unique=True, nullable=False)
    status = Column(String, default="pending", nullable=False)  # pending/confirmed/cancelled
    booked_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="bookings")
    flight = relationship("Flight", back_populates="bookings")
    seat = relationship("Seat", back_populates="booking")
    payment = relationship("Payment", back_populates="booking", uselist=False)
    refund = relationship("Refund", back_populates="booking", uselist=False)
    passenger = relationship("Passenger", back_populates="booking", uselist=False)