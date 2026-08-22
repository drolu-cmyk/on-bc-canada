from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from runtime.implementation_workspace import FileChange, RegisteredVerificationRunner, StagingWorkspace


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ImplementationWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "runtime").mkdir()
        (self.root / "docs").mkdir()
        (self.root / "runtime" / "example.py").write_text("VALUE = 1\n", encoding="utf-8")
        self.workspace = StagingWorkspace(self.root, allowed_roots=("runtime", "docs"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_includes_hash_and_missing_file_state(self):
        snapshots = self.workspace.snapshot(("runtime/example.py", "docs/new.md"))
        by_path = {item.path: item for item in snapshots}
        self.assertTrue(by_path["runtime/example.py"].exists)
        self.assertEqual(sha("VALUE = 1\n"), by_path["runtime/example.py"].sha256)
        self.assertFalse(by_path["docs/new.md"].exists)

    def test_valid_update_and_create_apply_with_preconditions(self):
        applied = self.workspace.apply_changes(
            (
                FileChange(
                    operation="update",
                    path="runtime/example.py",
                    reason="Update deterministic example behavior.",
                    content="VALUE = 2\n",
                    expected_sha256=sha("VALUE = 1\n"),
                ),
                FileChange(
                    operation="create",
                    path="docs/new.md",
                    reason="Document the new deterministic example behavior.",
                    content="# Example\n\nVALUE is now 2.\n",
                ),
            )
        )
        self.assertEqual(2, len(applied))
        self.assertEqual("VALUE = 2\n", (self.root / "runtime" / "example.py").read_text(encoding="utf-8"))
        self.assertTrue((self.root / "docs" / "new.md").exists())

    def test_path_traversal_and_forbidden_roots_fail_closed(self):
        for path in ("../outside.py", ".env/config.py", "secrets/key.txt"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    self.workspace.snapshot((path,))

    def test_stale_update_hash_fails_without_mutation(self):
        with self.assertRaisesRegex(ValueError, "stale or missing"):
            self.workspace.apply_changes(
                (
                    FileChange(
                        operation="update",
                        path="runtime/example.py",
                        reason="Attempt stale update for test coverage.",
                        content="VALUE = 3\n",
                        expected_sha256="0" * 64,
                    ),
                )
            )
        self.assertEqual("VALUE = 1\n", (self.root / "runtime" / "example.py").read_text(encoding="utf-8"))

    def test_secret_like_generated_content_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "secret material"):
            self.workspace.apply_changes(
                (
                    FileChange(
                        operation="create",
                        path="runtime/credential.py",
                        reason="Secret scan should reject this generated file.",
                        content='OPENAI_API_KEY="sk-proj-abcdefghijklmnopqrstuvwxyz123456"\n',
                    ),
                )
            )

    def test_registered_verification_runs_only_known_commands_without_shell(self):
        runner = RegisteredVerificationRunner(
            self.root,
            {"smoke": ("python", "-c", "print('ok')")},
        )
        result = runner.run(("smoke",))[0]
        self.assertTrue(result.passed)
        self.assertIn("ok", result.stdout)
        with self.assertRaisesRegex(ValueError, "unregistered"):
            runner.run(("arbitrary-shell-command",))


if __name__ == "__main__":
    unittest.main()
