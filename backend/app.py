from flask import Flask, jsonify, session, request
from flask_cors import CORS
import os
from dotenv import load_dotenv
from flask_jwt_extended import JWTManager

# Load environment variables from .env file
load_dotenv()

from .database.db import db
from .config import Config
from .users.models import User
from .auth.utils import hash_password
from .cameras.models import Camera # Import Camera model
from .alerts.models import Alert # Import Alert model
from .websocket.socket import sio_manager # Import WebSocketManager
from .camera_manager import CameraManager # Import CameraManager

def create_app():
    app = Flask(__name__)
    app.url_map.strict_slashes = False
    jwt = JWTManager(app)


    # ---------------- CONFIG ----------------
    app.config.from_object(Config)

    # Ensure SECRET_KEY is set for sessions
    if not app.config['SECRET_KEY']:
        raise ValueError("SECRET_KEY is not set. Please set it in your .env file or config.")
    app.secret_key = app.config['SECRET_KEY']

    # ---------------- INIT ----------------
    # Remove supports_credentials=True as we use Bearer tokens in headers, 
    # and it cannot be used with wildcard origins.
    CORS(app, resources={r"/api/*": {
        "origins": [
            "http://127.0.0.1:5500", 
            "http://localhost:5500", 
            "http://127.0.0.1:5501", 
            "http://localhost:5501", 
            "http://127.0.0.1:5502", 
            "http://localhost:5502", 
            "http://127.0.0.1:5000"
        ],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }})

    @app.before_request
    def log_request_info():
        if request.path.startswith('/api/'):
            print(f"DEBUG: {request.method} {request.path}")
            print(f"DEBUG Headers: {dict(request.headers)}")

    db.init_app(app)
    sio_manager.init_app(app) # Initialize WebSocketManager with the app

    # Import blueprints AFTER db initialization
    from .auth.routes import auth_bp
    from .cameras.routes import cameras_bp
    from .alerts.routes import alerts_bp
    from .users.routes import users_bp

    # ---------------- BLUEPRINTS ----------------
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(cameras_bp, url_prefix="/api/cameras") # Register cameras blueprint
    app.register_blueprint(alerts_bp, url_prefix="/api/alerts") # Register alerts blueprint
    app.register_blueprint(users_bp, url_prefix="/api/users") # Register users blueprint

    # ---------------- SETTINGS ----------------
    from .users.models import SystemSetting

    @app.route("/api/settings/learning-mode", methods=["GET", "POST"])
    def toggle_learning_mode():
        if request.method == "POST":
            data = request.json or {}
            enabled = data.get("enabled", False)
            setting = SystemSetting.query.filter_by(key="learning_mode").first()
            if not setting:
                setting = SystemSetting(key="learning_mode", value=str(enabled).lower())
                db.session.add(setting)
            else:
                setting.value = str(enabled).lower()
            db.session.commit()
            return jsonify({"enabled": enabled}), 200
        else:
            setting = SystemSetting.query.filter_by(key="learning_mode").first()
            enabled = (setting.value.lower() == "true") if setting else False
            return jsonify({"enabled": enabled}), 200

    # ---------------- HEALTH CHECK ----------------
    @app.route("/")
    def health():
        return jsonify({"status": "PREACT backend running"}), 200

    # ---------------- CONTEXT PROCESSOR & SETUP ----------------
    with app.app_context():
        db.create_all()

        # --- ADMIN USER SETUP ---
        # This will run on app startup and create an admin if one doesn't exist
        admin_email = os.environ.get("ADMIN_EMAIL")
        admin_password = os.environ.get("ADMIN_PASSWORD")

        if admin_email and admin_password:
            existing_admin = User.query.filter_by(email=admin_email).first()
            if not existing_admin:
                print(f"Creating default admin user: {admin_email}")
                new_admin = User(
                    fullname="Default Admin",
                    email=admin_email,
                    organization="PREACT VISION",
                    password_hash=hash_password(admin_password),
                    role="admin",
                    is_approved=True
                )
                db.session.add(new_admin)
                db.session.commit()
                print("Default admin user created successfully.")
            else:
                print(f"Admin user '{admin_email}' already exists.")
        else:
            print("ADMIN_EMAIL or ADMIN_PASSWORD not set in .env file. Skipping default admin creation.")

        # --- DEFAULT CAMERAS SETUP ---
        # Pre-populates the database with 3 virtual cameras for OBS
        default_cameras = [
            {"name": "Virtual Camera 1", "stream_url": "0"},
            {"name": "Virtual Camera 2", "stream_url": "1"},
            {"name": "Virtual Camera 3", "stream_url": "2"},
        ]
        
        for cam_info in default_cameras:
            existing_camera = Camera.query.filter_by(name=cam_info["name"]).first()
            if not existing_camera:
                print(f"Creating default camera: {cam_info['name']}")
                new_camera = Camera(
                    name=cam_info["name"],
                    stream_url=cam_info["stream_url"],
                    is_active=True,
                    status="disconnected"
                )
                db.session.add(new_camera)
            else:
                print(f"Default camera '{cam_info['name']}' already exists.")
        db.session.commit()
        
        # --- CAMERA MANAGER SETUP ---
        # Initialize and start camera manager after db.create_all()
        # This ensures the Camera table exists before cameras are queried
        app.camera_manager = CameraManager(app, sio_manager)
        app.camera_manager.start_all_cameras()

    return app

if __name__ == "__main__":
    app = create_app()
    # use_reloader=False is critical on Windows to prevent threads starting twice
    # and locking the camera hardware in the parent process.
    sio_manager.socketio.run(app, debug=True, use_reloader=False, host="0.0.0.0", port=5000, allow_unsafe_werkzeug=True)
