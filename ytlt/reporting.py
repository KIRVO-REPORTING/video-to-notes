from __future__ import annotations

import datetime as dt
import html
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}
SUMMARY_FILENAME = "summary.md"
LEGACY_SUMMARY_FILENAME = "summary.txt"
TIMESTAMP_RE = re.compile(
    r"\[(?P<start>\d{1,2}:\d{2}(?::\d{2})?)(?:-(?P<end>\d{1,2}:\d{2}(?::\d{2})?))?\]"
)
SUMMARY_SECTION_HEADINGS = {
    "summary",
    "key points",
    "segment conclusions",
    "notes",
    "摘要",
    "关键点",
    "分段结论",
    "备注",
}
DETAILS_OPEN_RE = re.compile(r"^<details(?:\s[^>]*)?>$", re.IGNORECASE)
DETAILS_CLOSE_RE = re.compile(r"^</details>$", re.IGNORECASE)
SUMMARY_TAG_RE = re.compile(r"^<summary>(?P<text>.*?)</summary>$", re.IGNORECASE)


def slugify(value: str, max_length: int = 72) -> str:
    value = re.sub(r"\s+", "-", value.strip().lower())
    value = re.sub(r"[^\w.-]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"-{2,}", "-", value).strip("-._")
    return (value[:max_length].strip("-._") or "video")


def parse_upload_date(value: str | None) -> str:
    if not value:
        return "unknown-date"
    if re.fullmatch(r"\d{8}", value):
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def timestamp_to_iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return dt.datetime.fromtimestamp(int(value), tz=dt.timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def platform_from_url(url: str) -> str:
    lowered = url.lower()
    if "bilibili.com" in lowered or "b23.tv" in lowered:
        return "bilibili"
    if "youtube.com" in lowered or "youtu.be" in lowered:
        return "youtube"
    return "video"


def timestamp_to_seconds(value: str) -> int | None:
    parts = value.split(":")
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None
    if len(numbers) == 2:
        minutes, seconds = numbers
        return minutes * 60 + seconds
    if len(numbers) == 3:
        hours, minutes, seconds = numbers
        return hours * 3600 + minutes * 60 + seconds
    return None


def source_url_at_time(source_url: str | None, seconds: int) -> str | None:
    if not source_url:
        return None
    parts = urlsplit(source_url)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "t"]
    query.append(("t", str(max(0, seconds))))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def is_summary_section_heading(value: str) -> bool:
    return value.strip().lower() in SUMMARY_SECTION_HEADINGS


def render_inline(text: str, source_url: str | None = None) -> str:
    rendered: list[str] = []
    cursor = 0
    for match in TIMESTAMP_RE.finditer(text):
        rendered.append(html.escape(text[cursor : match.start()]))
        timestamp_text = match.group(0)
        seconds = timestamp_to_seconds(match.group("start"))
        timestamp_url = source_url_at_time(source_url, seconds) if seconds is not None else None
        if timestamp_url:
            rendered.append(
                '<a class="timestamp-link" href="'
                f'{html.escape(timestamp_url, quote=True)}" target="_blank" rel="noopener">'
                f"{html.escape(timestamp_text)}</a>"
            )
        else:
            rendered.append(html.escape(timestamp_text))
        cursor = match.end()
    rendered.append(html.escape(text[cursor:]))
    return "".join(rendered)


def normalize_metadata(info: dict[str, Any], url: str, *, transcript_source: str) -> dict[str, Any]:
    upload_date = parse_upload_date(info.get("upload_date"))
    source_url = info.get("webpage_url") or info.get("original_url") or url
    return {
        "id": info.get("id") or "unknown-id",
        "platform": platform_from_url(source_url),
        "title": info.get("title") or "Untitled video",
        "source_url": source_url,
        "channel": info.get("channel") or info.get("uploader"),
        "channel_url": info.get("channel_url") or info.get("uploader_url"),
        "duration_seconds": info.get("duration"),
        "upload_date": upload_date,
        "published_at": timestamp_to_iso(info.get("release_timestamp"))
        or timestamp_to_iso(info.get("timestamp"))
        or upload_date,
        "processed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "transcript_source": transcript_source,
    }


def make_video_folder(output_root: Path, metadata: dict[str, Any]) -> Path:
    folder_name = (
        f"{metadata['upload_date']}_{metadata['platform']}_{metadata['id']}_"
        f"{slugify(str(metadata['title']))}"
    )
    folder = output_root / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def render_summary(text: str, source_url: str | None = None) -> str:
    if not text.strip():
        return '<p class="muted">Summary pending. Write summary.md and run video-to-notes finalize.</p>'

    return _render_summary_lines(text.splitlines(), source_url)


def _render_summary_lines(lines: list[str], source_url: str | None = None) -> str:
    blocks: list[str] = []
    paragraph: list[str] = []
    bullets: list[tuple[str, list[str]]] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            blocks.append(f"<p>{render_inline(' '.join(paragraph), source_url)}</p>")
            paragraph = []

    def flush_bullets() -> None:
        nonlocal bullets
        if bullets:
            items: list[str] = []
            for item, children in bullets:
                rendered_item = render_inline(item, source_url)
                if children:
                    child_items = "\n".join(
                        f"<li>{render_inline(child, source_url)}</li>" for child in children
                    )
                    items.append(f"<li>{rendered_item}\n<ul>\n{child_items}\n</ul>\n</li>")
                else:
                    items.append(f"<li>{rendered_item}</li>")
            joined_items = "\n".join(items)
            blocks.append(f"<ul>\n{joined_items}\n</ul>")
            bullets = []

    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            flush_bullets()
            index += 1
            continue
        bullet = _bullet_line(raw_line)
        if bullet:
            flush_paragraph()
            level, text = bullet
            if level > 0 and bullets:
                bullets[-1][1].append(text)
            else:
                bullets.append((text, []))
            index += 1
            continue
        if DETAILS_OPEN_RE.match(line):
            flush_paragraph()
            flush_bullets()
            details_html, index = _render_details_block(lines, index, source_url)
            blocks.append(details_html)
            continue
        if is_summary_section_heading(line):
            flush_paragraph()
            flush_bullets()
            blocks.append(f"<h2>{html.escape(line)}</h2>")
        elif line.startswith("### "):
            flush_paragraph()
            flush_bullets()
            blocks.append(f"<h3>{html.escape(line[4:].strip())}</h3>")
        elif line.startswith("## "):
            flush_paragraph()
            flush_bullets()
            blocks.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
        else:
            flush_bullets()
            paragraph.append(line)
        index += 1

    flush_paragraph()
    flush_bullets()
    return "\n".join(blocks)


def _bullet_line(raw_line: str) -> tuple[int, str] | None:
    expanded = raw_line.expandtabs(2)
    stripped = expanded.lstrip(" ")
    if not stripped.startswith("- "):
        return None
    indent = len(expanded) - len(stripped)
    return (1 if indent >= 2 else 0, stripped[2:].strip())


def _render_details_block(
    lines: list[str],
    start_index: int,
    source_url: str | None = None,
) -> tuple[str, int]:
    index = start_index + 1
    summary = "Details"
    if index < len(lines):
        summary_match = SUMMARY_TAG_RE.match(lines[index].strip())
        if summary_match:
            summary = summary_match.group("text").strip() or summary
            index += 1

    body_lines: list[str] = []
    depth = 1
    while index < len(lines):
        line = lines[index].strip()
        if DETAILS_OPEN_RE.match(line):
            depth += 1
        elif DETAILS_CLOSE_RE.match(line):
            depth -= 1
            if depth == 0:
                index += 1
                break
        body_lines.append(lines[index])
        index += 1

    body = _render_summary_lines(body_lines, source_url) if body_lines else ""
    return (
        '<details class="segment-detail">\n'
        f"<summary>{render_inline(summary, source_url)}</summary>\n"
        f'<div class="details-body">\n{body}\n</div>\n'
        "</details>",
        index,
    )


def build_report_html(metadata: dict[str, Any], summary: str, transcript: str) -> str:
    title = html.escape(str(metadata.get("title") or "Untitled video"))
    source_url = html.escape(str(metadata.get("source_url") or ""), quote=True)
    rows = [
        ("Source", f'<a href="{source_url}">{source_url}</a>' if source_url else "Unknown"),
        ("Video ID", f"<code>{html.escape(str(metadata.get('id') or 'Unknown'))}</code>"),
        ("Platform", html.escape(str(metadata.get("platform") or "Unknown"))),
        ("Channel", html.escape(str(metadata.get("channel") or "Unknown"))),
        ("Published", html.escape(str(metadata.get("published_at") or metadata.get("upload_date") or "Unknown"))),
        ("Duration", f"{html.escape(str(metadata.get('duration_seconds') or 'Unknown'))} seconds"),
        ("Processed", html.escape(str(metadata.get("processed_at") or "Unknown"))),
        ("Transcript source", html.escape(str(metadata.get("transcript_source") or "Unknown"))),
        ("Transcript file", f"<code>{html.escape(str(metadata.get('transcript_file', 'transcript.txt')))}</code>"),
    ]
    if metadata.get("processing_seconds") not in (None, ""):
        rows.insert(-2, ("Processing time", f"{html.escape(str(metadata.get('processing_seconds')))} seconds"))
    metadata_rows = "\n".join(f"<tr><th>{label}</th><td>{value}</td></tr>" for label, value in rows)
    transcript_text = html.escape(transcript.strip())
    summary_html = render_summary(summary, str(metadata.get("source_url") or ""))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light; --ink: #1f2933; --muted: #667085; --line: #d9e2ec; --paper: #ffffff; --bg: #f6f8fb; --accent: #0f766e; --warn: #9a3412; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.65; color: var(--ink); background: var(--bg); }}
    main {{ max-width: 980px; margin: 0 auto; padding: 36px 22px 64px; background: var(--paper); min-height: 100vh; }}
    h1 {{ font-size: clamp(24px, 3vw, 34px); line-height: 1.25; margin: 0 0 18px; letter-spacing: 0; }}
    h2 {{ margin-top: 34px; border-bottom: 1px solid var(--line); padding-bottom: 8px; font-size: 21px; }}
    h3 {{ margin-top: 22px; font-size: 17px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 18px 0 28px; }}
    th, td {{ border-bottom: 1px solid #e6ebf1; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ width: 160px; color: var(--muted); font-weight: 650; }}
    a {{ color: #0b63ce; }}
    .timestamp-link {{ font-variant-numeric: tabular-nums; font-weight: 650; text-decoration-thickness: 1px; }}
    details.segment-detail {{ border: 1px solid #d8dee8; border-radius: 8px; margin: 12px 0; background: #fbfcfe; }}
    details.segment-detail summary {{ cursor: pointer; padding: 10px 12px; font-weight: 700; line-height: 1.45; }}
    details.segment-detail[open] summary {{ border-bottom: 1px solid #e6ebf1; }}
    .details-body {{ padding: 10px 14px 14px; }}
    .details-body > :first-child {{ margin-top: 0; }}
    .details-body > :last-child {{ margin-bottom: 0; }}
    code {{ background: #eef2f7; border-radius: 4px; padding: 1px 5px; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 18px; }}
    .muted {{ color: var(--muted); }}
    .source-pill {{ display: inline-flex; align-items: center; gap: 6px; border: 1px solid #99f6e4; background: #ecfdf5; color: #115e59; border-radius: 999px; padding: 4px 10px; font-size: 13px; margin-bottom: 16px; }}
  </style>
</head>
<body>
<main>
  <div class="source-pill">{html.escape(str(metadata.get("transcript_source") or "unknown"))}</div>
  <h1>{title}</h1>
  <table>
{metadata_rows}
  </table>
  <section class="summary">
{summary_html}
  </section>
  <h2>Transcript</h2>
  <pre>{transcript_text}</pre>
</main>
</body>
</html>
"""


def write_report(folder: Path, metadata: dict[str, Any]) -> Path:
    transcript_path = folder / "transcript.txt"
    summary_path = migrate_summary_file(folder)
    transcript = transcript_path.read_text(encoding="utf-8-sig") if transcript_path.exists() else ""
    summary = summary_path.read_text(encoding="utf-8-sig") if summary_path.exists() else ""
    report = folder / "report.html"
    report.write_text(build_report_html(metadata, summary, transcript), encoding="utf-8")
    return report


def summary_file_path(folder: Path) -> Path:
    preferred = folder / SUMMARY_FILENAME
    if preferred.exists():
        return preferred
    legacy = folder / LEGACY_SUMMARY_FILENAME
    if legacy.exists():
        return legacy
    return preferred


def migrate_summary_file(folder: Path) -> Path:
    preferred = folder / SUMMARY_FILENAME
    legacy = folder / LEGACY_SUMMARY_FILENAME
    if preferred.exists() or not legacy.exists():
        return summary_file_path(folder)
    legacy.replace(preferred)
    return preferred


def delete_video_files(folder: Path, metadata: dict[str, Any]) -> list[str]:
    candidates: list[Path] = []
    video_file = metadata.get("video_file")
    if video_file:
        candidates.append(folder / str(video_file))
    candidates.extend(path for path in folder.glob("video.*") if path.suffix.lower() in VIDEO_EXTENSIONS)

    deleted: list[str] = []
    seen: set[Path] = set()
    for candidate in candidates:
        path = candidate.resolve()
        if path in seen or path.parent != folder.resolve():
            continue
        seen.add(path)
        if path.is_file():
            path.unlink()
            deleted.append(path.name)
    return deleted


def read_metadata(folder: Path) -> dict[str, Any] | None:
    path = folder / "metadata.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return None


def summary_preview(folder: Path, limit: int = 220) -> str:
    path = migrate_summary_file(folder)
    if not path.exists():
        return ""
    text = re.sub(r"\s+", " ", path.read_text(encoding="utf-8-sig")).strip()
    return text[:limit].rstrip() + ("..." if len(text) > limit else "")


def rebuild_index(workspace: Path) -> dict[str, Any]:
    processed = workspace / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    reports: list[dict[str, Any]] = []
    for folder in sorted(path for path in processed.iterdir() if path.is_dir()):
        metadata = read_metadata(folder)
        if not metadata:
            continue
        report_path = folder / "report.html"
        transcript_path = folder / "transcript.txt"
        reports.append(
            {
                "folder": folder.name,
                "title": metadata.get("title") or folder.name,
                "channel": metadata.get("channel"),
                "platform": metadata.get("platform"),
                "source_url": metadata.get("source_url"),
                "published_at": metadata.get("published_at") or metadata.get("upload_date"),
                "processed_at": metadata.get("processed_at") or metadata.get("downloaded_at"),
                "duration_seconds": metadata.get("duration_seconds"),
                "transcript_source": metadata.get("transcript_source"),
                "summary_preview": summary_preview(folder),
                "report_exists": report_path.exists(),
                "transcript_exists": transcript_path.exists(),
                "report_path": str(report_path),
            }
        )
    reports.sort(key=lambda item: str(item.get("processed_at") or ""), reverse=True)
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "workspace": str(workspace),
        "reports": reports,
    }
    (workspace / "index.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (workspace / "dashboard.html").write_text(build_dashboard_html(payload), encoding="utf-8")
    return payload


def build_dashboard_html(index: dict[str, Any]) -> str:
    data = json.dumps(index.get("reports", []), ensure_ascii=False)
    generated_at = html.escape(str(index.get("generated_at") or ""))
    workspace = html.escape(str(index.get("workspace") or ""))
    count = len(index.get("reports", []))
    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Video Reports</title>
  <link rel="icon" href="data:,">
  <style>
    :root {
      color-scheme: light;
      --ink: #232529;
      --muted: #6b6f76;
      --faint: #9da3ad;
      --line: #e3e5e8;
      --line-strong: #d0d4da;
      --bg: #f7f7f5;
      --paper: #ffffff;
      --hover: #f1f1ef;
      --blue: #2563eb;
      --green-bg: #edf7ed;
      --green-ink: #2f6f44;
      --orange-bg: #fbf0df;
      --orange-ink: #9a5a18;
      --purple-bg: #f2effa;
      --purple-ink: #694e9e;
      --gray-bg: #eeeeec;
      --gray-ink: #555b62;
      --red-bg: #faecec;
      --red-ink: #9b3434;
    }
    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
      letter-spacing: 0;
    }
    a { color: inherit; }
    .shell {
      width: min(100%, 1480px);
      margin: 0 auto;
      padding: 28px 28px 42px;
    }
    header {
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: flex-start;
      margin-bottom: 20px;
    }
    h1 {
      margin: 0;
      font-size: 30px;
      line-height: 1.2;
      font-weight: 720;
      letter-spacing: 0;
    }
    .workspace {
      color: var(--muted);
      font-size: 12px;
      margin-top: 7px;
      overflow-wrap: anywhere;
    }
    .generated {
      color: var(--muted);
      font-size: 12px;
      text-align: right;
      white-space: nowrap;
      padding-top: 8px;
    }
    .viewbar {
      display: flex;
      gap: 6px;
      margin-bottom: 12px;
      border-bottom: 1px solid var(--line);
      overflow-x: auto;
    }
    .view-tab {
      appearance: none;
      border: 0;
      border-bottom: 2px solid transparent;
      background: transparent;
      color: var(--muted);
      cursor: pointer;
      font: inherit;
      font-size: 14px;
      padding: 9px 10px 8px;
      white-space: nowrap;
    }
    .view-tab[aria-pressed="true"] {
      color: var(--ink);
      border-bottom-color: var(--ink);
      font-weight: 650;
    }
    .toolbar {
      display: grid;
      grid-template-columns: minmax(260px, 1fr) 160px 160px 170px;
      gap: 8px;
      margin-bottom: 12px;
    }
    input, select {
      min-width: 0;
      width: 100%;
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--paper);
      color: var(--ink);
      font: inherit;
      font-size: 13px;
      padding: 6px 9px;
    }
    input:focus, select:focus {
      outline: 2px solid rgba(37, 99, 235, .18);
      border-color: #8fb2ff;
    }
    .database {
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 6px;
      overflow: hidden;
    }
    .table-wrap {
      overflow: auto;
      max-height: calc(100vh - 210px);
    }
    table {
      width: 100%;
      min-width: 1240px;
      border-collapse: separate;
      border-spacing: 0;
      table-layout: fixed;
      font-size: 13px;
    }
    thead th {
      position: sticky;
      top: 0;
      z-index: 2;
      height: 34px;
      background: var(--paper);
      border-bottom: 1px solid var(--line-strong);
      border-right: 1px solid var(--line);
      color: var(--muted);
      font-weight: 600;
      text-align: left;
      padding: 0;
      white-space: nowrap;
    }
    thead th:last-child, tbody td:last-child { border-right: 0; }
    th button {
      width: 100%;
      height: 100%;
      appearance: none;
      border: 0;
      background: transparent;
      color: inherit;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 0 10px;
      font: inherit;
      text-align: left;
    }
    th button:hover { background: var(--hover); }
    tbody tr { background: var(--paper); }
    tbody tr:hover { background: #fbfbfa; }
    tbody td {
      height: 42px;
      border-bottom: 1px solid var(--line);
      border-right: 1px solid var(--line);
      padding: 7px 10px;
      vertical-align: middle;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    tbody tr:last-child td { border-bottom: 0; }
    .col-name { width: 330px; }
    .col-status { width: 120px; }
    .col-platform { width: 118px; }
    .col-source { width: 145px; }
    .col-channel { width: 180px; }
    .col-date { width: 132px; }
    .col-duration { width: 92px; }
    .col-processed { width: 132px; }
    .col-summary { width: 360px; }
    .title-link {
      display: block;
      color: var(--ink);
      text-decoration: none;
      font-weight: 560;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .title-link:hover { color: var(--blue); text-decoration: underline; text-underline-offset: 2px; }
    .muted { color: var(--muted); }
    .summary-cell {
      color: #4d535b;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      max-width: 100%;
      border-radius: 4px;
      padding: 2px 7px;
      font-size: 12px;
      line-height: 18px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .status-ready { background: var(--green-bg); color: var(--green-ink); }
    .status-incomplete { background: var(--red-bg); color: var(--red-ink); }
    .platform-youtube { background: var(--red-bg); color: var(--red-ink); }
    .platform-bilibili { background: var(--purple-bg); color: var(--purple-ink); }
    .platform-video { background: var(--gray-bg); color: var(--gray-ink); }
    .source-manual_subtitle, .source-auto_subtitle { background: var(--green-bg); color: var(--green-ink); }
    .source-local_whisper, .source-unknown { background: var(--orange-bg); color: var(--orange-ink); }
    .footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 14px;
      min-height: 38px;
      color: var(--muted);
      font-size: 12px;
      padding: 9px 11px;
      border-top: 1px solid var(--line);
      background: #fcfcfb;
    }
    .empty {
      color: var(--muted);
      padding: 28px 10px;
      text-align: center;
    }
    @media (max-width: 820px) {
      .shell { padding: 20px 14px 32px; }
      header { display: block; }
      .generated { text-align: left; white-space: normal; }
      h1 { font-size: 26px; }
      .toolbar { grid-template-columns: 1fr; }
      .table-wrap { max-height: none; }
    }
  </style>
</head>
<body>
<main class="shell">
  <header>
    <div>
      <h1>Video Reports</h1>
      <div class="workspace">__COUNT__ reports | __WORKSPACE__</div>
    </div>
    <div class="generated">Updated __GENERATED_AT__</div>
  </header>
  <nav class="viewbar" aria-label="Database views">
    <button class="view-tab" type="button" data-view="all" aria-pressed="true">All</button>
    <button class="view-tab" type="button" data-view="recent" aria-pressed="false">Recent</button>
    <button class="view-tab" type="button" data-view="captions" aria-pressed="false">Captions</button>
    <button class="view-tab" type="button" data-view="whisper" aria-pressed="false">Whisper</button>
    <button class="view-tab" type="button" data-view="incomplete" aria-pressed="false">Incomplete</button>
  </nav>
  <div class="toolbar">
    <input id="q" type="search" placeholder="Search reports">
    <select id="platform"></select>
    <select id="source"></select>
    <select id="sort"></select>
  </div>
  <section class="database" aria-label="Video report database">
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th class="col-name"><button type="button" data-sort="title">Name <span data-arrow="title"></span></button></th>
            <th class="col-status"><button type="button" data-sort="status">Status <span data-arrow="status"></span></button></th>
            <th class="col-platform"><button type="button" data-sort="platform">Platform <span data-arrow="platform"></span></button></th>
            <th class="col-source"><button type="button" data-sort="source">Source <span data-arrow="source"></span></button></th>
            <th class="col-channel"><button type="button" data-sort="channel">Channel <span data-arrow="channel"></span></button></th>
            <th class="col-date"><button type="button" data-sort="published">Published <span data-arrow="published"></span></button></th>
            <th class="col-duration"><button type="button" data-sort="duration">Length <span data-arrow="duration"></span></button></th>
            <th class="col-processed"><button type="button" data-sort="processed">Processed <span data-arrow="processed"></span></button></th>
            <th class="col-summary"><button type="button" data-sort="summary">Summary <span data-arrow="summary"></span></button></th>
          </tr>
        </thead>
        <tbody id="rows"></tbody>
      </table>
      <div class="empty" id="empty" hidden>No matching reports.</div>
    </div>
    <div class="footer">
      <span id="result-count"></span>
      <span id="visible-view"></span>
    </div>
  </section>
<script>
const reports = __REPORTS__;
const rows = document.getElementById('rows');
const empty = document.getElementById('empty');
const resultCount = document.getElementById('result-count');
const q = document.getElementById('q');
const platform = document.getElementById('platform');
const source = document.getElementById('source');
const sortSelect = document.getElementById('sort');
const tabs = Array.from(document.querySelectorAll('.view-tab'));
const visibleView = document.getElementById('visible-view');
let state = {
  view: 'all',
  sort: 'processed',
  direction: 'desc'
};

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}

function reportHref(item) {
  return `processed/${encodeURIComponent(item.folder)}/report.html`;
}

function unique(values) {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) => String(a).localeCompare(String(b)));
}

function labelSource(value) {
  return {
    manual_subtitle: 'Manual captions',
    auto_subtitle: 'Auto captions',
    local_whisper: 'Local Whisper',
    unknown: 'Unknown'
  }[value || 'unknown'] || value;
}

function status(item) {
  return item.report_exists && item.transcript_exists ? 'Ready' : 'Incomplete';
}

function sourceKey(item) {
  return item.transcript_source || 'unknown';
}

function platformKey(item) {
  return item.platform || 'video';
}

function shortDate(value) {
  if (!value) return '';
  const text = String(value);
  return text.length >= 10 ? text.slice(0, 10) : text;
}

function durationLabel(seconds) {
  const total = Number(seconds);
  if (!Number.isFinite(total) || total <= 0) return '';
  const rounded = Math.round(total);
  const h = Math.floor(rounded / 3600);
  const m = Math.floor((rounded % 3600) / 60);
  const s = rounded % 60;
  if (h) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function sortValue(item, key) {
  if (key === 'status') return status(item);
  if (key === 'source') return labelSource(sourceKey(item));
  if (key === 'published') return item.published_at || '';
  if (key === 'processed') return item.processed_at || '';
  if (key === 'duration') return Number(item.duration_seconds || 0);
  if (key === 'summary') return item.summary_preview || '';
  if (key === 'platform') return platformKey(item);
  return item[key] || '';
}

function populateFilters() {
  const platforms = unique(reports.map(platformKey));
  const sources = unique(reports.map(sourceKey));
  platform.innerHTML = '<option value="">All platforms</option>' +
    platforms.map(value => `<option value="${esc(value)}">${esc(value)}</option>`).join('');
  source.innerHTML = '<option value="">All sources</option>' +
    sources.map(value => `<option value="${esc(value)}">${esc(labelSource(value))}</option>`).join('');
  sortSelect.innerHTML = [
    ['processed:desc', 'Newest processed'],
    ['published:desc', 'Newest published'],
    ['title:asc', 'Name A-Z'],
    ['status:asc', 'Status'],
    ['platform:asc', 'Platform'],
    ['source:asc', 'Source'],
    ['duration:desc', 'Longest'],
    ['channel:asc', 'Channel A-Z']
  ].map(([value, label]) => `<option value="${value}">${label}</option>`).join('');
}

function matchesView(item) {
  if (state.view === 'recent') {
    const processed = Date.parse(item.processed_at || '');
    return Number.isFinite(processed) && Date.now() - processed <= 1000 * 60 * 60 * 24 * 14;
  }
  if (state.view === 'captions') return ['manual_subtitle', 'auto_subtitle'].includes(sourceKey(item));
  if (state.view === 'whisper') return sourceKey(item) === 'local_whisper' || sourceKey(item) === 'unknown';
  if (state.view === 'incomplete') return status(item) === 'Incomplete';
  return true;
}

function filteredReports() {
  const needle = q.value.trim().toLowerCase();
  const platformValue = platform.value;
  const sourceValue = source.value;
  return reports.filter(item => {
    const haystack = [item.title, item.channel, item.summary_preview, item.platform, labelSource(sourceKey(item))]
      .join(' ')
      .toLowerCase();
    return matchesView(item)
      && (!needle || haystack.includes(needle))
      && (!platformValue || platformKey(item) === platformValue)
      && (!sourceValue || sourceKey(item) === sourceValue);
  }).sort((a, b) => {
    const av = sortValue(a, state.sort);
    const bv = sortValue(b, state.sort);
    const result = typeof av === 'number' && typeof bv === 'number'
      ? av - bv
      : String(av).localeCompare(String(bv), undefined, {numeric: true, sensitivity: 'base'});
    return state.direction === 'asc' ? result : -result;
  });
}

function renderArrows() {
  document.querySelectorAll('[data-arrow]').forEach(el => {
    el.textContent = el.dataset.arrow === state.sort ? (state.direction === 'asc' ? '^' : 'v') : '';
  });
}

function render() {
  const items = filteredReports();
  rows.innerHTML = items.map(item => {
    const statusValue = status(item);
    const sourceValue = sourceKey(item);
    const platformValue = platformKey(item);
    return `
      <tr>
        <td><a class="title-link" href="${reportHref(item)}">${esc(item.title || item.folder)}</a></td>
        <td><span class="pill status-${statusValue.toLowerCase()}">${statusValue}</span></td>
        <td><span class="pill platform-${esc(platformValue)}">${esc(platformValue)}</span></td>
        <td><span class="pill source-${esc(sourceValue)}">${esc(labelSource(sourceValue))}</span></td>
        <td title="${esc(item.channel || '')}">${esc(item.channel || '')}</td>
        <td class="muted">${esc(shortDate(item.published_at))}</td>
        <td class="muted">${esc(durationLabel(item.duration_seconds))}</td>
        <td class="muted">${esc(shortDate(item.processed_at))}</td>
        <td><div class="summary-cell" title="${esc(item.summary_preview || '')}">${esc(item.summary_preview || 'Summary pending.')}</div></td>
      </tr>
    `;
  }).join('');
  resultCount.textContent = `${items.length} of ${reports.length} reports`;
  visibleView.textContent = state.view.charAt(0).toUpperCase() + state.view.slice(1);
  empty.hidden = items.length !== 0;
  renderArrows();
}

q.addEventListener('input', render);
platform.addEventListener('input', render);
source.addEventListener('input', render);
sortSelect.addEventListener('input', () => {
  const [sort, direction] = sortSelect.value.split(':');
  state.sort = sort;
  state.direction = direction;
  render();
});
tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    state.view = tab.dataset.view;
    tabs.forEach(item => item.setAttribute('aria-pressed', String(item === tab)));
    render();
  });
});
document.querySelectorAll('th button[data-sort]').forEach(button => {
  button.addEventListener('click', () => {
    const sort = button.dataset.sort;
    if (state.sort === sort) {
      state.direction = state.direction === 'asc' ? 'desc' : 'asc';
    } else {
      state.sort = sort;
      state.direction = ['title', 'channel', 'platform', 'source', 'status', 'summary'].includes(sort) ? 'asc' : 'desc';
    }
    sortSelect.value = `${state.sort}:${state.direction}`;
    render();
  });
});

populateFilters();
render();
</script>
</main>
</body>
</html>
"""
    return (
        template.replace("__REPORTS__", data)
        .replace("__GENERATED_AT__", generated_at)
        .replace("__WORKSPACE__", workspace)
        .replace("__COUNT__", str(count))
    )
