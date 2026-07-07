from __future__ import annotations

import json
from pathlib import Path

from .spec import InstallProfile


def download_model(model: str, target_dir: Path | None = None) -> Path | str:
    if model.startswith("/") or model.startswith("~") or Path(model).exists():
        return Path(model).expanduser().resolve()

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("Install huggingface-hub or run video-to-notes install --execute first.") from exc

    kwargs = {"repo_id": model}
    if target_dir:
        target_dir.mkdir(parents=True, exist_ok=True)
        kwargs["local_dir"] = str(target_dir / model.replace("/", "__"))
    return Path(snapshot_download(**kwargs))


def transcribe_video(
    video_path: Path,
    output_dir: Path,
    profile: InstallProfile,
    *,
    language: str | None = None,
    model_override: str | None = None,
    backend_override: str | None = None,
    device_override: str | None = None,
    compute_type_override: str | None = None,
) -> Path:
    backend = backend_override or profile.backend
    model = model_override or profile.model
    device = device_override or profile.device
    compute_type = compute_type_override or profile.compute_type
    if not model:
        raise RuntimeError("No transcription model selected.")

    output_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = output_dir / "transcript.txt"
    detail_path = output_dir / "transcript.json"

    if backend == "faster-whisper":
        _transcribe_with_faster_whisper(
            video_path,
            transcript_path,
            detail_path,
            model=model,
            device=device or "auto",
            compute_type=compute_type or "default",
            language=language,
        )
    elif backend == "mlx":
        _transcribe_with_mlx(
            video_path,
            transcript_path,
            detail_path,
            model=model,
            language=language,
        )
    else:
        raise RuntimeError(f"Unsupported transcription backend: {backend}")

    if not transcript_path.exists() or transcript_path.stat().st_size == 0:
        raise RuntimeError(f"Transcription did not create {transcript_path}")
    return transcript_path


def _transcribe_with_faster_whisper(
    video_path: Path,
    transcript_path: Path,
    detail_path: Path,
    *,
    model: str,
    device: str,
    compute_type: str,
    language: str | None,
) -> None:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Run video-to-notes configure --model-choice recommended --execute, "
            "or run ./install.sh first if the project is not installed yet."
        ) from exc

    whisper = WhisperModel(model, device=device, compute_type=compute_type)
    segments_iter, info = whisper.transcribe(str(video_path), language=language, beam_size=5)
    segments = [
        {
            "id": segment.id,
            "start": segment.start,
            "end": segment.end,
            "text": segment.text,
        }
        for segment in segments_iter
    ]
    transcript_path.write_text("".join(segment["text"] for segment in segments).strip() + "\n", encoding="utf-8")
    detail_path.write_text(
        json.dumps(
            {
                "backend": "faster-whisper",
                "model": model,
                "device": device,
                "compute_type": compute_type,
                "language": getattr(info, "language", None),
                "language_probability": getattr(info, "language_probability", None),
                "duration": getattr(info, "duration", None),
                "segments": segments,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _transcribe_with_mlx(
    video_path: Path,
    transcript_path: Path,
    detail_path: Path,
    *,
    model: str,
    language: str | None,
) -> None:
    try:
        import mlx_whisper
    except ImportError as exc:
        raise RuntimeError(
            "mlx-whisper is not installed. Run video-to-notes configure --model-choice recommended --execute, "
            "or run ./install.sh first if the project is not installed yet."
        ) from exc

    kwargs = {"path_or_hf_repo": model}
    if language:
        kwargs["language"] = language
    result = mlx_whisper.transcribe(str(video_path), **kwargs)
    text = str(result.get("text") or "").strip()
    transcript_path.write_text(text + "\n", encoding="utf-8")
    detail_path.write_text(
        json.dumps(
            {
                "backend": "mlx-whisper",
                "model": model,
                "language": result.get("language"),
                "segments": result.get("segments", []),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
