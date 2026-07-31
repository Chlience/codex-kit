from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOL = REPOSITORY_ROOT / "scripts" / "codex_kit.py"
MANAGED_START = "<!-- codex-kit:managed:start -->"
MANAGED_END = "<!-- codex-kit:managed:end -->"


class CodexKitCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.repo = root / "kit"
        self.codex_home = root / "codex-home"
        (self.repo / "catalog").mkdir(parents=True)
        (self.repo / "agents" / "modules").mkdir(parents=True)
        self.codex_home.mkdir()
        self.write_catalog("skills", [])
        self.write_catalog("plugins", [])
        self.write_catalog("agents", [])

    def write_catalog(self, kind: str, items: list[dict[str, object]]) -> None:
        array_names = {
            "skills": "skills",
            "plugins": "plugins",
            "agents": "modules",
        }
        payload = {"schema_version": 1, array_names[kind]: items}
        (self.repo / "catalog" / f"{kind}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def add_module(
        self, module_id: str, body: str, *, description: str = "Test rules"
    ) -> Path:
        path = self.repo / "agents" / "modules" / f"{module_id}.md"
        path.write_text(body, encoding="utf-8")
        agents_path = self.repo / "catalog" / "agents.json"
        catalog = json.loads(agents_path.read_text(encoding="utf-8"))
        catalog["modules"].append(
            {
                "id": module_id,
                "description": description,
                "path": f"agents/modules/{module_id}.md",
            }
        )
        agents_path.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOL), *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def validate(self) -> subprocess.CompletedProcess[str]:
        return self.run_cli("validate", "--repo", str(self.repo))

    def preview(
        self, *module_ids: str
    ) -> tuple[subprocess.CompletedProcess[str], str, str]:
        arguments = [
            "render-agents",
            "--repo",
            str(self.repo),
            "--codex-home",
            str(self.codex_home),
        ]
        for module_id in module_ids:
            arguments.extend(["--module", module_id])
        result = self.run_cli(*arguments)
        current_match = re.search(
            r"^current_sha256=(MISSING|[0-9a-f]{64})$", result.stdout, re.MULTILINE
        )
        rendered_match = re.search(
            r"^rendered_sha256=([0-9a-f]{64})$", result.stdout, re.MULTILINE
        )
        if current_match is None or rendered_match is None:
            self.fail(
                "preview did not emit hashes\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result, current_match.group(1), rendered_match.group(1)

    def apply(
        self, module_ids: tuple[str, ...], current: str, rendered: str
    ) -> subprocess.CompletedProcess[str]:
        arguments = [
            "render-agents",
            "--repo",
            str(self.repo),
            "--codex-home",
            str(self.codex_home),
        ]
        for module_id in module_ids:
            arguments.extend(["--module", module_id])
        arguments.extend(
            [
                "--apply",
                "--expect-current-sha256",
                current,
                "--expect-rendered-sha256",
                rendered,
            ]
        )
        return self.run_cli(*arguments)

    def test_validate_accepts_empty_catalogs(self) -> None:
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0 skill(s), 0 plugin(s), 0 module(s)", result.stdout)

    def test_validate_rejects_a_symlinked_catalog_directory(self) -> None:
        catalog = self.repo / "catalog"
        external = self.repo.parent / "external-catalog"
        catalog.rename(external)
        catalog.symlink_to(external, target_is_directory=True)

        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-symlink directory", result.stderr)

    def test_validate_rejects_unknown_fields_duplicate_ids_and_controls(self) -> None:
        invalid_catalogs = (
            [
                {
                    "id": "one",
                    "description": "One",
                    "repository": "https://github.com/example/one",
                    "unexpected": True,
                }
            ],
            [
                {
                    "id": "same",
                    "description": "One",
                    "repository": "https://github.com/example/one",
                },
                {
                    "id": "same",
                    "description": "Two",
                    "repository": "https://github.com/example/two",
                },
            ],
            [
                {
                    "id": "control",
                    "description": "bad\u0000text",
                    "repository": "https://github.com/example/control",
                }
            ],
        )
        expected_errors = ("unknown field", "duplicate id", "control character")
        for items, expected_error in zip(invalid_catalogs, expected_errors):
            with self.subTest(expected_error=expected_error):
                self.write_catalog("skills", items)
                result = self.validate()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected_error, result.stderr)

    def test_validate_rejects_bad_types_names_urls_and_scope(self) -> None:
        cases = (
            (
                "skills",
                [
                    {
                        "id": "Bad_ID",
                        "description": "Bad ID",
                        "repository": "https://github.com/example/repo",
                    }
                ],
                "kebab-case",
            ),
            (
                "skills",
                [
                    {
                        "id": "bad-url",
                        "description": "Bad URL",
                        "repository": "http://github.com/example/repo",
                    }
                ],
                "HTTPS github.com",
            ),
            (
                "skills",
                [
                    {
                        "id": "bad-scope",
                        "description": "Bad scope",
                        "repository": "https://github.com/example/repo",
                        "scope": "global",
                    }
                ],
                "scope",
            ),
            (
                "plugins",
                [
                    {
                        "id": "plugin",
                        "description": "Plugin",
                        "repository": "https://github.com/example/repo",
                        "marketplace": "Bad Marketplace",
                    }
                ],
                "kebab-case",
            ),
        )
        for kind, items, expected_error in cases:
            with self.subTest(kind=kind, expected_error=expected_error):
                self.write_catalog(kind, items)
                result = self.validate()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected_error, result.stderr)
                self.write_catalog(kind, [])

        agents = self.repo / "catalog" / "agents.json"
        agents.write_text(
            '{"schema_version": true, "modules": []}\n', encoding="utf-8"
        )
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("integer 1", result.stderr)

    def test_validate_rejects_unsafe_skill_paths(self) -> None:
        unsafe_paths = (
            "/absolute/skill",
            "../skill",
            "skills/../skill",
            r"skills\skill",
            "skills//skill",
            ".",
            "skills/./skill",
            "skills/skill/",
        )
        for skill_path in unsafe_paths:
            with self.subTest(path=skill_path):
                self.write_catalog(
                    "skills",
                    [
                        {
                            "id": "unsafe-path",
                            "description": "Unsafe path",
                            "repository": "https://github.com/example/repo",
                            "path": skill_path,
                        }
                    ],
                )
                result = self.validate()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("repository-relative POSIX path", result.stderr)

    def test_validate_rejects_unsafe_module_files(self) -> None:
        marker_path = self.add_module(
            "has-marker", "<!-- codex-kit:managed:start -->\n"
        )
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("reserved codex-kit marker", result.stderr)

        marker_path.unlink()
        external = self.repo.parent / "external.md"
        external.write_text("# Outside\n", encoding="utf-8")
        marker_path.symlink_to(external)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-symlink regular file", result.stderr)

    def test_validate_rejects_unnormalized_module_paths(self) -> None:
        (self.repo / "agents" / "modules" / "rules.md").write_text(
            "# Rules\n", encoding="utf-8"
        )
        unsafe_paths = (
            "agents/modules//rules.md",
            "agents/modules/./rules.md",
            "agents/./modules/rules.md",
        )
        for module_path in unsafe_paths:
            with self.subTest(path=module_path):
                self.write_catalog(
                    "agents",
                    [
                        {
                            "id": "rules",
                            "description": "Rules",
                            "path": module_path,
                        }
                    ],
                )
                result = self.validate()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("repository-relative POSIX path", result.stderr)

    def test_preview_appends_in_catalog_order_without_writing(self) -> None:
        target = self.codex_home / "AGENTS.md"
        original = b"# Local rules\r\n\r\nKeep this byte sequence.\n"
        target.write_bytes(original)
        self.add_module("first", "# First\n")
        self.add_module("second", "# Second without final newline")

        result, current, rendered = self.preview("second", "first")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(current, r"^[0-9a-f]{64}$")
        self.assertRegex(rendered, r"^[0-9a-f]{64}$")
        self.assertIn("--- ", result.stdout)
        self.assertIn("+++ ", result.stdout)
        self.assertLess(result.stdout.index("# First"), result.stdout.index("# Second"))
        self.assertEqual(target.read_bytes(), original)
        self.assertFalse((self.codex_home / "backups").exists())

        applied = self.apply(("second", "first"), current, rendered)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        content = target.read_bytes()
        self.assertTrue(content.startswith(original))
        self.assertIn(MANAGED_START.encode(), content)
        self.assertIn(b"<!-- codex-kit:module:first:start -->", content)
        self.assertIn(b"<!-- codex-kit:module:second:end -->", content)
        self.assertLess(content.index(b"# First"), content.index(b"# Second"))

    def test_replacement_preserves_all_bytes_outside_managed_block(self) -> None:
        prefix = b"# Before\r\nopaque-before\xce\xb1\n"
        suffix = b"\r\nopaque-after\n"
        old_block = (
            MANAGED_START.encode()
            + b"\nold managed content\n"
            + MANAGED_END.encode()
        )
        target = self.codex_home / "AGENTS.md"
        target.write_bytes(prefix + old_block + suffix)
        self.add_module("rules", "# Current rules\n")

        result, current, rendered = self.preview("rules")
        self.assertEqual(result.returncode, 0, result.stderr)
        applied = self.apply(("rules",), current, rendered)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        content = target.read_bytes()
        self.assertTrue(content.startswith(prefix))
        self.assertTrue(content.endswith(suffix))
        self.assertNotIn(b"old managed content", content)
        self.assertIn(b"# Current rules", content)

    def test_nonempty_override_stops_rendering(self) -> None:
        self.add_module("rules", "# Rules\n")
        (self.codex_home / "AGENTS.override.md").write_text(
            "# Override\n", encoding="utf-8"
        )
        result = self.run_cli(
            "render-agents",
            "--repo",
            str(self.repo),
            "--codex-home",
            str(self.codex_home),
            "--module",
            "rules",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-empty AGENTS.override.md", result.stderr)
        self.assertFalse((self.codex_home / "AGENTS.md").exists())

    def test_symlink_target_is_rejected(self) -> None:
        self.add_module("rules", "# Rules\n")
        external = self.repo.parent / "external-agents.md"
        external.write_text("# External\n", encoding="utf-8")
        (self.codex_home / "AGENTS.md").symlink_to(external)
        result = self.run_cli(
            "render-agents",
            "--repo",
            str(self.repo),
            "--codex-home",
            str(self.codex_home),
            "--module",
            "rules",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-symlink regular file", result.stderr)
        self.assertEqual(external.read_text(encoding="utf-8"), "# External\n")

    def test_apply_creates_backup_and_preserves_permissions(self) -> None:
        self.add_module("rules", "# Rules\n")
        target = self.codex_home / "AGENTS.md"
        original = b"# Existing\n"
        target.write_bytes(original)
        target.chmod(0o640)
        _, current, rendered = self.preview("rules")

        result = self.apply(("rules",), current, rendered)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)
        backups = list(
            (self.codex_home / "backups" / "codex-kit").glob("*/AGENTS.md")
        )
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o640)
        self.assertIn(f"backup={backups[0]}", result.stdout)

    def test_apply_creates_a_missing_target_without_backup(self) -> None:
        self.add_module("rules", "# Rules\n")
        target = self.codex_home / "AGENTS.md"
        _, current, rendered = self.preview("rules")
        self.assertEqual(current, "MISSING")

        result = self.apply(("rules",), current, rendered)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"# Rules", target.read_bytes())
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertFalse((self.codex_home / "backups").exists())

    def test_apply_rejects_symlinked_backup_paths(self) -> None:
        self.add_module("rules", "# Rules\n")
        target = self.codex_home / "AGENTS.md"
        original = b"# Existing\n"
        target.write_bytes(original)
        _, current, rendered = self.preview("rules")
        external = self.repo.parent / "external-backups"
        external.mkdir()

        backups = self.codex_home / "backups"
        backups.symlink_to(external, target_is_directory=True)
        result = self.apply(("rules",), current, rendered)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-symlink directory", result.stderr)
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(list(external.iterdir()), [])

        backups.unlink()
        backups.mkdir()
        (backups / "codex-kit").symlink_to(external, target_is_directory=True)
        result = self.apply(("rules",), current, rendered)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-symlink directory", result.stderr)
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(list(external.iterdir()), [])

    def test_apply_requires_both_preview_hashes(self) -> None:
        self.add_module("rules", "# Rules\n")
        result = self.run_cli(
            "render-agents",
            "--repo",
            str(self.repo),
            "--codex-home",
            str(self.codex_home),
            "--module",
            "rules",
            "--apply",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--apply requires", result.stderr)
        self.assertFalse((self.codex_home / "AGENTS.md").exists())

    def test_direct_apply_rejects_non_utf8_agents_file(self) -> None:
        self.add_module("rules", "# Rules\n")
        invalid = b"# Rules\n\xff\n"
        (self.codex_home / "AGENTS.md").write_bytes(invalid)
        result = self.run_cli(
            "render-agents",
            "--repo",
            str(self.repo),
            "--codex-home",
            str(self.codex_home),
            "--module",
            "rules",
            "--apply",
            "--expect-current-sha256",
            hashlib.sha256(invalid).hexdigest(),
            "--expect-rendered-sha256",
            "0" * 64,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not valid UTF-8", result.stderr)
        self.assertEqual((self.codex_home / "AGENTS.md").read_bytes(), invalid)
        self.assertFalse((self.codex_home / "backups").exists())

    def test_apply_stops_when_target_changes_after_preview(self) -> None:
        self.add_module("rules", "# Rules\n")
        target = self.codex_home / "AGENTS.md"
        target.write_text("# Initial\n", encoding="utf-8")
        _, current, rendered = self.preview("rules")
        changed = b"# Changed after preview\n"
        target.write_bytes(changed)

        result = self.apply(("rules",), current, rendered)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("changed after preview", result.stderr)
        self.assertEqual(target.read_bytes(), changed)
        self.assertFalse((self.codex_home / "backups").exists())

    def test_apply_stops_when_module_changes_after_preview(self) -> None:
        module_path = self.add_module("rules", "# Version one\n")
        _, current, rendered = self.preview("rules")
        module_path.write_text("# Version two\n", encoding="utf-8")

        result = self.apply(("rules",), current, rendered)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rendered AGENTS.md changed after preview", result.stderr)
        self.assertFalse((self.codex_home / "AGENTS.md").exists())
        self.assertFalse((self.codex_home / "backups").exists())

    def test_malformed_or_reversed_managed_markers_are_rejected(self) -> None:
        self.add_module("rules", "# Rules\n")
        target = self.codex_home / "AGENTS.md"
        cases = (
            f"{MANAGED_START}\nmissing end\n",
            f"{MANAGED_END}\n{MANAGED_START}\n",
            "<!-- codex-kit:managed:start-ish -->\n",
        )
        for content in cases:
            with self.subTest(content=content):
                target.write_text(content, encoding="utf-8")
                result = self.run_cli(
                    "render-agents",
                    "--repo",
                    str(self.repo),
                    "--codex-home",
                    str(self.codex_home),
                    "--module",
                    "rules",
                )
                self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
