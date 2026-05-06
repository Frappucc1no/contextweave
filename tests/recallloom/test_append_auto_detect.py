from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
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
from core.protocol.contracts import FILE_KEYS, SECTION_KEYS
from core.protocol.markers import daily_log_entry_marker, file_marker


def helper_env() -> dict[str, str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env["PYTHONUTF8"] = "1"
    env["RECALLLOOM_SUPPORT_ADVISORY_FILE"] = str(RELEASE_ADVISORY_PATH)
    return env


def valid_daily_log_entry_text() -> str:
    blocks: list[str] = []
    for section_key in SECTION_KEYS["daily_log"]:
        blocks.append(f"<!-- section: {section_key} -->\n{section_key.replace('_', ' ')}")
    return "\n\n".join(blocks) + "\n"


class AppendAutoDetectTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name).resolve()
        (self.project_root / "AGENTS.md").write_text("# test project\n", encoding="utf-8")
        self.logical_workday = logical_workday_for(
            datetime.now().astimezone(),
            DEFAULT_ROLLOVER_HOUR,
        )
        self.entry_text = valid_daily_log_entry_text()
        self.entry_file = self.project_root / "entry.md"
        self.entry_file.write_text(self.entry_text, encoding="utf-8")

        init_proc, init_payload = self.run_script(
            "init_context.py",
            str(self.project_root),
            "--date",
            self.logical_workday.isoformat(),
            "--create-daily-log",
            "--json",
        )
        self.assertEqual(init_proc.returncode, 0, init_proc.stderr or init_proc.stdout)
        self.workspace_language = init_payload.get("workspace_language", "en")

        self.state_path = self.project_root / ".recallloom" / FILE_KEYS["state"]
        initial_state = self.read_state()
        seeded_proc, seeded_payload = self.run_script(
            "append_daily_log_entry.py",
            str(self.project_root),
            "--date",
            self.logical_workday.isoformat(),
            "--entry-file",
            str(self.entry_file),
            "--expected-workspace-revision",
            str(initial_state["workspace_revision"]),
            "--json",
        )
        self.assertEqual(seeded_proc.returncode, 0, seeded_proc.stderr or seeded_proc.stdout)
        self.workspace_revision = seeded_payload["new_workspace_revision"]
        self.daily_log_path = (
            self.project_root
            / ".recallloom"
            / "daily_logs"
            / f"{self.logical_workday.isoformat()}.md"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_script(
        self,
        script_name: str,
        *args: str,
        input_text: str | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], dict]:
        proc = subprocess.run(
            helper_command(SCRIPTS_DIR, script_name, *args),
            cwd=REPO_ROOT,
            env=helper_env(),
            text=True,
            input=input_text,
            capture_output=True,
            check=False,
        )
        self.assertTrue(proc.stdout.strip(), proc.stderr)
        return proc, json.loads(proc.stdout)

    def read_state(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def write_state(self, state: dict) -> None:
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def public_path(self, path: Path) -> str:
        return path.relative_to(self.project_root).as_posix()

    def add_time_policy_cue(self) -> None:
        update_protocol_path = self.project_root / ".recallloom" / "update_protocol.md"
        update_protocol_path.write_text(
            update_protocol_path.read_text(encoding="utf-8")
            + "\n- Timezone policy: review append date manually when crossing workday rollover.\n",
            encoding="utf-8",
        )

    def stale_daily_log_cursor(self) -> None:
        state = self.read_state()
        state["daily_logs"]["latest_file"] = "daily_logs/1999-01-01.md"
        self.write_state(state)

    def write_active_daily_log(self, log_date) -> Path:
        log_path = self.project_root / ".recallloom" / "daily_logs" / f"{log_date.isoformat()}.md"
        log_path.write_text(
            (
                file_marker("daily_log", self.workspace_language)
                + "\n"
                + daily_log_entry_marker(
                    entry_id="entry-1",
                    created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                    writer_id="test-auto-detect",
                    entry_seq=1,
                )
                + "\n\n"
                + self.entry_text.strip("\n")
                + "\n"
            ),
            encoding="utf-8",
        )
        return log_path

    def backdate_latest_active_daily_log(self, log_date) -> Path:
        backdated_path = self.project_root / ".recallloom" / "daily_logs" / f"{log_date.isoformat()}.md"
        self.daily_log_path.replace(backdated_path)
        return backdated_path

    def test_auto_same_day_append_with_entry_file_succeeds_without_date_or_revision(self) -> None:
        self.stale_daily_log_cursor()

        proc, payload = self.run_script(
            "append_daily_log_entry.py",
            str(self.project_root),
            "--entry-file",
            str(self.entry_file),
            "--json",
        )

        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertEqual(payload["input_mode"], "file")
        self.assertEqual(payload["target_path"], self.public_path(self.daily_log_path))
        self.assertEqual(payload["entry_seq"], 2)
        self.assertEqual(payload["new_workspace_revision"], self.workspace_revision + 1)
        self.assertTrue(payload["auto_detect"]["date_used"])
        self.assertTrue(payload["auto_detect"]["workspace_revision_used"])
        self.assertEqual(payload["auto_detect"]["date_resolution_source"], "auto_same_day_active")
        self.assertEqual(payload["auto_detect"]["workspace_revision_source"], "state_current")
        self.assertEqual(payload["auto_detect"]["workspace_revision_guard_mode"], "lock_snapshot_current")
        self.assertEqual(payload["auto_detect"]["resolved_workspace_revision"], self.workspace_revision)
        self.assertEqual(
            self.read_state()["daily_logs"]["latest_file"],
            f"daily_logs/{self.logical_workday.isoformat()}.md",
        )

    def test_auto_same_day_append_with_stdin_succeeds_without_date_or_revision(self) -> None:
        self.stale_daily_log_cursor()

        proc, payload = self.run_script(
            "append_daily_log_entry.py",
            str(self.project_root),
            "--stdin",
            "--json",
            input_text=self.entry_text,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertEqual(payload["input_mode"], "stdin")
        self.assertEqual(payload["target_path"], self.public_path(self.daily_log_path))
        self.assertEqual(payload["entry_seq"], 2)
        self.assertTrue(payload["auto_detect"]["date_used"])
        self.assertTrue(payload["auto_detect"]["workspace_revision_used"])
        self.assertEqual(payload["auto_detect"]["date_resolution_source"], "auto_same_day_active")
        self.assertEqual(payload["auto_detect"]["workspace_revision_source"], "state_current")
        self.assertEqual(payload["auto_detect"]["workspace_revision_guard_mode"], "lock_snapshot_current")
        self.assertEqual(payload["auto_detect"]["resolved_workspace_revision"], self.workspace_revision)

    def test_auto_logical_workday_append_creates_new_active_log_when_latest_active_lags(self) -> None:
        previous_day = self.logical_workday - timedelta(days=1)
        backdated_path = self.backdate_latest_active_daily_log(previous_day)

        proc, payload = self.run_script(
            "append_daily_log_entry.py",
            str(self.project_root),
            "--entry-file",
            str(self.entry_file),
            "--json",
        )

        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertEqual(payload["target_path"], self.public_path(self.daily_log_path))
        self.assertEqual(payload["entry_seq"], 1)
        self.assertEqual(payload["new_workspace_revision"], self.workspace_revision + 1)
        self.assertTrue(payload["auto_detect"]["date_used"])
        self.assertTrue(payload["auto_detect"]["workspace_revision_used"])
        self.assertEqual(payload["auto_detect"]["date_resolution_source"], "auto_logical_workday")
        self.assertEqual(payload["auto_detect"]["workspace_revision_source"], "state_current")
        self.assertEqual(payload["auto_detect"]["workspace_revision_guard_mode"], "lock_snapshot_current")
        self.assertEqual(payload["auto_detect"]["resolved_workspace_revision"], self.workspace_revision)
        self.assertEqual(payload["auto_detect"]["resolved_date"], self.logical_workday.isoformat())
        self.assertEqual(payload["auto_detect"]["latest_active_daily_log"], self.public_path(backdated_path))
        self.assertEqual(payload["auto_detect"]["latest_active_day"], previous_day.isoformat())
        self.assertEqual(
            self.read_state()["daily_logs"]["latest_file"],
            f"daily_logs/{self.logical_workday.isoformat()}.md",
        )

    def test_explicit_date_and_revision_path_still_succeeds(self) -> None:
        proc, payload = self.run_script(
            "append_daily_log_entry.py",
            str(self.project_root),
            "--date",
            self.logical_workday.isoformat(),
            "--entry-file",
            str(self.entry_file),
            "--expected-workspace-revision",
            str(self.workspace_revision),
            "--json",
        )

        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertFalse(payload["auto_detect"]["date_used"])
        self.assertFalse(payload["auto_detect"]["workspace_revision_used"])
        self.assertEqual(payload["auto_detect"]["date_resolution_source"], "explicit")
        self.assertEqual(payload["auto_detect"]["workspace_revision_source"], "explicit")
        self.assertEqual(payload["auto_detect"]["workspace_revision_guard_mode"], "explicit_mismatch_check")
        self.assertEqual(payload["auto_detect"]["resolved_workspace_revision"], self.workspace_revision)
        self.assertEqual(payload["target_path"], self.public_path(self.daily_log_path))
        self.assertEqual(payload["entry_seq"], 2)

    def test_explicit_stale_revision_still_fails(self) -> None:
        proc, payload = self.run_script(
            "append_daily_log_entry.py",
            str(self.project_root),
            "--date",
            self.logical_workday.isoformat(),
            "--entry-file",
            str(self.entry_file),
            "--expected-workspace-revision",
            str(self.workspace_revision - 1),
            "--json",
        )

        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["blocked_reason"], "stale_write_context")

    def test_historical_append_still_requires_allow_historical_with_auto_or_explicit_revision(self) -> None:
        historical_date = (self.logical_workday - timedelta(days=1)).isoformat()
        cases = (
            ("auto_revision", []),
            (
                "explicit_revision",
                ["--expected-workspace-revision", str(self.workspace_revision)],
            ),
        )

        for label, extra_args in cases:
            with self.subTest(label=label):
                proc, payload = self.run_script(
                    "append_daily_log_entry.py",
                    str(self.project_root),
                    "--date",
                    historical_date,
                    "--entry-file",
                    str(self.entry_file),
                    *extra_args,
                    "--json",
                )

                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["blocked_reason"], "historical_append_requires_confirmation")

    def test_future_dated_target_still_blocked(self) -> None:
        future_date = (self.logical_workday + timedelta(days=2)).isoformat()

        proc, payload = self.run_script(
            "append_daily_log_entry.py",
            str(self.project_root),
            "--date",
            future_date,
            "--entry-file",
            str(self.entry_file),
            "--json",
        )

        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["blocked_reason"], "project_time_policy_review_required")
        self.assertIn(future_date, payload["error"])

    def test_future_dated_active_daily_log_still_blocked(self) -> None:
        future_date = self.logical_workday + timedelta(days=2)
        future_log_path = self.write_active_daily_log(future_date)

        proc, payload = self.run_script(
            "append_daily_log_entry.py",
            str(self.project_root),
            "--entry-file",
            str(self.entry_file),
            "--json",
        )

        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["blocked_reason"], "project_time_policy_review_required")
        self.assertIn(self.public_path(future_log_path), payload["error"])
        self.assertNotIn(future_log_path.as_posix(), payload["error"])

    def test_project_time_policy_cues_fail_closed_without_explicit_date(self) -> None:
        self.add_time_policy_cue()

        for label, extra_args in (
            ("auto_revision", []),
            ("explicit_revision_only", ["--expected-workspace-revision", str(self.workspace_revision)]),
        ):
            with self.subTest(label=label):
                proc, payload = self.run_script(
                    "append_daily_log_entry.py",
                    str(self.project_root),
                    "--entry-file",
                    str(self.entry_file),
                    *extra_args,
                    "--json",
                )

                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["blocked_reason"], "project_time_policy_review_required")
                self.assertIn("explicit --date", payload["error"])
                self.assertIn("--date", payload["recovery_command"])
                self.assertIn("timezone", payload["details"]["project_time_policy_cues"])
                self.assertIn("rollover", payload["details"]["project_time_policy_cues"])

    def test_no_auto_detect_fails_closed_when_date_or_revision_is_missing(self) -> None:
        cases = (
            (
                "missing_both",
                [
                    "--entry-file",
                    str(self.entry_file),
                    "--no-auto-detect",
                    "--json",
                ],
            ),
            (
                "missing_date",
                [
                    "--entry-file",
                    str(self.entry_file),
                    "--expected-workspace-revision",
                    str(self.workspace_revision),
                    "--no-auto-detect",
                    "--json",
                ],
            ),
            (
                "missing_revision",
                [
                    "--date",
                    self.logical_workday.isoformat(),
                    "--entry-file",
                    str(self.entry_file),
                    "--no-auto-detect",
                    "--json",
                ],
            ),
        )

        for label, extra_args in cases:
            with self.subTest(label=label):
                proc, payload = self.run_script(
                    "append_daily_log_entry.py",
                    str(self.project_root),
                    *extra_args,
                )

                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["blocked_reason"], "invalid_prepared_input")
                self.assertIn("--no-auto-detect requires explicit", payload["error"])


if __name__ == "__main__":
    unittest.main()
