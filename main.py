import os
import re
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field, field_validator

# ----------------------------
# App and CORS
# ----------------------------
app = FastAPI(title="Stk Barbershop Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# Rate Limiting (in-memory)
# ----------------------------
# Simple IP-based rate limiter: max 1 request / 15s, 5 / 5min
RATE_LIMIT_WINDOW_SHORT = timedelta(seconds=15)
RATE_LIMIT_MAX_SHORT = 1
RATE_LIMIT_WINDOW_LONG = timedelta(minutes=5)
RATE_LIMIT_MAX_LONG = 5
_request_log: dict[str, list[datetime]] = {}


def check_rate_limit(ip: str) -> None:
    now = datetime.utcnow()
    history = _request_log.get(ip, [])
    # prune old entries
    history = [t for t in history if now - t <= RATE_LIMIT_WINDOW_LONG]
    _request_log[ip] = history

    # checks
    short_count = len([t for t in history if now - t <= RATE_LIMIT_WINDOW_SHORT])
    long_count = len(history)

    if short_count >= RATE_LIMIT_MAX_SHORT or long_count >= RATE_LIMIT_MAX_LONG:
        raise HTTPException(status_code=429, detail="Prea multe cereri. Încearcă din nou mai târziu.")

    # record
    history.append(now)
    _request_log[ip] = history


# ----------------------------
# Models and validation
# ----------------------------
ALLOWED_SERVICES = {"tuns", "aranjat barba", "pachet complet"}
PHONE_REGEX = re.compile(r"^[+]?([0-9]{8,15})$")


class AppointmentRequest(BaseModel):
    full_name: str = Field(min_length=2)
    phone: str
    email: Optional[EmailStr] = None
    service: str
    date: str  # YYYY-MM-DD
    time: str  # HH:MM
    message: Optional[str] = None
    captcha_a: int
    captcha_b: int
    captcha_result: int

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = v.strip().replace(" ", "")
        if not PHONE_REGEX.match(v):
            raise ValueError("Număr de telefon invalid")
        return v

    @field_validator("service")
    @classmethod
    def validate_service(cls, v: str) -> str:
        v_norm = v.strip().lower()
        if v_norm not in ALLOWED_SERVICES:
            raise ValueError("Serviciu invalid")
        return v_norm

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Format dată invalid (YYYY-MM-DD)")
        return v

    @field_validator("time")
    @classmethod
    def validate_time(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%H:%M")
        except ValueError:
            raise ValueError("Format oră invalid (HH:MM)")
        return v

    def combined_datetime(self) -> datetime:
        dt = datetime.strptime(f"{self.date} {self.time}", "%Y-%m-%d %H:%M")
        return dt

    def validate_future(self) -> None:
        if self.combined_datetime() <= datetime.utcnow():
            raise ValueError("Data și ora nu pot fi în trecut")

    def validate_captcha(self) -> None:
        if self.captcha_a + self.captcha_b != self.captcha_result:
            raise ValueError("Captcha invalid")


class AppointmentResponse(BaseModel):
    success: bool
    message: str


# ----------------------------
# Utility: send email via SMTP
# ----------------------------

def send_email(subject: str, html_body: str) -> None:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    mail_from = os.getenv("MAIL_FROM", smtp_user or "")
    mail_to = os.getenv("MAIL_TO", "stkbarbershop@gmail.com")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")

    if not smtp_host or not smtp_port or not mail_from or not mail_to:
        raise RuntimeError("Configurare SMTP incompletă")

    msg = MIMEMultipart()
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if use_tls:
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
        server.starttls()
    else:
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)

    try:
        if smtp_user and smtp_pass:
            server.login(smtp_user, smtp_pass)
        server.sendmail(mail_from, [mail_to], msg.as_string())
    finally:
        try:
            server.quit()
        except Exception:
            pass


# ----------------------------
# Routes
# ----------------------------
@app.get("/")
def root():
    return {"service": "Stk Barbershop API", "status": "ok"}


@app.post("/api/appointment", response_model=AppointmentResponse)
async def create_appointment(payload: AppointmentRequest, request: Request):
    # Rate limit
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(client_ip)

    # Extra validations
    try:
        payload.validate_future()
        payload.validate_captcha()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Compose email body
    appt_dt = payload.combined_datetime()
    html_body = f"""
    <h2>Programare nouă - Stk Barbershop</h2>
    <p><strong>Nume complet:</strong> {payload.full_name}</p>
    <p><strong>Telefon:</strong> {payload.phone}</p>
    <p><strong>Email:</strong> {payload.email or '-'}
    <p><strong>Serviciu:</strong> {payload.service.title()}</p>
    <p><strong>Data:</strong> {appt_dt.strftime('%Y-%m-%d')}</p>
    <p><strong>Ora:</strong> {appt_dt.strftime('%H:%M')}</p>
    <p><strong>Mesaj:</strong> {payload.message or '-'}
    <hr/>
    <p>Mesaj generat automat de formularul online.</p>
    """

    subject = f"Programare nouă: {payload.full_name} - {appt_dt.strftime('%Y-%m-%d %H:%M')}"

    try:
        send_email(subject, html_body)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Eroare la trimiterea emailului: {str(e)}")

    return AppointmentResponse(success=True, message="Programarea a fost trimisă cu succes.")


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        from database import db

        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
