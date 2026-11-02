from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import read_config
from .ffmpeg import resolve_ffmpeg_path


MINIMUM_PYTHON = (3, 10)


class SourceAcquisitionError(RuntimeError):
    def __init__(self, stage: str, category: str, host: str, message: str):
        super().__init__(message)
        self.stage = stage
        self.category = category
        self.host = host


def acquisition_error(exc: Exception, *, stage: str, url: str) -> SourceAcquisitionError:
    """Classify failures without mistaking a network failure for absent captions."""
    detail = str(exc).lower()
    reason = getattr(exc, "reason", exc)
    host = urlparse(url).hostname or "unknown host"
    if isinstance(reason, socket.gaierror) or any(
        phrase in detail for phrase in ("failed to resolve", "name or service not known", "nodename nor servname", "getaddrinfo failed", "temporary failure in name resolution")
    ):
        category = "dns"
        message = f"Cannot resolve {host} from this execution environment. Check network access and DNS before retrying; cookies and Whisper settings cannot fix this failure."
    elif isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in detail:
        category = "timeout"
        message = f"Connection to {host} timed out. Check network access before retrying."
    elif isinstance(reason, ssl.SSLError) or "certificate_verify_failed" in detail:
        category = "tls"
        message = f"TLS verification failed for {host}. Check the network and certificate configuration; do not disable certificate verification."
    elif any(phrase in detail for phrase in ("sign in", "login required", "authentication required", "cookies are required")):
        category = "authentication"
        message = f"{host} requires authentication. Retry using an authorized browser cookie source."
    else:
        category = "source"
        message = str(exc)
    return SourceAcquisitionError(stage, category, host, message)


def check_source_network(url: str, *, timeout: float = 8) -> dict[str, Any]:
    """Check HTTPS transport; an HTTP rejection still proves the host is reachable."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return {"checked": True, "reachable": False, "category": "invalid_url", "message": "Expected an HTTP(S) source URL."}
    target = parsed._replace(netloc=parsed.netloc.rsplit("@", 1)[-1], query="", fragment="").geturl()
    try:
        request = urllib.request.Request(target, method="HEAD", headers={"User-Agent": "video-to-notes/0.2"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
    except (OSError, urllib.error.URLError) as exc:
        error = acquisition_error(exc, stage="network_check", url=url)
        return {"checked": True, "host": parsed.hostname, "reachable": False, "category": error.category, "message": str(error)}
    return {"checked": True, "host": parsed.hostname, "reachable": True, "http_status": status}


@dataclass(frozen=True)
class JavascriptRuntime:
    name: str
    path: str
    version: str

    @property
    def yt_dlp_value(self) -> str:
        return f"{self.name}:{self.path}"


_RUNTIME_MINIMUMS: dict[str, tuple[int, ...]] = {
    "deno": (2, 3, 0),
    "node": (22, 0, 0),
    "quickjs": (2023, 12, 9),
}

_RUNTIME_BINARIES: dict[str, tuple[str, ...]] = {
    "deno": ("deno",),
    "node": ("node", "nodejs"),
    "quickjs": ("qjs",),
}


def _version_tuple(text: str) -> tuple[int, ...] | None:
    match = re.search(r"(?<!\d)(\d+)(?:[.\-](\d+))(?:[.\-](\d+))?", text)
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def _runtime_version(path: str) -> str | None:
    try:
        result = subprocess.run(
            [path, "--version"],
            check=True,
            text=True,
            capture_output=True,
            timeout=8,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return (result.stdout or result.stderr).strip().splitlines()[0]


def _runtime(name: str, path: str | None) -> JavascriptRuntime | None:
    if not path:
        return None
    version = _runtime_version(path)
    parsed = _version_tuple(version or "")
    if not version or not parsed or parsed < _RUNTIME_MINIMUMS[name]:
        return None
    return JavascriptRuntime(name=name, path=str(Path(path).expanduser().resolve()), version=version)


def _explicit_runtime(value: str) -> tuple[str, str] | None:
    for name in _RUNTIME_MINIMUMS:
        prefix = f"{name}:"
        if value.startswith(prefix):
            return name, value[len(prefix) :]
    basename = Path(value).name.lower().removesuffix(".exe")
    for name, binaries in _RUNTIME_BINARIES.items():
        if basename in binaries:
            return name, value
    return None


def detect_javascript_runtimes() -> list[JavascriptRuntime]:
    runtimes: list[JavascriptRuntime] = []
    seen: set[tuple[str, str]] = set()

    explicit = os.environ.get("VIDEO_TO_NOTES_JS_RUNTIME") or os.environ.get("YTLT_JS_RUNTIME")
    candidates: list[tuple[str, str | None]] = []
    if explicit:
        parsed = _explicit_runtime(explicit)
        if parsed:
            candidates.append(parsed)

    for name, binaries in _RUNTIME_BINARIES.items():
        for binary in binaries:
            candidates.append((name, shutil.which(binary)))

    for name, path in candidates:
        runtime = _runtime(name, path)
        if not runtime:
            continue
        key = (runtime.name, runtime.path)
        if key in seen:
            continue
        seen.add(key)
        runtimes.append(runtime)
    return runtimes


def is_youtube_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")


def youtube_ydl_options(url: str) -> dict[str, Any]:
    if not is_youtube_url(url):
        return {}
    runtimes = detect_javascript_runtimes()
    if not runtimes:
        raise RuntimeError(
            "YouTube requires Deno 2.3+ or Node.js 22+ for JavaScript challenge solving. "
            "Install one of those runtimes, ensure it is on PATH, and run video-to-notes doctor."
        )
    return {"js_runtimes": {runtime.name: {"path": runtime.path} for runtime in runtimes}}


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def doctor(workspace: Path, *, check_config: bool = True, source_url: str | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    runtimes = detect_javascript_runtimes()
    yt_dlp_version = _package_version("yt-dlp")
    ejs_version = _package_version("yt-dlp-ejs")
    ffmpeg = resolve_ffmpeg_path(workspace)

    if sys.version_info[:2] < MINIMUM_PYTHON:
        errors.append("Python 3.10+ is required.")
    if not yt_dlp_version:
        errors.append("yt-dlp is not installed.")
    if not ejs_version:
        errors.append('yt-dlp-ejs is not installed; reinstall with "yt-dlp[default]".')
    if not runtimes:
        errors.append("No supported JavaScript runtime found; install Deno 2.3+ or Node.js 22+.")
    if not ffmpeg:
        errors.append("ffmpeg is unavailable.")

    config = read_config(workspace) if check_config else None
    if check_config and not config:
        warnings.append("Workspace is not configured yet; run video-to-notes configure.")
    elif config:
        whisper = config.get("whisper") or {}
        profile = config.get("profile") or {}
        model = config.get("model") or {}
        if whisper.get("fallback_enabled") is True:
            backend = profile.get("backend")
            module = "mlx_whisper" if backend == "mlx" else "faster_whisper" if backend == "faster-whisper" else None
            if not module or importlib.util.find_spec(module) is None:
                errors.append(f"Configured Whisper backend is unavailable: {backend or 'unknown'}.")
            model_source = profile.get("model")
            model_path = model.get("path")
            if model_source and "/" in str(model_source):
                if not model_path or not Path(str(model_path)).expanduser().exists():
                    errors.append("Configured Whisper model cache is missing; rerun configure with --execute.")

    network = check_source_network(source_url) if source_url else {"checked": False}
    if not network["checked"]:
        warnings.append("Network access was not checked; pass --url VIDEO_URL before processing a remote source.")
    elif not network["reachable"]:
        errors.append(network["message"])
    elif network["http_status"] >= 400:
        warnings.append(f"Source host is reachable but returned HTTP {network['http_status']}; metadata and media access are not yet verified.")

    return {
        "ready": not errors,
        "python": ".".join(map(str, sys.version_info[:3])),
        "yt_dlp": yt_dlp_version,
        "yt_dlp_ejs": ejs_version,
        "javascript_runtimes": [asdict(runtime) for runtime in runtimes],
        "ffmpeg": ffmpeg,
        "workspace": str(workspace),
        "configured": read_config(workspace) is not None,
        "config_checked": check_config,
        "network": network,
        "errors": errors,
        "warnings": warnings,
    }
