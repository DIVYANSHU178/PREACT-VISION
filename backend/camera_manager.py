import threading
import time
import cv2
import numpy as np
from collections import deque
import os
from datetime import datetime

from flask import current_app
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

# Import database and models
from .database.db import db
from .cameras.models import Camera
from .alerts.models import Alert

# Import AI engine components
from .ai_utils import preprocess_frame, ThreatEngine
from .behavior_model import BehaviorModel

# Import WebSocket manager
from .websocket.socket import sio_manager

class CameraWorker(threading.Thread):
    def __init__(self, app, camera_id, stream_url, ws_manager, WINDOW_SIZE=16, THREAT_THRESHOLD=60):
        super().__init__()
        self.app = app
        self.camera_id = camera_id
        self.stream_url = stream_url
        self.ws_manager = ws_manager
        self.WINDOW_SIZE = WINDOW_SIZE
        self.THREAT_THRESHOLD = THREAT_THRESHOLD

        self.running = False
        self.cap = None
        self.latest_frame = None
        self.frame_buffer = deque(maxlen=self.WINDOW_SIZE)
        self.behavior_model = self._load_ai_model()
        self.last_alert_time = 0
        self.alert_cooldown = 300 # 5 minutes cooldown per camera/event
        self.latest_status = {
            "behavior": "initializing",
            "threat_score": 0,
            "threat_level": "NORMAL",
            "updated_at": datetime.utcnow().isoformat()
        }

        print(f"CameraWorker for Camera {self.camera_id} ({self.stream_url}) initialized.")

    def _load_ai_model(self):
        """Load behavior model once for this worker."""
        return BehaviorModel(model_dir="model")

    def run(self):
        print(f"Starting CameraWorker for Camera {self.camera_id}...")
        self.running = True
        
        # Handle cases where stream_url might be an integer (for local webcams/OBS Virtual Cam)
        try:
            url = int(self.stream_url)
            # On Windows, CAP_DSHOW is often more reliable for local cameras
            self.cap = cv2.VideoCapture(url, cv2.CAP_DSHOW)
        except ValueError:
            url = self.stream_url
            self.cap = cv2.VideoCapture(url)

        if not self.cap.isOpened():
            print(f"Error: Could not open video stream for Camera {self.camera_id} at {self.stream_url}")
            self._update_camera_status("error")
            self.running = False
            return

        self._update_camera_status("streaming")
        
        frame_count = 0
        # In this updated version, we can reduce inference frequency to every 4 frames 
        # to prevent overloading but maintain the sliding window.
        inference_interval = 4 

        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                print(f"Warning: Could not read frame from Camera {self.camera_id}. Reattempting connection...")
                self._update_camera_status("reconnecting")
                self.cap.release()
                time.sleep(2) # Wait before trying to reconnect
                self.cap = cv2.VideoCapture(url)
                if not self.cap.isOpened():
                    print(f"Error: Reconnection failed for Camera {self.camera_id}.")
                    self._update_camera_status("disconnected")
                    self.running = False
                continue

            self.latest_frame = frame.copy()
            frame_count += 1

            # Store the frame for the sliding window
            # We use resized frames to save memory in the buffer
            resized_frame = cv2.resize(frame, (224, 224))
            # Convert BGR to RGB
            resized_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
            self.frame_buffer.append(resized_frame)

            if frame_count % inference_interval == 0:
                # Perform temporal inference if buffer is full
                if len(self.frame_buffer) == self.WINDOW_SIZE:
                    with self.app.app_context():
                        camera = Camera.query.get(self.camera_id)
                        
                        # Use new BehaviorModel to predict
                        result = self.behavior_model.predict_window(list(self.frame_buffer))
                        behavior = result["behavior"]
                        probs = result.get("probs", {})
                        
                        # Use ThreatEngine
                        res = ThreatEngine.calculate(camera, behavior)
                        threat_score = res["score"]
                        threat_level = res["level"]

                        # Trigger alert if high threat and not on cooldown
                        if threat_score >= self.THREAT_THRESHOLD and (time.time() - self.last_alert_time > self.alert_cooldown):
                            self._handle_alert(frame, behavior, res)
                            self.last_alert_time = time.time()
                        
                        # Broadcast live camera status update
                        self._broadcast_camera_status_update(res, behavior, self.camera_id)
                else:
                    self._broadcast_camera_status_update({"score": 0, "level": "NORMAL"}, "buffering", self.camera_id)

            # Small sleep to prevent busy-waiting and allow other threads to run
            time.sleep(0.01)

        self._cleanup()
        print(f"CameraWorker for Camera {self.camera_id} stopped.")

    def stop(self):
        self.running = False

    def _cleanup(self):
        if self.cap:
            self.cap.release()
        self._update_camera_status("disconnected")

    def _update_camera_status(self, status):
        with self.app.app_context():
            camera = Camera.query.get(self.camera_id)
            if camera:
                camera.status = status
                db.session.commit()
                # Broadcast status change to frontend
                message = {
                    "type": "camera_status_update",
                    "camera_id": self.camera_id,
                    "status": status,
                }
                self.ws_manager.broadcast(message)

    def _handle_alert(self, frame, behavior, res):
        print(f"ALERT! Camera {self.camera_id}: {behavior} (Score: {res['score']}, Level: {res['level']})")
        snapshot_path = self._save_snapshot(frame)
        self._store_alert_in_db(behavior, res, snapshot_path)
        self._broadcast_alert(behavior, res, snapshot_path)

    def _save_snapshot(self, frame):
        with self.app.app_context():
            # Ensure the snapshots directory exists
            snapshots_dir = os.path.join(current_app.root_path, '..', 'data', 'snapshots')
            os.makedirs(snapshots_dir, exist_ok=True)
            
            timestamp = int(time.time())
            filename = f"camera_{self.camera_id}_alert_{timestamp}.jpg"
            filepath = os.path.join(snapshots_dir, filename)
            
            try:
                # Save the frame. 'frame' is still the original BGR frame here.
                cv2.imwrite(filepath, frame)
                print(f"Snapshot saved to {filepath}")
                return f"data/snapshots/{filename}" # Return relative path for frontend
            except Exception as e:
                print(f"Error saving snapshot for camera {self.camera_id}: {e}")
                return None

    def _store_alert_in_db(self, behavior, res, snapshot_path):
        with self.app.app_context():
            new_alert = Alert(
                camera_id=self.camera_id,
                behavior=behavior,
                threat_score=res["score"],
                threat_level=res["level"],
                base_score=res["base"],
                context_multiplier=res["context"],
                novelty_factor=res["novelty"],
                snapshot_path=snapshot_path
            )
            db.session.add(new_alert)
            db.session.commit()
            print(f"Alert stored in DB for Camera {self.camera_id}.")

    def _broadcast_alert(self, behavior, res, snapshot_path):
        message = {
            "type": "new_alert",
            "camera_id": self.camera_id,
            "behavior": behavior,
            "threat_score": res["score"],
            "threat_level": res["level"],
            "timestamp": datetime.utcnow().isoformat(), # Use current UTC time for broadcast
            "snapshot_path": snapshot_path,
        }
        self.ws_manager.broadcast(message)
        print(f"Alert broadcasted for Camera {self.camera_id}.")

    def _broadcast_camera_status_update(self, res, behavior, camera_id):
        # Update in-memory state
        self.latest_status = {
            "behavior": behavior,
            "threat_score": res.get("score", 0),
            "threat_level": res.get("level", "NORMAL"),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # This will send continuous updates to the dashboard
        message = {
            "type": "camera_live_update",
            "camera_id": camera_id,
            "threat_score": res.get("score", 0),
            "threat_level": res.get("level", "NORMAL"),
            "behavior": behavior,
            "base_score": res.get("base", 0.1),
            "context_multiplier": res.get("context", 1.0),
            "novelty_factor": res.get("novelty", 1.0),
            "timestamp": datetime.utcnow().isoformat()
        }
        self.ws_manager.broadcast(message)

class CameraManager:
    def __init__(self, app, ws_manager):
        self.app = app
        self.app_context = app.app_context() # Store app_context for worker threads
        self.camera_workers = {}
        self.ws_manager = ws_manager
        self.engine = create_engine(self.app.config['SQLALCHEMY_DATABASE_URI'])
        self.Session = sessionmaker(bind=self.engine)
        print("CameraManager initialized.")

    def start_camera(self, camera_id):
        if camera_id in self.camera_workers and self.camera_workers[camera_id].is_alive():
            print(f"Camera {camera_id} is already running.")
            return

        with self.app_context:
            with current_app.app_context():
                camera = Camera.query.get(camera_id)
                if not camera:
                    print(f"Camera with ID {camera_id} not found.")
                    return

                print(f"Starting camera {camera.name} (ID: {camera.id}, URL: {camera.stream_url})...")
                worker = CameraWorker(
                    app=self.app, # Pass the app object
                    camera_id=camera.id,
                    stream_url=camera.stream_url,
                    ws_manager=self.ws_manager
                )
                self.camera_workers[camera_id] = worker
                worker.start()
                print(f"Camera {camera_id} worker thread started.")

    def stop_camera(self, camera_id):
        if camera_id in self.camera_workers:
            print(f"Stopping camera {camera_id}...")
            worker = self.camera_workers[camera_id]
            worker.stop()
            worker.join() # Wait for the thread to finish
            del self.camera_workers[camera_id]
            print(f"Camera {camera_id} worker thread stopped and removed.")
        else:
            print(f"Camera {camera_id} is not running.")

    def start_all_cameras(self):
        with self.app_context:
            with current_app.app_context():
                active_cameras = Camera.query.filter_by(is_active=True).all()
                if not active_cameras:
                    print("No active cameras found to start.")
                    return

                print(f"Starting {len(active_cameras)} active cameras...")
                for camera in active_cameras:
                    self.start_camera(camera.id)
                print("All active cameras started.")

    def stop_all_cameras(self):
        print("Stopping all cameras...")
        for camera_id in list(self.camera_workers.keys()):
            self.stop_camera(camera_id)
        print("All cameras stopped.")

    def get_latest_frame(self, camera_id):
        if camera_id in self.camera_workers:
            return self.camera_workers[camera_id].latest_frame
        return None

    def get_all_camera_statuses(self):
        """Returns in-memory behavior/threat data for all running cameras."""
        statuses = {}
        for cam_id, worker in self.camera_workers.items():
            statuses[cam_id] = worker.latest_status
        return statuses

