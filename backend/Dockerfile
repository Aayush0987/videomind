# VideoMind backend image (§21.1). Base dependency group only — no torch, no
# sentence-transformers. The GeminiEmbedder is pure HTTP, so the default path
# never needs a local ML stack, which keeps the image inside free-tier limits.
FROM python:3.11-slim

# ffmpeg is required by yt-dlp / faster-whisper for audio handling (§21.1).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the dependency manifest first so `pip install` is cached across code
# changes (layer caching, §21.1).
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Now the application (and any locally-seeded demo cache under data/seed).
COPY . .

# Data lives on a mounted volume in production; DATA_DIR points at it (§21.1).
ENV DATA_DIR=/data
ENV ENABLE_WHISPER=false

# Run as a non-root user (§21.1). It owns /data so first-boot seeding can write.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

# On first boot, if the volume has no database yet but the image carries a
# seeded demo cache, copy it into DATA_DIR so the deployed demo always has
# three working videos (§21.3). Then honour $PORT (Render injects it).
CMD ["sh", "-c", "if [ ! -f \"$DATA_DIR/videomind.sqlite3\" ] && [ -d /app/data/seed ]; then mkdir -p \"$DATA_DIR\" && cp -a /app/data/seed/. \"$DATA_DIR\"/; fi; exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
