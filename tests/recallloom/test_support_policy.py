from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "skills" / "recallloom" / "scripts"
RELEASE_ADVISORY_PATH = REPO_ROOT / "release-advisory.json"

if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from _helper_runtime import helper_command


def good_env(tmpdir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env["PYTHONUTF8"] = "1"
    env["RECALLLOOM_SUPPORT_ADVISORY_FILE"] = str(RELEASE_ADVISORY_PATH)
    env["RECALLLOOM_SUPPORT_CACHE_DIR"] = str(tmpdir / "support-cache")
    env["RECALLLOOM_SUPPORT_DATE"] = "2026-05-04"
    return env


def offline_env(tmpdir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env["PYTHONUTF8"] = "1"
    env["RECALLLOOM_SUPPORT_ADVISORY_FILE"] = str(tmpdir / "missing-advisory.json")
    env["RECALLLOOM_SUPPORT_CACHE_DIR"] = str(tmpdir / "empty-support-cache")
    env["RECALLLOOM_SUPPORT_DATE"] = "2026-05-04"
    return env


class SupportPolicyTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp(prefix="recallloom-support-policy-"))
        self.project = self._tmpdir / "project"
        self.project.mkdir(parents=True)
        subprocess.run(["git", "init", str(self.project)], text=True, capture_output=True, check=True)
        (self.project / "AGENTS.md").write_text("# Test Project\n", encoding="utf-8")
        self.project = self.project.resolve()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def run_json(self, env: dict[str, str], *args: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        proc = subprocess.run(
            helper_command(SCRIPTS_DIR, "recallloom.py", *args, "--json"),
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertTrue(proc.stdout.strip(), proc.stderr)
        return proc, json.loads(proc.stdout)

    def test_unknown_offline_blocks_mutating_init(self) -> None:
        proc, payload = self.run_json(offline_env(self._tmpdir), "init", str(self.project))

        self.assertEqual(proc.returncode, 4, proc.stderr)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["blocked_reason"], "package_support_blocked")
        self.assertEqual(payload["package_support"]["package_support_state"], "unknown_offline")
        self.assertFalse(payload["package_support"]["allowed"])

    def test_unknown_offline_still_allows_status(self) -> None:
        init_proc, init_payload = self.run_json(good_env(self._tmpdir), "init", str(self.project))
        self.assertEqual(init_proc.returncode, 0, init_proc.stderr or init_proc.stdout)
        self.assertTrue(init_payload["ok"])

        proc, payload = self.run_json(offline_env(self._tmpdir), "status", str(self.project))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(payload["package_support"]["allowed"])
        self.assertEqual(payload["package_support"]["package_support_state"], "unknown_offline")
        self.assertEqual(payload["package_support"]["source"], "file")
        self.assertNotIn("cache_path", payload["package_support"])
        self.assertNotIn("package_path", payload["package_support"])


if __name__ == "__main__":
    unittest.main()
