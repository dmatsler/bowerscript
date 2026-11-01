"""Memory reporting for a host with no metrics dashboard.

Render's free tier gives you the Logs tab and nothing else, so the cheapest
useful telemetry is a line per video saying how much resident memory the
process holds and how much audio is still sitting in temp. Every line starts
with "[mem]" so it can be filtered out of the stream.

No new dependency. psutil is used if it happens to be installed, otherwise
/proc/self/status, which is what Render runs. The resource fallback is there
so local dev on macOS prints something rather than nothing — it reports the
high-water mark rather than the current value, and the line says so.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Optional

try:
    import psutil as _psutil
except ImportError:  # the normal case — psutil isn't in requirements.txt
    _psutil = None

_MB = 1024 * 1024


def _read_rss() -> tuple[Optional[float], str]:
    """Return (megabytes, how-we-measured). None when nothing works."""
    if _psutil is not None:
        return _psutil.Process().memory_info().rss / _MB, "current"

    try:
        with open("/proc/self/status", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    # Format is "VmRSS:\t  123456 kB".
                    return int(line.split()[1]) / 1024, "current"
    except (OSError, ValueError, IndexError):
        pass

    # No /proc: macOS. ru_maxrss is a peak, and its unit differs by platform
    # (bytes on Darwin, kilobytes on Linux).
    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak / (_MB if sys.platform == "darwin" else 1024), "peak"
    except Exception:  # noqa: BLE001 - telemetry must never break a job
        return None, "unavailable"


def rss_mb() -> Optional[float]:
    """Resident memory in MB, rounded, or None if the platform won't say."""
    value, _ = _read_rss()
    return None if value is None else round(value, 1)


def temp_mb() -> tuple[float, int]:
    """Total size of the per-video workdirs, and how many are alive.

    Only directories, so this never counts the shared cookie copy, which
    sits next to them under the same prefix.
    """
    total = 0
    count = 0
    for workdir in Path(tempfile.gettempdir()).glob("yt2md_*"):
        if not workdir.is_dir():
            continue
        count += 1
        for item in workdir.rglob("*"):
            try:
                if item.is_file():
                    total += item.stat().st_size
            except OSError:
                pass  # deleted mid-walk; chunks are removed as they're sent
    return round(total / _MB, 1), count


def log(event: str) -> None:
    """Emit one '[mem]' line.

    print() rather than logging: the project configures no logging, and
    Render's Logs tab is just stdout — same convention as entrypoint.sh.
    """
    value, source = _read_rss()
    rss = "n/a" if value is None else f"{value:.1f}MB"
    note = "" if source == "current" else f" ({source})"
    temp, dirs = temp_mb()
    print(
        f"[mem] {event} rss={rss}{note} temp={temp:.1f}MB dirs={dirs}",
        flush=True,
    )
