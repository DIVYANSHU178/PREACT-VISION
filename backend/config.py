import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    # General Flask Secret Key
    SECRET_KEY = os.getenv("SECRET_KEY", "preact-secret-key-dev")

    # JWT Secret Key
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "preact-jwt-secret-key-dev")

    # Database configuration
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'preact.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Email configuration (for sending user credentials)
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    SMTP_EMAIL = os.getenv("SMTP_EMAIL", "preactvision1@gmail.com")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "mlzi dhmx zgey vygv")
