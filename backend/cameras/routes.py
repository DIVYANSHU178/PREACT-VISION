from flask import Blueprint, jsonify, request, Response, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
import cv2
import numpy as np
from functools import wraps
from ..database.db import db
from .models import Camera
from ..users.models import User 
from ..auth.routes import login_required

cameras_bp = Blueprint('cameras', __name__)

# Helper to check user role (assuming 'admin' role has full access)
def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        identity = get_jwt_identity()
        user = User.query.filter_by(id=identity).first()
        if user and user.role == 'admin':
            return fn(*args, **kwargs)
        else:
            return jsonify({"msg": "Admin access required"}), 403
    return wrapper

def generate_frames(app, camera_id):
    # Use the app object directly to avoid context issues in the generator loop
    while True:
        if not hasattr(app, 'camera_manager'):
            import time
            time.sleep(0.5)
            continue
            
        frame = app.camera_manager.get_latest_frame(camera_id)
        
        # If no frame is available, generate a "Connecting..." placeholder
        if frame is None:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "Connecting to Camera...", (150, 240), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        try:
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                import time
                time.sleep(0.1)
                continue
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        except Exception as e:
            print(f"Error encoding frame for camera {camera_id}: {e}")
        
        import time
        time.sleep(0.04) # Limit to ~25 FPS

@cameras_bp.route('/stream/<int:camera_id>')
def video_feed(camera_id):
    # Pass the actual application object to the generator
    return Response(generate_frames(current_app._get_current_object(), camera_id),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@cameras_bp.route('', methods=['GET'])
@login_required()
def get_all_cameras():
    # Only approved users can view cameras. Admins can view all, regular users only their assigned/active ones.
    identity = get_jwt_identity()
    user = User.query.filter_by(id=identity).first()

    if not user or not user.is_approved:
        return jsonify({"msg": "Unauthorized access"}), 401

    if user.role == 'admin':
        cameras = Camera.query.all()
    else:
        cameras = Camera.query.filter_by(is_active=True).all()

    return jsonify([camera.to_dict() for camera in cameras]), 200

@cameras_bp.route('/live', methods=['GET'])
@login_required()
def get_live_cameras():
    """Returns real-time behavior/threat status for all cameras."""
    identity = get_jwt_identity()
    user = User.query.filter_by(id=identity).first()

    if not user or not user.is_approved:
        return jsonify({"msg": "Unauthorized access"}), 401

    if user.role == 'admin':
        cameras = Camera.query.all()
    else:
        cameras = Camera.query.filter_by(is_active=True).all()

    # Get live statuses from camera manager
    cm_statuses = {}
    if hasattr(current_app, 'camera_manager'):
        cm_statuses = current_app.camera_manager.get_all_camera_statuses()

    results = []
    for cam in cameras:
        status_info = cm_statuses.get(cam.id, {
            "behavior": "unknown",
            "threat_score": 0,
            "threat_level": "NORMAL",
            "updated_at": None
        })
        
        cam_data = cam.to_dict()
        cam_data.update(status_info)
        results.append(cam_data)

    return jsonify(results), 200

@cameras_bp.route('/<int:camera_id>', methods=['GET'])
@jwt_required()
def get_camera(camera_id):
    identity = get_jwt_identity()
    user = User.query.filter_by(id=identity).first()

    if not user or not user.is_approved:
        return jsonify({"msg": "Unauthorized access"}), 401

    camera = Camera.query.get(camera_id)
    if not camera:
        return jsonify({"msg": "Camera not found"}), 404

    # Authorization check: Admin can see any camera, regular user can only see active ones
    if user.role != 'admin' and not camera.is_active:
        return jsonify({"msg": "Unauthorized to view this camera"}), 403
    
    return jsonify(camera.to_dict()), 200

# Endpoint to add a new camera (Admin only)
@cameras_bp.route('', methods=['POST'])
@jwt_required()
@admin_required # Custom decorator for role-based access
def add_camera():
    data = request.get_json()
    name = data.get('name')
    stream_url = data.get('stream_url')

    if not name or not stream_url:
        return jsonify({"msg": "Missing camera name or stream URL"}), 400

    new_camera = Camera(name=name, stream_url=stream_url)
    db.session.add(new_camera)
    db.session.commit()

    # Optional: Start the newly added camera immediately
    # if 'camera_manager' in globals():
    #     global camera_manager
    #     camera_manager.start_camera(new_camera.id)

    return jsonify(new_camera.to_dict()), 201

# Endpoint to update camera details (Admin only)
@cameras_bp.route('/<int:camera_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_camera(camera_id):
    camera = Camera.query.get(camera_id)
    if not camera:
        return jsonify({"msg": "Camera not found"}), 404

    data = request.get_json()
    camera.name = data.get('name', camera.name)
    camera.stream_url = data.get('stream_url', camera.stream_url)
    camera.is_active = data.get('is_active', camera.is_active)
    db.session.commit()

    # Manage worker thread if URL or active status changes
    if hasattr(current_app, 'camera_manager'):
        cm = current_app.camera_manager
        # If active, stop and restart to apply changes (like new URL)
        if camera.is_active:
            cm.stop_camera(camera_id)
            cm.start_camera(camera_id)
        else:
            cm.stop_camera(camera_id)

    return jsonify(camera.to_dict()), 200

# Endpoint to delete a camera (Admin only)
@cameras_bp.route('/<int:camera_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_camera(camera_id):
    camera = Camera.query.get(camera_id)
    if not camera:
        return jsonify({"msg": "Camera not found"}), 404

    # Ensure to stop the camera worker if it's running
    if hasattr(current_app, 'camera_manager'):
        current_app.camera_manager.stop_camera(camera_id)

    db.session.delete(camera)
    db.session.commit()
    return jsonify({"msg": "Camera deleted"}), 200

from functools import wraps # Import wraps for decorator
