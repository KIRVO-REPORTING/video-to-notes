from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ytlt.reporting import render_summary, summary_preview, write_report


class ReportingTests(unittest.TestCase):
    def test_timestamped_key_points_render_as_source_video_links(self) -> None:
        source_url = "https://www.bilibili.com/video/BV123/?spm_id_from=test&t=9"
        summary = """Summary

Short summary.

Key Points

- [01:24-02:44] Install the dock animation.
"""

        rendered = render_summary(summary, source_url)

        self.assertIn('class="timestamp-link"', rendered)
        self.assertIn("spm_id_from=test&amp;t=84", rendered)
        self.assertIn(">[01:24-02:44]</a> Install the dock animation.", rendered)

    def test_timestamped_key_points_support_hour_format(self) -> None:
        summary = """Key Points

- [01:02:03-01:04:00] Long video chapter.
"""

        rendered = render_summary(summary, "https://www.youtube.com/watch?v=abc")

        self.assertIn("watch?v=abc&amp;t=3723", rendered)
        self.assertIn("t=3723", rendered)

    def test_nested_key_points_render_as_nested_bullets(self) -> None:
        summary = """Summary

Short summary.

Key Points

- [01:24-02:44] Main conclusion.
  - [01:30-01:40] Supporting detail.
  - [01:41-01:50] Supporting caveat.

- [02:45-03:10] Second conclusion.
"""

        rendered = render_summary(summary, "https://www.youtube.com/watch?v=abc")

        self.assertGreaterEqual(rendered.count("<ul>"), 2)
        self.assertIn("watch?v=abc&amp;t=84", rendered)
        self.assertIn("watch?v=abc&amp;t=90", rendered)
        self.assertIn("Supporting caveat.", rendered)

    def test_foldable_segment_details_render_as_details(self) -> None:
        summary = """Summary

Short summary.

Segment Conclusions

<details>
<summary>[01:24-02:44] Install the dock animation.</summary>

The speaker shows why the dock animation matters for the overall workflow.
- Keep the visual feedback compact.
- Avoid turning every note into a rigid evidence table.
</details>
"""

        rendered = render_summary(summary, "https://www.youtube.com/watch?v=abc")

        self.assertIn('<details class="segment-detail">', rendered)
        self.assertIn("<summary>", rendered)
        self.assertIn("watch?v=abc&amp;t=84", rendered)
        self.assertIn("Avoid turning every note into a rigid evidence table.", rendered)

    def test_report_prefers_summary_md_over_legacy_txt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "transcript.txt").write_text("transcript\n", encoding="utf-8")
            (folder / "summary.txt").write_text("legacy summary\n", encoding="utf-8")
            (folder / "summary.md").write_text("markdown summary\n", encoding="utf-8")

            report = write_report(folder, {"title": "Video", "source_url": "https://example.test/video"})

            self.assertIn("markdown summary", report.read_text(encoding="utf-8"))
            self.assertEqual("markdown summary", summary_preview(folder))

    def test_report_reads_legacy_summary_txt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "transcript.txt").write_text("transcript\n", encoding="utf-8")
            (folder / "summary.txt").write_text("legacy summary\n", encoding="utf-8")

            report = write_report(folder, {"title": "Video", "source_url": "https://example.test/video"})

            self.assertIn("legacy summary", report.read_text(encoding="utf-8"))
            self.assertEqual("legacy summary", summary_preview(folder))
            self.assertTrue((folder / "summary.md").exists())
            self.assertFalse((folder / "summary.txt").exists())


if __name__ == "__main__":
    unittest.main()
