from ..database.db import db
from datetime import datetime

class User(db.Model):
    __tablename__ = 'user'
    __table_args__ = {'extend_existing': True} # Added to prevent redefinition errors during development/hot-reloading

    id = db.Column(db.Integer, primary_key=True)

    fullname = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    organization = db.Column(db.String(120))

    password_hash = db.Column(db.String(255), nullable=True) # Changed to 255 for bcrypt hash length

    role = db.Column(db.String(20), default="user")   # admin | user
    is_approved = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<User {self.email}>"

class SystemSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return f"<SystemSetting {self.key}={self.value}>"