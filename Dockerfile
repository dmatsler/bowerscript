FROM python:3.12-slim

# ffmpeg is required for audio extraction + chunking.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Deno: yt-dlp uses it (auto-detected on PATH) to solve YouTube's JS
# challenges. Without a JS runtime, format URLs stay locked and downloads
# fail with "Requested format is not available".
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

WORKDIR /app

# Build-time install is the *floor* — entrypoint.sh refreshes yt-dlp to the
# latest nightly on every container start.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY frontend ./frontend
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Persistent data (sqlite + saved .md) lives here. Compose mounts a host
# directory at this path so the library survives restarts and rebuilds —
# see deploy/docker-compose.example.yml.
ENV DATA_DIR=/data
RUN mkdir -p /data

# Set to 0 to skip the startup yt-dlp refresh (e.g. local dev, offline).
ENV YTDLP_AUTO_UPDATE=1

EXPOSE 8000

# entrypoint.sh binds $PORT, defaulting to 8000.
CMD ["./entrypoint.sh"]
