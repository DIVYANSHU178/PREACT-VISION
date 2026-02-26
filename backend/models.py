import torch
import torch.nn as nn
from torchvision.models import swin_t, Swin_T_Weights
from torchvision import transforms

# --- CONSTANTS ---
CLASSES = [
    "bag_drop",
    "crowd-formation",
    "loitering",
    "normal",
    "pacing",
    "running",
    "sudden-direction-change",
]

# Image transforms (ImageNet normalization)
IMG_TF = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

# --- MODEL ARCHITECTURE ---
class SwinTemporalNet(nn.Module):
    def __init__(self, num_classes: int, window_len: int = 16):
        """
        num_classes: number of behaviors to classify.
        window_len: number of frames per video window.
        """
        super().__init__()
        # Swin-Tiny backbone (features)
        weights = Swin_T_Weights.IMAGENET1K_V1
        backbone = swin_t(weights=weights)
        self.feature_extractor = backbone.features
        self.norm = backbone.norm
        self.window_len = window_len
        embed_dim = 768  # swin_t output dim (after norm)

        # Temporal Transformer Encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=embed_dim,
            nhead=12,
            dim_feedforward=3072,
            batch_first=True,
        )
        self.temporal_encoder = nn.TransformerEncoder(
            encoder_layer,
            num_layers=6,
        )
        
        # Behavior Classification Head
        self.cls_head = nn.Linear(embed_dim, num_classes)

    def encode_frame(self, x):  # x: (B*T, 3, 224, 224)
        """Pass through Swin-Tiny to get spatial features."""
        f = self.feature_extractor(x)      # Output: (B*T, 7, 7, 768)
        # Global average pooling (over H and W) + norm
        f = self.norm(f.mean([1, 2]))      # (B*T, 768)
        return f

    def forward(self, x):  # x: (B, T, C, H, W)
        """Input is a batch of video windows."""
        B, T, C, H, W = x.shape
        # Flatten batch and time dimensions for backbone
        x = x.view(B * T, C, H, W)
        feats = self.encode_frame(x)       # (B*T, 768)
        
        # Reshape back to (B, T, 768)
        feats = feats.view(B, T, -1)       # (B, T, 768)
        
        # Temporal attention
        t_out = self.temporal_encoder(feats)  # (B, T, 768)
        
        # Pool across time (taking last timestep)
        pooled = t_out[:, -1]              # (B, 768)
        
        # Classification
        logits = self.cls_head(pooled)     # (B, num_classes)
        return logits
