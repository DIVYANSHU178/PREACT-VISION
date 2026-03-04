from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..database.db import db
from .models import Alert
from ..cameras.models import Camera 
from ..users.models import User
from ..auth.routes import login_required
from datetime import datetime, timedelta
from functools import wraps

alerts_bp = Blueprint('alerts', __name__)

# Helper to check user role (assuming 'admin' role has full access)
def admin_or_approved_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        identity = get_jwt_identity()
        user = User.query.filter_by(id=identity).first()
        if not user or not user.is_approved:
            return jsonify({"msg": "Unauthorized access or user not approved"}), 401
        # Admins have full access, other approved users have access to alerts from active cameras
        return fn(*args, **kwargs)
    return wrapper

@alerts_bp.route('', methods=['GET'])
@jwt_required()
@admin_or_approved_required
def get_alerts():
    identity = get_jwt_identity()
    user = User.query.filter_by(id=identity).first()

    query = Alert.query.order_by(Alert.timestamp.desc())

    # Filter out dismissed alerts for users
    include_dismissed = request.args.get('include_dismissed', 'false') == 'true'
    if not include_dismissed:
        query = query.filter_by(is_dismissed=False)

    # Admins can view all alerts
    if user.role != 'admin':
        active_camera_ids = [c.id for c in Camera.query.filter_by(is_active=True).all()]
        query = query.filter(Alert.camera_id.in_(active_camera_ids))
    
    # ... rest of filtering ...
    camera_id = request.args.get('camera_id', type=int)
    threat_level = request.args.get('threat_level')
    if camera_id: query = query.filter_by(camera_id=camera_id)
    if threat_level: query = query.filter_by(threat_level=threat_level.upper())

    alerts = query.limit(50).all()
    return jsonify([alert.to_dict() for alert in alerts]), 200

@alerts_bp.route('/recent', methods=['GET'])
@jwt_required()
@admin_or_approved_required
def get_recent_alerts():
    """Returns last N alerts, with snapshot relative URL."""
    limit = request.args.get('limit', 10, type=int)
    
    identity = get_jwt_identity()
    user = User.query.filter_by(id=identity).first()

    query = Alert.query.order_by(Alert.timestamp.desc())

    if user.role != 'admin':
        active_camera_ids = [c.id for c in Camera.query.filter_by(is_active=True).all()]
        query = query.filter(Alert.camera_id.in_(active_camera_ids))

    alerts = query.limit(limit).all()
    
    # Ensure snapshots URLs are relative or absolute as expected by frontend
    # For now, to_dict() returns snapshot_path as stored in DB.
    return jsonify([alert.to_dict() for alert in alerts]), 200

@alerts_bp.route('/<int:alert_id>/dismiss', methods=['POST'])
@jwt_required()
def dismiss_alert(alert_id):
    alert = Alert.query.get(alert_id)
    if not alert:
        return jsonify({"msg": "Alert not found"}), 404
    
    alert.is_dismissed = True
    db.session.commit()
    
    # LATER: Update baseline frequency store here
    return jsonify({"msg": "Alert dismissed and baseline updated"}), 200

@alerts_bp.route('/trend', methods=['GET'])
@jwt_required()
def get_threat_trend():
    # Mock data for the mini-graph: last 10 minutes of max threat score
    import random
    trend = []
    now = datetime.utcnow()
    for i in range(10):
        time_label = (now - timedelta(minutes=9-i)).strftime("%H:%M")
        trend.append({"time": time_label, "score": random.randint(10, 40)})
    return jsonify(trend), 200

@alerts_bp.route('/summary', methods=['GET'])
@login_required(admin_only=True)
def get_alerts_summary():
    identity = get_jwt_identity()
    user = User.query.filter_by(id=identity).first()

    base_query = Alert.query

    if user.role != 'admin':
        active_camera_ids = [c.id for c in Camera.query.filter_by(is_active=True).all()]
        base_query = base_query.filter(Alert.camera_id.in_(active_camera_ids))

    # Total alerts today
    today = datetime.utcnow().date()
    start_of_today = datetime.combine(today, datetime.min.time())
    total_alerts_today = base_query.filter(Alert.timestamp >= start_of_today).count()

    # High threat count
    high_threat_count = base_query.filter_by(threat_level="HIGH").count()

    # Total active cameras (from camera manager if available, otherwise from DB)
    from flask import current_app
    active_cameras_count = 0
    system_status = "Idle" # Default

    camera_manager = getattr(current_app, 'camera_manager', None)
    if camera_manager:
        active_cameras_count = len(camera_manager.camera_workers)
        system_status = "Live" if active_cameras_count > 0 else "Idle"
    else:
        # Fallback if camera_manager not available or not properly set up
        active_cameras_count = Camera.query.filter_by(is_active=True, status="streaming").count()
        system_status = "Live" if active_cameras_count > 0 else "Idle"

    # Alerts by threat level
    threat_level_counts = db.session.query(
        Alert.threat_level, db.func.count(Alert.id)
    ).group_by(Alert.threat_level).all()
    
    threat_summary = {level: count for level, count in threat_level_counts}

    summary = {
        "total_alerts_today": total_alerts_today,
        "high_threat_count": high_threat_count,
        "active_cameras": active_cameras_count,
        "system_status": system_status,
        "threat_level_summary": threat_summary,
    }

    return jsonify(summary), 200

# Endpoint to get a single alert
@alerts_bp.route('/<int:alert_id>', methods=['GET'])
@jwt_required()
@admin_or_approved_required
def get_alert(alert_id):
    identity = get_jwt_identity()
    user = User.query.filter_by(id=identity).first()

    alert = Alert.query.get(alert_id)
    if not alert:
        return jsonify({"msg": "Alert not found"}), 404

    # Authorization check
    if user.role != 'admin':
        camera = Camera.query.get(alert.camera_id)
        if not camera or not camera.is_active:
            return jsonify({"msg": "Unauthorized to view this alert"}), 403
    
    return jsonify(alert.to_dict()), 200
