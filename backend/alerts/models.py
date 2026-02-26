from ..database.db import db
from datetime import datetime

class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    camera_id = db.Column(db.Integer, db.ForeignKey('camera.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    behavior = db.Column(db.String(255), nullable=False)
    threat_score = db.Column(db.Integer, nullable=False) # 0-100 (Contextual Threat Score)
    threat_level = db.Column(db.String(50), nullable=False) # NORMAL, LOW, MEDIUM, HIGH, CRITICAL
    snapshot_path = db.Column(db.String(255), nullable=True) # Path to stored image snapshot
    
    # NEW: Threat engine breakdown
    base_score = db.Column(db.Float, default=0.0)
    context_multiplier = db.Column(db.Float, default=1.0)
    novelty_factor = db.Column(db.Float, default=1.0)
    is_dismissed = db.Column(db.Boolean, default=False)

    camera = db.relationship('Camera', backref=db.backref('alerts', lazy=True))

    def __repr__(self):
        return f'<Alert {self.behavior} from Camera {self.camera_id} at {self.timestamp}>'

    def to_dict(self):
        return {
            "id": self.id,
            "camera_id": self.camera_id,
            "timestamp": self.timestamp.isoformat(),
            "behavior": self.behavior,
            "threat_score": self.threat_score,
            "threat_level": self.threat_level,
            "snapshot_path": self.snapshot_path,
            "camera_name": self.camera.name if self.camera else None,
            "base_score": self.base_score,
            "context_multiplier": self.context_multiplier,
            "novelty_factor": self.novelty_factor,
            "is_dismissed": self.is_dismissed
        }
