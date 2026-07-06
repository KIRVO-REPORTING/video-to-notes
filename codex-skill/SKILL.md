---
name: youtube-local-transcribe
description: Caption-first local video archiving, transcription, summarization, report generation, default clean Notion database publishing, dashboard workflow, concise final answers, and video-topic thread titles for YouTube, youtu.be, Bilibili, b23.tv, BV, av, ep, ss, and other yt-dlp supported video URLs. Use when the user sends a bare video link or asks to download subtitles, transcribe locally, summarize a video, create notes, generate an HTML report, publish to Notion, create a Notion report database, sync local reports, open a local browser report, inspect past video reports, or serve a local report dashboard.
---

# YouTube Local Transcribe

Use this workflow for bare video URLs and explicit video transcription, summary, archive, Notion sync, or report requests. Prefer downloadable subtitles first; use local Whisper only when captions are missing, unsuitable, or the user forces transcription. Publish or update the clean Notion report by default after local finalization unless the user explicitly asks for local-only output or Notion is unavailable.

## Current Artifact Workflow

For bare video links, report requests, Notion sync requests, or the current clean report output, produce the current artifact directly:

1. Process the video with `ytlt process`, preferring captions and falling back to local Whisper only when needed.
2. Read `metadata.json` and `transcript.txt`; write `summary.md` with an answer-first overview and timestamped segment summaries grounded in the transcript.
3. Run `ytlt finalize "<video-folder>"` to refresh the local `report.html` and dashboard index.
4. Publish or update the Notion database row report by default. The Notion row opened from `Name` is the report content page.
5. Rename the current Codex thread to a concise video-topic title when a thread-title tool is available and the current thread id can be resolved.
6. Return the Notion report row URL as the primary output, plus the database URL and local `report.html` path.

Do not stop at only a local HTML report or dashboard for bare links or report requests unless the user explicitly asks for local-only output or Notion publishing is blocked. Local files remain the backing archive; Notion is the reader-facing deliverable.

Keep user-facing progress and final responses focused on the video result. Avoid dumping download, transcode, caption conversion, test, command, codec, cleanup, or file-by-file process logs unless the user asks for that detail or the workflow fails.

The current Notion artifact is:

- Parent page with a short `报告数据库` section and concise sync status.
- Database named `本地视频报告数据库`.
- One row per report. Opening `Name` shows the report body itself.
- No duplicate detail page, no `Report Page` property, and no `Status` property.
- Row body sections: `摘要`, `分段结论`, `备注`, `来源与本地文件`.
- Timestamped segment headings are clickable source-video links that seek to the start second.

## Setup Check

If `ytlt` is not installed, ask the user to install the public package or run from the repository root:

```bash
python -m pip install -e .
ytlt probe
ytlt setup --dry-run
ytlt setup --execute
```

`ytlt setup --execute` detects the local hardware, installs the matching backend plus `imageio-ffmpeg`, verifies ffmpeg, downloads the recommended model into `<workspace>/models`, and writes `<workspace>/config.json` with the resolved ffmpeg path. When deciding what model or backend to install, read `references/model-selection.md`.

## Process One Video

Run:

```bash
ytlt process "VIDEO_URL"
```

Useful options:

```bash
ytlt process "VIDEO_URL" --language zh
ytlt process "VIDEO_URL" --cookies-from-browser chrome
ytlt process "VIDEO_URL" --force-transcribe
ytlt process "VIDEO_URL" --open
ytlt process "VIDEO_URL" --publish-notion
```

The processor creates a per-video folder under `<workspace>/processed/`, writes `metadata.json`, `transcript.txt`, and `report.html`, and updates `index.json` plus `dashboard.html`.
When local Whisper is needed, it uses the configured model path from `<workspace>/config.json` unless `--model` is provided.

The JSON output includes the folder and report paths. Read `metadata.json` and `transcript.txt` before summarizing.

## Write The Summary

Write a grounded Markdown summary to `<video-folder>/summary.md`. Use the user's language unless the user requests another language. Prefer a segmented, answer-first structure with foldable segment details over a flat list of bullets.

Do not force every segment into `Point` / `Evidence` / `Implication` labels. Each segment should use a foldable block whose collapsed title is the timestamp range plus the segment conclusion. Put supporting details inside the folded body using natural prose, short bullets, or brief caveats. Include transcript-backed specifics, examples, claims, or caveats where they materially help, but avoid mechanical labels unless the user explicitly asks for them.

Use this structure:

```text
Summary

One-paragraph answer-first summary naming the video's core conclusion.

Segment Conclusions

<details>
<summary>[mm:ss-mm:ss] Segment conclusion</summary>

Short paragraph or 2-4 concise bullets explaining the takeaway, the key supporting detail, and why it matters when useful.
</details>

<details>
<summary>[mm:ss-mm:ss] Segment conclusion</summary>

- Concise takeaway from this segment.
- Concrete transcript-backed detail, example, claim, or caveat.
</details>

Notes

- Caveats about subtitle quality, audio quality, uncertain terms, or incomplete transcript.
```

For video reports, each `<summary>` line must start with a bracketed timestamp or time range such as `[01:24-02:44]`, using the transcript's actual timing. Use `[hh:mm:ss-hh:mm:ss]` for videos longer than one hour. The report renderer and CLI Notion publisher convert bracketed timestamps into clickable source-video links that seek to the start time, so keep the timestamp at the beginning of each folded segment summary. When writing report content through the Notion connector Markdown path, avoid colons in the linked label because Notion can split the link; use an inline link like `[01m24s-02m44s](https://www.youtube.com/watch?v=VIDEO_ID&t=84)` instead of leaving it as plain text.

Finalize:

```bash
ytlt finalize "<video-folder>"
```

Finalization re-renders `report.html`, deletes any retained downloaded `video.*` media file, and refreshes the dashboard index. Continue into Notion publishing before responding unless the user explicitly asked for local-only output or Notion is unavailable.

## Notion Publishing

Use Notion publishing by default for bare video links and report requests. Skip it only when the user explicitly asks for local-only output, the environment has neither CLI Notion credentials nor a connected Notion app, or publishing fails after a reasonable retry. If skipped or blocked, state the reason in the final response and still return the local report path.

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
ytlt finalize "<video-folder>" --publish-notion
ytlt publish-notion "<video-folder>"
```

When Notion publishing succeeds, the JSON output includes `notion.notion_url`. Include that link in the final response alongside the local dashboard link. The publisher stores `notion_page_id`, `notion_url`, and `notion_synced_at` in `metadata.json`; later publishes update the same Notion page.

When running in Codex with a connected Notion app but no `NOTION_TOKEN`, use the Notion connector after `ytlt finalize`. Use the clean Notion database layout below. Do not claim the CLI wrote to Notion unless `--publish-notion` or `ytlt publish-notion` was used.

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
- `Duration Seconds` number
- `Summary` rich text
- `Local Report` rich text

Create database views:

- `Dashboard`: core columns, sorted by `Processed` descending.
- `All Reports`: same as Dashboard.
- `Captions`: filter `Transcript Source = manual_subtitle`.
- `Whisper`: filter `Transcript Source = local_whisper`.
- `Recent`: recent reports without status filtering.

For each report, create one database row as the only Notion report page. Put the report content directly inside that row page so opening `Name` shows metadata, source link, summary, segment conclusions, notes, and local report path. Keep full transcripts local unless the user explicitly asks to copy them into Notion.

Use this row body structure:

```text
## 摘要
One answer-first summary paragraph.

## 分段结论
<details>
<summary>[01m24s-02m44s](SOURCE_URL_WITH_t=84) Segment conclusion</summary>

Short paragraph or 2-4 concise bullets explaining the segment's takeaway with concrete transcript-backed details. Do not force `Point` / `Evidence` / `Implication` labels unless the user asks for that format.
</details>

## 备注
- Caveats about subtitles, transcription, uncertain terms, or source claims.

## 来源与本地文件
- Source: SOURCE_URL
- Platform: youtube | bilibili | video
- Channel: CHANNEL
- Published: DATE
- Transcript Source: manual_subtitle | auto_subtitle | local_whisper
- Local Report: /absolute/path/to/report.html
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

## Thread Title And Final Response

After reading `metadata.json`, derive the user-facing title from the source video's real title. If it is too long, trim it to a concise topic title of about 45-60 characters. Do not name the thread with generic workflow words such as `transcribe`, `caption`, `download`, or `youtube-local-transcribe`.

When a Codex thread-management tool is available and the current thread id can be resolved, rename the current thread to that concise video-topic title before the final response. If the thread id cannot be resolved, continue without blocking the report.

Final responses should use this shape:

```text
已完成：VIDEO_TITLE

Notion 报告：NOTION_ROW_URL
本地报告：/absolute/path/to/report.html

摘要：One concise answer-first paragraph.

分段结论

<details>
<summary>[mm:ss-mm:ss] Segment conclusion</summary>

Concise natural-language details, examples, or caveats from this segment.
</details>

<details>
<summary>[mm:ss-mm:ss] Segment conclusion</summary>

Concise natural-language details, examples, or caveats from this segment.
</details>

备注：Only include caveats or failures that affect trust in the result.
```

Keep this response compact. Include conversion/process details only when they change the outcome, explain a failure, or the user explicitly asks for them.

## Dashboard

Open or serve previous reports:

```bash
ytlt rebuild-index
ytlt serve --open
```

`ytlt serve` binds to `127.0.0.1` by default and opens a local dashboard of past reports. Do not expose the server publicly unless the user explicitly asks.

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
