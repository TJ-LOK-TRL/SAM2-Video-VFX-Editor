# 🧠 Advanced AI Video Editor with SAM2

An advanced video editing suite powered by **Segment Anything 2 (SAM2)** for object segmentation and tracking. This tool allows for professional-grade VFX, object removal, and background manipulation using a **Vue.js** frontend and a **Flask (Python)** backend.

---

## 🌟 Key Features

### 🎬 Core Video Editing
* **Multi-Element Timeline**: Support for multiple video and text layers.
* **Transform Tools**: Drag, resize, and grab elements directly on the canvas. Includes rotation, "Fit to Canvas" mode, and Horizontal Flip (Y-axis mirroring).
* **Video Adjustments**: Control playback speed, start/end points, and volume (frontend).
* **Visual Enhancements**: Add rounded corners (border-radius) and Fade-in/Fade-out animations.
* **Layer Management**: Centralized list to filter and manage all video and text elements.

### 🎭 AI Object Segmentation & Masking
* **Interactive Selection**: Select objects by adding or removing points. The editor tracks these objects throughout the entire video.
* **VFX Masks**: Generate masks to apply localized effects that follow the object's movement.
* **Chroma Key**: Remove backgrounds via manual color selection or auto-picking from a specific pixel coordinate.
* **Transparency**: Full support for alpha channels and transparent backgrounds.

### 🧪 Object & Background Effects
Apply 8 unique effects to tracked objects or 6 effects to the background (everything except the masked objects).

| Effect | Description |
| :--- | :--- |
| **Original** | Resets the selection to its original state. |
| **Erase** | Removes the object. Uses background replacement or fills with black. |
| **Blend** | Applies textures from another video/image onto the object (perfect for clothing/surface textures). |
| **Color** | Advanced grading: Brightness, Contrast, Exposure, Hue, Saturation, Sharpen, Noise, Blur, and Vignette. Features a **Factor** slider to mix with original textures/shadows. |
| **Overlay** | Attaches a video/image that follows the object (can be placed in front or behind). |
| **Cut** | Makes the object area transparent, revealing the canvas or layers underneath. |
| **Split** | Extracts the object into a separate video with a transparent background. |
| **Label** | Attaches dynamic text labels that follow the object's movement. |

### ✍️ Text & UI
* **Typography**: Customizable fonts, fontSize, color, and X-axis alignment.
* **Styles**: Support for Bold and Italic (dependent on font compatibility).
* **Auth**: Integrated Login system for user management.

## 🧱 System Prerequisites

Before starting, make sure you have the following packages installed on your system:

```bash
sudo apt-get update
sudo apt-get install -y libgl1-mesa-glx
sudo apt-get install -y libglib2.0-0
sudo apt-get install -y ffmpeg
```

---

## 🚀 Installation Manual

### ✅ Prerequisites
- Python 3.10 or higher
- Node.js (v16+) and npm
- Git installed
- Recommended environment: Linux/macOS or WSL2 (to avoid dependency issues on Windows)

---

### 📥 Project Setup

1. **Clone the repository**:

# SAM2 Project

## Repository Cloning

```bash
git clone https://github.com/TJ-LOK-TRL/SAM2-Video-VFX-Editor.git
cd SAM2-Video-VFX-Editor
```

## Required Directory Structure

```plaintext
SAM2-Video-VFX-Editor/
├── backend/
│   ├── segment-anything-2/  # ← Must be added manually
│   ├── videos/
│   │   └── frames/
├── frontend/
```

## Preparar o SAM2

1. **Manually download Segment Anything 2**
2. **Extract to:** `backend/segment-anything-2`

---

## 🌐 Frontend (Vue.js)

```bash
cd frontend
npm install
npm run dev
```

---

## 🖥️ Backend (Flask + Python)

### Create folders and virtual environment:

```bash
cd backend
mkdir -p videos/frames
python -m venv venv
source venv/bin/activate  # Linux/macOS
# OU
venv\Scripts\activate     # Windows
```

### Install dependencies:

```bash
pip install -r requirements.txt
```

### Run Flask server:

```bash
python app.py
```

---

## 📝 requirements.txt File

```
flask==3.1.0
flask-cors==5.0.1
flask-sqlalchemy==3.1.1
opencv-python==4.11.0.86
numpy==2.2.4
torch==2.6.0
Pillow==11.2.0
supervision==0.25.1
matplotlib==3.10.1
dill==0.3.9
torch==2.6.0
torchvision==0.21.0
nvidia-cuda-runtime-cu12==12.4.127
nvidia-cudnn-cu12==9.1.0.70
triton==3.2.0
```

---

## ⚠️ Important Notes

### For GPU (CUDA):

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

- Make sure all dependencies have been installed correctly.
- Keep the exact folder structure as specified.
