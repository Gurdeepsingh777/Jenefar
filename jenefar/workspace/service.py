from __future__ import annotations

import difflib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from jenefar.workspace.policy import WorkspacePolicy


class WorkspaceService:
    def __init__(self, policy: WorkspacePolicy | None = None) -> None:
        self.policy = policy or WorkspacePolicy()

    def inspect_file(self, path: str, max_bytes: int = 200_000) -> dict[str, object]:
        candidate = self.policy.require_allowed(path)
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        data = candidate.read_bytes()
        truncated = len(data) > max_bytes
        if truncated:
            data = data[:max_bytes]
        return {
            "path": str(candidate),
            "size": candidate.stat().st_size,
            "truncated": truncated,
            "content": data.decode("utf-8", errors="replace"),
        }

    def list_directory(self, path: str, max_items: int = 200) -> list[dict[str, object]]:
        candidate = self.policy.require_allowed(path)
        if not candidate.is_dir():
            raise NotADirectoryError(candidate)
        output: list[dict[str, object]] = []
        for item in sorted(candidate.iterdir(), key=lambda value: (not value.is_dir(), value.name.lower()))[:max_items]:
            output.append({
                "name": item.name,
                "path": str(item),
                "type": "directory" if item.is_dir() else "file",
            })
        return output

    def backup(self, path: str) -> str:
        candidate = self.policy.require_allowed(path)
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        backup_dir = candidate.parent / ".jenefar-backups"
        backup_dir.mkdir(exist_ok=True)
        backup = backup_dir / f"{candidate.name}.{os.getpid()}.{time.time_ns()}.bak"
        shutil.copy2(candidate, backup)
        return str(backup)

    def create_file(self, path: str, content: str) -> dict[str, object]:
        candidate = self.policy.require_allowed(path)
        if candidate.exists():
            raise FileExistsError(candidate)
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text(content, encoding="utf-8")
        return {
            "path": str(candidate),
            "created": True,
            "size": candidate.stat().st_size,
        }

    def edit_file(self, path: str, new_content: str) -> dict[str, object]:
        candidate = self.policy.require_allowed(path)
        if not candidate.exists():
            return self.create_file(str(candidate), new_content)
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        before = candidate.read_text(encoding="utf-8", errors="replace")
        backup = self.backup(str(candidate))

        fd, temp_name = tempfile.mkstemp(prefix=f".{candidate.name}.", dir=str(candidate.parent))
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(new_content)
                handle.flush()
                os.fsync(handle.fileno())
            temp_path.replace(candidate)
        finally:
            temp_path.unlink(missing_ok=True)

        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=str(candidate),
                tofile=str(candidate),
            )
        )
        return {"path": str(candidate), "backup": backup, "diff": diff[-40000:]}

    def run_python(self, path: str, timeout: int = 60) -> dict[str, object]:
        candidate = self.policy.require_allowed(path)
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        if candidate.suffix.lower() != ".py":
            raise ValueError("workspace_run_python only executes .py files.")

        completed = subprocess.run(
            [sys.executable, "-u", str(candidate)],
            cwd=str(candidate.parent),
            capture_output=True,
            text=True,
            timeout=max(1, min(timeout, 300)),
        )
        return {
            "path": str(candidate),
            "returncode": completed.returncode,
            "stdout": completed.stdout[-20000:],
            "stderr": completed.stderr[-20000:],
        }

    def validate_python(self, path: str, timeout: int = 30) -> dict[str, object]:
        """Compile-check an authorized Python file without running top-level logic."""
        candidate = self.policy.require_allowed(path)
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        if candidate.suffix.lower() != ".py":
            raise ValueError("workspace_validate_python only validates .py files.")

        try:
            completed = subprocess.run(
                [sys.executable, "-m", "py_compile", str(candidate)],
                cwd=str(candidate.parent),
                capture_output=True,
                text=True,
                timeout=max(1, min(timeout, 120)),
            )
            return {
                "path": str(candidate),
                "returncode": completed.returncode,
                "valid": completed.returncode == 0,
                "stdout": completed.stdout[-10000:],
                "stderr": completed.stderr[-10000:],
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "path": str(candidate),
                "returncode": -1,
                "valid": False,
                "stdout": str(exc.stdout or "")[-10000:],
                "stderr": "Python syntax validation timed out.",
            }

    def run_pytest(self, path: str, timeout: int = 120) -> dict[str, object]:
        """Run pytest against an authorized file or directory."""
        candidate = self.policy.require_allowed(path)
        if not candidate.exists():
            raise FileNotFoundError(candidate)

        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(candidate)],
            cwd=str(candidate if candidate.is_dir() else candidate.parent),
            capture_output=True,
            text=True,
            timeout=max(1, min(timeout, 300)),
        )
        return {
            "path": str(candidate),
            "returncode": completed.returncode,
            "passed": completed.returncode == 0,
            "stdout": completed.stdout[-20000:],
            "stderr": completed.stderr[-20000:],
        }

    def diff_file(self, path: str) -> dict[str, object]:
        candidate = self.policy.require_allowed(path)
        backup_dir = candidate.parent / ".jenefar-backups"
        backups = sorted(backup_dir.glob(f"{candidate.name}.*.bak")) if backup_dir.is_dir() else []
        if not backups:
            return {"path": str(candidate), "diff": ""}
        before = backups[-1].read_text(encoding="utf-8", errors="replace")
        after = candidate.read_text(encoding="utf-8", errors="replace")
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=str(backups[-1]),
                tofile=str(candidate),
            )
        )
        return {"path": str(candidate), "diff": diff[-40000:]}
