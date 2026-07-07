---
name: video-to-notes
description: Caption-first local video archiving, transcription, summarization, report generation, configurable local/Notion/Obsidian publishing, dashboard workflow, concise final answers, and video-topic thread titles for YouTube, youtu.be, Bilibili, b23.tv, BV, av, ep, ss, and other yt-dlp supported video URLs. Use when the user sends a bare video link or asks to download subtitles, transcribe locally, summarize a video, create notes, generate an HTML report, publish to Notion, publish to Obsidian, create or sync report databases/notes, open a local browser report, inspect past video reports, or serve a local report dashboard.
---

# Video to Notes

Use this workflow for bare video URLs and explicit video transcription, summary, archive, local report, Notion sync, Obsidian sync, or report requests. Prefer downloadable subtitles first; use local Whisper only when captions are missing, unsuitable, or the user forces transcription. Respect the user's `video-to-notes configure` output environment: `local`, `notion`, or `obsidian`.

## Current Artifact Workflow

For bare video links, report requests, Notion sync requests, Obsidian sync requests, or the current clean report output, produce the configured artifact directly:

1. Process the video with `video-to-notes process`, preferring captions and falling back to local Whisper only when needed.
2. Read `metadata.json` and `transcript.txt`; write `summary.md` with an answer-first overview and timestamped Key Points grounded in the transcript.
3. Run `video-to-notes finalize "<video-folder>"` to refresh the local `report.html` and dashboard index.
4. Publish or update the configured target when applicable: Notion database row for `notion`, Obsidian note/dashboard for `obsidian`, or local dashboard only for `local`.
5. Rename the current Codex thread to a concise video-topic title when a thread-title tool is available and the current thread id can be resolved.
6. Return the primary reader-facing output for the configured target: Notion row URL, Obsidian note path/URI, or local `report.html` path.

Do not assume Notion is always the desired destination. If `<workspace>/config.json` exists, use its configured `preferences.output_environment`. If it is missing and the user has not specified a destination, local output is acceptable, but suggest `video-to-notes configure` for persistent language/model/environment preferences.

Keep user-facing progress and final responses focused on the video result. Avoid dumping download, transcode, caption conversion, test, command, codec, cleanup, or file-by-file process logs unless the user asks for that detail or the workflow fails.

The current Notion artifact is:

- Parent page with a short `报告数据库` section and concise sync status.
- Database named `本地视频报告数据库`.
- One row per report. Opening `Name` shows the report body itself.
- No duplicate detail page, no `Report Page` property, and no `Status` property.
- Row body sections: `Summary`, `Key Points`, `Notes`, source/local metadata, and a final folded `Transcript` block.
- Timestamped Key Points are clickable source-video links that seek to the start second.

## Setup Check

If `video-to-notes` is not installed and this repository is available, install from the repository root with the bootstrap script. The script checks for Python 3.9+, pip, and venv support, creates `.venv`, installs required Python packages, and then offers to run `video-to-notes configure`.

```bash
./install.sh
```

For Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

If Python is missing, stop and follow the script's OS-specific Python installation instructions before continuing. Do not ask users to install Python packages manually unless they chose a manual setup path.

For non-interactive agent setup, skip the installer prompt and then run configuration explicitly:

```bash
VIDEO_TO_NOTES_SKIP_CONFIGURE=1 ./install.sh
.venv/bin/video-to-notes probe
.venv/bin/video-to-notes configure
```

For Windows PowerShell non-interactive setup:

```powershell
$env:VIDEO_TO_NOTES_SKIP_CONFIGURE = "1"
powershell -ExecutionPolicy Bypass -File .\install.ps1
.\.venv\Scripts\video-to-notes.exe probe
.\.venv\Scripts\video-to-notes.exe configure
```

The installer also accepts the legacy `YTLT_SKIP_CONFIGURE=1` variable for compatibility.

If `video-to-notes` is already on PATH, run:

```bash
video-to-notes probe
video-to-notes configure
```

`video-to-notes configure` asks for the user's usual language, local Whisper fallback model choice, and output environment. The recommended model is based on the detected hardware. Choosing no model is allowed but not recommended because videos without usable captions cannot fall back to local transcription.

Non-interactive examples:

```bash
video-to-notes configure --language zh --model-choice recommended --environment local --execute
video-to-notes configure --language zh --model-choice recommended --environment notion --execute
video-to-notes configure --language zh --model-choice recommended --environment obsidian --execute
video-to-notes configure --language zh --model-choice none --environment local
```

`--execute` installs the matching backend plus `imageio-ffmpeg`, verifies ffmpeg, downloads or configures the selected model when needed, and writes `<workspace>/config.json`. `video-to-notes setup --execute` remains available for model-only setup. When deciding what model or backend to install, read `references/model-selection.md`.

## Process One Video

Run:

```bash
video-to-notes process "VIDEO_URL"
```

Useful options:

```bash
video-to-notes process "VIDEO_URL" --language zh
video-to-notes process "VIDEO_URL" --cookies-from-browser chrome
video-to-notes process "VIDEO_URL" --force-transcribe
video-to-notes process "VIDEO_URL" --open
video-to-notes process "VIDEO_URL" --publish-notion
video-to-notes process "VIDEO_URL" --publish-obsidian
video-to-notes process "VIDEO_URL" --environment local
```

The processor creates a per-video folder under `<workspace>/processed/`, writes `metadata.json`, `transcript.txt`, and `report.html`, and updates `index.json` plus `dashboard.html`.
When local Whisper is needed, it uses the configured model path from `<workspace>/config.json` unless `--model` is provided. If the user configured `model-choice none`, no-caption videos should fail with a clear message instead of silently attempting Whisper.

The JSON output includes the folder and report paths. Read `metadata.json` and `transcript.txt` before summarizing.

## Write The Summary

Write a grounded Markdown summary to `<video-folder>/summary.md`. Use the user's language unless the user requests another language. Prefer an answer-first structure with timestamped Key Points and optional one-level nested supporting bullets.

Do not force every point into `Point` / `Evidence` / `Implication` labels. Use top-level bullets for the video's major conclusions, claims, risks, decisions, or methods. Use nested bullets only when a point needs transcript-backed support, examples, numbers, caveats, or subclaims. Do not add nested bullets just to satisfy the shape.

Use this structure:

```text
Summary

One-paragraph answer-first summary naming the video's core conclusion.

Key Points

- [mm:ss-mm:ss] Point 1.
  - [mm:ss-mm:ss] Supporting detail, example, subclaim, number, or caveat.
  - [mm:ss-mm:ss] Another supporting detail when it materially helps.

- [mm:ss-mm:ss] Point 2.
- [mm:ss-mm:ss] Point 3.

Notes

- Caveats about subtitle quality, audio quality, uncertain terms, or incomplete transcript.
```

For video reports, each Key Point bullet and nested supporting bullet should start with a bracketed timestamp or time range such as `[01:24-02:44]`, using the transcript's actual timing. Use `[hh:mm:ss-hh:mm:ss]` for videos longer than one hour. The report renderer and CLI Notion publisher convert bracketed timestamps into clickable source-video links that seek to the start time, so keep the timestamp at the beginning of each bullet. When writing report content through the Notion connector Markdown path, avoid colons in the linked label because Notion can split the link; use an inline link like `[01m24s-02m44s](https://www.youtube.com/watch?v=VIDEO_ID&t=84)` instead of leaving it as plain text.

For long videos, consider parallel drafting after reading the full transcript once. Treat a video as long when it is roughly over 45 minutes, has a very large transcript, or naturally breaks into many segments. Split the transcript into contiguous timestamp ranges and, when subagents or parallel work are available, draft each range independently into candidate Key Points. Each parallel draft must receive only the metadata, its transcript slice, neighboring boundary context when needed, and the output structure above. The main agent must then merge the drafts into one coherent `summary.md`, remove repetition, normalize point wording, verify timestamp ranges against the transcript, and keep the final response focused on the report rather than the coordination process.

Finalize:

```bash
video-to-notes finalize "<video-folder>"
```

Finalization re-renders `report.html`, deletes any retained downloaded `video.*` media file, and refreshes the dashboard index. Continue into the configured output target before responding. Use `--environment local`, `--environment notion`, or `--environment obsidian` to override the configured destination for one run.

## Notion Publishing

Use Notion publishing when the user asks for Notion, passes `--publish-notion`, or configured `video-to-notes configure --environment notion`. If a Notion connector/MCP/app is connected in the current agent environment, prefer that path for setup and publishing: create or reuse the report database through the connector, write the report row through the connector after `video-to-notes finalize`, and do not require local `NOTION_TOKEN`. Skip Notion only when the user explicitly asks for local-only output, the environment has neither CLI Notion credentials nor a connected Notion app/MCP, or publishing fails after a reasonable retry. If skipped or blocked, state the reason in the final response and still return the local report path.

For CLI-based publishing, the required environment is:

```bash
export NOTION_TOKEN="secret_..."
```

Set exactly one target:

```bash
export NOTION_DATA_SOURCE_ID="..."
export NOTION_PARENT_PAGE_ID="..."
export NOTION_DATABASE_ID="..."
```

Prefer `NOTION_DATA_SOURCE_ID` for a Notion database/data-source dashboard. Use `NOTION_PARENT_PAGE_ID` only when the user wants plain child pages under a normal Notion page. `NOTION_DATABASE_ID` resolves the database's first data source automatically.

When CLI credentials and a target are available, publish during finalization or publish the already processed folder:

```bash
video-to-notes finalize "<video-folder>" --publish-notion
video-to-notes publish-notion "<video-folder>"
```

When Notion publishing succeeds, the JSON output includes `notion.notion_url`. Include that link in the final response alongside the local dashboard link. The publisher stores `notion_page_id`, `notion_url`, and `notion_synced_at` in `metadata.json`; later publishes update the same Notion page.

When running in Codex, ChatGPT, or another agent with a connected Notion app/MCP but no `NOTION_TOKEN`, use the connector after `video-to-notes finalize`. Use the clean Notion database layout below. Do not claim the CLI wrote to Notion unless `--publish-notion` or `video-to-notes publish-notion` was used.

Connector/MCP setup path:

1. Ask the connector/MCP to search for an existing report workspace/page/database named `本地视频报告数据库` or a user-specified target.
2. If no suitable target exists, create a clean parent page and database using the schema below.
3. After `video-to-notes finalize`, read `metadata.json`, `summary.md`, `transcript.txt`, and local `report.html`.
4. Create or update exactly one database row for the report; the row opened from `Name` is the report body.
5. Write connector-created Notion IDs/URLs back to `metadata.json` when local file editing is available. Use the same metadata field names as CLI publishing where possible: `notion_page_id`, `notion_url`, `notion_database_id`, `notion_database_url`, `notion_data_source_id`, and `notion_synced_at`.

In final responses, lead with the video title and Notion row URL. Include the local report path only as the backing archive.

### Clean Notion Database Layout

When syncing reports to Notion, create or reuse one parent page as the workspace landing page. Keep this page clean:

- Add a short `报告数据库` section with the report database.
- Add a concise sync status section.
- Do not create separate report detail pages. The database row opened from `Name` is the report content page.
- Do not leave individual report pages scattered on the landing page.

Create or reuse a database named `本地视频报告数据库` under the parent page. Match the local dashboard columns:

- `Name` title
- `Platform` select: `youtube`, `bilibili`, `video`
- `Transcript Source` select: `manual_subtitle`, `auto_subtitle`, `local_whisper`, `unknown`
- `Channel` rich text
- `Source URL` URL
- `Published` date
- `Processed` date
- `Processing Seconds` number
- `Duration Seconds` number
- `Summary` rich text
- `Local Report` rich text

Create database views:

- `Dashboard`: core columns, sorted by `Processed` descending.
- `All Reports`: same as Dashboard.
- `Captions`: filter `Transcript Source = manual_subtitle`.
- `Whisper`: filter `Transcript Source = local_whisper`.
- `Recent`: recent reports without status filtering.

For each report, create one database row as the only Notion report page. Put the report content directly inside that row page so opening `Name` shows metadata, source link, summary, Key Points, notes, local report path, and the full transcript. The full transcript should be included by default as the final folded `Transcript` block, not as always-expanded page text.

Use this row body structure:

```text
## Summary
One answer-first summary paragraph.

## Key Points
- [01m24s-02m44s](SOURCE_URL_WITH_t=84) Main conclusion.
  - [01m30s-01m40s](SOURCE_URL_WITH_t=90) Concrete transcript-backed detail, example, number, or caveat.

## Notes
- Caveats about subtitles, transcription, uncertain terms, or source claims.

## Source And Local Files
- Source: SOURCE_URL
- Platform: youtube | bilibili | video
- Channel: CHANNEL
- Published: DATE
- Transcript Source: manual_subtitle | auto_subtitle | local_whisper
- Processing Seconds: PROCESSING_SECONDS
- Local Report: /absolute/path/to/report.html

<toggle title="Transcript">
Full transcript text.
</toggle>
```

Before syncing existing local reports, scan for folders containing both `metadata.json` and `report.html`; also read `index.json` when present. Deduplicate by `source_url`, then `platform + id`, then folder path. Skip evaluation and `.test-workspace` artifacts unless the user asks for every local report or explicitly includes tests.

After syncing, write the following fields back to each relevant `metadata.json` when possible:

- `notion_parent_page_id`, `notion_parent_url`
- `notion_database_id`, `notion_database_url`
- `notion_data_source_id`
- `notion_database_row_id`, `notion_database_row_url`
- `notion_page_id`, `notion_url` pointing to the same database row page
- `notion_synced_at`
- `notion_sync_method`

## Obsidian Publishing

Use Obsidian publishing when the user asks for Obsidian, passes `--publish-obsidian`, or configured `video-to-notes configure --environment obsidian`.

For CLI-based publishing, set the vault path:

```bash
export OBSIDIAN_VAULT_PATH="/path/to/your/vault"
```

Optional settings:

```bash
export OBSIDIAN_REPORTS_DIR="Video Reports"
export OBSIDIAN_INDEX_NOTE="Video Reports Dashboard.md"
```

Publish during finalization, publish an already processed folder, or sync a workspace:

```bash
video-to-notes finalize "<video-folder>" --publish-obsidian
video-to-notes publish-obsidian "<video-folder>"
video-to-notes sync-obsidian
```

The Obsidian publisher creates or updates one Markdown note per report and maintains a dashboard note. It writes YAML frontmatter, source metadata, timestamp-linked summary sections, local report path, and the transcript unless `--obsidian-no-transcript` is used.

When Obsidian publishing succeeds, the JSON output includes `obsidian.obsidian_note_path`, `obsidian.obsidian_note_uri`, and `obsidian.obsidian_index_note_path`. Include the note path or URI in the final response alongside the local report path. The publisher stores `obsidian_note_path`, `obsidian_vault_path`, `obsidian_synced_at`, and `obsidian_sync_method` in `metadata.json`; later publishes update the same note.

## Thread Title And Final Response

After reading `metadata.json`, derive the user-facing title from the source video's real title. If it is too long, trim it to a concise topic title of about 45-60 characters. Do not name the thread with generic workflow words such as `transcribe`, `caption`, `download`, or `video-to-notes`.

When a Codex thread-management tool is available and the current thread id can be resolved, rename the current thread to that concise video-topic title before the final response. If the thread id cannot be resolved, continue without blocking the report.

Final responses should use this shape, adapting the link line to the configured output target:

```text
Completed: VIDEO_TITLE

Report: NOTION_ROW_URL | OBSIDIAN_NOTE_PATH_OR_URI | /absolute/path/to/report.html
Local report: /absolute/path/to/report.html

Summary: One concise answer-first paragraph.

Key Points

- [mm:ss-mm:ss] Main point.
  - [mm:ss-mm:ss] Optional supporting detail or caveat.
- [mm:ss-mm:ss] Second main point.

Notes: Only include caveats or failures that affect trust in the result. Do not include the full transcript in the chat response; it is included in Notion or Obsidian when that output target is used.
```

Keep this response compact. Include conversion/process details only when they change the outcome, explain a failure, or the user explicitly asks for them.

## Dashboard

Open or serve previous reports:

```bash
video-to-notes rebuild-index
video-to-notes serve --open
```

`video-to-notes serve` binds to `127.0.0.1` by default and opens a local dashboard of past reports. Do not expose the server publicly unless the user explicitly asks.

## Output Contract

Each processed folder should contain:

- `metadata.json`: source URL, title, channel, platform, publish time, duration, processing time, and `transcript_source`
- `transcript.txt`: subtitle-derived or local Whisper transcript
- `summary.md`: Codex-written summary, after the summary step
- `report.html`: browser-readable report

`transcript_source` is one of:

- `manual_subtitle`
- `auto_subtitle`
- `local_whisper`

Do not rely on generated summaries without reading the transcript and metadata.
