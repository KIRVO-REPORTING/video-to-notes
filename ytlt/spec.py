from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .ffmpeg import resolve_ffmpeg_path


@dataclass(frozen=True)
class NvidiaGpu:
    name: str
    vram_mb: int


@dataclass(frozen=True)
class MachineSpec:
    os: str
    arch: str
    python: str
    ram_gb: float | None
    is_apple_silicon: bool
    nvidia_gpus: list[NvidiaGpu]
    ffmpeg: str | None
    workspace: str


@dataclass(frozen=True)
class InstallProfile:
    id: str
    backend: str
    model: str | None
    device: str | None
    compute_type: str | None
    pip_extras: list[str]
    reason: str
    notes: list[str]


MODEL_MATRIX: list[dict[str, Any]] = [
    {
        "case": "Downloadable manual or automatic captions",
        "backend": "none",
        "model": "none",
        "compute": "none",
        "rule": "Use captions directly; do not install or run Whisper for that video.",
    },
    {
        "case": "Apple Silicon with >=16 GB unified memory",
        "backend": "mlx-whisper",
        "model": "mlx-community/whisper-large-v3-turbo",
        "compute": "mlx",
        "rule": "Default macOS quality/speed profile.",
    },
    {
        "case": "Apple Silicon with 8-15 GB unified memory",
        "backend": "mlx-whisper",
        "model": "mlx-community/whisper-small-mlx",
        "compute": "mlx",
        "rule": "Conservative default; users can opt into turbo for shorter videos.",
    },
    {
        "case": "NVIDIA CUDA with >=10 GB VRAM",
        "backend": "faster-whisper",
        "model": "large-v3-turbo",
        "compute": "float16",
        "rule": "Fast GPU profile using faster-whisper's built-in alias.",
    },
    {
        "case": "NVIDIA CUDA with 6-9 GB VRAM",
        "backend": "faster-whisper",
        "model": "large-v3-turbo",
        "compute": "int8_float16",
        "rule": "Balanced VRAM profile; fallback to medium if out of memory.",
    },
    {
        "case": "NVIDIA CUDA with 4-5 GB VRAM",
        "backend": "faster-whisper",
        "model": "Systran/faster-whisper-small",
        "compute": "int8_float16",
        "rule": "Small model by default; medium is a manual upgrade.",
    },
    {
        "case": "CPU only with >=16 GB RAM",
        "backend": "faster-whisper",
        "model": "Systran/faster-whisper-small",
        "compute": "int8",
        "rule": "Usable but slow; captions remain strongly preferred.",
    },
    {
        "case": "CPU only with 8-15 GB RAM",
        "backend": "faster-whisper",
        "model": "Systran/faster-whisper-base",
        "compute": "int8",
        "rule": "Safe default for mainstream laptops.",
    },
    {
        "case": "CPU only with <8 GB RAM",
        "backend": "faster-whisper",
        "model": "Systran/faster-whisper-tiny",
        "compute": "int8",
        "rule": "Minimal fallback; do not promise transcript quality.",
    },
    {
        "case": "Intel/AMD integrated GPU, AMD ROCm, or unsupported GPU",
        "backend": "faster-whisper",
        "model": "RAM-based CPU fallback",
        "compute": "cpu / int8",
        "rule": "Treat as CPU until this package validates a non-CUDA GPU backend.",
    },
]


def default_workspace() -> Path:
    return Path.home() / "Documents" / "youtube"


def _ram_gb() -> float | None:
    if sys.platform == "win32":
        try:
            import ctypes

            class MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatusEx()
            status.dwLength = ctypes.sizeof(status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return round(status.ullTotalPhys / 1024**3, 1)
        except Exception:
            return None

    if hasattr(os, "sysconf"):
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return round((pages * page_size) / 1024**3, 1)
        except (ValueError, OSError, TypeError):
            return None
    return None


def _nvidia_gpus() -> list[NvidiaGpu]:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return []
    cmd = [
        nvidia_smi,
        "--query-gpu=name,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(cmd, check=True, text=True, capture_output=True, timeout=8)
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        return []

    gpus: list[NvidiaGpu] = []
    for line in result.stdout.splitlines():
        if not line.strip() or "," not in line:
            continue
        name, memory = [part.strip() for part in line.split(",", 1)]
        try:
            vram_mb = int(float(memory))
        except ValueError:
            continue
        gpus.append(NvidiaGpu(name=name, vram_mb=vram_mb))
    return gpus


def probe(workspace: Path | None = None) -> MachineSpec:
    system = platform.system()
    machine = platform.machine()
    return MachineSpec(
        os=system,
        arch=machine,
        python=platform.python_version(),
        ram_gb=_ram_gb(),
        is_apple_silicon=system == "Darwin" and machine in {"arm64", "aarch64"},
        nvidia_gpus=_nvidia_gpus(),
        ffmpeg=resolve_ffmpeg_path(workspace),
        workspace=str((workspace or default_workspace()).expanduser()),
    )


def recommend(spec: MachineSpec) -> InstallProfile:
    ram = spec.ram_gb or 0
    notes: list[str] = []
    if spec.ffmpeg is None:
        notes.append("Setup will install imageio-ffmpeg so yt-dlp can merge split audio/video media.")

    if spec.is_apple_silicon:
        if ram >= 16:
            return InstallProfile(
                id="apple-silicon-turbo",
                backend="mlx",
                model="mlx-community/whisper-large-v3-turbo",
                device="mlx",
                compute_type="mlx",
                pip_extras=["mlx"],
                reason="Apple Silicon with enough unified memory for the turbo MLX model.",
                notes=notes,
            )
        return InstallProfile(
            id="apple-silicon-small",
            backend="mlx",
            model="mlx-community/whisper-small-mlx",
            device="mlx",
            compute_type="mlx",
            pip_extras=["mlx"],
            reason="Apple Silicon with limited unified memory; use a smaller MLX model first.",
            notes=notes + ["Use --model mlx-community/whisper-large-v3-turbo manually for short videos."],
        )

    if spec.nvidia_gpus:
        best = max(spec.nvidia_gpus, key=lambda gpu: gpu.vram_mb)
        vram_gb = best.vram_mb / 1024
        if vram_gb >= 10:
            profile_id = "nvidia-turbo-float16"
            model = "large-v3-turbo"
            compute = "float16"
            reason = f"NVIDIA GPU {best.name} has about {vram_gb:.1f} GB VRAM."
        elif vram_gb >= 6:
            profile_id = "nvidia-turbo-int8-float16"
            model = "large-v3-turbo"
            compute = "int8_float16"
            reason = f"NVIDIA GPU {best.name} has moderate VRAM; use quantized GPU inference."
        else:
            profile_id = "nvidia-small-int8-float16"
            model = "Systran/faster-whisper-small"
            compute = "int8_float16"
            reason = f"NVIDIA GPU {best.name} has limited VRAM; start with small."
        return InstallProfile(
            id=profile_id,
            backend="faster-whisper",
            model=model,
            device="cuda",
            compute_type=compute,
            pip_extras=["faster-whisper"],
            reason=reason,
            notes=notes,
        )

    if ram >= 16:
        model = "Systran/faster-whisper-small"
        profile_id = "cpu-small-int8"
        reason = "CPU-only machine with enough RAM for small int8 transcription."
    elif ram >= 8:
        model = "Systran/faster-whisper-base"
        profile_id = "cpu-base-int8"
        reason = "CPU-only machine with mainstream RAM; use base int8."
    else:
        model = "Systran/faster-whisper-tiny"
        profile_id = "cpu-tiny-int8"
        reason = "CPU-only machine with constrained RAM; use tiny int8."

    return InstallProfile(
        id=profile_id,
        backend="faster-whisper",
        model=model,
        device="cpu",
        compute_type="int8",
        pip_extras=["faster-whisper"],
        reason=reason,
        notes=notes
        + [
            "CPU transcription can be slow; prefer downloadable captions when present.",
            "Intel/AMD integrated GPUs and unsupported discrete GPUs use this CPU path by default.",
        ],
    )


def should_cache_model(profile: InstallProfile) -> bool:
    """Return whether setup should pre-download a model into the workspace cache."""
    return bool(profile.model and "/" in profile.model and not profile.model.startswith(("~", "/")))


def install_commands(
    profile: InstallProfile,
    project_root: Path | None = None,
    *,
    model_target: Path | None = None,
) -> list[list[str]]:
    root = project_root or Path.cwd()
    extras = ",".join(profile.pip_extras)
    target = f".[{extras}]" if extras else "."
    commands = [[sys.executable, "-m", "pip", "install", "-e", target]]
    commands.append(
        [
            sys.executable,
            "-c",
            "from ytlt.ffmpeg import resolve_ffmpeg_path; "
            "path = resolve_ffmpeg_path(); "
            "assert path, 'ffmpeg unavailable after setup'; "
            "print(f'ffmpeg available: {path}')",
        ]
    )
    if should_cache_model(profile):
        command = [sys.executable, "-m", "ytlt", "download-model", profile.model]
        if model_target:
            command.extend(["--target", str(model_target)])
        commands.append(command)
    if profile.backend == "faster-whisper" and profile.device == "cuda":
        commands.append(
            [
                sys.executable,
                "-c",
                "from faster_whisper import WhisperModel; "
                f"WhisperModel({profile.model!r}, device='cuda', compute_type={profile.compute_type!r}); "
                "print('CUDA faster-whisper backend loaded')",
            ]
        )
    if profile.backend == "mlx":
        commands.append(
            [
                sys.executable,
                "-c",
                "import mlx_whisper; print('MLX Whisper backend import ok')",
            ]
        )
    return [[str(root / part) if i == 0 and part.startswith("./") else part for i, part in enumerate(cmd)] for cmd in commands]


def to_json(data: Any) -> str:
    def default(value: Any) -> Any:
        if hasattr(value, "__dataclass_fields__"):
            return asdict(value)
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    return json.dumps(data, ensure_ascii=False, indent=2, default=default) + "\n"
