from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .reporting import (
    DETAILS_CLOSE_RE,
    DETAILS_OPEN_RE,
    SUMMARY_TAG_RE,
    TIMESTAMP_RE,
    _bullet_line,
    is_summary_section_heading,
    read_metadata,
    source_url_at_time,
    summary_file_path,
    summary_preview,
    timestamp_to_seconds,
)


DEFAULT_NOTION_VERSION = "2026-03-11"
MAX_RICH_TEXT_LENGTH = 1900
MAX_CHILDREN_PER_APPEND = 100


class NotionError(RuntimeError):
    pass


@dataclass(frozen=True)
class NotionPublishConfig:
    token: str
    parent_page_id: str | None = None
    data_source_id: str | None = None
    database_id: str | None = None
    api_version: str = DEFAULT_NOTION_VERSION

    @classmethod
    def from_values(
        cls,
        *,
        token: str | None = None,
        parent_page_id: str | None = None,
        data_source_id: str | None = None,
        database_id: str | None = None,
        api_version: str | None = None,
    ) -> "NotionPublishConfig":
        resolved_token = token or os.environ.get("NOTION_TOKEN") or os.environ.get("NOTION_API_KEY")
        if not resolved_token:
            raise NotionError("Set NOTION_TOKEN or pass --notion-token before publishing to Notion.")

        if any((parent_page_id, data_source_id, database_id)):
            resolved_parent = parent_page_id
            resolved_data_source = data_source_id
            resolved_database = database_id
        else:
            resolved_parent = os.environ.get("NOTION_PARENT_PAGE_ID")
            resolved_data_source = os.environ.get("NOTION_DATA_SOURCE_ID")
            resolved_database = os.environ.get("NOTION_DATABASE_ID")
        targets = [value for value in (resolved_parent, resolved_data_source, resolved_database) if value]
        if len(targets) != 1:
            raise NotionError(
                "Set exactly one Notion target: --notion-parent-page-id, "
                "--notion-data-source-id, or --notion-database-id."
            )

        return cls(
            token=resolved_token,
            parent_page_id=resolved_parent,
            data_source_id=resolved_data_source,
            database_id=resolved_database,
            api_version=api_version or os.environ.get("NOTION_VERSION") or DEFAULT_NOTION_VERSION,
        )


class NotionClient:
    def __init__(
        self,
        token: str,
        *,
        api_version: str = DEFAULT_NOTION_VERSION,
        base_url: str = "https://api.notion.com/v1",
    ) -> None:
        self.token = token
        self.api_version = api_version
        self.base_url = base_url.rstrip("/")

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/{path.lstrip('/')}",
            data=payload,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Notion-Version": self.api_version,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            message = raw_error
            try:
                parsed = json.loads(raw_error)
                message = parsed.get("message") or raw_error
            except json.JSONDecodeError:
                pass
            raise NotionError(f"Notion API {exc.code} error for {method} /{path.lstrip('/')}: {message}") from exc
        except urllib.error.URLError as exc:
            raise NotionError(f"Could not reach Notion API: {exc.reason}") from exc

        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise NotionError(f"Notion API returned invalid JSON for {method} /{path.lstrip('/')}") from exc

    def retrieve_database(self, database_id: str) -> dict[str, Any]:
        return self.request("GET", f"databases/{database_id}")

    def retrieve_data_source(self, data_source_id: str) -> dict[str, Any]:
        return self.request("GET", f"data_sources/{data_source_id}")

    def create_page(self, parent: dict[str, Any], properties: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "pages", {"parent": parent, "properties": properties})

    def update_page(self, page_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        return self.request("PATCH", f"pages/{page_id}", {"properties": properties})

    def list_children(self, block_id: str) -> list[dict[str, Any]]:
        children: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            query = {"page_size": "100"}
            if cursor:
                query["start_cursor"] = cursor
            response = self.request("GET", f"blocks/{block_id}/children?{urllib.parse.urlencode(query)}")
            children.extend(response.get("results") or [])
            if not response.get("has_more"):
                return children
            cursor = response.get("next_cursor")
            if not cursor:
                return children

    def clear_children(self, block_id: str) -> None:
        for child in self.list_children(block_id):
            child_id = child.get("id")
            if child_id:
                self.request("DELETE", f"blocks/{child_id}")

    def append_children(self, block_id: str, children: list[dict[str, Any]]) -> None:
        for batch in _batched(children, MAX_CHILDREN_PER_APPEND):
            self.request("PATCH", f"blocks/{block_id}/children", {"children": batch})


def publish_report_to_notion(
    folder: Path,
    config: NotionPublishConfig,
    *,
    workspace: Path | None = None,
    client: NotionClient | None = None,
) -> dict[str, Any]:
    folder = folder.expanduser().resolve()
    metadata = read_metadata(folder)
    if not metadata:
        raise NotionError(f"Missing or invalid metadata.json in {folder}")

    notion = client or NotionClient(config.token, api_version=config.api_version)
    parent, schema = _resolve_parent_and_schema(notion, config)
    properties = _page_properties(schema, metadata, folder)
    page_id = str(metadata.get("notion_page_id") or "")
    if page_id:
        page = notion.update_page(page_id, properties)
        notion.clear_children(page_id)
    else:
        page = notion.create_page(parent, properties)
        page_id = str(page.get("id") or "")
        if not page_id:
            raise NotionError("Notion did not return a page id.")

    notion.append_children(page_id, report_blocks(folder, metadata, workspace=workspace))
    result = {
        "notion_page_id": page_id,
        "notion_url": page.get("url") or metadata.get("notion_url"),
        "notion_synced_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    metadata.update({key: value for key, value in result.items() if value})
    if config.data_source_id or config.database_id:
        metadata["notion_data_source_id"] = schema.get("id")
    if config.parent_page_id:
        metadata["notion_parent_page_id"] = config.parent_page_id
    (folder / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def report_blocks(folder: Path, metadata: dict[str, Any], *, workspace: Path | None = None) -> list[dict[str, Any]]:
    source_url = str(metadata.get("source_url") or "")
    summary_path = summary_file_path(folder)
    summary = summary_path.read_text(encoding="utf-8-sig") if summary_path.exists() else ""
    transcript_path = folder / str(metadata.get("transcript_file") or "transcript.txt")
    transcript = transcript_path.read_text(encoding="utf-8-sig") if transcript_path.exists() else ""
    local_report = folder / "report.html"

    blocks: list[dict[str, Any]] = [
        _heading("Video Details", level=2),
        _bullet("Source", source_url, link=source_url or None),
        _bullet("Platform", metadata.get("platform")),
        _bullet("Channel", metadata.get("channel")),
        _bullet("Published", metadata.get("published_at") or metadata.get("upload_date")),
        _bullet("Duration", _duration_label(metadata.get("duration_seconds"))),
        _bullet("Transcript source", metadata.get("transcript_source")),
        _bullet("Processed", metadata.get("processed_at")),
    ]
    if metadata.get("processing_seconds") not in (None, ""):
        blocks.append(_bullet("Processing seconds", metadata.get("processing_seconds")))
    blocks.append(_bullet("Local report", str(local_report)))
    if workspace:
        blocks.append(_bullet("Workspace", str(workspace)))

    blocks.extend(_summary_blocks(summary, source_url))
    blocks.append(_transcript_toggle(transcript, source_url))
    return blocks


def _resolve_parent_and_schema(
    client: NotionClient,
    config: NotionPublishConfig,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if config.parent_page_id:
        return {"type": "page_id", "page_id": config.parent_page_id}, {}

    data_source_id = config.data_source_id
    if not data_source_id and config.database_id:
        database = client.retrieve_database(config.database_id)
        data_sources = database.get("data_sources") or []
        if not data_sources:
            raise NotionError(f"Database {config.database_id} did not return any data sources.")
        data_source_id = data_sources[0].get("id")
    if not data_source_id:
        raise NotionError("Missing Notion data source id.")

    schema = client.retrieve_data_source(str(data_source_id))
    return {"type": "data_source_id", "data_source_id": str(data_source_id)}, schema


def _page_properties(schema: dict[str, Any], metadata: dict[str, Any], folder: Path) -> dict[str, Any]:
    title = str(metadata.get("title") or folder.name)
    properties_schema = schema.get("properties") or {}
    if not properties_schema:
        return {"title": {"title": _rich_text(title)}}

    title_name = _find_property_name(properties_schema, expected_type="title")
    if not title_name:
        raise NotionError("The target Notion data source has no title property.")

    properties: dict[str, Any] = {title_name: {"title": _rich_text(title)}}
    _maybe_set_property(properties, properties_schema, ["Source URL", "Source", "URL"], metadata.get("source_url"))
    _maybe_set_property(properties, properties_schema, ["Platform"], metadata.get("platform"))
    _maybe_set_property(properties, properties_schema, ["Channel"], metadata.get("channel"))
    _maybe_set_property(properties, properties_schema, ["Published", "Publish Date"], metadata.get("published_at"))
    _maybe_set_property(
        properties,
        properties_schema,
        ["Processed", "Processed At", "Processing Time"],
        metadata.get("processed_at"),
    )
    _maybe_set_property(properties, properties_schema, ["Duration Seconds", "Duration"], metadata.get("duration_seconds"))
    _maybe_set_property(
        properties,
        properties_schema,
        ["Processing Seconds", "Processing Time Seconds", "Processing Duration Seconds"],
        metadata.get("processing_seconds"),
    )
    _maybe_set_property(properties, properties_schema, ["Transcript Source", "Source Type"], metadata.get("transcript_source"))
    _maybe_set_property(properties, properties_schema, ["Folder", "Report Folder"], folder.name)
    _maybe_set_property(properties, properties_schema, ["Local Report", "Report Path"], str((folder / "report.html").resolve()))
    _maybe_set_property(properties, properties_schema, ["Summary", "Summary Preview"], summary_preview(folder))
    return properties


def _maybe_set_property(
    properties: dict[str, Any],
    schema: dict[str, Any],
    names: list[str],
    value: Any,
) -> None:
    if value in (None, ""):
        return
    name = _find_named_property(schema, names)
    if not name:
        return
    prop_type = schema[name].get("type")
    converted = _property_value(prop_type, value)
    if converted is not None:
        properties[name] = converted


def _property_value(prop_type: str | None, value: Any) -> dict[str, Any] | None:
    text = str(value)
    if prop_type == "url":
        return {"url": text}
    if prop_type == "rich_text":
        return {"rich_text": _rich_text(text)}
    if prop_type == "select":
        return {"select": {"name": text[:100]}}
    if prop_type == "multi_select":
        return {"multi_select": [{"name": text[:100]}]}
    if prop_type == "number":
        try:
            return {"number": float(value)}
        except (TypeError, ValueError):
            return None
    if prop_type == "date":
        date_value = _notion_date(text)
        return {"date": {"start": date_value}} if date_value else None
    if prop_type == "checkbox":
        return {"checkbox": bool(value)}
    return None


def _find_property_name(schema: dict[str, Any], *, expected_type: str) -> str | None:
    for name, definition in schema.items():
        if definition.get("type") == expected_type:
            return name
    return None


def _find_named_property(schema: dict[str, Any], names: list[str]) -> str | None:
    normalized = {_normalize_name(name): name for name in schema}
    for candidate in names:
        match = normalized.get(_normalize_name(candidate))
        if match:
            return match
    return None


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _summary_blocks(summary: str, source_url: str) -> list[dict[str, Any]]:
    if not summary.strip():
        return [_heading("Summary", level=2), _paragraph("Summary pending.")]

    return _summary_blocks_from_lines(summary.splitlines(), source_url)


def _summary_blocks_from_lines(lines: list[str], source_url: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    paragraph: list[str] = []
    bullets: list[tuple[str, list[str]]] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            blocks.extend(_paragraph_blocks(" ".join(paragraph), source_url=source_url))
            paragraph = []

    def flush_bullets() -> None:
        nonlocal bullets
        if bullets:
            blocks.extend(_bulleted_item(item, source_url, children) for item, children in bullets)
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
            toggle, index = _toggle_block_from_details(lines, index, source_url)
            blocks.append(toggle)
            continue
        if is_summary_section_heading(line):
            flush_paragraph()
            flush_bullets()
            blocks.append(_heading(line, level=2))
        elif line.startswith("### "):
            flush_paragraph()
            flush_bullets()
            blocks.append(_heading(line[4:].strip(), level=3))
        elif line.startswith("## "):
            flush_paragraph()
            flush_bullets()
            blocks.append(_heading(line[3:].strip(), level=2))
        else:
            flush_bullets()
            paragraph.append(line)
        index += 1

    flush_paragraph()
    flush_bullets()
    return blocks


def _toggle_block_from_details(
    lines: list[str],
    start_index: int,
    source_url: str,
) -> tuple[dict[str, Any], int]:
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

    children = _summary_blocks_from_lines(body_lines, source_url) if body_lines else [_paragraph("")]
    return _toggle(summary, children, source_url=source_url), index


def _paragraph_blocks(text: str, *, source_url: str | None = None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if source_url and TIMESTAMP_RE.search(text):
        blocks.append(_rich_block("paragraph", _timestamp_rich_text(text, source_url)))
        return blocks
    for chunk in _split_text(text):
        blocks.append(_paragraph(chunk))
    return blocks


def _timestamp_rich_text(text: str, source_url: str) -> list[dict[str, Any]]:
    rich: list[dict[str, Any]] = []
    cursor = 0
    for match in TIMESTAMP_RE.finditer(text):
        rich.extend(_rich_text(text[cursor : match.start()]))
        seconds = timestamp_to_seconds(match.group("start"))
        timestamp_url = source_url_at_time(source_url, seconds) if seconds is not None else None
        rich.extend(_rich_text(match.group(0), link=timestamp_url))
        cursor = match.end()
    rich.extend(_rich_text(text[cursor:]))
    return rich or _rich_text("")


def _heading(text: str, *, level: int) -> dict[str, Any]:
    block_type = "heading_3" if level == 3 else "heading_2"
    return _rich_block(block_type, _rich_text(text))


def _toggle(text: str, children: list[dict[str, Any]], *, source_url: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "toggle",
        "toggle": {
            "rich_text": _timestamp_rich_text(text, source_url),
            "children": children,
        },
    }


def _bulleted_item(text: str, source_url: str, children: list[str] | None = None) -> dict[str, Any]:
    block = _rich_block("bulleted_list_item", _timestamp_rich_text(text, source_url))
    if children:
        block["bulleted_list_item"]["children"] = [
            _bulleted_item(child, source_url) for child in children
        ]
    return block


def _transcript_toggle(transcript: str, source_url: str) -> dict[str, Any]:
    code_blocks = _code_blocks(transcript.strip() or "Transcript pending.")
    if len(code_blocks) <= MAX_CHILDREN_PER_APPEND:
        children = code_blocks
    else:
        children = [
            _toggle(f"Transcript part {index}", batch, source_url=source_url)
            for index, batch in enumerate(_batched(code_blocks, MAX_CHILDREN_PER_APPEND), start=1)
        ]
    return _toggle("Transcript", children, source_url=source_url)


def _paragraph(text: str) -> dict[str, Any]:
    return _rich_block("paragraph", _rich_text(text))


def _bullet(label: str, value: Any, *, link: str | None = None) -> dict[str, Any]:
    text = "" if value is None else str(value)
    rich = _rich_text(f"{label}: ")
    rich.extend(_rich_text(text, link=link))
    return _rich_block("bulleted_list_item", rich)


def _rich_block(block_type: str, rich_text: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "object": "block",
        "type": block_type,
        block_type: {"rich_text": rich_text},
    }


def _code_blocks(text: str) -> list[dict[str, Any]]:
    return [
        {
            "object": "block",
            "type": "code",
            "code": {"language": "plain text", "rich_text": _rich_text(chunk)},
        }
        for chunk in _split_text(text)
    ]


def _rich_text(text: str, *, link: str | None = None) -> list[dict[str, Any]]:
    chunks = _split_text(text)
    result = []
    for chunk in chunks:
        text_obj: dict[str, Any] = {"content": chunk}
        if link:
            text_obj["link"] = {"url": link}
        result.append({"type": "text", "text": text_obj})
    return result


def _split_text(text: str, limit: int = MAX_RICH_TEXT_LENGTH) -> list[str]:
    if text == "":
        return [""]
    chunks: list[str] = []
    cursor = 0
    while cursor < len(text):
        end = min(cursor + limit, len(text))
        chunks.append(text[cursor:end])
        cursor = end
    return chunks


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


def _notion_date(value: str) -> str | None:
    if "T" in value:
        return value
    date_part = value[:10]
    return date_part if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_part) else None


def _batched(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]
