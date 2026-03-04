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
    def __init__(self, app, camera_id, stream_url, ws_manager, WINDOW_SIZE=16, THREAT_THRESHOLD=80):
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
        self.alert_cooldown = 300 # 5 minutes cooldown
        self.is_processing = False
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
        
        try:
            url = int(self.stream_url)
            self.cap = cv2.VideoCapture(url, cv2.CAP_DSHOW)
        except ValueError:
            url = self.stream_url
            self.cap = cv2.VideoCapture(url)

        if not self.cap.isOpened():
            print(f"Error: Could not open video stream for Camera {self.camera_id}")
            self._update_camera_status("error")
            self.running = False
            return

        self._update_camera_status("streaming")
        
        frame_count = 0
        inference_interval = 25 # Process AI once per ~1 second

        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                self._update_camera_status("reconnecting")
                self.cap.release()
                time.sleep(2)
                self.cap = cv2.VideoCapture(url)
                if not self.cap.isOpened():
                    self._update_camera_status("disconnected")
                    self.running = False
                continue

            self.latest_frame = frame.copy()
            frame_count += 1

            # Buffer management
            resized_frame = cv2.resize(frame, (224, 224))
            self.frame_buffer.append(resized_frame)

            # Non-blocking inference
            if frame_count % inference_interval == 0 and not self.is_processing:
                if len(self.frame_buffer) == self.WINDOW_SIZE:
                    frames_copy = list(self.frame_buffer)
                    threading.Thread(target=self._run_inference_task, args=(frames_copy, frame.copy())).start()
                else:
                    self._broadcast_camera_status_update({"score": 0, "level": "NORMAL"}, "buffering", self.camera_id)

            time.sleep(0.001)

        self._cleanup()

    def _run_inference_task(self, frames, original_frame):
        """AI Inference in a separate thread to prevent capture lag."""
        self.is_processing = True
        try:
            with self.app.app_context():
                camera = Camera.query.get(self.camera_id)
                if not camera: return

                prediction = self.behavior_model.predict(frames)
                behavior = prediction["label"]
                confidence = prediction["confidence"]
                
                base_scores = {
                    "normal": 5, "loitering": 40, "pacing": 55, "running": 70, "sudden-direction-change": 80
                }
                base_score = base_scores.get(behavior, 5)
                threat_score = int(base_score * confidence)
                
                res = {
                    "score": threat_score, "level": "NORMAL", "base": base_score/100, "context": 1.0, "novelty": 1.0
                }
                if threat_score > 80: res["level"] = "HIGH"
                elif threat_score > 60: res["level"] = "MEDIUM"
                elif threat_score > 30: res["level"] = "LOW"

                # Suspicious filter
                if behavior.lower() != "normal" and threat_score >= self.THREAT_THRESHOLD:
                    if (time.time() - self.last_alert_time > self.alert_cooldown):
                        self._handle_alert(original_frame, behavior, res)
                        self.last_alert_time = time.time()
                
                self._broadcast_camera_status_update(res, behavior, self.camera_id)
        except Exception as e:
            print(f"DEBUG Inference Error: {e}")
        finally:
            self.is_processing = False

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
                self.ws_manager.broadcast({
                    "type": "camera_status_update", "camera_id": self.camera_id, "status": status
                })

    def _handle_alert(self, frame, behavior, res):
        print(f"ALERT! Camera {self.camera_id}: {behavior} (Score: {res['score']})")
        snapshot_path = self._save_snapshot(frame)
        self._store_alert_in_db(behavior, res, snapshot_path)
        self._broadcast_alert(behavior, res, snapshot_path)

    def _save_snapshot(self, frame):
        with self.app.app_context():
            snapshots_dir = os.path.join(current_app.root_path, '..', 'data', 'snapshots')
            os.makedirs(snapshots_dir, exist_ok=True)
            filename = f"camera_{self.camera_id}_alert_{int(time.time())}.jpg"
            filepath = os.path.join(snapshots_dir, filename)
            cv2.imwrite(filepath, frame)
            return f"data/snapshots/{filename}"

    def _store_alert_in_db(self, behavior, res, snapshot_path):
        with self.app.app_context():
            new_alert = Alert(
                camera_id=self.camera_id, behavior=behavior, threat_score=res["score"],
                threat_level=res["level"], base_score=res["base"], context_multiplier=1.0,
                novelty_factor=1.0, snapshot_path=snapshot_path
            )
            db.session.add(new_alert)
            db.session.commit()

    def _broadcast_alert(self, behavior, res, snapshot_path):
        self.ws_manager.broadcast({
            "type": "new_alert", "camera_id": self.camera_id, "behavior": behavior,
            "threat_score": res["score"], "threat_level": res["level"],
            "timestamp": datetime.utcnow().isoformat(), "snapshot_path": snapshot_path
        })

    def _broadcast_camera_status_update(self, res, behavior, camera_id):
        self.latest_status = {
            "behavior": behavior, "threat_score": res["score"],
            "threat_level": res["level"], "updated_at": datetime.utcnow().isoformat()
        }
        self.ws_manager.broadcast({
            "type": "camera_live_update", "camera_id": camera_id,
            "threat_score": res["score"], "threat_level": res["level"],
            "behavior": behavior, "timestamp": datetime.utcnow().isoformat()
        })

class CameraManager:
    def __init__(self, app, ws_manager):
        self.app = app
        self.camera_workers = {}
        self.ws_manager = ws_manager
        print("CameraManager initialized.")

    def start_camera(self, camera_id):
        if camera_id in self.camera_workers and self.camera_workers[camera_id].is_alive():
            return
        with self.app.app_context():
            camera = Camera.query.get(camera_id)
            if not camera: return
            worker = CameraWorker(app=self.app, camera_id=camera.id, stream_url=camera.stream_url, ws_manager=self.ws_manager)
            self.camera_workers[camera_id] = worker
            worker.start()

    def stop_camera(self, camera_id):
        if camera_id in self.camera_workers:
            self.camera_workers[camera_id].stop()
            self.camera_workers[camera_id].join()
            del self.camera_workers[camera_id]

    def start_all_cameras(self):
        with self.app.app_context():
            active_cameras = Camera.query.filter_by(is_active=True).all()
            for camera in active_cameras:
                self.start_camera(camera.id)

    def stop_all_cameras(self):
        for camera_id in list(self.camera_workers.keys()):
            self.stop_camera(camera_id)

    def get_latest_frame(self, camera_id):
        if camera_id in self.camera_workers:
            return self.camera_workers[camera_id].latest_frame
        return None

    def get_all_camera_statuses(self):
        statuses = {}
        for cam_id, worker in self.camera_workers.items():
            statuses[cam_id] = worker.latest_status
        return statuses
