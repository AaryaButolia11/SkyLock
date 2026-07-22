import base64
import httpx
from app.logging_config import logger
from app.config import settings

RESEND_API_URL = "https://api.resend.com/emails"


def send_email(to: str, subject: str, body: str, attachment_bytes: bytes = None, attachment_filename: str = None):
    """
    Sends a real email via Resend's HTTP API (port 443).
    Raw SMTP (ports 25/465/587) is blocked on Render's free tier, so we go
    over plain HTTPS instead — same effect, no platform restriction.
    Falls back to logging the error if delivery fails.
    """
    payload = {
        "from": settings.resend_from_email,
        "to": [to],
        "subject": subject,
        "text": body,
    }

    if attachment_bytes and attachment_filename:
        payload["attachments"] = [
            {
                "filename": attachment_filename,
                "content": base64.b64encode(attachment_bytes).decode("utf-8"),
            }
        ]

    try:
        response = httpx.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        logger.info(f"[EMAIL SENT] To: {to} | Subject: {subject}" + (" | with attachment" if attachment_bytes else ""))
    except httpx.HTTPStatusError as e:
        logger.error(
            f"[EMAIL FAILED] To: {to} | Subject: {subject} | "
            f"Status: {e.response.status_code} | Body: {e.response.text}"
        )
    except Exception as e:
        logger.error(f"[EMAIL FAILED] To: {to} | Subject: {subject} | Error: {e}")


def send_booking_confirmation(user_email: str, booking, flight, seat, payment, passenger=None):
    subject = f"Booking Confirmed — {flight.flight_number}"

    base_fare = round(payment.amount * 0.94, 2) if payment else 0
    taxes_fees = round((payment.amount if payment else 0) - base_fare, 2)

    passenger_block = ""
    if passenger:
        passenger_block = (
            f"Passenger: {passenger.full_name}\n"
            f"Age / Gender: {passenger.age} / {passenger.gender}\n"
            f"Meal preference: {passenger.meal_preference.replace('_', ' ').title()}\n"
        )

    body = (
        f"Hi,\n\n"
        f"Your booking is confirmed. Your boarding pass is attached.\n\n"
        f"Flight: {flight.flight_number} ({flight.origin} -> {flight.destination})\n"
        f"Departure: {flight.departure_time.strftime('%d %b %Y, %H:%M')}\n"
        f"Arrival: {flight.arrival_time.strftime('%d %b %Y, %H:%M')}\n"
        f"Seat: {seat.seat_number} ({seat.seat_class})\n\n"
        f"{passenger_block}\n"
        f"Base fare: ₹{base_fare}\n"
        f"Taxes & fees: ₹{taxes_fees}\n"
        f"Total paid: ₹{payment.amount}\n"
        f"Booking ID: {booking.id}\n\n"
        f"Thanks for booking with SkyLock."
    )

    from app.services.ticket_pdf import generate_ticket_pdf
    pdf_bytes = generate_ticket_pdf(booking, flight, seat, payment, user_email, passenger=passenger)

    send_email(
        to=user_email,
        subject=subject,
        body=body,
        attachment_bytes=pdf_bytes,
        attachment_filename=f"skylock-ticket-{booking.id}.pdf",
    )


def send_cancellation_email(user_email: str, booking, refund_amount: float):
    subject = f"Booking Cancelled — #{booking.id}"
    body = (
        f"Hi,\n\n"
        f"Your booking #{booking.id} has been cancelled.\n"
        f"Refund amount: ₹{refund_amount}\n\n"
        f"Thanks for using SkyLock."
    )
    send_email(user_email, subject, body)