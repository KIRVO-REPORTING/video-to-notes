from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ytlt.obsidian import (
    ObsidianPublishConfig,
    discover_obsidian_vaults,
    publish_report_to_obsidian,
    sync_workspace_to_obsidian,
)


class ObsidianPublishingTests(unittest.TestCase):
    def test_explicit_vault_ignores_environment_vault(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"OBSIDIAN_VAULT_PATH": "env-vault"}):
            config = ObsidianPublishConfig.from_values(vault_path=tmp, reports_dir="Reports")

        self.assertEqual(config.vault_path, Path(tmp).resolve())
        self.assertEqual(config.reports_dir, "Reports")

    def test_workspace_configured_vault_is_used_without_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {}, clear=True):
            root = Path(tmp)
            workspace = root / "workspace"
            vault = root / "vault"
            (vault / ".obsidian").mkdir(parents=True)
            workspace.mkdir()
            (workspace / "config.json").write_text(
                json.dumps({"obsidian": {"vault_path": str(vault), "reports_dir": "Reports"}}),
                encoding="utf-8",
            )

            with patch("ytlt.obsidian.detect_obsidian_vault", return_value=None):
                config = ObsidianPublishConfig.from_values(workspace=workspace)

        self.assertEqual(config.vault_path, vault.resolve())
        self.assertEqual(config.reports_dir, "Reports")

    def test_discovers_recent_obsidian_vault_from_app_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {}, clear=True):
            home = Path(tmp)
            old_vault = home / "Old Vault"
            new_vault = home / "New Vault"
            (old_vault / ".obsidian").mkdir(parents=True)
            (new_vault / ".obsidian").mkdir(parents=True)
            state_dir = home / "Library" / "Application Support" / "obsidian"
            state_dir.mkdir(parents=True)
            (state_dir / "obsidian.json").write_text(
                json.dumps(
                    {
                        "vaults": {
                            "old": {"path": str(old_vault), "ts": 1},
                            "new": {"path": str(new_vault), "ts": 2, "open": True},
                        }
                    }
                ),
                encoding="utf-8",
            )

            vaults = discover_obsidian_vaults(home)

        self.assertEqual(vaults, [new_vault.resolve(), old_vault.resolve()])

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
            self.assertTrue(note.name.startswith("Video Title - "))
            self.assertIn("# Video Title", note_text)
            self.assertIn("aliases:", note_text)
            self.assertIn('  - "Video Title"', note_text)
            self.assertIn("## Segment Conclusions", note_text)
            self.assertIn("[01:24-02:44](https://example.test/watch?v=abc&t=84)", note_text)
            self.assertIn("[[Video Reports/", index.read_text(encoding="utf-8"))

            metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["obsidian_note_path"], str(note))
            self.assertEqual(metadata["obsidian_vault_path"], str(vault.resolve()))
            self.assertEqual(metadata["obsidian_sync_method"], "video_to_notes_cli_vault")

    def test_publish_generates_content_tags_from_summary_and_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "workspace" / "processed" / "video"
            folder.mkdir(parents=True)
            self._write_report_files(folder, extra_metadata={"title": "AI Safety Roadmap"})
            (folder / "summary.md").write_text(
                "Summary\n\nThis video covers reinforcement learning, AI safety, model evaluation, and governance.\n",
                encoding="utf-8",
            )
            (folder / "transcript.txt").write_text(
                "The talk compares reinforcement learning systems with AI safety review practices.",
                encoding="utf-8",
            )

            result = publish_report_to_obsidian(folder, ObsidianPublishConfig(vault_path=root / "vault"))
            note_text = Path(result["obsidian_note_path"]).read_text(encoding="utf-8")

        self.assertIn('  - "ai-safety"', note_text)
        self.assertIn('  - "reinforcement-learning"', note_text)

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
