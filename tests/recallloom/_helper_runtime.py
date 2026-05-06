from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import sys


def resolve_helper_python() -> str:
    candidates: list[str] = []
    configured = os.environ.get("RECALLLOOM_TEST_PYTHON")
    if configured:
        candidates.append(configured)
    if sys.version_info >= (3, 10):
        candidates.append(sys.executable)
    for name in ("python3.13", "python3.12", "python3.11", "python3.10"):
        resolved = shutil.which(name)
        if resolved:
            candidates.append(resolved)

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        probe = subprocess.run(
            [
                candidate,
                "-c",
                "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if probe.returncode == 0:
            return candidate

    return sys.executable


HELPER_PYTHON = resolve_helper_python()


def helper_command(script_root: Path, script_name: str, *args: str) -> list[str]:
    return [HELPER_PYTHON, str(script_root / script_name), *args]
