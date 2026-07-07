from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ytlt.obsidian import ObsidianPublishConfig, publish_report_to_obsidian, sync_workspace_to_obsidian


class ObsidianPublishingTests(unittest.TestCase):
    def test_explicit_vault_ignores_environment_vault(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"OBSIDIAN_VAULT_PATH": "env-vault"}):
            config = ObsidianPublishConfig.from_values(vault_path=tmp, reports_dir="Reports")

        self.assertEqual(config.vault_path, Path(tmp).resolve())
        self.assertEqual(config.reports_dir, "Reports")

    def test_publish_creates_note_index_and_records_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "workspace" / "processed" / "video"
            folder.mkdir(parents=True)
            self._write_report_files(folder)
            vault = root / "vault"

            result = publish_report_to_obsidian(
                folder,
                ObsidianPublishConfig(vault_path=vault),
                workspace=root / "workspace",
            )

            note = Path(result["obsidian_note_path"])
            index = Path(result["obsidian_index_note_path"])
            note_text = note.read_text(encoding="utf-8")
            self.assertTrue(note.exists())
            self.assertTrue(index.exists())
            self.assertIn("# Video Title", note_text)
            self.assertIn("## Segment Conclusions", note_text)
            self.assertIn("[01:24-02:44](https://example.test/watch?v=abc&t=84)", note_text)
            self.assertIn("[[Video Reports/", index.read_text(encoding="utf-8"))

            metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["obsidian_note_path"], str(note))
            self.assertEqual(metadata["obsidian_vault_path"], str(vault.resolve()))
            self.assertEqual(metadata["obsidian_sync_method"], "video_to_notes_cli_vault")

    def test_publish_updates_existing_obsidian_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "workspace" / "processed" / "video"
            folder.mkdir(parents=True)
            existing = root / "vault" / "Reports" / "existing.md"
            self._write_report_files(folder, extra_metadata={"obsidian_note_path": str(existing)})

            publish_report_to_obsidian(
                folder,
                ObsidianPublishConfig(vault_path=root / "vault", reports_dir="Reports"),
            )
            first_text = existing.read_text(encoding="utf-8")

            (folder / "summary.md").write_text("Summary\n\nUpdated summary.\n", encoding="utf-8")
            publish_report_to_obsidian(
                folder,
                ObsidianPublishConfig(vault_path=root / "vault", reports_dir="Reports"),
            )

            self.assertTrue(existing.exists())
            self.assertIn("Updated summary.", existing.read_text(encoding="utf-8"))
            self.assertNotEqual(first_text, existing.read_text(encoding="utf-8"))
            self.assertEqual(len(list((root / "vault" / "Reports").glob("*.md"))), 1)

    def test_sync_workspace_publishes_all_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            for name in ("one", "two"):
                folder = workspace / "processed" / name
                folder.mkdir(parents=True)
                self._write_report_files(folder, extra_metadata={"id": name, "title": f"Video {name}"})

            result = sync_workspace_to_obsidian(workspace, ObsidianPublishConfig(vault_path=root / "vault"))

            self.assertEqual(result["reports"], 2)
            self.assertEqual(len(list((root / "vault" / "Video Reports").glob("*.md"))), 2)
            index_text = (root / "vault" / "Video Reports Dashboard.md").read_text(encoding="utf-8")
            self.assertIn("Video one", index_text)
            self.assertIn("Video two", index_text)

    def _write_report_files(self, folder: Path, extra_metadata: dict[str, object] | None = None) -> None:
        metadata = {
            "id": "abc",
            "title": "Video Title",
            "source_url": "https://example.test/watch?v=abc",
            "platform": "youtube",
            "channel": "Channel",
            "duration_seconds": 120,
            "published_at": "2026-07-01",
            "processed_at": "2026-07-05T00:00:00+00:00",
            "transcript_source": "manual_subtitle",
            "transcript_file": "transcript.txt",
        }
        metadata.update(extra_metadata or {})
        (folder / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        (folder / "report.html").write_text("<html>report</html>", encoding="utf-8")
        (folder / "summary.md").write_text(
            "Summary\n\nShort summary.\n\nSegment Conclusions\n\n[01:24-02:44] Important point.\n",
            encoding="utf-8",
        )
        (folder / "transcript.txt").write_text("Transcript text.", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
