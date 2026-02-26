import datetime
import cv2
import numpy as np

# --- THREAT ENGINE ---
class ThreatEngine:
    """
    3-Factor Contextual Threat Engine:
    ThreatScore = BaseBehaviorScore x ContextMultiplier x NoveltyFactor
    """
    
    # Factor 1: BaseBehaviorScore
    BEHAVIOR_SCORES = {
        "normal": 0.1,
        "loitering": 0.4,
        "pacing": 0.5,
        "running": 0.6,
        "sudden-direction-change": 0.7,
        "crowd-formation": 0.75,
        "bag_drop": 0.95,
        "buffering": 0.0
    }

    @staticmethod
    def get_base_score(behavior):
        return ThreatEngine.BEHAVIOR_SCORES.get(behavior.lower(), 0.1)

    @staticmethod
    def get_context_multiplier(camera, behavior):
        """
        Factor 2: ContextMultiplier (rule-based)
        Inputs: camera.zone, current_time
        """
        now = datetime.datetime.now()
        is_night = now.hour >= 22 or now.hour < 6
        
        zone = camera.zone.lower() if camera and camera.zone else "general"
        multiplier = 1.0

        # Zone-specific rules
        if zone == "gym" or zone == "park":
            if behavior == "running": multiplier = 0.2
            elif behavior == "loitering": multiplier = 0.3
            elif behavior == "crowd-formation": multiplier = 0.5
        
        elif zone == "entry" or zone == "gate":
            if behavior == "running": multiplier = 2.5
            elif behavior == "loitering": multiplier = 2.0
            elif behavior == "bag_drop": multiplier = 3.0
            elif behavior == "crowd-formation": multiplier = 1.5
            
        elif zone == "market":
            if behavior == "loitering": multiplier = 1.2
            elif behavior == "crowd-formation": multiplier = 2.0
            elif behavior == "bag_drop": multiplier = 1.8

        # Night multiplier (apply if not already reduced by zone rules)
        if is_night and multiplier >= 1.0:
            multiplier *= 2.0
            
        return multiplier

    @staticmethod
    def get_novelty_factor(camera_id, behavior):
        """
        Factor 3: NoveltyFactor (baseline learning)
        """
        return 1.0

    @staticmethod
    def calculate(camera, behavior):
        # Local import to avoid circular dependency
        from .users.models import SystemSetting
        
        # Check if Learning Mode is ON
        learning_mode = False
        try:
            setting = SystemSetting.query.filter_by(key="learning_mode").first()
            if setting:
                learning_mode = (setting.value.lower() == "true")
        except:
            pass

        base = ThreatEngine.get_base_score(behavior)
        context = ThreatEngine.get_context_multiplier(camera, behavior)
        novelty = ThreatEngine.get_novelty_factor(camera.id if camera else None, behavior)
        
        # Final Score Calculation
        final_score = base * context * novelty * 100
        
        # If Learning Mode is ON, cap the score unless it's critical
        if learning_mode and final_score < 90:
            final_score *= 0.5

        # Ensure 0-100 range
        final_score = min(100.0, max(0.0, final_score))
        
        # Threat Level Buckets
        level = "NORMAL"
        if final_score > 95: level = "CRITICAL"
        elif final_score > 80: level = "HIGH"
        elif final_score > 60: level = "MEDIUM"
        elif final_score > 30: level = "LOW"
        
        return {
            "score": int(final_score),
            "level": level,
            "base": base,
            "context": context,
            "novelty": novelty
        }

# --- PREPROCESSING UTILS ---
def blur_faces(frame):
    """Placeholder for face blurring."""
    return frame

def preprocess_frame(frame):
    """
    Preprocesses a single frame for AI inference.
    """
    if frame is None:
        return None

    # Resize (e.g., to 224x224 for many vision models)
    target_size = (224, 224)
    resized_frame = cv2.resize(frame, target_size, interpolation=cv2.INTER_AREA)

    # Convert BGR to RGB (OpenCV reads as BGR by default)
    rgb_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)

    # Normalize to 0-1 range
    normalized_frame = rgb_frame.astype(np.float32) / 255.0

    # Apply face blurring
    blurred_frame = blur_faces(normalized_frame)

    # Add batch dimension
    preprocessed_frame = np.expand_dims(blurred_frame, axis=0)

    return preprocessed_frame
