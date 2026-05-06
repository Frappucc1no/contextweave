from __future__ import annotations

from datetime import datetime
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
DEFAULT_ROLLOVER_HOUR = 3

if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from _helper_runtime import helper_command
from core.continuity.workday import logical_workday_for
from core.protocol.contracts import DAILY_LOG_ENTRY_RE, FILE_KEYS, SECTION_KEYS


def valid_daily_log_entry_text(label: str) -> str:
    blocks: list[str] = []
    for section_key in SECTION_KEYS["daily_log"]:
        blocks.append(f"<!-- section: {section_key} -->\n- {label}: {section_key.replace('_', ' ')}")
    return "\n\n".join(blocks) + "\n"


class DailyLogSequenceContractTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp(prefix="recallloom-daily-log-contract-"))
        self.project_root = (self._tmpdir / "project").resolve()
        self.project_root.mkdir(parents=True)
        subprocess.run(["git", "init", str(self.project_root)], text=True, capture_output=True, check=True)
        (self.project_root / "AGENTS.md").write_text("# test project\n", encoding="utf-8")
        self.logical_workday = logical_workday_for(
            datetime.now().astimezone(),
            DEFAULT_ROLLOVER_HOUR,
        )
        self.env = os.environ.copy()
        self.env.update(
            {
                "LC_ALL": "C",
                "LANG": "C",
                "PYTHONUTF8": "1",
                "RECALLLOOM_SUPPORT_ADVISORY_FILE": str(RELEASE_ADVISORY_PATH),
                "RECALLLOOM_SUPPORT_CACHE_DIR": str(self._tmpdir / "support-cache"),
                "RECALLLOOM_SUPPORT_DATE": "2026-05-04",
            }
        )
        self.state_path = self.project_root / ".recallloom" / FILE_KEYS["state"]
        self.daily_log_path = (
            self.project_root
            / ".recallloom"
            / "daily_logs"
            / f"{self.logical_workday.isoformat()}.md"
        )

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def run_script(
        self,
        script_name: str,
        *args: str,
        input_text: str | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], dict]:
        proc = subprocess.run(
            helper_command(SCRIPTS_DIR, script_name, *args),
            cwd=REPO_ROOT,
            env=self.env,
            text=True,
            input=input_text,
            capture_output=True,
            check=False,
        )
        self.assertTrue(proc.stdout.strip(), proc.stderr)
        return proc, json.loads(proc.stdout)

    def init_sidecar(self) -> None:
        proc, payload = self.run_script(
            "init_context.py",
            str(self.project_root),
            "--date",
            self.logical_workday.isoformat(),
            "--create-daily-log",
            "--json",
        )
        self.assertEqual(proc.returncode, 0, payload)

    def read_state(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def write_state(self, state: dict) -> None:
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def append_entry(self, label: str) -> dict:
        entry_file = self._tmpdir / f"{label}.md"
        entry_file.write_text(valid_daily_log_entry_text(label), encoding="utf-8")
        state = self.read_state()
        proc, payload = self.run_script(
            "append_daily_log_entry.py",
            str(self.project_root),
            "--date",
            self.logical_workday.isoformat(),
            "--entry-file",
            str(entry_file),
            "--expected-workspace-revision",
            str(state["workspace_revision"]),
            "--writer-id",
            "test-daily-log-sequence-contract",
            "--json",
        )
        self.assertEqual(proc.returncode, 0, payload)
        return payload

    def rewrite_entry_marker(self, occurrence: int, *, entry_id: str, entry_seq: int) -> None:
        lines = self.daily_log_path.read_text(encoding="utf-8").splitlines()
        seen = 0
        for index, line in enumerate(lines):
            match = DAILY_LOG_ENTRY_RE.match(line.strip())
            if match is None:
                continue
            seen += 1
            if seen != occurrence:
                continue
            lines[index] = (
                f"<!-- daily-log-entry: entry-id={entry_id} | "
                f"created-at={match.group('created_at')} | "
                f"writer-id={match.group('writer_id').strip()} | "
                f"entry-seq={entry_seq} -->"
            )
            self.daily_log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
        self.fail(f"daily-log-entry marker {occurrence} was not found")

    def update_daily_log_state(self, *, latest_entry_id: str, latest_entry_seq: int, entry_count: int) -> None:
        state = self.read_state()
        state["daily_logs"]["latest_entry_id"] = latest_entry_id
        state["daily_logs"]["latest_entry_seq"] = latest_entry_seq
        state["daily_logs"]["entry_count"] = entry_count
        self.write_state(state)

    def validate(self) -> tuple[subprocess.CompletedProcess[str], dict]:
        return self.run_script("validate_context.py", str(self.project_root), "--json")

    def finding_codes(self, payload: dict, *, level: str | None = None) -> set[str]:
        return {
            finding["code"]
            for finding in payload["findings"]
            if level is None or finding["level"] == level
        }

    def test_helper_generated_daily_log_validates(self) -> None:
        self.init_sidecar()
        self.append_entry("first")
        self.append_entry("second")

        proc, payload = self.validate()

        self.assertEqual(proc.returncode, 0, payload)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["error_count"], 0)
        codes = self.finding_codes(payload)
        self.assertNotIn("invalid_daily_log_entry_sequence", codes)
        self.assertNotIn("daily_log_entry_count_mismatch", codes)
        self.assertNotIn("noncanonical_daily_log_entry_id", codes)

    def test_validator_rejects_global_count_written_as_file_local_sequence(self) -> None:
        self.init_sidecar()
        self.append_entry("first")
        self.append_entry("second")
        self.rewrite_entry_marker(2, entry_id="entry-9", entry_seq=9)
        self.update_daily_log_state(latest_entry_id="entry-9", latest_entry_seq=9, entry_count=9)

        proc, payload = self.validate()

        self.assertNotEqual(proc.returncode, 0, payload)
        self.assertFalse(payload["valid"])
        error_codes = self.finding_codes(payload, level="error")
        self.assertIn("invalid_daily_log_entry_sequence", error_codes)
        self.assertIn("daily_log_entry_count_mismatch", error_codes)

    def test_validator_warns_on_noncanonical_daily_log_entry_id(self) -> None:
        self.init_sidecar()
        self.append_entry("first")
        self.rewrite_entry_marker(1, entry_id="entry-8", entry_seq=1)
        self.update_daily_log_state(latest_entry_id="entry-8", latest_entry_seq=1, entry_count=1)

        proc, payload = self.validate()

        self.assertEqual(proc.returncode, 0, payload)
        self.assertTrue(payload["valid"])
        self.assertIn(
            "noncanonical_daily_log_entry_id",
            self.finding_codes(payload, level="warning"),
        )


if __name__ == "__main__":
    unittest.main()
