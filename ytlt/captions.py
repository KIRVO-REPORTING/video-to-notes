from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PREFERRED_CAPTION_EXTS = ("vtt", "srt", "ttml", "json3", "srv3", "srv2", "srv1")
DEFAULT_LANGUAGE_ORDER = ("zh-Hans", "zh-Hant", "zh", "en", "ja", "ko")


@dataclass(frozen=True)
class CaptionTrack:
    language: str
    ext: str
    url: str
    source: str
    name: str | None = None


def _language_candidates(language: str | None) -> list[str]:
    candidates: list[str] = []
    if language:
        candidates.append(language)
        if "-" in language:
            candidates.append(language.split("-", 1)[0])
    candidates.extend(DEFAULT_LANGUAGE_ORDER)

    seen: set[str] = set()
    deduped: list[str] = []
    for item in candidates:
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(item)
    return deduped


def _track_for_language(
    language: str,
    subtitle_map: dict[str, list[dict[str, Any]]],
    source: str,
) -> CaptionTrack | None:
    keys = list(subtitle_map)
    exact_key = next((key for key in keys if key.lower() == language.lower()), None)
    prefix_key = next((key for key in keys if key.lower().startswith(language.lower() + "-")), None)
    contains_key = next((key for key in keys if language.lower() in key.lower()), None)
    key = exact_key or prefix_key or contains_key
    if not key:
        return None

    tracks = subtitle_map.get(key) or []
    for preferred in PREFERRED_CAPTION_EXTS:
        for track in tracks:
            ext = str(track.get("ext") or "").lower()
            url = track.get("url")
            if ext == preferred and url:
                return CaptionTrack(
                    language=key,
                    ext=ext,
                    url=str(url),
                    source=source,
                    name=track.get("name"),
                )

    for track in tracks:
        url = track.get("url")
        if url:
            return CaptionTrack(
                language=key,
                ext=str(track.get("ext") or "caption").lower(),
                url=str(url),
                source=source,
                name=track.get("name"),
            )
    return None


def choose_caption_track(
    info: dict[str, Any],
    language: str | None = None,
    *,
    allow_auto: bool = True,
) -> CaptionTrack | None:
    languages = _language_candidates(language)
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}

    for lang in languages:
        track = _track_for_language(lang, manual, "manual_subtitle")
        if track:
            return track

    if allow_auto:
        for lang in languages:
            track = _track_for_language(lang, auto, "auto_subtitle")
            if track:
                return track

    if manual:
        for lang in manual:
            track = _track_for_language(lang, manual, "manual_subtitle")
            if track:
                return track

    if allow_auto and auto:
        for lang in auto:
            track = _track_for_language(lang, auto, "auto_subtitle")
            if track:
                return track
    return None


def download_caption(track: CaptionTrack, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = re.sub(r"[^a-z0-9]+", "", track.ext.lower()) or "caption"
    lang = re.sub(r"[^A-Za-z0-9_.-]+", "-", track.language).strip("-") or "unknown"
    path = target_dir / f"captions.{lang}.{suffix}"
    data = _download_caption_bytes(track.url)
    path.write_bytes(data)
    return path


def _fetch_url(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "ytlt/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _download_caption_bytes(url: str, *, depth: int = 0) -> bytes:
    data = _fetch_url(url)
    text = data.decode("utf-8-sig", errors="replace")
    if not _is_hls_playlist(text):
        return data
    if depth >= 4:
        raise RuntimeError(f"Nested caption playlist is too deep: {url}")

    parts: list[bytes] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        segment_url = urllib.parse.urljoin(url, line)
        parts.append(_download_caption_bytes(segment_url, depth=depth + 1))
    if not parts:
        raise RuntimeError(f"Caption playlist did not contain any segments: {url}")
    return b"\n".join(parts)


def _is_hls_playlist(text: str) -> bool:
    return text.lstrip("\ufeff\r\n\t ").startswith("#EXTM3U")


def _strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_vtt_or_srt(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.replace("\ufeff", "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.upper().startswith("WEBVTT") or line.upper().startswith("NOTE"):
            continue
        if re.fullmatch(r"\d+", line):
            continue
        if "-->" in line:
            continue
        if line.startswith(("Kind:", "Language:", "STYLE", "REGION", "X-TIMESTAMP-MAP=")):
            continue
        cleaned = _strip_tags(line)
        if cleaned:
            lines.append(cleaned)
    return _dedupe_adjacent(lines)


def _parse_json3(text: str) -> str:
    payload = json.loads(text)
    lines: list[str] = []
    for event in payload.get("events", []):
        segs = event.get("segs") or []
        line = "".join(seg.get("utf8", "") for seg in segs)
        cleaned = _strip_tags(line)
        if cleaned:
            lines.append(cleaned)
    return _dedupe_adjacent(lines)


def _parse_ttml(text: str) -> str:
    root = ET.fromstring(text)
    lines: list[str] = []
    for element in root.iter():
        if element.text and element.text.strip():
            cleaned = _strip_tags(element.text)
            if cleaned:
                lines.append(cleaned)
    return _dedupe_adjacent(lines)


def _dedupe_adjacent(lines: list[str]) -> str:
    deduped: list[str] = []
    previous = ""
    for line in lines:
        if line == previous:
            continue
        deduped.append(line)
        previous = line
    return "\n".join(deduped).strip() + "\n"


def caption_to_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    ext = path.suffix.lower().lstrip(".")
    if ext in {"json3", "json"}:
        return _parse_json3(raw)
    if ext in {"ttml", "xml", "srv1", "srv2", "srv3"}:
        try:
            return _parse_ttml(raw)
        except ET.ParseError:
            return _parse_vtt_or_srt(raw)
    return _parse_vtt_or_srt(raw)


def write_transcript_from_caption(caption_path: Path, transcript_path: Path) -> Path:
    text = caption_to_text(caption_path)
    if not text.strip():
        raise RuntimeError(f"Caption file did not produce text: {caption_path}")
    transcript_path.write_text(text, encoding="utf-8")
    return transcript_path
