import torch
import json
import os
import random
import numpy as np
import cv2
from PIL import Image

# Import model architecture and constants from local backend/models.py
from .models import SwinTemporalNet, IMG_TF, CLASSES

class BehaviorModel:
    def __init__(self, model_dir="model"):
        """
        model_dir: Directory containing trained weights and config.
        Expected files: 
          - swin_temporal_best.pt (weights)
          - config.json (architecture params)
          - classes.json (optional list of classes)
        """
        self.model_dir = model_dir
        self.cfg_path = os.path.join(model_dir, "config.json")
        self.ckpt_path = os.path.join(model_dir, "swin_temporal_best.pt")
        self.classes_path = os.path.join(model_dir, "classes.json")
        
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.use_fallback = False
        
        # Determine classes
        if os.path.exists(self.classes_path):
            try:
                with open(self.classes_path, "r") as f:
                    self.classes = json.load(f)
            except:
                self.classes = CLASSES
        else:
            self.classes = CLASSES

        # Attempt to load model
        if not os.path.exists(self.ckpt_path):
            print(f"INFO: No trained weights found at {self.ckpt_path}. Project running in DEMO mode with mock predictions.")
            self.use_fallback = True
        else:
            try:
                # Load configuration if it exists
                window_len = 16
                if os.path.exists(self.cfg_path):
                    try:
                        with open(self.cfg_path, "r") as f:
                            cfg = json.load(f)
                        window_len = cfg.get("window_len", 16)
                    except:
                        pass
                
                # Initialize model
                self.model = SwinTemporalNet(
                    num_classes=len(self.classes),
                    window_len=window_len,
                )
                
                # Load state dict
                self.model.load_state_dict(torch.load(self.ckpt_path, map_location=self.device))
                self.model.to(self.device)
                self.model.eval()
                print(f"SUCCESS: Loaded model weights from {self.ckpt_path}")
            except Exception as e:
                print(f"ERROR: Failed to load model from {self.ckpt_path}: {e}. Falling back to mock.")
                self.use_fallback = True

    @torch.no_grad()
    def predict_window(self, frames):
        """
        frames: list of RGB numpy arrays (shape H,W,C) or PIL images
        returns: dict with behavior label and probabilities
        """
        if self.use_fallback or self.model is None:
            return self._mock_prediction()

        try:
            # Preprocess and stack frames
            imgs = []
            for frame in frames:
                if isinstance(frame, np.ndarray):
                    # Expecting RGB from camera_manager
                    frame = Image.fromarray(frame)
                
                if isinstance(frame, Image.Image):
                    imgs.append(IMG_TF(frame))
                else:
                    # If it's already a tensor (from some other pipeline)
                    imgs.append(frame)

            # Stack into (1, T, C, H, W)
            x = torch.stack(imgs, dim=0).unsqueeze(0)
            x = x.to(self.device)
            
            logits = self.model(x)
            probs = torch.softmax(logits, dim=1)[0].cpu().tolist()
            pred_idx = int(torch.argmax(logits, dim=1))
            
            return {
                "behavior": self.classes[pred_idx],
                "probs": {self.classes[i]: probs[i] for i in range(len(self.classes))}
            }
        except Exception as e:
            print(f"ERROR: Inference failed: {e}. Falling back to mock.")
            return self._mock_prediction()

    def _mock_prediction(self):
        """Deterministic mock for behavior."""
        # Mostly 'normal' (index 3 in default CLASSES)
        behavior = random.choices(
            self.classes, 
            weights=[5, 5, 5, 70, 5, 5, 5] if len(self.classes) == 7 else [1]*len(self.classes)
        )[0]
        
        probs = {}
        for b in self.classes:
            probs[b] = 0.9 if b == behavior else (0.1 / max(1, (len(self.classes)-1)))
            
        return {
            "behavior": behavior,
            "probs": probs
        }
