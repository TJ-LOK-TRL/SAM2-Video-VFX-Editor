# SAM2 job image: PyTorch + CUDA runtime for GPU inference
FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_NO_CACHE_DIR=1

# Install system deps needed by SAM2 and video processing
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy backend requirements (rely on same requirements file) and install
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Clone the SAM2 repository and install demo dependencies
RUN git clone https://github.com/facebookresearch/segment-anything-2.git /app/backend/segment-anything-2 \
    && cd /app/backend/segment-anything-2 \
    && pip install -e ".[demo]"

# Download SAM2 tiny checkpoint
RUN mkdir -p /app/backend/segment-anything-2/checkpoints \
    && curl -L -o /app/backend/segment-anything-2/checkpoints/sam2_hiera_tiny.pt \
       https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_tiny.pt

# Copy application code
COPY backend/ /app/backend/
COPY sam2-job/ /app/sam2_job/

# Expose nothing (runs as Job). Entrypoint runs the job script which reads env vars.
ENTRYPOINT ["python", "/app/sam2_job/run_job.py"]
