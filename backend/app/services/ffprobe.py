import json
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

FFPROBE_MISSING_MESSAGE = (
    "ffprobe was not found on PATH. superCPE measures every uploaded video's "
    "duration with ffprobe (Standards 7.02.7) and cannot run without it. "
    "Install ffmpeg (e.g. `brew install ffmpeg`) and restart."
)


class FfprobeNotFoundError(RuntimeError):
    pass


def ensure_ffprobe_available() -> None:
    if shutil.which("ffprobe") is None:
        raise FfprobeNotFoundError(FFPROBE_MISSING_MESSAGE)


def duration_seconds(path: str | Path) -> Decimal:
    ensure_ffprobe_available()
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(f"ffprobe could not read {path}: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    try:
        return Decimal(data["format"]["duration"])
    except (KeyError, ArithmeticError) as exc:
        raise ValueError(f"ffprobe returned no duration for {path}") from exc
