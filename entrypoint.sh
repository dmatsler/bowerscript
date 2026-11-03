#!/bin/sh
# Container entrypoint: refresh yt-dlp to the newest nightly, then boot.
#
# yt-dlp breaks whenever YouTube changes its player, and the fix is always
# "update yt-dlp". requirements.txt only resolves at *build* time, so a
# container built in July runs July's yt-dlp forever. Doing the update here
# means `docker compose restart app` picks up the latest fix without a
# rebuild. --pre pulls the nightly channel, where YouTube fixes land first.
#
# Failure-safe: if PyPI is unreachable, we log it and boot with whatever
# version is already installed rather than refusing to start.

set -u

if [ "${YTDLP_AUTO_UPDATE:-1}" = "1" ]; then
  echo "[entrypoint] refreshing yt-dlp (nightly)..."
  if pip install -q --no-cache-dir -U --pre "yt-dlp[default]"; then
    echo "[entrypoint] yt-dlp refresh OK"
  else
    echo "[entrypoint] yt-dlp refresh FAILED — booting with installed version"
  fi
else
  echo "[entrypoint] YTDLP_AUTO_UPDATE=0, skipping yt-dlp refresh"
fi

python -c "import yt_dlp; print('[entrypoint] yt-dlp', yt_dlp.version.__version__)"

# exec so uvicorn becomes PID 1 and receives Docker's stop signals directly.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
