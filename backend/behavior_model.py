import torch
import torch.nn as nn
import os
import numpy as np
from .models import SwinTemporalModel, CLASSES_5
from .ai_utils import preprocess_frames

class BehaviorModel:
    def __init__(self, model_dir="model"):
        """
        Loads the trained SwinTemporalModel for behavior recognition.
        """
        self.model_path = os.path.join(model_dir, "swin_temporal_best.pt")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.classes = CLASSES_5
        self.model = None
        self.use_fallback = False

        if not os.path.exists(self.model_path):
            print(f"ERROR: Model file not found at {self.model_path}. Fallback to mock mode.")
            self.use_fallback = True
        else:
            try:
                # Initialize model architecture
                self.model = SwinTemporalModel(num_classes=len(self.classes))
                
                # Load weights with CPU fallback support
                state_dict = torch.load(self.model_path, map_location=self.device)
                self.model.load_state_dict(state_dict)
                
                self.model.to(self.device)
                self.model.eval()
                print(f"SUCCESS: Behavior model loaded on {self.device}")
            except Exception as e:
                print(f"ERROR: Failed to load behavior model: {e}")
                self.use_fallback = True

    @torch.no_grad()
    def predict(self, frame_buffer):
        """
        Performs inference on a buffer of 16 frames.
        Returns: {"label": str, "confidence": float}
        """
        if self.use_fallback or self.model is None:
            return self._mock_predict()

        try:
            # Preprocess frames (16, 3, 224, 224)
            input_tensor = preprocess_frames(frame_buffer)
            
            # Add batch dimension (1, 16, 3, 224, 224)
            input_tensor = input_tensor.unsqueeze(0).to(self.device)
            
            # Inference
            logits = self.model(input_tensor)
            
            # Softmax to get probabilities
            probs = torch.softmax(logits, dim=1)[0]
            
            conf, pred_idx = torch.max(probs, dim=0)
            
            return {
                "label": self.classes[pred_idx.item()],
                "confidence": float(conf.item())
            }
        except Exception as e:
            print(f"ERROR: Inference failed: {e}")
            return self._mock_predict()

    def _mock_predict(self):
        """Graceful fallback for development/error states."""
        return {
            "label": "normal",
            "confidence": 0.95
        }

    @torch.no_grad()
    def predict_window(self, frame_buffer):
        """
        Legacy compatibility wrapper for existing camera_manager logic.
        """
        res = self.predict(frame_buffer)
        # Convert to expected legacy format if necessary
        return {
            "behavior": res["label"],
            "probs": {res["label"]: res["confidence"]} # Minimal probs for compatibility
        }
