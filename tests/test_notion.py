from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from ytlt.notion import NotionPublishConfig, publish_report_to_notion


class FakeNotionClient:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []
        self.cleared: list[str] = []
        self.appended: list[dict[str, Any]] = []
        self.retrieved_database_ids: list[str] = []
        self.retrieved_data_source_ids: list[str] = []

    def retrieve_database(self, database_id: str) -> dict[str, Any]:
        self.retrieved_database_ids.append(database_id)
        return {"data_sources": [{"id": "data-source-from-db"}]}

    def retrieve_data_source(self, data_source_id: str) -> dict[str, Any]:
        self.retrieved_data_source_ids.append(data_source_id)
        return {
            "id": data_source_id,
            "properties": {
                "Name": {"type": "title"},
                "Source URL": {"type": "url"},
                "Platform": {"type": "select"},
                "Processed": {"type": "date"},
                "Processing Seconds": {"type": "number"},
                "Summary": {"type": "rich_text"},
                "Local Report": {"type": "rich_text"},
            },
        }

    def create_page(self, parent: dict[str, Any], properties: dict[str, Any]) -> dict[str, Any]:
        self.created.append({"parent": parent, "properties": properties})
        return {"id": "page-123", "url": "https://notion.test/page-123"}

    def update_page(self, page_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        self.updated.append({"page_id": page_id, "properties": properties})
        return {"id": page_id, "url": "https://notion.test/existing"}

    def append_children(self, block_id: str, children: list[dict[str, Any]]) -> None:
        self.appended.append({"block_id": block_id, "children": children})

    def clear_children(self, block_id: str) -> None:
        self.cleared.append(block_id)


class NotionPublishingTests(unittest.TestCase):
    def test_explicit_target_ignores_environment_targets(self) -> None:
        with patch.dict("os.environ", {"NOTION_PARENT_PAGE_ID": "env-parent"}):
            config = NotionPublishConfig.from_values(token="secret", data_source_id="explicit-data-source")

        self.assertIsNone(config.parent_page_id)
        self.assertEqual(config.data_source_id, "explicit-data-source")

    def test_publish_creates_data_source_page_and_records_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self._write_report_files(folder)
            client = FakeNotionClient()

            result = publish_report_to_notion(
                folder,
                NotionPublishConfig(token="secret", data_source_id="data-source-123"),
                client=client,  # type: ignore[arg-type]
            )

            self.assertEqual(result["notion_page_id"], "page-123")
            self.assertEqual(client.retrieved_data_source_ids, ["data-source-123"])
            self.assertEqual(client.created[0]["parent"]["data_source_id"], "data-source-123")
            self.assertIn("Name", client.created[0]["properties"])
            self.assertEqual(client.created[0]["properties"]["Source URL"]["url"], "https://example.test/watch?v=abc")
            self.assertEqual(client.created[0]["properties"]["Processed"]["date"]["start"], "2026-07-05T00:00:00+00:00")
            self.assertEqual(client.created[0]["properties"]["Processing Seconds"]["number"], 12.345)
            self.assertIn("Local Report", client.created[0]["properties"])
            self.assertNotIn("Status", client.created[0]["properties"])
            self.assertFalse(client.cleared)

            metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["notion_page_id"], "page-123")
            self.assertEqual(metadata["notion_url"], "https://notion.test/page-123")

    def test_publish_updates_existing_notion_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self._write_report_files(folder, extra_metadata={"notion_page_id": "existing-page"})
            client = FakeNotionClient()

            publish_report_to_notion(
                folder,
                NotionPublishConfig(token="secret", database_id="database-123"),
                client=client,  # type: ignore[arg-type]
            )

            self.assertEqual(client.retrieved_database_ids, ["database-123"])
            self.assertEqual(client.retrieved_data_source_ids, ["data-source-from-db"])
            self.assertEqual(client.updated[0]["page_id"], "existing-page")
            self.assertEqual(client.cleared, ["existing-page"])
            self.assertFalse(client.created)
            self.assertEqual(client.appended[0]["block_id"], "existing-page")

    def test_summary_timestamps_become_notion_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self._write_report_files(folder)
            client = FakeNotionClient()

            publish_report_to_notion(
                folder,
                NotionPublishConfig(token="secret", data_source_id="data-source-123"),
                client=client,  # type: ignore[arg-type]
            )

            rendered = json.dumps(client.appended[0]["children"], ensure_ascii=False)
            self.assertIn('"content": "[01:24-02:44]"', rendered)
            self.assertIn('"url": "https://example.test/watch?v=abc&t=84"', rendered)

    def test_nested_key_points_become_nested_notion_bullets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self._write_report_files(
                folder,
                summary=(
                    "Summary\n\nShort summary.\n\nKey Points\n\n"
                    "- [01:24-02:44] Main conclusion.\n"
                    "  - [01:30-01:40] Supporting detail.\n"
                ),
            )
            client = FakeNotionClient()

            publish_report_to_notion(
                folder,
                NotionPublishConfig(token="secret", data_source_id="data-source-123"),
                client=client,  # type: ignore[arg-type]
            )

            children = client.appended[0]["children"]
            rendered = json.dumps(children, ensure_ascii=False)
            self.assertIn('"type": "bulleted_list_item"', rendered)
            self.assertIn('"children"', rendered)
            self.assertIn('"content": "[01:30-01:40]"', rendered)
            self.assertIn('"url": "https://example.test/watch?v=abc&t=90"', rendered)

    def test_foldable_segments_become_notion_toggles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self._write_report_files(
                folder,
                summary=(
                    "Summary\n\nShort summary.\n\nSegment Conclusions\n\n"
                    "<details>\n"
                    "<summary>[01:24-02:44] Important conclusion.</summary>\n\n"
                    "Natural-language detail without rigid labels.\n"
                    "- Supporting detail.\n"
                    "</details>\n"
                ),
            )
            client = FakeNotionClient()

            publish_report_to_notion(
                folder,
                NotionPublishConfig(token="secret", data_source_id="data-source-123"),
                client=client,  # type: ignore[arg-type]
            )

            children = client.appended[0]["children"]
            rendered = json.dumps(children, ensure_ascii=False)
            self.assertIn('"type": "toggle"', rendered)
            self.assertIn('"content": "[01:24-02:44]"', rendered)
            self.assertIn('"url": "https://example.test/watch?v=abc&t=84"', rendered)
            self.assertIn("Natural-language detail without rigid labels.", rendered)

    def test_transcript_is_last_notion_toggle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self._write_report_files(folder)
            client = FakeNotionClient()

            publish_report_to_notion(
                folder,
                NotionPublishConfig(token="secret", data_source_id="data-source-123"),
                client=client,  # type: ignore[arg-type]
            )

            transcript = client.appended[0]["children"][-1]
            rendered = json.dumps(transcript, ensure_ascii=False)
            self.assertEqual(transcript["type"], "toggle")
            self.assertIn('"content": "Transcript"', rendered)
            self.assertIn('"type": "code"', rendered)
            self.assertIn("Transcript text.", rendered)

    def _write_report_files(
        self,
        folder: Path,
        extra_metadata: dict[str, Any] | None = None,
        summary: str | None = None,
    ) -> None:
        metadata = {
            "id": "abc",
            "title": "Video Title",
            "source_url": "https://example.test/watch?v=abc",
            "platform": "youtube",
            "channel": "Channel",
            "duration_seconds": 120,
            "published_at": "2026-07-01",
            "processed_at": "2026-07-05T00:00:00+00:00",
            "processing_seconds": 12.345,
            "transcript_source": "manual_subtitle",
            "transcript_file": "transcript.txt",
        }
        metadata.update(extra_metadata or {})
        (folder / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        (folder / "summary.md").write_text(
            summary or "Summary\n\nShort summary.\n\nKey Points\n\n- [01:24-02:44] Important point.\n",
            encoding="utf-8",
        )
        (folder / "transcript.txt").write_text("Transcript text.", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
