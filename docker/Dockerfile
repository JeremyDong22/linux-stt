# Linux STT - Docker Testing Environment
# Version: 1.0
# Description: Provides a Linux environment to test SenseVoice STT with web interface
#
# Build: docker build -t linux-stt .
# Run:   docker run -p 8080:8080 linux-stt

FROM python:3.11-slim-bookworm

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies with retry for transient network errors
RUN apt-get update && \
    for i in 1 2 3; do \
        apt-get install -y --no-install-recommends \
            libportaudio2 \
            libsndfile1 \
            ffmpeg \
        && break || sleep 5; \
    done && \
    rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements first for caching
COPY docker/requirements-docker.txt /app/requirements.txt

# Install Python dependencies
# Using CPU-only PyTorch to keep image smaller
RUN pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/linux_stt /app/linux_stt
COPY web /app/web

# Expose web interface port
EXPOSE 8080

# Set working directory for web app
WORKDIR /app/web

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run web server
CMD ["python", "app.py"]
