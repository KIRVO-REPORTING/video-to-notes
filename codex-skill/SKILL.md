---
name: video-to-notes
description: Use immediately for any bare YouTube or YouTube Shorts URL, youtu.be link, Bilibili or b23.tv link, or other video URL; do not ask what the user wants. Treat a message containing only a supported video URL as a request to create timestamped notes and a report, then publish to the configured local, Notion, or Obsidian target. Also use for video transcription, summaries, subtitles, reports, publishing, syncing, and dashboards.
---

# Video to Notes

Turn a supported video URL into a transcript-backed report. Prefer downloadable captions; use the configured local Whisper backend only when captions are missing or unusable.

## Non-negotiable behavior

- Treat a message containing only a supported video URL as a complete request. Start the full report workflow immediately; never reply with “What do you want me to do with this link?”
- Treat YouTube watch, Shorts, live, and `youtu.be` URLs equally. Preserve query parameters such as `t`, `list`, or tracking parameters when passing the URL to the processor.
- When the user states a narrower goal such as “only download,” “only translate,” or “only extract subtitles,” perform that goal instead of forcing the full report workflow.
- Do not ask for cookies, credentials, language, or output destination before the first safe attempt. Ask only after a concrete failure proves user input is required.
- Respect `<workspace>/config.json` preferences. If no configuration exists, use local output and mention configuration only after delivering the result.
- Read `metadata.json` and the complete `transcript.txt` before writing claims about the video.

## Bare URL workflow

1. Run `video-to-notes doctor --url "VIDEO_URL"` and use the workspace path it returns. A dependency-only `ready` result does not verify network access. Do not assume the current repository or shell directory is the video workspace. If the command is missing or doctor fails, follow [references/setup.md](references/setup.md).
2. Process into local artifacts first, regardless of the configured publishing target:

   ```bash
   video-to-notes process "VIDEO_URL" --environment local
   ```

   This prevents an incomplete report from being published before `summary.md` and `tags.json` exist.
3. Read the returned `metadata.json` and the entire `transcript.txt`.
4. Follow [references/reporting.md](references/reporting.md) to write grounded `summary.md` and `tags.json`.
5. Finalize only after both files are ready. Select exactly one route:
   - Local: `video-to-notes finalize "VIDEO_FOLDER" --environment local`
   - Notion with CLI credentials: `video-to-notes finalize "VIDEO_FOLDER" --environment notion`
   - Notion connector without CLI credentials: finalize with `--environment local`, then follow [references/notion.md](references/notion.md).
   - Obsidian: follow [references/obsidian.md](references/obsidian.md).
6. Return the primary reader-facing artifact: the Notion row URL, Obsidian note path/URI, or local `report.html`. Include the local report as the backing archive when publishing remotely.

Do not stop after `process`; its HTML is preliminary until the summary, tags, and `finalize` step are complete.

## Target selection

Read `preferences.output_environment` from `<workspace>/config.json` when it exists:

- `local`: finalize locally.
- `notion`: read [references/notion.md](references/notion.md) before publishing.
- `obsidian`: read [references/obsidian.md](references/obsidian.md) before publishing.

An explicit user destination overrides configuration for that run. If remote publishing is unavailable, keep the completed local report, state the exact publishing blocker, and return the local path. Never claim a remote sync succeeded unless a URL/path was returned by the publisher or connector.

## Failure handling

- A DNS, connection, or TLS failure is an acquisition failure, not evidence of absent captions. Follow [references/setup.md](references/setup.md) to diagnose it before changing cookies or Whisper settings. Respect the execution environment's network permissions; the skill cannot grant network access.
- If acquisition fails, do not fabricate metadata or put an article, summary, or source notice in `transcript.txt` to make finalization succeed. An author-published article may support a separately labeled article summary; it does not complete video transcription.
- If metadata extraction or captions fail because authentication is required, retry with available browser cookies. Ask the user only if no authorized cookie source is available.
- If captions are absent and Whisper is not configured, run `video-to-notes doctor`, then follow [references/setup.md](references/setup.md). Read [references/model-selection.md](references/model-selection.md) only when choosing or troubleshooting a backend/model. Do not ask what the link is for.
- If the source is private, deleted, region-restricted, or unsupported, report that specific reason and preserve any artifacts already created.
- Never substitute web-search snippets, page metadata, or a guessed summary for a missing transcript. If no transcript can be obtained, report the failure instead of inventing notes.
- If Notion or Obsidian publishing fails, do not discard or regenerate the completed local report.

## Existing reports and dashboards

For an already processed folder, update `summary.md` or `tags.json` if requested and run:

```bash
video-to-notes finalize "VIDEO_FOLDER"
```

For dashboard work:

```bash
video-to-notes rebuild-index
video-to-notes serve --open
```

Keep the server bound to `127.0.0.1` unless the user explicitly requests public exposure.

## Progress and final response

Keep progress updates short and outcome-oriented. Do not dump download, codec, conversion, or file-by-file logs unless they explain a failure.

When a thread-title tool is available, rename the task using the real video topic rather than generic words such as “transcribe” or “video-to-notes”. Do not block completion when task renaming is unavailable.

Use a compact final response:

```text
Completed: VIDEO_TITLE

Report: PRIMARY_REPORT_URL_OR_PATH
Local report: /absolute/path/to/report.html  # include for remote targets

Summary: One concise answer-first paragraph.

Key Points
- [mm:ss-mm:ss] Main point.
- [mm:ss-mm:ss] Second point.

Notes: Only trust-affecting caveats or publishing failures.
```

Do not paste the full transcript into chat; keep it in the report or configured publishing target.
