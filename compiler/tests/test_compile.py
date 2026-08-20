from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from curriculum_compiler.compile import CompileError, compile_release


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "content/modules"


def file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class CompilerTests(unittest.TestCase):
    def test_release_is_deterministic_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_root = Path(first)
            second_root = Path(second)
            first_manifest = compile_release(SOURCE, first_root, "applied-ai-training-canada", "0.1.0")
            copied_source = second_root / "source"
            shutil.copytree(SOURCE, copied_source)
            second_output = second_root / "out"
            second_manifest = compile_release(copied_source, second_output, "applied-ai-training-canada", "0.1.0")

            self.assertEqual(file_hashes(first_root), file_hashes(second_output))
            self.assertTrue(first_manifest.exists())
            release_root = first_manifest.parent
            self.assertTrue((release_root / "evidence-index.json").exists())
            self.assertTrue((release_root / "checks/report.json").exists())
            self.assertEqual(
                len(list((release_root / "learner/pages").glob("*.md"))),
                len(list(SOURCE.glob("*.yaml"))),
            )

    def test_missing_outcome_mapping_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "modules"
            source.mkdir()
            module = yaml.safe_load((SOURCE / "cc-101.yaml").read_text(encoding="utf-8"))
            module["evidence"][0]["maps_to_outcomes"] = ["not-an-outcome"]
            (source / "cc-101.yaml").write_text(yaml.safe_dump(module), encoding="utf-8")
            with self.assertRaises(CompileError):
                compile_release(source, Path(temp) / "out", "program", "0.1.0")


if __name__ == "__main__":
    unittest.main()
