"""Constrained local staging workspace for reversible agent-generated changes.

The model never receives an unrestricted filesystem tool. It proposes typed file
changes. This adapter validates every path, precondition, file type, content size,
and obvious secret material before applying changes inside an operator-selected
staging root. Registered verification commands run without a shell.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, Mapping, Sequence


ChangeOperation = Literal["create", "update", "delete"]

_ALLOWED_EXTENSIONS = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".py",
    ".sql",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
_FORBIDDEN_SEGMENTS = {".git", ".env", "secrets", "local-data", "node_modules", ".venv"}
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-proj-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"OPENAI_API_KEY\s*=\s*['\"][^'\"]{12,}['\"]"),
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


@dataclass(frozen=True)
class FileSnapshot:
    path: str
    exists: bool
    sha256: str | None
    content: str | None


@dataclass(frozen=True)
class FileChange:
    operation: ChangeOperation
    path: str
    reason: str
    content: str | None = None
    expected_sha256: str | None = None


@dataclass(frozen=True)
class AppliedChange:
    operation: ChangeOperation
    path: str
    before_sha256: str | None
    after_sha256: str | None


class StagingWorkspace:
    """Apply preconditioned text changes only inside explicitly allowed roots."""

    def __init__(
        self,
        root: str | Path,
        *,
        allowed_roots: Sequence[str],
        max_files: int = 30,
        max_file_bytes: int = 200_000,
    ) -> None:
        self.root = Path(root).resolve()
        if not self.root.exists() or not self.root.is_dir():
            raise ValueError("staging workspace root must exist and be a directory")
        normalized = tuple(self._normalize_allowed_root(item) for item in allowed_roots)
        if not normalized:
            raise ValueError("at least one staging workspace root must be allowed")
        self.allowed_roots = normalized
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes

    @staticmethod
    def _normalize_allowed_root(value: str) -> str:
        path = PurePosixPath(value.strip().replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError(f"invalid allowed workspace root: {value}")
        if any(part in _FORBIDDEN_SEGMENTS for part in path.parts):
            raise ValueError(f"forbidden workspace root: {value}")
        return path.as_posix().rstrip("/")

    def _safe_relative(self, value: str) -> str:
        path = PurePosixPath(value.strip().replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError(f"unsafe workspace path: {value}")
        if any(part in _FORBIDDEN_SEGMENTS for part in path.parts):
            raise ValueError(f"forbidden workspace path: {value}")
        normalized = path.as_posix()
        if not any(normalized == root or normalized.startswith(root + "/") for root in self.allowed_roots):
            raise ValueError(f"workspace path is outside allowed roots: {value}")
        if Path(normalized).suffix.lower() not in _ALLOWED_EXTENSIONS:
            raise ValueError(f"unsupported staging file type: {value}")
        resolved = (self.root / normalized).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"workspace path escapes staging root: {value}") from exc
        return normalized

    def snapshot(self, paths: Sequence[str]) -> list[FileSnapshot]:
        if len(paths) > self.max_files:
            raise ValueError("requested workspace snapshot exceeds file-count limit")
        snapshots: list[FileSnapshot] = []
        seen: set[str] = set()
        for value in paths:
            relative = self._safe_relative(value)
            if relative in seen:
                continue
            seen.add(relative)
            full_path = self.root / relative
            if not full_path.exists():
                snapshots.append(FileSnapshot(relative, False, None, None))
                continue
            if not full_path.is_file():
                raise ValueError(f"workspace context path is not a regular file: {relative}")
            raw = full_path.read_bytes()
            if len(raw) > self.max_file_bytes:
                raise ValueError(f"workspace context file exceeds size limit: {relative}")
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"workspace context file is not UTF-8 text: {relative}") from exc
            snapshots.append(FileSnapshot(relative, True, _sha256_bytes(raw), content))
        return snapshots

    def validate_changes(self, changes: Sequence[FileChange]) -> list[tuple[FileChange, Path, str | None]]:
        if not changes:
            raise ValueError("implementation change set is empty")
        if len(changes) > self.max_files:
            raise ValueError("implementation change set exceeds file-count limit")
        validated: list[tuple[FileChange, Path, str | None]] = []
        seen: set[str] = set()
        for change in changes:
            if change.operation not in {"create", "update", "delete"}:
                raise ValueError(f"unsupported change operation: {change.operation}")
            relative = self._safe_relative(change.path)
            if relative in seen:
                raise ValueError(f"multiple changes target the same path: {relative}")
            seen.add(relative)
            if len(change.reason.strip()) < 8:
                raise ValueError(f"change reason is too vague: {relative}")
            full_path = self.root / relative
            before_hash: str | None = None
            if full_path.exists():
                if not full_path.is_file():
                    raise ValueError(f"change target is not a regular file: {relative}")
                raw = full_path.read_bytes()
                if len(raw) > self.max_file_bytes:
                    raise ValueError(f"existing staging file exceeds size limit: {relative}")
                before_hash = _sha256_bytes(raw)

            if change.operation == "create":
                if full_path.exists():
                    raise ValueError(f"create target already exists: {relative}")
                if change.expected_sha256 is not None:
                    raise ValueError(f"create change cannot carry an expected hash: {relative}")
                self._validate_content(change, relative)
            elif change.operation == "update":
                if not full_path.exists():
                    raise ValueError(f"update target does not exist: {relative}")
                if not change.expected_sha256 or change.expected_sha256 != before_hash:
                    raise ValueError(f"stale or missing update precondition: {relative}")
                self._validate_content(change, relative)
            else:
                if not full_path.exists():
                    raise ValueError(f"delete target does not exist: {relative}")
                if change.content is not None:
                    raise ValueError(f"delete change cannot carry content: {relative}")
                if not change.expected_sha256 or change.expected_sha256 != before_hash:
                    raise ValueError(f"stale or missing delete precondition: {relative}")
            validated.append((change, full_path, before_hash))
        return validated

    def _validate_content(self, change: FileChange, relative: str) -> None:
        if change.content is None:
            raise ValueError(f"{change.operation} change requires complete UTF-8 text content: {relative}")
        encoded = change.content.encode("utf-8")
        if len(encoded) > self.max_file_bytes:
            raise ValueError(f"generated file exceeds staging size limit: {relative}")
        for pattern in _SECRET_PATTERNS:
            if pattern.search(change.content):
                raise ValueError(f"generated file appears to contain secret material: {relative}")

    def apply_changes(self, changes: Sequence[FileChange]) -> list[AppliedChange]:
        validated = self.validate_changes(changes)
        backups: dict[Path, bytes | None] = {}
        applied: list[AppliedChange] = []
        try:
            for change, full_path, before_hash in validated:
                backups[full_path] = full_path.read_bytes() if full_path.exists() else None
                if change.operation == "delete":
                    full_path.unlink()
                    after_hash = None
                else:
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = full_path.with_name(full_path.name + ".agent-stage-tmp")
                    temporary.write_text(change.content or "", encoding="utf-8", newline="")
                    os.replace(temporary, full_path)
                    after_hash = _sha256_text(change.content or "")
                applied.append(AppliedChange(change.operation, change.path, before_hash, after_hash))
        except Exception:
            for full_path, backup in backups.items():
                if backup is None:
                    if full_path.exists():
                        full_path.unlink()
                else:
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_bytes(backup)
            raise
        return applied


@dataclass(frozen=True)
class VerificationResult:
    verification_id: str
    passed: bool
    return_code: int
    stdout: str
    stderr: str


class RegisteredVerificationRunner:
    """Run only operator-registered argv lists with shell=False."""

    def __init__(
        self,
        workspace_root: str | Path,
        registry: Mapping[str, Sequence[str]],
        *,
        timeout_seconds: int = 180,
        output_limit: int = 12_000,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.registry = {key: tuple(value) for key, value in registry.items()}
        self.timeout_seconds = timeout_seconds
        self.output_limit = output_limit
        if not self.registry:
            raise ValueError("verification command registry cannot be empty")
        for key, argv in self.registry.items():
            if not key.strip() or not argv or any(not str(part).strip() for part in argv):
                raise ValueError("verification registry contains an invalid command")

    def run(self, verification_ids: Sequence[str]) -> list[VerificationResult]:
        if not verification_ids:
            raise ValueError("at least one registered verification is required")
        unknown = [item for item in verification_ids if item not in self.registry]
        if unknown:
            raise ValueError(f"unregistered verification IDs: {sorted(set(unknown))}")
        results: list[VerificationResult] = []
        for verification_id in dict.fromkeys(verification_ids):
            completed = subprocess.run(
                list(self.registry[verification_id]),
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                shell=False,
                check=False,
            )
            results.append(
                VerificationResult(
                    verification_id=verification_id,
                    passed=completed.returncode == 0,
                    return_code=completed.returncode,
                    stdout=completed.stdout[-self.output_limit :],
                    stderr=completed.stderr[-self.output_limit :],
                )
            )
        return results
