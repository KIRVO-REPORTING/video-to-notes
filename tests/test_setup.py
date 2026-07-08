from __future__ import annotations

import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ytlt.cli import process_url, run_configure
from ytlt.config import (
    configured_language,
    configured_model_path,
    configured_output_environment,
    local_whisper_disabled,
    model_cache_dir,
    model_cache_path,
    write_config,
)
from ytlt.spec import InstallProfile, MachineSpec, NvidiaGpu, install_commands, recommend, should_cache_model


def _spec(workspace: Path) -> MachineSpec:
    return MachineSpec(
        os="Darwin",
        arch="arm64",
        python="3.11.0",
        ram_gb=24.0,
        is_apple_silicon=True,
        nvidia_gpus=[],
        ffmpeg="/usr/local/bin/ffmpeg",
        workspace=str(workspace),
    )


def _profile() -> InstallProfile:
    return InstallProfile(
        id="apple-silicon-turbo",
        backend="mlx",
        model="mlx-community/whisper-large-v3-turbo",
        device="mlx",
        compute_type="mlx",
        pip_extras=["mlx"],
        reason="test",
        notes=[],
    )


class SetupTests(unittest.TestCase):
    def test_install_plan_downloads_model_to_workspace_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = model_cache_dir(Path(tmp))
            commands = install_commands(_profile(), Path("/repo"), model_target=target)

        self.assertIn(".[mlx]", commands[0])
        self.assertIn("resolve_ffmpeg_path", commands[1][-1])
        self.assertEqual(commands[2][-2:], ["--target", str(target)])
        self.assertIn("mlx-community/whisper-large-v3-turbo", commands[2])

    def test_config_records_ffmpeg_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            profile = _profile()
            write_config(workspace, _spec(workspace), profile, model_path=None)

            config = json.loads((workspace / "config.json").read_text(encoding="utf-8"))

        self.assertEqual(config["ffmpeg"]["path"], "/usr/local/bin/ffmpeg")

    def test_config_records_user_preferences_and_disabled_whisper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            profile = InstallProfile(
                id="captions-only",
                backend="none",
                model=None,
                device=None,
                compute_type=None,
                pip_extras=[],
                reason="disabled",
                notes=[],
            )
            write_config(
                workspace,
                _spec(workspace),
                profile,
                preferred_language="ja",
                output_environment="obsidian",
                whisper_model_mode="none",
            )

            self.assertEqual(configured_language(workspace), "ja")
            self.assertEqual(configured_output_environment(workspace), "obsidian")
            self.assertTrue(local_whisper_disabled(workspace))

    def test_apple_silicon_limited_memory_uses_public_mlx_small_checkpoint(self) -> None:
        spec = MachineSpec(
            os="Darwin",
            arch="arm64",
            python="3.11.0",
            ram_gb=8.0,
            is_apple_silicon=True,
            nvidia_gpus=[],
            ffmpeg="/usr/local/bin/ffmpeg",
            workspace="/tmp/youtube",
        )

        profile = recommend(spec)

        self.assertEqual(profile.backend, "mlx")
        self.assertEqual(profile.model, "mlx-community/whisper-small-mlx")
        self.assertTrue(should_cache_model(profile))

    def test_nvidia_turbo_uses_faster_whisper_alias_without_workspace_download(self) -> None:
        spec = MachineSpec(
            os="Windows",
            arch="AMD64",
            python="3.11.0",
            ram_gb=32.0,
            is_apple_silicon=False,
            nvidia_gpus=[NvidiaGpu(name="RTX", vram_mb=12288)],
            ffmpeg="C:/ffmpeg/bin/ffmpeg.exe",
            workspace="C:/Users/test/Documents/youtube",
        )

        profile = recommend(spec)
        commands = install_commands(profile, Path("/repo"), model_target=Path("/models"))

        self.assertEqual(profile.backend, "faster-whisper")
        self.assertEqual(profile.model, "large-v3-turbo")
        self.assertFalse(should_cache_model(profile))
        self.assertFalse(any("download-model" in command for command in commands for command in command))
        self.assertIn("large-v3-turbo", commands[-1][-1])

    def test_configured_model_path_uses_matching_downloaded_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            profile = _profile()
            model_path = model_cache_path(workspace, profile.model or "")
            model_path.mkdir(parents=True)
            write_config(workspace, _spec(workspace), profile, model_path=model_path)

            self.assertEqual(configured_model_path(workspace, profile), str(model_path))

    def test_process_uses_configured_model_path_for_whisper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            profile = _profile()
            spec = _spec(workspace)
            model_path = model_cache_path(workspace, profile.model or "")
            model_path.mkdir(parents=True)
            write_config(workspace, spec, profile, model_path=model_path)
            info = {
                "id": "abc",
                "title": "Needs Whisper",
                "webpage_url": "https://example.test/video",
                "subtitles": {},
                "automatic_captions": {},
            }
            args = argparse.Namespace(
                workspace=str(workspace),
                output_root=None,
                url="https://example.test/video",
                cookies_from_browser=None,
                cookies=None,
                force_transcribe=False,
                language="en",
                no_auto_subs=False,
                no_transcribe_fallback=False,
                model=None,
                backend=None,
                device=None,
                compute_type=None,
                referer=None,
                delete_video=True,
                open=False,
            )

            def fake_transcribe(video_path: Path, folder: Path, _profile: InstallProfile, **kwargs: object) -> Path:
                self.assertEqual(kwargs["model_override"], str(model_path))
                transcript = folder / "transcript.txt"
                transcript.write_text("transcribed\n", encoding="utf-8")
                return transcript

            with patch("ytlt.cli.extract_info", return_value=info), patch("ytlt.cli.probe", return_value=spec), patch(
                "ytlt.cli.recommend", return_value=profile
            ), patch("ytlt.cli.download_video", return_value=workspace / "video.mp4"), patch(
                "ytlt.cli.transcribe_video", side_effect=fake_transcribe
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(process_url(args), 0)

    def test_process_fails_without_captions_when_whisper_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            disabled = InstallProfile(
                id="captions-only",
                backend="none",
                model=None,
                device=None,
                compute_type=None,
                pip_extras=[],
                reason="disabled",
                notes=[],
            )
            write_config(workspace, _spec(workspace), disabled, whisper_model_mode="none")
            info = {
                "id": "abc",
                "title": "Needs Whisper",
                "webpage_url": "https://example.test/video",
                "subtitles": {},
                "automatic_captions": {},
            }
            args = argparse.Namespace(
                workspace=str(workspace),
                output_root=None,
                url="https://example.test/video",
                cookies_from_browser=None,
                cookies=None,
                force_transcribe=False,
                language=None,
                no_auto_subs=False,
                no_transcribe_fallback=False,
                model=None,
                backend=None,
                device=None,
                compute_type=None,
                referer=None,
                delete_video=True,
                open=False,
            )

            with patch("ytlt.cli.extract_info", return_value=info):
                with self.assertRaises(SystemExit) as raised:
                    process_url(args)

            self.assertIn("local Whisper fallback is disabled", str(raised.exception))

    def test_configure_dry_run_reports_recommendation_without_writing_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            args = argparse.Namespace(
                workspace=str(workspace),
                language="zh",
                environment="local",
                model_choice="recommended",
                model=None,
                execute=False,
                dry_run=True,
            )

            with patch("ytlt.cli.probe", return_value=_spec(workspace)), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(run_configure(args), 0)

            payload = json.loads(out.getvalue())
            self.assertEqual(payload["language"], "zh")
            self.assertEqual(payload["output_environment"], "local")
            self.assertEqual(payload["selected_profile"]["model"], "mlx-community/whisper-large-v3-turbo")
            self.assertFalse((workspace / "config.json").exists())

    def test_configure_notion_next_steps_include_connector_and_cli_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            args = argparse.Namespace(
                workspace=str(workspace),
                language="zh",
                environment="notion",
                model_choice="none",
                model=None,
                execute=False,
                dry_run=False,
            )

            with patch("ytlt.cli.probe", return_value=_spec(workspace)), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(run_configure(args), 0)

            payload = json.loads(out.getvalue())
            next_steps = "\n".join(payload["next_steps"])
            self.assertIn("Notion connector/MCP", next_steps)
            self.assertIn("NOTION_TOKEN", next_steps)

    def test_configure_obsidian_records_auto_discovered_vault(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            vault = root / "vault"
            (vault / ".obsidian").mkdir(parents=True)
            args = argparse.Namespace(
                workspace=str(workspace),
                language="zh",
                environment="obsidian",
                obsidian_vault=None,
                model_choice="none",
                model=None,
                execute=False,
                dry_run=False,
            )

            with (
                patch("ytlt.cli.probe", return_value=_spec(workspace)),
                patch("ytlt.cli.discover_obsidian_vaults", return_value=[vault.resolve()]),
                contextlib.redirect_stdout(io.StringIO()) as out,
            ):
                self.assertEqual(run_configure(args), 0)

            payload = json.loads(out.getvalue())
            config = json.loads((workspace / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["obsidian"]["vault_path"], str(vault.resolve()))
            self.assertEqual(config["obsidian"]["vault_path"], str(vault.resolve()))
            self.assertIn("Obsidian vault is configured", "\n".join(payload["next_steps"]))


if __name__ == "__main__":
    unittest.main()
