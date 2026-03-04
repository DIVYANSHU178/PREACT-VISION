import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from ..config import Config

def send_email(to_email, subject, html_content):
    msg = MIMEMultipart()
    msg["From"] = Config.SMTP_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(html_content, "html"))

    server = smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT)
    server.starttls()
    server.login(Config.SMTP_EMAIL, Config.SMTP_PASSWORD)
    server.send_message(msg)
    server.quit()
