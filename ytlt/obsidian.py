from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.parse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import read_config
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
CONTENT_TAG_LIMIT = 12
CONTENT_TEXT_LIMIT = 20000

ENGLISH_TAG_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "are",
    "because",
    "been",
    "before",
    "being",
    "between",
    "but",
    "can",
    "could",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "into",
    "more",
    "not",
    "notes",
    "only",
    "other",
    "over",
    "part",
    "point",
    "report",
    "should",
    "summary",
    "than",
    "that",
    "the",
    "their",
    "then",
    "there",
    "this",
    "through",
    "transcript",
    "under",
    "video",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
    "you",
    "your",
    "youtube",
    "bilibili",
}

CJK_TAG_STOPWORDS = {
    "一个",
    "以及",
    "但是",
    "内容",
    "因为",
    "所以",
    "总结",
    "摘要",
    "视频",
    "这个",
    "这些",
}


class ObsidianError(RuntimeError):
    pass


def discover_obsidian_vaults(home: Path | None = None) -> list[Path]:
    """Return likely local Obsidian vaults, ordered by Obsidian recency when available."""
    home_path = (home or Path.home()).expanduser().resolve()
    state_vaults = _vaults_from_obsidian_state(home_path)
    if state_vaults:
        return _unique_paths(state_vaults)
    return _unique_paths(_vaults_from_common_locations(home_path))


def detect_obsidian_vault(home: Path | None = None) -> Path | None:
    vaults = discover_obsidian_vaults(home)
    return vaults[0] if vaults else None


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
        workspace: Path | None = None,
    ) -> "ObsidianPublishConfig":
        configured = _configured_obsidian_settings(workspace)
        resolved_vault = (
            vault_path
            or os.environ.get("OBSIDIAN_VAULT_PATH")
            or os.environ.get("OBSIDIAN_VAULT")
            or configured.get("vault_path")
            or detect_obsidian_vault()
        )
        if not resolved_vault:
            raise ObsidianError(
                "No Obsidian vault was found. Run video-to-notes configure --environment obsidian, "
                "set OBSIDIAN_VAULT_PATH, or pass --obsidian-vault before publishing."
            )

        resolved_reports_dir = (
            reports_dir
            or os.environ.get("OBSIDIAN_REPORTS_DIR")
            or configured.get("reports_dir")
            or DEFAULT_REPORTS_DIR
        )
        resolved_index_note = (
            index_note
            or os.environ.get("OBSIDIAN_INDEX_NOTE")
            or configured.get("index_note")
            or DEFAULT_INDEX_NOTE
        )
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
        "obsidian_sync_method": "video_to_notes_cli_vault",
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
    tags = _obsidian_tags(metadata, summary, transcript)

    frontmatter = _frontmatter(
        {
            "video_to_notes_id": metadata.get("id"),
            "title": metadata.get("title") or folder.name,
            "aliases": _obsidian_aliases(metadata, folder),
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
            "tags": tags,
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


def _configured_obsidian_settings(workspace: Path | None) -> dict[str, Any]:
    if not workspace:
        return {}
    config = read_config(workspace) or {}
    settings = config.get("obsidian") or {}
    if not isinstance(settings, dict):
        return {}
    vault_path = settings.get("vault_path") or settings.get("vault")
    resolved: dict[str, Any] = {
        "reports_dir": settings.get("reports_dir"),
        "index_note": settings.get("index_note"),
    }
    if vault_path:
        resolved["vault_path"] = str(vault_path)
    return resolved


def _vaults_from_obsidian_state(home: Path) -> list[Path]:
    ranked: list[tuple[int, float, Path]] = []
    for state_file in _obsidian_state_files(home):
        try:
            payload = json.loads(state_file.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        vaults = payload.get("vaults")
        if isinstance(vaults, dict):
            entries = vaults.values()
        elif isinstance(vaults, list):
            entries = vaults
        else:
            entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            path_value = entry.get("path")
            if not path_value:
                continue
            path = Path(str(path_value)).expanduser()
            if not _is_vault_path(path):
                continue
            opened = 1 if entry.get("open") else 0
            try:
                timestamp = float(entry.get("ts") or entry.get("mtime") or 0)
            except (TypeError, ValueError):
                timestamp = 0
            ranked.append((opened, timestamp, path.resolve()))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [path for _, _, path in ranked]


def _obsidian_state_files(home: Path) -> list[Path]:
    candidates = [
        home / "Library" / "Application Support" / "obsidian" / "obsidian.json",
        home / ".config" / "obsidian" / "obsidian.json",
        home / "AppData" / "Roaming" / "obsidian" / "obsidian.json",
    ]
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "obsidian" / "obsidian.json")
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        candidates.append(Path(xdg_config_home) / "obsidian" / "obsidian.json")
    return [path.expanduser() for path in candidates if path.expanduser().is_file()]


def _vaults_from_common_locations(home: Path) -> list[Path]:
    roots = [
        home / "Documents",
        home / "Desktop",
        home / "Obsidian",
        home / "Dropbox",
        home / "Google Drive",
        home / "OneDrive",
        home / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents",
    ]
    vaults: list[Path] = []
    for root in roots:
        root = root.expanduser()
        if not root.is_dir():
            continue
        if _is_vault_path(root):
            vaults.append(root.resolve())
            continue
        try:
            markers = root.rglob(".obsidian")
            for marker in markers:
                if marker.is_dir():
                    vaults.append(marker.parent.resolve())
        except OSError:
            continue
    return vaults


def _is_vault_path(path: Path) -> bool:
    try:
        expanded = path.expanduser()
        return expanded.is_dir() and (expanded / ".obsidian").is_dir()
    except OSError:
        return False


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.expanduser().resolve()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        unique.append(resolved)
    return unique


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

    base = _report_note_basename(folder, metadata)
    candidate = reports_dir / f"{base}.md"
    if not candidate.exists() or _frontmatter_source_url(candidate) == metadata.get("source_url"):
        return candidate

    for index in range(2, 1000):
        candidate = reports_dir / f"{base}-{index}.md"
        if not candidate.exists() or _frontmatter_source_url(candidate) == metadata.get("source_url"):
            return candidate
    raise ObsidianError(f"Could not choose a unique Obsidian note path for {folder}")


def _report_note_basename(folder: Path, metadata: dict[str, Any]) -> str:
    title = str(metadata.get("title") or folder.name)
    context = " - ".join(
        part
        for part in [
            _short_date(metadata.get("published_at") or metadata.get("upload_date")),
            str(metadata.get("platform") or "video"),
            str(metadata.get("id") or ""),
        ]
        if part
    )
    return " - ".join(
        part
        for part in [
            _safe_filename(title, limit=90),
            _safe_filename(context, limit=40) if context else "",
        ]
        if part
    ) or "video-report"


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


def _obsidian_aliases(metadata: dict[str, Any], folder: Path) -> list[str]:
    title = str(metadata.get("title") or folder.name).strip()
    return [title] if title else []


def _obsidian_tags(metadata: dict[str, Any], summary: str, transcript: str) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for value in ["video-report", "video-to-notes", metadata.get("platform") or "video"]:
        _append_tag(tags, seen, value)
    for value in _metadata_tag_values(metadata):
        _append_tag(tags, seen, value)
    for value in _rank_content_tags(metadata, summary, transcript):
        _append_tag(tags, seen, value)
        if len(tags) >= CONTENT_TAG_LIMIT:
            break
    return tags


def _metadata_tag_values(metadata: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("categories", "tags"):
        raw = metadata.get(key)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if item not in (None, ""))
        elif raw not in (None, ""):
            values.append(str(raw))
    return values


def _rank_content_tags(metadata: dict[str, Any], summary: str, transcript: str) -> list[str]:
    scores: Counter[str] = Counter()
    title = str(metadata.get("title") or "")
    channel = str(metadata.get("channel") or "")
    weighted_sources = [
        (title, 6),
        (summary, 4),
        (channel, 2),
        (transcript[:CONTENT_TEXT_LIMIT], 1),
    ]
    for text, weight in weighted_sources:
        for candidate in _tag_candidates(text):
            tag = _normalize_tag(candidate)
            if tag:
                scores[tag] += weight
    for value in ["video-report", "video-to-notes", metadata.get("platform") or "video"]:
        normalized = _normalize_tag(str(value))
        if normalized:
            scores.pop(normalized, None)
    return [tag for tag, _ in scores.most_common()]


def _tag_candidates(text: str) -> list[str]:
    cleaned = re.sub(r"https?://\S+", " ", text)
    cleaned = re.sub(r"\[[^\]]*\]", " ", cleaned)
    candidates: list[str] = []
    for line in cleaned.splitlines():
        words = [
            match.group(0).lower()
            for match in re.finditer(r"[A-Za-z][A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*", line)
        ]
        words = [word for word in words if _useful_latin_tag_word(word)]
        candidates.extend(f"{words[index]}-{words[index + 1]}" for index in range(len(words) - 1))
        candidates.extend(words)
        for match in re.finditer(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3]{2,16}", line):
            candidates.extend(_cjk_candidates(match.group(0)))
    return candidates


def _useful_latin_tag_word(word: str) -> bool:
    if len(word) < 2 or word in ENGLISH_TAG_STOPWORDS:
        return False
    if word.isdigit():
        return False
    return True


def _cjk_candidates(value: str) -> list[str]:
    text = value.strip()
    if not text or text in CJK_TAG_STOPWORDS:
        return []
    if len(text) <= 8:
        return [text]
    chunks: list[str] = []
    for size in (6, 4, 3, 2):
        chunks.extend(text[index : index + size] for index in range(0, len(text) - size + 1))
    return [chunk for chunk in chunks if chunk not in CJK_TAG_STOPWORDS]


def _append_tag(tags: list[str], seen: set[str], value: Any) -> None:
    tag = _normalize_tag(str(value))
    if not tag or tag in seen:
        return
    seen.add(tag)
    tags.append(tag)


def _normalize_tag(value: str) -> str | None:
    text = value.strip().lstrip("#").lower()
    text = text.replace("'", "").replace("’", "")
    text = re.sub(r"[/\\]+", "-", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^\w.\-\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3]+", "-", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    if not text or text.isdigit():
        return None
    return text[:48].strip("-._") or None


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
