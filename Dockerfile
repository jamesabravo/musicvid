# Base container with Python, FFmpeg, and headless Blender
FROM python:3.11-slim

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install FFmpeg, fonts, Blender, and system runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    blender \
    fonts-noto-mono \
    fonts-dejavu-core \
    libgl1 \
    libx11-6 \
    libxi6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source
COPY . .

# Set up volume for audio/midi inputs and video outputs
VOLUME ["/data"]

ENTRYPOINT ["python", "/app/musicvid"]
CMD ["--help"]

