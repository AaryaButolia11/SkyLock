from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Refund(Base):
    __tablename__ = "refunds"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), unique=True, nullable=False)
    payment_id = Column(Integer, ForeignKey("payments.id"), unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    reason = Column(String, nullable=True)
    status = Column(String, default="processed", nullable=False)  # processed/pending/failed
    refunded_at = Column(DateTime(timezone=True), server_default=func.now())

    booking = relationship("Booking", back_populates="refund")
    payment = relationship("Payment", back_populates="refund")