from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor


def generate_ticket_pdf(booking, flight, seat, payment, user_email: str, passenger=None) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    blue = HexColor("#2f7cf6")
    dark = HexColor("#0b3a63")
    muted = HexColor("#5c7c98")

    # header band
    c.setFillColor(blue)
    c.rect(0, height - 90, width, 90, fill=True, stroke=False)
    c.setFillColor(HexColor("#ffffff"))
    c.setFont("Helvetica-Bold", 22)
    c.drawString(50, height - 55, "SkyLock — Boarding Pass")

    # route
    c.setFillColor(dark)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 135, f"{flight.origin}   ->   {flight.destination}")

    c.setFont("Helvetica", 10)
    c.setFillColor(muted)
    c.drawString(50, height - 155, f"Flight {flight.flight_number}")

    # flight timing block
    y = height - 190
    c.setFillColor(dark)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Flight details")
    c.setFont("Helvetica", 10)
    y -= 18
    c.drawString(50, y, f"Departure: {flight.departure_time.strftime('%d %b %Y, %H:%M')}")
    y -= 16
    c.drawString(50, y, f"Arrival:   {flight.arrival_time.strftime('%d %b %Y, %H:%M')}")
    y -= 16
    c.drawString(50, y, f"Seat: {seat.seat_number}  ({seat.seat_class})")

    # passenger block
    y -= 34
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Passenger details")
    c.setFont("Helvetica", 10)
    y -= 18
    if passenger:
        c.drawString(50, y, f"Name: {passenger.full_name}")
        y -= 16
        c.drawString(50, y, f"Age / Gender: {passenger.age} / {passenger.gender}")
        y -= 16
        c.drawString(50, y, f"Meal preference: {passenger.meal_preference.replace('_', ' ').title()}")
        y -= 16
    else:
        c.drawString(50, y, f"Contact: {user_email}")
        y -= 16

    # payment / fees breakdown
    y -= 20
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Payment summary")
    c.setFont("Helvetica", 10)
    y -= 18

    base_fare = round(payment.amount * 0.94, 2) if payment else 0
    taxes_fees = round((payment.amount if payment else 0) - base_fare, 2)

    c.drawString(50, y, f"Base fare:      Rs. {base_fare}")
    y -= 16
    c.drawString(50, y, f"Taxes & fees:   Rs. {taxes_fees}")
    y -= 16
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, f"Total paid:     Rs. {payment.amount if payment else 0}")
    y -= 16
    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Payment status: {payment.status.upper() if payment else 'N/A'}")

    y -= 24
    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Booking ID: {booking.id}   |   Status: {booking.status.upper()}")

    # footer
    y -= 30
    c.setStrokeColor(HexColor("#cccccc"))
    c.line(50, y, width - 50, y)
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(50, y - 15, "This is a system-generated ticket. Have a safe flight.")

    c.save()
    buffer.seek(0)
    return buffer.read()