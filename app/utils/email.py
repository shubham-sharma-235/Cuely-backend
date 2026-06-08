import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", f"CueManager <{SMTP_USER}>")


def send_otp_email(to_email: str, owner_name: str, otp: str) -> None:
    """
    Send OTP verification email.
    Raises an exception if SMTP credentials are not configured —
    the caller (auth router) catches this and returns a 500.
    """
    if not SMTP_USER or not SMTP_PASS:
        raise RuntimeError(
            "SMTP credentials not configured. Set SMTP_USER and SMTP_PASS in .env"
        )

    subject = "Your CueManager verification code"

    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;background:#0f0f1c;border-radius:12px;border:1px solid rgba(212,168,67,0.2);">
      <h2 style="font-family:serif;color:#d4a843;letter-spacing:1px;margin:0 0 8px;">CueManager</h2>
      <p style="color:#7a7890;font-size:13px;margin:0 0 24px;">Club management for billiards owners</p>
      <p style="color:#e8e6f0;font-size:15px;margin:0 0 8px;">Hi {owner_name},</p>
      <p style="color:#7a7890;font-size:14px;margin:0 0 24px;">Use the code below to verify your account. It expires in <strong style="color:#e8e6f0;">5 minutes</strong>.</p>
      <div style="background:#161628;border:1px solid rgba(212,168,67,0.3);border-radius:10px;padding:20px;text-align:center;margin:0 0 24px;">
        <span style="font-family:monospace;font-size:36px;font-weight:700;letter-spacing:12px;color:#d4a843;">{otp}</span>
      </div>
      <p style="color:#4a4860;font-size:12px;margin:0;">If you did not register for CueManager, ignore this email.</p>
    </div>
    """

    text = f"Your CueManager verification code is: {otp}\n\nIt expires in 5 minutes."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = to_email
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, to_email, msg.as_string())
