from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .reporting import (
    TIMESTAMP_RE,
    is_summary_section_heading,
    read_metadata,
    source_url_at_time,
    summary_file_path,
    summary_preview,
    timestamp_to_seconds,
)


DEFAULT_REPORTS_DIR = "Video Reports"
DEFAULT_INDEX_NOTE = "Video Reports Dashboard.md"


class ObsidianError(RuntimeError):
    pass


@dataclass(frozen=True)
class ObsidianPublishConfig:
    vault_path: Path
    reports_dir: str = DEFAULT_REPORTS_DIR
    index_note: str = DEFAULT_INDEX_NOTE
    include_transcript: bool = True

    @classmethod
    def from_values(
        cls,
        *,
        vault_path: str | Path | None = None,
        reports_dir: str | None = None,
        index_note: str | None = None,
        include_transcript: bool = True,
    ) -> "ObsidianPublishConfig":
        resolved_vault = vault_path or os.environ.get("OBSIDIAN_VAULT_PATH") or os.environ.get("OBSIDIAN_VAULT")
        if not resolved_vault:
            raise ObsidianError("Set OBSIDIAN_VAULT_PATH or pass --obsidian-vault before publishing to Obsidian.")

        resolved_reports_dir = reports_dir or os.environ.get("OBSIDIAN_REPORTS_DIR") or DEFAULT_REPORTS_DIR
        resolved_index_note = index_note or os.environ.get("OBSIDIAN_INDEX_NOTE") or DEFAULT_INDEX_NOTE
        if not str(resolved_index_note).lower().endswith(".md"):
            resolved_index_note = f"{resolved_index_note}.md"

        return cls(
            vault_path=Path(resolved_vault).expanduser().resolve(),
            reports_dir=str(resolved_reports_dir),
            index_note=str(resolved_index_note),
            include_transcript=include_transcript,
        )


def publish_report_to_obsidian(
    folder: Path,
    config: ObsidianPublishConfig,
    *,
    workspace: Path | None = None,
    update_index: bool = True,
) -> dict[str, Any]:
    folder = folder.expanduser().resolve()
    metadata = read_metadata(folder)
    if not metadata:
        raise ObsidianError(f"Missing or invalid metadata.json in {folder}")

    vault = config.vault_path.expanduser().resolve()
    reports_dir = _safe_child_path(vault, config.reports_dir, default=DEFAULT_REPORTS_DIR, expect_file=False)
    index_note = _safe_child_path(vault, config.index_note, default=DEFAULT_INDEX_NOTE, expect_file=True)
    vault.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    index_note.parent.mkdir(parents=True, exist_ok=True)

    note_path = _report_note_path(vault, reports_dir, folder, metadata)
    note_path.parent.mkdir(parents=True, exist_ok=True)
    synced_at = dt.datetime.now(dt.timezone.utc).isoformat()
    note_path.write_text(
        report_markdown(folder, metadata, workspace=workspace, include_transcript=config.include_transcript),
        encoding="utf-8",
    )

    result = {
        "obsidian_note_path": str(note_path),
        "obsidian_note_uri": _obsidian_uri(note_path),
        "obsidian_index_note_path": str(index_note),
        "obsidian_vault_path": str(vault),
        "obsidian_reports_dir": str(reports_dir.relative_to(vault)),
        "obsidian_synced_at": synced_at,
        "obsidian_sync_method": "ytlt_cli_vault",
    }
    metadata.update({key: value for key, value in result.items() if value})
    (folder / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if update_index:
        write_obsidian_index(vault, reports_dir, index_note)

    return result


def sync_workspace_to_obsidian(
    workspace: Path,
    config: ObsidianPublishConfig,
    *,
    include_tests: bool = False,
) -> dict[str, Any]:
    workspace = workspace.expanduser().resolve()
    vault = config.vault_path.expanduser().resolve()
    reports_dir = _safe_child_path(vault, config.reports_dir, default=DEFAULT_REPORTS_DIR, expect_file=False)
    index_note = _safe_child_path(vault, config.index_note, default=DEFAULT_INDEX_NOTE, expect_file=True)
    folders = list(_iter_report_folders(workspace, include_tests=include_tests))
    results = [
        publish_report_to_obsidian(folder, config, workspace=workspace, update_index=False)
        for folder in folders
    ]
    write_obsidian_index(vault, reports_dir, index_note)
    return {
        "obsidian_vault_path": str(vault),
        "obsidian_reports_dir": str(reports_dir.relative_to(vault)),
        "obsidian_index_note_path": str(index_note),
        "obsidian_index_note_uri": _obsidian_uri(index_note),
        "reports": len(results),
        "notes": [item["obsidian_note_path"] for item in results],
    }


def report_markdown(
    folder: Path,
    metadata: dict[str, Any],
    *,
    workspace: Path | None = None,
    include_transcript: bool = True,
) -> str:
    source_url = str(metadata.get("source_url") or "")
    summary_path = summary_file_path(folder)
    summary = summary_path.read_text(encoding="utf-8-sig") if summary_path.exists() else ""
    transcript_path = folder / str(metadata.get("transcript_file") or "transcript.txt")
    transcript = transcript_path.read_text(encoding="utf-8-sig") if transcript_path.exists() else ""
    local_report = folder / "report.html"

    frontmatter = _frontmatter(
        {
            "ytlt_id": metadata.get("id"),
            "title": metadata.get("title") or folder.name,
            "platform": metadata.get("platform"),
            "source_url": source_url,
            "channel": metadata.get("channel"),
            "published": metadata.get("published_at") or metadata.get("upload_date"),
            "processed": metadata.get("processed_at"),
            "duration_seconds": metadata.get("duration_seconds"),
            "transcript_source": metadata.get("transcript_source"),
            "local_report": str(local_report),
            "local_folder": str(folder),
            "workspace": str(workspace) if workspace else None,
            "tags": ["video-report", "ytlt", str(metadata.get("platform") or "video")],
        }
    )

    lines = [
        frontmatter,
        f"# {metadata.get('title') or folder.name}",
        "",
        "## Video Details",
        f"- Source: {_markdown_link(source_url, source_url) if source_url else 'Unknown'}",
        f"- Platform: {metadata.get('platform') or 'Unknown'}",
        f"- Channel: {metadata.get('channel') or 'Unknown'}",
        f"- Published: {metadata.get('published_at') or metadata.get('upload_date') or 'Unknown'}",
        f"- Duration: {_duration_label(metadata.get('duration_seconds'))}",
        f"- Transcript source: {metadata.get('transcript_source') or 'Unknown'}",
        f"- Processed: {metadata.get('processed_at') or 'Unknown'}",
        f"- Local report: {local_report}",
    ]
    if workspace:
        lines.append(f"- Workspace: {workspace}")

    lines.extend(["", _summary_markdown(summary.strip() or "Summary pending.", source_url)])
    if include_transcript:
        lines.extend(["", "## Transcript", "", _code_fence(transcript.strip() or "Transcript pending.")])
    lines.append("")
    return "\n".join(lines)


def write_obsidian_index(vault: Path, reports_dir: Path, index_note: Path) -> Path:
    vault = vault.expanduser().resolve()
    reports_dir.mkdir(parents=True, exist_ok=True)
    index_note.parent.mkdir(parents=True, exist_ok=True)
    records = _collect_note_records(vault, reports_dir)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    lines = [
        "# Video Reports Dashboard",
        "",
        f"Updated: {now}",
        f"Reports: {len(records)}",
        "",
        "## All Reports",
        "",
        "| Name | Platform | Source | Channel | Published | Processed | Duration | Summary |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        lines.append(_index_row(vault, record))

    lines.extend(["", "## Recent", ""])
    lines.extend(_view_links(vault, records[:10]) or ["No reports yet."])

    caption_records = [
        record for record in records if record.get("transcript_source") in {"manual_subtitle", "auto_subtitle"}
    ]
    lines.extend(["", "## Captions", ""])
    lines.extend(_view_links(vault, caption_records) or ["No caption reports yet."])

    whisper_records = [
        record for record in records if record.get("transcript_source") in {"local_whisper", "unknown", None, ""}
    ]
    lines.extend(["", "## Whisper", ""])
    lines.extend(_view_links(vault, whisper_records) or ["No Whisper reports yet."])
    lines.append("")

    index_note.write_text("\n".join(lines), encoding="utf-8")
    return index_note


def _iter_report_folders(workspace: Path, *, include_tests: bool) -> list[Path]:
    processed = workspace / "processed"
    if not processed.exists():
        return []
    folders = []
    for folder in sorted(path for path in processed.iterdir() if path.is_dir()):
        if not include_tests and any(part in {".test-workspace", "test-workspace"} for part in folder.parts):
            continue
        if (folder / "metadata.json").is_file() and (folder / "report.html").is_file():
            folders.append(folder)
    return folders


def _safe_child_path(vault: Path, value: str, *, default: str, expect_file: bool) -> Path:
    raw = value.strip() or default
    candidate = Path(raw)
    if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
        raise ObsidianError(f"Obsidian path must be relative to the vault: {value}")
    if expect_file and candidate.suffix.lower() != ".md":
        candidate = candidate.with_suffix(".md")
    path = (vault / candidate).resolve()
    if vault.resolve() not in [path, *path.parents]:
        raise ObsidianError(f"Obsidian path escapes the vault: {value}")
    return path


def _report_note_path(vault: Path, reports_dir: Path, folder: Path, metadata: dict[str, Any]) -> Path:
    stored = metadata.get("obsidian_note_path")
    if stored:
        stored_path = Path(str(stored)).expanduser().resolve()
        if vault in [stored_path, *stored_path.parents]:
            return stored_path

    base = _safe_filename(
        " - ".join(
            part
            for part in [
                _short_date(metadata.get("published_at") or metadata.get("upload_date")),
                str(metadata.get("platform") or "video"),
                str(metadata.get("id") or ""),
                str(metadata.get("title") or folder.name),
            ]
            if part
        )
    )
    candidate = reports_dir / f"{base}.md"
    if not candidate.exists() or _frontmatter_source_url(candidate) == metadata.get("source_url"):
        return candidate

    for index in range(2, 1000):
        candidate = reports_dir / f"{base}-{index}.md"
        if not candidate.exists() or _frontmatter_source_url(candidate) == metadata.get("source_url"):
            return candidate
    raise ObsidianError(f"Could not choose a unique Obsidian note path for {folder}")


def _safe_filename(value: str, *, limit: int = 120) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value)
    text = re.sub(r"\s+", " ", text).strip(" .-_")
    text = text[:limit].strip(" .-_")
    return text or "video-report"


def _frontmatter(data: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in data.items():
        if value in (None, ""):
            continue
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {_yaml_scalar(item)}")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _link_summary_timestamps(text: str, source_url: str) -> str:
    if not source_url:
        return text
    parts: list[str] = []
    cursor = 0
    for match in TIMESTAMP_RE.finditer(text):
        parts.append(text[cursor : match.start()])
        seconds = timestamp_to_seconds(match.group("start"))
        timestamp_url = source_url_at_time(source_url, seconds) if seconds is not None else None
        if timestamp_url:
            parts.append(_markdown_link(match.group(0).strip("[]"), timestamp_url))
        else:
            parts.append(match.group(0))
        cursor = match.end()
    parts.append(text[cursor:])
    return "".join(parts)


def _summary_markdown(text: str, source_url: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if is_summary_section_heading(stripped):
            lines.append(f"## {stripped}")
        else:
            lines.append(_link_summary_timestamps(raw_line, source_url))
    return "\n".join(lines)


def _markdown_link(label: str, url: str) -> str:
    escaped_label = label.replace("[", "\\[").replace("]", "\\]")
    escaped_url = url.replace(")", "%29")
    return f"[{escaped_label}]({escaped_url})"


def _code_fence(text: str) -> str:
    fence = "```"
    while fence in text:
        fence += "`"
    return f"{fence}text\n{text}\n{fence}"


def _duration_label(value: Any) -> str:
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return "Unknown"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _short_date(value: Any) -> str:
    text = "" if value in (None, "") else str(value)
    return text[:10] if len(text) >= 10 else text


def _obsidian_uri(path: Path) -> str:
    return "obsidian://open?path=" + urllib.parse.quote(str(path), safe="")


def _collect_note_records(vault: Path, reports_dir: Path) -> list[dict[str, Any]]:
    records = []
    for note_path in sorted(reports_dir.glob("*.md")):
        metadata = _read_frontmatter(note_path)
        if not metadata:
            continue
        metadata["note_path"] = note_path
        metadata["summary"] = _summary_from_note(note_path)
        records.append(metadata)
    records.sort(key=lambda item: str(item.get("processed") or ""), reverse=True)
    return records


def _read_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    metadata: dict[str, Any] = {}
    current_list: str | None = None
    for raw_line in text[4:end].splitlines():
        if raw_line.startswith("  - ") and current_list:
            metadata.setdefault(current_list, []).append(_unquote_yaml(raw_line[4:].strip()))
            continue
        current_list = None
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not value:
            metadata[key] = []
            current_list = key
        else:
            metadata[key] = _unquote_yaml(value)
    return metadata


def _unquote_yaml(value: str) -> str:
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return value
    return str(loaded)


def _frontmatter_source_url(path: Path) -> str | None:
    return _read_frontmatter(path).get("source_url")


def _summary_from_note(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig")
    for heading in ("\n## Summary\n", "\n## 摘要\n"):
        if heading in text:
            text = text.split(heading, 1)[1]
            break
    if "\n## " in text:
        text = text.split("\n## ", 1)[0]
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()[:220]


def _index_row(vault: Path, record: dict[str, Any]) -> str:
    note_path = record["note_path"]
    title = str(record.get("title") or note_path.stem)
    source = str(record.get("source_url") or "")
    return "| " + " | ".join(
        [
            _wiki_link(vault, note_path, title),
            _table_cell(record.get("platform")),
            _markdown_link("source", source) if source else "",
            _table_cell(record.get("channel")),
            _table_cell(_short_date(record.get("published"))),
            _table_cell(_short_date(record.get("processed"))),
            _table_cell(_duration_label(record.get("duration_seconds"))),
            _table_cell(record.get("summary")),
        ]
    ) + " |"


def _view_links(vault: Path, records: list[dict[str, Any]]) -> list[str]:
    return [f"- {_wiki_link(vault, record['note_path'], str(record.get('title') or record['note_path'].stem))}" for record in records]


def _wiki_link(vault: Path, note_path: Path, title: str) -> str:
    rel = note_path.relative_to(vault).with_suffix("").as_posix()
    return f"[[{rel}|{title.replace('|', '-')}]]"


def _table_cell(value: Any) -> str:
    text = "" if value in (None, "") else str(value)
    return re.sub(r"\s+", " ", text).replace("|", "\\|").strip()
