from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


CONFIG_FILENAME = "config.json"


def _valid_ffmpeg(value: str | os.PathLike[str] | None) -> str | None:
    if not value:
        return None
    raw = str(value)
    path = Path(raw).expanduser()
    if path.is_dir():
        found = shutil.which("ffmpeg", path=str(path))
        return found
    if path.is_file():
        return str(path)
    return shutil.which(raw)


def _configured_ffmpeg(workspace: Path | str | None) -> str | None:
    if not workspace:
        return None
    path = Path(workspace).expanduser() / CONFIG_FILENAME
    if not path.exists():
        return None
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return None

    ffmpeg = config.get("ffmpeg")
    candidates: list[str | None] = []
    if isinstance(ffmpeg, dict):
        candidates.append(ffmpeg.get("path"))
    candidates.append(config.get("ffmpeg_path"))

    for candidate in candidates:
        resolved = _valid_ffmpeg(candidate)
        if resolved:
            return resolved
    return None


def _imageio_ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg
    except Exception:
        return None
    try:
        return _valid_ffmpeg(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return None


def resolve_ffmpeg_path(
    workspace: Path | str | None = None,
    *,
    explicit: str | os.PathLike[str] | None = None,
) -> str | None:
    for candidate in (
        _valid_ffmpeg(explicit),
        _valid_ffmpeg(os.environ.get("YTLT_FFMPEG")),
        _configured_ffmpeg(workspace),
        _valid_ffmpeg("ffmpeg"),
        _imageio_ffmpeg(),
    ):
        if candidate:
            return candidate
    return None
