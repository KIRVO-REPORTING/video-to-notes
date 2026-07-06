# youtube-local-transcribe

Caption First | Local Whisper Fallback | Searchable HTML Reports

Turn YouTube, Bilibili, TED, and other `yt-dlp` supported video URLs into local transcripts, summaries, and browser-readable reports. It tries captions first, uses local Whisper only when needed, and keeps your processed reports in a local dashboard.

## Quick Install - Copy & Run

```bash
git clone https://github.com/KIRVO-REPORTING/youtube-local-transcribe-skill-public.git
cd youtube-local-transcribe-skill-public
python -m pip install -e .
```

Start with any video that has captions:

```bash
ytlt process "VIDEO_URL" --language zh --open
```

Need local transcription when captions are missing? Run setup once:

```bash
ytlt setup --execute
```

Setup detects your machine, chooses the right backend, verifies ffmpeg, and downloads the recommended Whisper model into your local workspace.

Only want caption download and reports? You can skip setup until a video needs local Whisper.

## Works With

| Tool | How to use it |
|---|---|
| Terminal | Run `ytlt process "VIDEO_URL"` directly. |
| Codex | Install the `codex-skill` folder as `youtube-local-transcribe`. |
| Claude Code / Cursor | Ask the AI to install this repo, then call `ytlt` for video URLs. |

Default workspace:

```text
~/Documents/youtube
```

Use another workspace:

```bash
ytlt process "VIDEO_URL" --workspace /path/to/workspace
```

## What It Can Do

| Workflow | Command |
|---|---|
| Download captions and build a report | `ytlt process "VIDEO_URL" --language en --open` |
| Use browser cookies for private or region-limited videos | `ytlt process "VIDEO_URL" --cookies-from-browser chrome` |
| Force local Whisper transcription | `ytlt process "VIDEO_URL" --force-transcribe` |
| Skip local transcription if captions are missing | `ytlt process "VIDEO_URL" --no-transcribe-fallback` |
| Publish a report into Notion | `ytlt finalize "/path/to/video-folder" --publish-notion` |
| Rebuild the report index | `ytlt rebuild-index` |
| Open the local dashboard | `ytlt serve --open` |

Each processed video gets its own folder under:

```text
<workspace>/processed/
```

The folder contains:

- `metadata.json`
- `transcript.txt`
- `report.html`
- `summary.md` after you write or generate a summary

## Publish To Notion

Create a Notion integration token, share the target page or data source with that integration, then set:

```bash
export NOTION_TOKEN="secret_..."
export NOTION_DATA_SOURCE_ID="..."
```

Use exactly one target:

- `NOTION_DATA_SOURCE_ID` for a Notion database/data source dashboard.
- `NOTION_PARENT_PAGE_ID` to create report pages under a normal Notion page.
- `NOTION_DATABASE_ID` to resolve the database's first data source automatically.

Publish while processing:

```bash
ytlt process "VIDEO_URL" --language zh --publish-notion
```

Publish after writing `summary.md`:

```bash
ytlt finalize "/path/to/processed/video-folder" --publish-notion
```

Publish an existing processed folder without re-rendering:

```bash
ytlt publish-notion "/path/to/processed/video-folder"
```

When a report is published, `metadata.json` records `notion_page_id`, `notion_url`, and `notion_synced_at` so later runs update the same Notion page instead of creating duplicates.
When publishing to a Notion database, the database row opened from `Name` is the report content page; no separate detail-page URL is required.

## Examples

### You

Transcribe this video and open the report:

```bash
ytlt process "https://www.youtube.com/watch?v=VIDEO_ID" --language zh --open
```

### ytlt

```json
{
  "transcript_source": "manual_subtitle",
  "transcript": ".../processed/.../transcript.txt",
  "report": ".../processed/.../report.html",
  "dashboard": ".../dashboard.html"
}
```

### You

Summarize the transcript, then finalize the report:

```bash
ytlt finalize "/path/to/processed/video-folder" --open --publish-notion
```

### ytlt

```json
{
  "report": "/path/to/processed/video-folder/report.html",
  "deleted_video_files": [],
  "notion": {
    "notion_page_id": "...",
    "notion_url": "https://www.notion.so/...",
    "notion_synced_at": "..."
  }
}
```

## Codex Skill Install

From a cloned copy of this repo:

```bash
mkdir -p "$HOME/.codex/skills/youtube-local-transcribe"
rsync -a --delete codex-skill/ "$HOME/.codex/skills/youtube-local-transcribe/"
```

Restart Codex after replacing an installed skill so the new `SKILL.md` metadata is loaded.

Then send Codex a video URL or ask:

```text
Use youtube-local-transcribe to process this video and create a summary report: VIDEO_URL
```

Codex replies should lead with the real video title, the Notion row/report link, and a compact summary. Video summaries use foldable segmented conclusions: each collapsed title starts with a timestamp range and the segment conclusion, while the expanded body uses natural prose or concise bullets instead of fixed `Point` / `Evidence` / `Implication` labels. Codex should rename the thread to the video topic when thread tools are available instead of leaving a generic transcription title. Conversion and download details stay out of the final answer unless they affect the result.

## Local Development

```bash
git clone https://github.com/KIRVO-REPORTING/youtube-local-transcribe-skill-public.git
cd youtube-local-transcribe-skill-public
python -m pip install -e .
```

Run tests:

```bash
python -m unittest discover -s tests
```

Try a caption-first smoke test:

```bash
ytlt process "https://www.ted.com/talks/sir_ken_robinson_do_schools_kill_creativity" --language en --no-transcribe-fallback
```

## Notes

- Python 3.9+ is required. Python 3.10+ is recommended.
- Captions are always preferred before local Whisper.
- `ytlt setup --execute` is only needed for local Whisper fallback.
- Hardware model selection lives in `codex-skill/references/model-selection.md`.
- Generated workspaces, downloaded media, models, virtual environments, and build metadata are ignored by `.gitignore`.
