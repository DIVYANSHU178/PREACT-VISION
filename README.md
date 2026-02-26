# PREACT VISION - Real-time Behavior Threat Analysis

PREACT VISION is an advanced CCTV monitoring system that uses Swin-Tiny and Temporal Transformer models to detect suspicious behaviors and calculate contextual threat scores.

## Project Structure
- `ai_engine/`: Core AI logic and legacy placeholder models.
- `backend/`: Flask-based API server with Camera Manager and WebSocket integration.
- `frontend/`: Interactive dashboards for Users and Admins.
- `training/`: Training package for the Swin-Temporal behavior model.
- `data/`: Dataset storage, snapshots, and alert history.
- `model/`: Trained model weights and configuration.

## Setup Instructions

### 1. Training the Model
To train the behavior recognition model:
1. Ensure your dataset is placed at `data/dataset/train` and `data/dataset/val`.
2. The dataset should have subfolders for each class: `bag_drop`, `crowd-formation`, `loitering`, `normal`, `pacing`, `running`, `sudden-direction-change`.
3. Each class folder should contain sequence folders (`seq_...`), each containing ordered frames (`0001.jpg`, etc.).
4. Run the training script:
   ```bash
   python -m training.train
   ```
   - **GPU Recommended**: Requires CUDA for efficient training (Swin backbone + Transformer).
   - **CPU**: Possible but will be very slow.
5. The best model will be saved at `model/swin_temporal_best.pt`.

### 2. Backend Setup
1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   pip install -r backend/requirements.txt
   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
   ```
2. Configure your `.env` file with `SECRET_KEY`, `ADMIN_EMAIL`, etc.
3. Start the backend:
   ```bash
   cd backend
   python app.py
   ```

### 3. Frontend Setup
Open `frontend/splash/index.html` in your browser (using a local server like Live Server) to access the system.

## How it Works
- **Model Architecture**: Uses a Swin-Tiny spatial backbone to extract frame features, followed by a 6-layer Temporal Transformer to analyze motion patterns over a 16-frame window.
- **Inference**: Handled by `backend/behavior_model.py`. If no trained weights are found in `model/`, it uses a fallback mock to keep the UI alive.
- **Threat Engine**: Combines behavior probabilities with contextual rules (zone, time) and novelty factors to produce a 0-100 threat score.

## API Endpoints
- `GET /api/cameras/live`: Returns real-time status for all cameras.
- `GET /api/alerts/recent`: Returns last N threat alerts.
- `GET /api/auth/admin/pending`: List pending access requests.
