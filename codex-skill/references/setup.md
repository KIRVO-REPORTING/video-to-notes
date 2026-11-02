# Setup and Recovery

Read this reference only on a new machine, when `video-to-notes` is unavailable, when `doctor` reports errors, or when local transcription needs configuration.

## Install

From the repository root:

```bash
# macOS/Linux
./install.sh

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

The installer finds or provisions Python 3.10+, creates `.venv`, installs yt-dlp with its EJS solver, checks Deno 2.3+ or Node.js 22+ and ffmpeg, and installs this Codex skill when Codex is detected.

For non-interactive installation:

```bash
VIDEO_TO_NOTES_SKIP_CONFIGURE=1 ./install.sh
.venv/bin/video-to-notes doctor
.venv/bin/video-to-notes configure --language zh --model-choice recommended --environment local --execute
```

On Windows, use the equivalent `.venv\Scripts\video-to-notes.exe` commands. The legacy `YTLT_SKIP_CONFIGURE=1` variable remains supported.

## Diagnose

If the command is already installed, run:

```bash
video-to-notes doctor
video-to-notes doctor --url "VIDEO_URL"
video-to-notes probe
```

Resolve every `doctor` error before claiming the installation is ready. Do not treat warnings as fatal unless they affect the current source or configured backend.

`doctor` without `--url` checks local dependencies only and reports `network.checked=false`. With `--url`, it checks transport from the actual CLI process. An HTTP rejection proves the host is reachable, but does not prove that yt-dlp can retrieve captions or media.

If the CLI reports a DNS or network failure, identify whether this execution environment permits outbound access. Browser access can work while a sandboxed CLI cannot connect. Retry only through an available, authorized download path; do not bypass sandbox restrictions. Authentication retries and model installation do not fix DNS failure. If no permitted path exists, report the acquisition stage and blocker, and leave the transcription incomplete.

## Configure

Interactive configuration:

```bash
video-to-notes configure
```

Non-interactive examples:

```bash
video-to-notes configure --language zh --model-choice recommended --environment local --execute
video-to-notes configure --language zh --model-choice recommended --environment notion --execute
video-to-notes configure --language zh --model-choice recommended --environment obsidian --execute
video-to-notes configure --language zh --model-choice none --environment local
```

When selecting a recommended or custom Whisper model non-interactively, include `--execute`. Without it, configuration must fail rather than write a misleading enabled fallback.

Read [model-selection.md](model-selection.md) only when choosing, overriding, or troubleshooting the Whisper backend/model. Caption-backed videos do not require Whisper.
