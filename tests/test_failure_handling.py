from __future__ import annotations

import contextlib
import io
import json
import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from ytlt.cli import main
from ytlt.runtime import JavascriptRuntime, check_source_network, doctor


class NetworkDiagnosisTests(unittest.TestCase):
    def test_dns_failure_reports_unreachable(self) -> None:
        error = urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))
        with patch("ytlt.runtime.urllib.request.urlopen", side_effect=error):
            result = check_source_network("https://www.youtube.com/watch?v=example")
        self.assertFalse(result["reachable"])
        self.assertEqual(result["category"], "dns")

    def test_http_rejection_is_distinct_from_no_connectivity(self) -> None:
        error = urllib.error.HTTPError("https://example.test/", 403, "Forbidden", {}, None)
        with patch("ytlt.runtime.urllib.request.urlopen", side_effect=error):
            result = check_source_network("https://example.test/video")
        self.assertTrue(result["reachable"])
        self.assertEqual(result["http_status"], 403)

    def test_network_failure_overrides_healthy_dependencies(self) -> None:
        runtime = JavascriptRuntime("node", "/opt/node", "v24.0.0")
        with tempfile.TemporaryDirectory() as tmp, patch(
            "ytlt.runtime.detect_javascript_runtimes", return_value=[runtime]
        ), patch("ytlt.runtime._package_version", return_value="1.0"), patch(
            "ytlt.runtime.resolve_ffmpeg_path", return_value="/opt/ffmpeg"
        ), patch("ytlt.runtime.check_source_network", return_value={
            "checked": True, "reachable": False, "category": "dns", "message": "DNS blocked"
        }):
            result = doctor(Path(tmp), source_url="https://www.youtube.com/watch?v=example")
        self.assertFalse(result["ready"])
        self.assertIn("DNS blocked", result["errors"])

    def test_metadata_dns_failure_never_downloads_or_transcribes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "ytlt.cli.extract_info", side_effect=RuntimeError("Failed to resolve 'www.youtube.com'")
        ), patch("ytlt.cli.download_video") as download, patch(
            "ytlt.cli.transcribe_video"
        ) as transcribe, contextlib.redirect_stderr(io.StringIO()) as stderr:
            code = main(["process", "https://www.youtube.com/watch?v=example", "--workspace", tmp, "--environment", "local"])
        payload = json.loads(stderr.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(payload["stage"], "metadata")
        self.assertEqual(payload["category"], "dns")
        download.assert_not_called()
        transcribe.assert_not_called()


class FinalizationGuardTests(unittest.TestCase):
    def fixture(self, root: Path) -> Path:
        folder = root / "processed" / "video"
        folder.mkdir(parents=True)
        (folder / "metadata.json").write_text(json.dumps({
            "id": "example", "title": "Example", "transcript_source": "manual_subtitle",
            "source_url": "https://www.youtube.com/watch?v=example", "video_file": "video.webm"
        }))
        (folder / "transcript.txt").write_text("The speaker explains the example.\n")
        (folder / "summary.md").write_text("Summary\n\nAn explanation of the example.\n")
        (folder / "tags.json").write_text('{"tags": []}')
        (folder / "video.webm").write_bytes(b"retained media fixture")
        return folder

    def finalize(self, folder: Path) -> int:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(["finalize", str(folder), "--environment", "local"])

    def test_missing_transcript_rejects_without_rendering_or_deleting_media(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = self.fixture(Path(tmp))
            (folder / "transcript.txt").unlink()
            self.assertEqual(self.finalize(folder), 2)
            self.assertFalse((folder / "report.html").exists())
            self.assertTrue((folder / "video.webm").exists())

    def test_blank_transcript_rejects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = self.fixture(Path(tmp))
            (folder / "transcript.txt").write_text(" \n\t")
            self.assertEqual(self.finalize(folder), 2)

    def test_article_source_notice_cannot_be_finalized_as_transcription(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = self.fixture(Path(tmp))
            metadata = json.loads((folder / "metadata.json").read_text())
            metadata["transcript_source"] = "author_published_script"
            (folder / "metadata.json").write_text(json.dumps(metadata))
            (folder / "transcript.txt").write_text("See the author website for the full article.")
            self.assertEqual(self.finalize(folder), 2)

    def test_missing_and_invalid_tags_reject(self) -> None:
        for content in (None, "not json", '{"tags": [1]}'):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                folder = self.fixture(Path(tmp))
                if content is None:
                    (folder / "tags.json").unlink()
                else:
                    (folder / "tags.json").write_text(content)
                self.assertEqual(self.finalize(folder), 2)
                self.assertTrue((folder / "video.webm").exists())

    def test_complete_report_still_finalizes_and_cleans_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = self.fixture(Path(tmp))
            self.assertEqual(self.finalize(folder), 0)
            self.assertTrue((folder / "report.html").is_file())
            self.assertFalse((folder / "video.webm").exists())


if __name__ == "__main__":
    unittest.main()
