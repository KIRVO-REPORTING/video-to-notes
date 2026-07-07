# Model Selection

Read this reference when installing the public video transcription workflow on a new machine, troubleshooting local transcription performance, or deciding which model/backend to use.

## First Rule

If the video has downloadable manual or automatic subtitles in a suitable language, do not install or run Whisper for that video. Use the subtitle file to create `transcript.txt`.

## Hardware Matrix

| Local spec | Backend | Default model | Device / compute | Notes |
|---|---|---|---|---|
| Downloadable manual or auto captions | none | none | none | Use captions directly; fastest and lowest cost |
| Apple Silicon macOS, >=16 GB unified memory | `mlx` | `mlx-community/whisper-large-v3-turbo` | MLX | Best current local default from English + multilingual testing |
| Apple Silicon macOS, 8-15 GB unified memory | `mlx` | `mlx-community/whisper-small-mlx` | MLX | Faster and safer on limited memory; lower accuracy than turbo |
| Windows/Linux with NVIDIA CUDA, >=10 GB VRAM | `faster-whisper` | `large-v3-turbo` | `cuda` / `float16` | Use faster-whisper's built-in alias; avoid the stale Systran repo path |
| Windows/Linux with NVIDIA CUDA, 6-9 GB VRAM | `faster-whisper` | `large-v3-turbo` | `cuda` / `int8_float16` | Lower VRAM profile; fallback to small if out of memory |
| Windows/Linux with NVIDIA CUDA, 4-5 GB VRAM | `faster-whisper` | `Systran/faster-whisper-small` | `cuda` / `int8_float16` | Conservative GPU profile |
| CPU only, Intel/AMD integrated GPU, or unsupported GPU, >=16 GB RAM | `faster-whisper` | `Systran/faster-whisper-small` | `cpu` / `int8` | Slow but usable; Chinese may be better than MLX small |
| CPU only, Intel/AMD integrated GPU, or unsupported GPU, 8-15 GB RAM | `faster-whisper` | `Systran/faster-whisper-base` | `cpu` / `int8` | Mainstream CPU fallback |
| CPU only, Intel/AMD integrated GPU, or unsupported GPU, <8 GB RAM | `faster-whisper` | `Systran/faster-whisper-tiny` | `cpu` / `int8` | Minimal fallback; quality is limited |
| AMD ROCm / DirectML / OpenVINO requested | CPU fallback by default | RAM-based CPU model | `cpu` / `int8` | Treat GPU acceleration as experimental until this package validates it |

## Install Commands

Always start with:

```bash
video-to-notes probe
video-to-notes recommend
video-to-notes setup --dry-run
```

Run the plan only after checking it:

```bash
video-to-notes setup --execute
```

`setup --execute` downloads the hardware-recommended model into `<workspace>/models` and writes `<workspace>/config.json`. `video-to-notes install --execute` remains a compatible alias for the same setup behavior.

For manual installs:

```bash
# Apple Silicon
python -m pip install -e ".[mlx]"

# NVIDIA CUDA or CPU
python -m pip install -e ".[faster-whisper]"
```

NVIDIA `large-v3-turbo` is a faster-whisper alias, not a workspace-cached Hugging Face repo path. Setup should let faster-whisper resolve/cache it at runtime instead of trying to `snapshot_download` `Systran/faster-whisper-large-v3-turbo`.

## Overrides

Use explicit overrides only when the default recommendation is wrong or the user requests a different quality/speed tradeoff:

```bash
video-to-notes process "VIDEO_URL" --force-transcribe --backend faster-whisper --model Systran/faster-whisper-medium --device cpu --compute-type int8
video-to-notes process "VIDEO_URL" --force-transcribe --backend mlx --model mlx-community/whisper-large-v3-turbo
```
