from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ytlt.captions import CaptionTrack, download_caption, write_transcript_from_caption
from ytlt.cli import process_url


class CaptionDownloadTests(unittest.TestCase):
    def test_hls_playlist_segments_are_written_as_caption_text(self) -> None:
        responses = {
            "https://example.test/subs/en.m3u8": b"""#EXTM3U
#EXT-X-VERSION:4
#EXTINF:1.0,
segment0.vtt
#EXTINF:1.0,
/subs/segment1.vtt
#EXT-X-ENDLIST
""",
            "https://example.test/subs/segment0.vtt": b"""WEBVTT
X-TIMESTAMP-MAP=LOCAL:00:00:00.000,MPEGTS:0

00:00:00.000 --> 00:00:01.000
Hello
""",
            "https://example.test/subs/segment1.vtt": b"""WEBVTT

00:00:01.000 --> 00:00:02.000
world
""",
        }

        def fake_fetch(url: str) -> bytes:
            return responses[url]

        track = CaptionTrack(
            language="en",
            ext="vtt",
            url="https://example.test/subs/en.m3u8",
            source="manual_subtitle",
        )
        with tempfile.TemporaryDirectory() as tmp, patch("ytlt.captions._fetch_url", side_effect=fake_fetch):
            target_dir = Path(tmp)
            caption_path = download_caption(track, target_dir)
            transcript_path = target_dir / "transcript.txt"

            write_transcript_from_caption(caption_path, transcript_path)

            self.assertNotIn("#EXTM3U", caption_path.read_text(encoding="utf-8"))
            self.assertEqual("Hello\nworld\n", transcript_path.read_text(encoding="utf-8"))

    def test_no_transcribe_fallback_stops_when_no_caption_track_exists(self) -> None:
        args = argparse.Namespace(
            workspace=None,
            output_root=None,
            url="https://example.test/video",
            cookies_from_browser=None,
            cookies=None,
            force_transcribe=False,
            language="en",
            no_auto_subs=False,
            no_transcribe_fallback=True,
        )
        info = {
            "id": "no-captions",
            "title": "No captions",
            "webpage_url": "https://example.test/video",
            "subtitles": {},
            "automatic_captions": {},
        }

        with tempfile.TemporaryDirectory() as tmp, patch("ytlt.cli.extract_info", return_value=info), patch(
            "ytlt.cli._workspace", return_value=Path(tmp)
        ), patch("ytlt.cli.download_video") as download_video:
            with self.assertRaises(SystemExit) as raised:
                process_url(args)

            self.assertIn("No usable captions found", str(raised.exception))
            download_video.assert_not_called()


if __name__ == "__main__":
    unittest.main()
