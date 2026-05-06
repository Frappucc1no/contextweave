from __future__ import annotations

from contextlib import redirect_stderr
from datetime import datetime, timedelta
import io
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


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
from _common import cli_failure_payload
from core.continuity.workday import logical_workday_for
from core.failure.contracts import failure_payload
from core.protocol.contracts import FILE_KEYS, SECTION_KEYS


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


class FailureGuidancePayloadTests(unittest.TestCase):
    def test_shared_failure_payload_includes_guidance_fields(self) -> None:
        payload = failure_payload(
            "invalid_prepared_input",
            language="en",
            error="Prepared entry is empty.",
            script_name="append_daily_log_entry.py",
        )

        self.assertEqual(payload["schema_version"], "1.1")
        self.assertEqual(payload["failure_stage"], "helper_execution")
        self.assertTrue(payload["next_actions"])
        self.assertTrue(payload["suggestion"])
        self.assertTrue(payload["recovery_command"])
        self.assertIn("append_daily_log_entry.py", payload["recovery_command"])

    def test_invalid_prepared_input_json_modes_stay_json_aware_without_retry_context(self) -> None:
        cases = (
            ("json-string", {"input_mode": "json-string"}, ("--entry-json",)),
            ("json-stdin", {"input_mode": "json-stdin"}, ("--stdin", "--input-format json")),
            (
                "json-file",
                {"input_mode": "json-file", "entry_path": "/tmp/entry.json"},
                ("--entry-file", "--input-format json"),
            ),
        )

        for label, details, expected_tokens in cases:
            with self.subTest(label=label):
                payload = failure_payload(
                    "invalid_prepared_input",
                    language="en",
                    error="Prepared entry JSON is invalid.",
                    details=details,
                    script_name="append_daily_log_entry.py",
                )

                self.assertEqual(payload["blocked_reason"], "invalid_prepared_input")
                self.assertEqual(payload["schema_version"], "1.1")
                combined = f"{payload['suggestion']} {payload['recovery_command']}"
                for token in expected_tokens:
                    self.assertIn(token, combined)

    def test_python_runtime_guidance_distinguishes_bootstrap_from_interpreter_gate(self) -> None:
        runtime_gate = failure_payload(
            "python_runtime_unavailable",
            error="RecallLoom helper scripts require Python 3.10+; current interpreter is 3.9.9",
            language="en",
            script_name="append_daily_log_entry.py",
        )
        bootstrap_gate = failure_payload(
            "python_runtime_unavailable",
            error="RecallLoom runtime bootstrap failed: Missing package metadata file: /tmp/missing.json",
            language="en",
            script_name="append_daily_log_entry.py",
        )

        self.assertEqual(runtime_gate["failure_stage"], "runtime_gate")
        self.assertEqual(bootstrap_gate["failure_stage"], "runtime_bootstrap")
        self.assertNotIn("python3.13 skills/recallloom/scripts/", runtime_gate["recovery_command"])
        self.assertNotIn(str(Path(sys.executable)), runtime_gate["recovery_command"])
        self.assertIn(Path(sys.executable).name, runtime_gate["recovery_command"])
        self.assertIn("package-metadata.json", bootstrap_gate["recovery_command"])
        self.assertNotEqual(runtime_gate["user_message"], bootstrap_gate["user_message"])
        self.assertNotEqual(runtime_gate["operator_note"], bootstrap_gate["operator_note"])

    def test_bootstrap_runtime_payload_matches_contract_shape(self) -> None:
        module_name = "recallloom_dispatcher_bootstrap_test"
        spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / "recallloom.py")
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with redirect_stderr(io.StringIO()):
            try:
                spec.loader.exec_module(module)
            except SystemExit as exc:
                self.assertEqual(exc.code, 2)

        payload = module._bootstrap_runtime_payload(
            "RecallLoom helper scripts require Python 3.10+; current interpreter is 3.9.9",
            "3.10",
        )

        self.assertEqual(payload["schema_version"], "1.1")
        self.assertEqual(payload["failure_stage"], "runtime_bootstrap")
        self.assertTrue(payload["blocked"])
        self.assertEqual(payload["blocked_reason"], "python_runtime_unavailable")
        self.assertTrue(payload["suggestion"])
        self.assertTrue(payload["recovery_command"])
        self.assertIn("recallloom.py", payload["recovery_command"])

    def test_status_bootstrap_runtime_payload_matches_contract_shape(self) -> None:
        module_name = "recallloom_status_bootstrap_test"
        spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / "summarize_continuity_status.py")
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with redirect_stderr(io.StringIO()):
            try:
                spec.loader.exec_module(module)
            except SystemExit as exc:
                self.assertEqual(exc.code, 2)

        payload = module._bootstrap_runtime_payload(
            "RecallLoom helper scripts require Python 3.10+; current interpreter is 3.9.9",
            "3.10",
        )

        self.assertEqual(payload["schema_version"], "1.1")
        self.assertEqual(payload["failure_stage"], "runtime_bootstrap")
        self.assertTrue(payload["blocked"])
        self.assertEqual(payload["blocked_reason"], "python_runtime_unavailable")
        self.assertTrue(payload["suggestion"])
        self.assertTrue(payload["recovery_command"])
        self.assertIn("summarize_continuity_status.py", payload["recovery_command"])

    def test_dispatcher_runtime_gate_is_reachable_without_helper_shim(self) -> None:
        script_path = str(SCRIPTS_DIR / "recallloom.py")
        runtime_gate_probe = f"""
import runpy
import sys

class FakeVersionInfo(tuple):
    major = 3
    minor = 9
    micro = 9

    def __new__(cls):
        return tuple.__new__(cls, (3, 9, 9, "final", 0))

sys.version_info = FakeVersionInfo()
sys.argv = [{script_path!r}, "status", ".", "--json"]
runpy.run_path({script_path!r}, run_name="__main__")
"""

        proc = subprocess.run(
            [sys.executable, "-c", runtime_gate_probe],
            cwd=REPO_ROOT,
            env=helper_env(),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 2, proc.stdout + "\n" + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["blocked_reason"], "python_runtime_unavailable")
        self.assertEqual(payload["failure_stage"], "runtime_bootstrap")
        self.assertIn("current interpreter is 3.9.9", payload["error"])
        self.assertIn("RecallLoom cannot start yet", payload["user_message"])

    def test_no_project_root_recovery_command_is_literal(self) -> None:
        payload = cli_failure_payload(
            "no_project_root",
            error="No RecallLoom project root found.",
            details={"project_root": "/tmp/recallloom-project"},
        )

        self.assertIn("init_context.py", payload["recovery_command"])
        self.assertIn("recallloom-project", payload["recovery_command"])
        self.assertNotIn("/tmp/recallloom-project", payload["recovery_command"])
        self.assertNotIn("<project-path>", payload["recovery_command"])

    def test_failure_payload_redacts_path_bearing_error_by_default(self) -> None:
        project_root = "/tmp/recallloom-project"
        future_log = f"{project_root}/.recallloom/daily_logs/2099-01-01.md"

        payload = failure_payload(
            "project_time_policy_review_required",
            language="en",
            error=f"Latest active daily log is future-dated: {future_log}",
            details={
                "project_root": project_root,
                "latest_active_daily_log": future_log,
            },
            script_name="append_daily_log_entry.py",
        )

        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertIn(".recallloom/daily_logs/2099-01-01.md", payload["error"])
        self.assertNotIn(future_log, payload["error"])
        self.assertNotIn(project_root, serialized)
        self.assertNotIn(str(Path(sys.executable)), payload["recovery_command"])

    def test_failure_payload_debug_flag_keeps_private_paths(self) -> None:
        project_root = "/tmp/recallloom-project"
        future_log = f"{project_root}/.recallloom/daily_logs/2099-01-01.md"

        with mock.patch.dict(os.environ, {"RECALLLOOM_DEBUG_JSON_PATHS": "1"}, clear=False):
            payload = failure_payload(
                "no_project_root",
                language="en",
                error=f"No RecallLoom project root found near {future_log}",
                details={
                    "project_root": project_root,
                    "latest_active_daily_log": future_log,
                },
                script_name="init_context.py",
            )

        self.assertIn(future_log, payload["error"])
        self.assertEqual(payload["details"]["project_root"], project_root)
        self.assertEqual(payload["details"]["latest_active_daily_log"], future_log)
        self.assertIn("init_context.py", payload["recovery_command"])
        self.assertIn(str(Path(sys.executable)), payload["recovery_command"])


class AppendHelperFailureGuidanceTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name).resolve()
        (self.project_root / "AGENTS.md").write_text("# test project\n", encoding="utf-8")
        self.logical_workday = logical_workday_for(
            datetime.now().astimezone(),
            DEFAULT_ROLLOVER_HOUR,
        )
        self.entry_file = self.project_root / "entry.md"
        self.entry_file.write_text(valid_daily_log_entry_text(), encoding="utf-8")
        init_proc, init_payload = self.run_script(
            "init_context.py",
            str(self.project_root),
            "--date",
            self.logical_workday.isoformat(),
            "--create-daily-log",
            "--json",
        )
        self.assertEqual(init_proc.returncode, 0, init_proc.stderr or init_proc.stdout)
        self.assertEqual(init_payload["project_root"], self.project_root.name)
        self.state_path = self.project_root / ".recallloom" / FILE_KEYS["state"]
        seeded_proc, seeded_payload = self.run_script(
            "append_daily_log_entry.py",
            str(self.project_root),
            "--date",
            self.logical_workday.isoformat(),
            "--entry-file",
            str(self.entry_file),
            "--expected-workspace-revision",
            str(json.loads(self.state_path.read_text(encoding="utf-8"))["workspace_revision"]),
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

    def run_script(self, script_name: str, *args: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        proc = subprocess.run(
            helper_command(SCRIPTS_DIR, script_name, *args),
            cwd=REPO_ROOT,
            env=helper_env(),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertTrue(proc.stdout.strip(), proc.stderr)
        return proc, json.loads(proc.stdout)

    def assert_failure_contract(self, payload: dict, *, reason: str) -> None:
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["blocked_reason"], reason)
        self.assertEqual(payload["schema_version"], "1.1")
        self.assertTrue(payload["next_actions"])
        self.assertTrue(payload["suggestion"])
        self.assertTrue(payload["recovery_command"])

    def assert_no_placeholder_tokens(self, payload: dict) -> None:
        self.assertNotIn("<", payload["recovery_command"])
        self.assertNotIn(">", payload["recovery_command"])

    def test_future_date_guard_includes_recovery_command(self) -> None:
        future_date = (self.logical_workday + timedelta(days=2)).isoformat()
        proc, payload = self.run_script(
            "append_daily_log_entry.py",
            str(self.project_root),
            "--date",
            future_date,
            "--entry-file",
            str(self.entry_file),
            "--expected-workspace-revision",
            str(self.workspace_revision),
            "--json",
        )

        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assert_failure_contract(payload, reason="project_time_policy_review_required")
        self.assertEqual(payload["failure_stage"], "helper_execution")
        self.assertIn("append_daily_log_entry.py", payload["recovery_command"])
        self.assertIn("--date", payload["recovery_command"])
        self.assertNotIn(self.project_root.as_posix(), payload["recovery_command"])
        self.assert_no_placeholder_tokens(payload)

    def test_historical_append_requires_allow_historical_guidance(self) -> None:
        historical_date = (self.logical_workday - timedelta(days=1)).isoformat()
        proc, payload = self.run_script(
            "append_daily_log_entry.py",
            str(self.project_root),
            "--date",
            historical_date,
            "--entry-file",
            str(self.entry_file),
            "--expected-workspace-revision",
            str(self.workspace_revision),
            "--json",
        )

        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assert_failure_contract(payload, reason="historical_append_requires_confirmation")
        self.assertIn("--allow-historical", payload["recovery_command"])
        self.assertIn(historical_date, payload["recovery_command"])
        self.assert_no_placeholder_tokens(payload)

    def test_stale_revision_guidance_points_back_to_preflight(self) -> None:
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
        self.assert_failure_contract(payload, reason="stale_write_context")
        self.assertIn("preflight_context_check.py", payload["recovery_command"])
        self.assertIn("workspace revision", payload["suggestion"].lower())
        self.assert_no_placeholder_tokens(payload)

    def test_missing_prepared_input_receives_retry_guidance(self) -> None:
        proc, payload = self.run_script(
            "append_daily_log_entry.py",
            str(self.project_root),
            "--date",
            self.logical_workday.isoformat(),
            "--expected-workspace-revision",
            str(self.workspace_revision),
            "--json",
        )

        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assert_failure_contract(payload, reason="invalid_prepared_input")
        self.assertIn("--entry-file", payload["recovery_command"])
        self.assertIn("one valid input source", payload["suggestion"])
        self.assert_no_placeholder_tokens(payload)

    def test_malformed_managed_file_guidance_points_to_validate(self) -> None:
        self.daily_log_path.write_text("broken daily log\n", encoding="utf-8")
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

        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assert_failure_contract(payload, reason="malformed_managed_file")
        self.assertIn("validate_context.py", payload["recovery_command"])
        self.assertNotIn(self.project_root.as_posix(), payload["recovery_command"])
        self.assert_no_placeholder_tokens(payload)


if __name__ == "__main__":
    unittest.main()
