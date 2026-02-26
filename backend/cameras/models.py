from ..database.db import db

class Camera(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    # This URL could be an RTSP stream, a file path, or a webcam index (e.g., 0 for default webcam)
    stream_url = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), default="disconnected") # e.g., 'connected', 'disconnected', 'streaming', 'error'
    is_active = db.Column(db.Boolean, default=True)
    
    # NEW: Contextual fields
    zone = db.Column(db.String(50), default="general") # e.g., gym, park, entry, market
    context_rules = db.Column(db.JSON, nullable=True) # Per-camera custom weight overrides

    def __repr__(self):
        return f'<Camera {self.name}>'

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "stream_url": self.stream_url,
            "status": self.status,
            "is_active": self.is_active,
            "zone": self.zone
        }
