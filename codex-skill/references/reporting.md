# Report Content

Read this reference after processing a video and before finalizing it.

## Summary

Write `<video-folder>/summary.md` in the user’s language unless another language was requested. Ground every claim in the complete transcript and use an answer-first structure:

```text
Summary

One paragraph stating the video’s core conclusion.

Key Points

- [mm:ss-mm:ss] Major conclusion, claim, method, risk, or decision.
  - [mm:ss-mm:ss] Supporting example, number, caveat, or subclaim when useful.
- [mm:ss-mm:ss] Another major point.

Notes

- Only subtitle, transcription, source-claim, or completeness caveats that affect trust.
```

Start every Key Point bullet, including nested bullets, with a real transcript timestamp or range. Use `[hh:mm:ss-hh:mm:ss]` for videos longer than one hour. Do not invent precision that the transcript does not support.

Avoid mechanical `Point / Evidence / Implication` labels. Use nested bullets only when they add material support.

For Notion connector Markdown, use timestamp links without colons in the label, for example:

```markdown
[01m24s-02m44s](https://www.youtube.com/watch?v=VIDEO_ID&t=84)
```

## Tags

Write 3–8 concise subject tags to `<video-folder>/tags.json`:

```json
{
  "tags": ["AI基础设施", "半导体", "光通信"]
}
```

Use only transcript-supported subjects, entities, industries, methods, or durable concepts. Merge synonyms and near-duplicates.

Exclude source and workflow labels such as `video`, `youtube`, `bilibili`, `video-report`, `video-to-notes`, `notion-import`, `manual_subtitle`, `auto_subtitle`, `local_whisper`, `summary`, and `transcript`. Do not use a channel name merely as provenance. If evidence is insufficient, write `{"tags": []}`.

## Long videos

For a transcript over roughly 45 minutes, divide candidate notes into contiguous timestamp ranges if that improves accuracy. Merge them into one coherent summary, remove repetition, and verify all timestamps against the full transcript before finalizing.

## Output contract

After finalization, the folder should contain:

- `metadata.json`: source, title, channel, platform, publish time, duration, processing time, and `transcript_source`
- `transcript.txt`: caption-derived or local Whisper transcript
- `summary.md`: grounded summary and timestamped Key Points
- `tags.json`: sanitized subject tags or an empty list
- `report.html`: final reader-facing local report

Valid `transcript_source` values are `manual_subtitle`, `auto_subtitle`, and `local_whisper`.

Run `video-to-notes finalize "VIDEO_FOLDER"` only after `summary.md` and `tags.json` are ready. Finalization re-renders the report, refreshes the dashboard, and deletes retained downloaded media.

Finalization and CLI publication reject an unsupported transcript source, an absent or blank transcript, a missing summary, or malformed/missing tags. These checks establish that required artifacts exist; they cannot prove that arbitrary text is an authentic transcript. Read the full acquired transcript and its provenance before summarizing. Preserve downloaded media when validation fails so the acquisition can be recovered.
