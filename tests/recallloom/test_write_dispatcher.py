from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = REPO_ROOT / "skills" / "recallloom" / "scripts"

if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from _helper_runtime import helper_command


def rolling_summary_body() -> str:
    return "\n".join(
        [
            "<!-- section: current_state -->",
            "- D2 write dispatcher is under focused test.",
            "",
            "<!-- section: active_judgments -->",
            "- The dispatcher must not infer write targets from content.",
            "",
            "<!-- section: risks_open_questions -->",
            "- None for this fixture.",
            "",
            "<!-- section: next_step -->",
            "- Run the write dispatcher regression suite.",
            "",
            "<!-- section: recent_pivots -->",
            "- Added an agent-native write command.",
            "",
        ]
    )


def context_brief_body() -> str:
    return "\n".join(
        [
            "<!-- section: mission -->",
            "- Keep project continuity durable.",
            "",
            "<!-- section: current_phase -->",
            "- Testing write dispatch.",
            "",
            "<!-- section: source_of_truth -->",
            "- RecallLoom sidecar files remain authoritative.",
            "",
            "<!-- section: core_workflow -->",
            "- Preflight, then commit with revision guards.",
            "",
            "<!-- section: boundaries -->",
            "- Do not infer target files.",
            "",
        ]
    )


def update_protocol_body() -> str:
    return "\n".join(
        [
            "<!-- section: project_specific_overrides -->",
            "- Always choose write targets explicitly in Phase 1.",
            "",
        ]
    )


class RecallLoomWriteDispatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp(prefix="recallloom-write-dispatcher-"))
        self.project = self._tmpdir / "project"
        self.project.mkdir(parents=True)
        subprocess.run(["git", "init", str(self.project)], text=True, capture_output=True, check=True)
        self.project = self.project.resolve()
        (self.project / "AGENTS.md").write_text("# Test Project\n", encoding="utf-8")

        advisory_path = self._tmpdir / "support-advisory.json"
        advisory_path.write_text(
            json.dumps(
                {
                    "latest_version": "0.3.4",
                    "minimum_mutating_version": "0.3.4",
                    "minimum_readonly_version": "0.3.4",
                    "advisory_level": "supported",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.env = os.environ.copy()
        self.env.update(
            {
                "RECALLLOOM_SUPPORT_ADVISORY_FILE": str(advisory_path),
                "RECALLLOOM_SUPPORT_CACHE_DIR": str(self._tmpdir / "support-cache"),
                "RECALLLOOM_SUPPORT_DATE": "2026-05-04",
            }
        )

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def run_script(
        self,
        script_name: str,
        *args: str,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            helper_command(SCRIPT_ROOT, script_name, *args),
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
            env=self.env,
        )

    def run_dispatcher(
        self,
        *args: str,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess:
        return self.run_script("recallloom.py", *args, input_text=input_text)

    def run_dispatcher_json(self, *args: str, input_text: str | None = None) -> dict:
        proc = self.run_dispatcher(*args, "--json", input_text=input_text)
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"recallloom.py failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )
        return json.loads(proc.stdout)

    def init_project(self) -> None:
        self.run_dispatcher_json("init", str(self.project))

    def write_source(self, name: str, text: str) -> Path:
        path = self._tmpdir / name
        path.write_text(text, encoding="utf-8")
        return path

    def seed_current_state(self) -> None:
        source_path = self.write_source("seed-summary.md", rolling_summary_body())
        proc = self.run_script(
            "commit_context_file.py",
            str(self.project),
            "--file-key",
            "rolling_summary",
            "--source-file",
            str(source_path),
            "--expected-file-revision",
            "1",
            "--expected-workspace-revision",
            "1",
            "--writer-id",
            "SeedWorker",
            "--json",
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"seed commit failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )

    def make_summary_stale(self) -> None:
        state_path = self.project / ".recallloom" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["workspace_revision"] += 1
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def assert_write_blocked_without_mutation(
        self,
        *args: str,
        expected_allowed_operation_level: str,
        input_text: str | None = None,
    ) -> dict:
        state_path = self.project / ".recallloom" / "state.json"
        summary_path = self.project / ".recallloom" / "rolling_summary.md"
        before_state = state_path.read_text(encoding="utf-8")
        before_summary = summary_path.read_text(encoding="utf-8")

        proc = self.run_dispatcher(*args, "--json", input_text=input_text)

        self.assertEqual(proc.returncode, 3, msg=proc.stdout + "\n" + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["schema_version"], "1.1")
        self.assertEqual(payload["blocked_reason"], "stale_write_context")
        self.assertEqual(payload["details"]["allowed_operation_level"], expected_allowed_operation_level)
        self.assertIn("summary_stale", payload["details"])
        self.assertIn("continuity_drift_risk_level", payload["details"])
        self.assertIn("freshness_risk_level", payload["details"])
        self.assertIn("recommended_actions", payload["details"])
        self.assertTrue(payload["package_support"]["allowed"])
        self.assertEqual(state_path.read_text(encoding="utf-8"), before_state)
        self.assertEqual(summary_path.read_text(encoding="utf-8"), before_summary)
        return payload

    def test_dry_run_current_state_reports_target_revisions_without_mutation(self) -> None:
        self.init_project()
        self.seed_current_state()
        source_path = self.write_source("summary.md", rolling_summary_body())
        state_path = self.project / ".recallloom" / "state.json"
        summary_path = self.project / ".recallloom" / "rolling_summary.md"
        before_state = state_path.read_text(encoding="utf-8")
        before_summary = summary_path.read_text(encoding="utf-8")

        payload = self.run_dispatcher_json(
            "write",
            str(self.project),
            "--type",
            "current-state",
            "--source-file",
            str(source_path),
            "--dry-run",
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["schema_version"], "1.1")
        self.assertEqual(payload["command"], "write")
        self.assertEqual(payload["write_type"], "current-state")
        self.assertEqual(payload["file_key"], "rolling_summary")
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["input_mode"], "file")
        self.assertEqual(payload["target_path"], summary_path.relative_to(self.project).as_posix())
        self.assertEqual(payload["expected_file_revision"], 2)
        self.assertEqual(payload["expected_workspace_revision"], 2)
        self.assertTrue(payload["package_support"]["allowed"])
        self.assertNotIn(self.project.as_posix(), json.dumps(payload, ensure_ascii=False))
        self.assertEqual(state_path.read_text(encoding="utf-8"), before_state)
        self.assertEqual(summary_path.read_text(encoding="utf-8"), before_summary)

    def test_dry_run_maps_all_three_write_types(self) -> None:
        self.init_project()
        self.seed_current_state()
        source_path = self.write_source("prepared.md", rolling_summary_body())
        expected = {
            "current-state": ("rolling_summary", self.project / ".recallloom" / "rolling_summary.md"),
            "stable-context": ("context_brief", self.project / ".recallloom" / "context_brief.md"),
            "protocol-rules": ("update_protocol", self.project / ".recallloom" / "update_protocol.md"),
        }

        for write_type, (file_key, target_path) in expected.items():
            with self.subTest(write_type=write_type):
                payload = self.run_dispatcher_json(
                    "write",
                    str(self.project),
                    "--type",
                    write_type,
                    "--source-file",
                    str(source_path),
                    "--dry-run",
                )
                self.assertEqual(payload["file_key"], file_key)
                self.assertEqual(payload["target_path"], target_path.relative_to(self.project).as_posix())
                self.assertTrue(payload["dry_run"])

    def test_real_current_state_routes_through_commit_helper_and_updates_state_file(self) -> None:
        self.init_project()
        self.seed_current_state()
        source_path = self.write_source("summary.md", rolling_summary_body())
        state_path = self.project / ".recallloom" / "state.json"
        summary_path = self.project / ".recallloom" / "rolling_summary.md"

        payload = self.run_dispatcher_json(
            "write",
            str(self.project),
            "--type",
            "current-state",
            "--source-file",
            str(source_path),
            "--writer-id",
            "D2Worker",
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["schema_version"], "1.1")
        self.assertEqual(payload["command"], "write")
        self.assertEqual(payload["write_type"], "current-state")
        self.assertFalse(payload["dry_run"])
        self.assertEqual(payload["file_key"], "rolling_summary")
        self.assertEqual(payload["input_mode"], "file")
        self.assertEqual(payload["target_path"], summary_path.relative_to(self.project).as_posix())
        self.assertEqual(payload["new_file_revision"], 3)
        self.assertEqual(payload["new_workspace_revision"], 3)
        self.assertEqual(payload["writer_id"], "D2Worker")
        self.assertTrue(payload["package_support"]["allowed"])
        self.assertNotIn(self.project.as_posix(), json.dumps(payload, ensure_ascii=False))

        summary_text = summary_path.read_text(encoding="utf-8")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertIn("D2 write dispatcher is under focused test.", summary_text)
        self.assertIn("<!-- last-writer: [D2Worker]", summary_text)
        self.assertEqual(state["workspace_revision"], 3)
        self.assertEqual(state["files"]["rolling_summary"]["file_revision"], 3)

    def test_missing_type_fails_closed_without_mutation(self) -> None:
        self.init_project()
        source_path = self.write_source("summary.md", rolling_summary_body())
        state_path = self.project / ".recallloom" / "state.json"
        summary_path = self.project / ".recallloom" / "rolling_summary.md"
        before_state = state_path.read_text(encoding="utf-8")
        before_summary = summary_path.read_text(encoding="utf-8")

        proc = self.run_dispatcher(
            "write",
            str(self.project),
            "--source-file",
            str(source_path),
            "--json",
        )

        self.assertEqual(proc.returncode, 2, msg=proc.stdout + "\n" + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["schema_version"], "1.1")
        self.assertEqual(payload["blocked_reason"], "invalid_prepared_input")
        self.assertFalse(payload["details"]["phase_1_infers_target"])
        self.assertIn("Phase 1", payload["error"])
        self.assertIn("Phase 1", payload["suggestion"])
        self.assertTrue(payload["package_support"]["allowed"])
        self.assertEqual(state_path.read_text(encoding="utf-8"), before_state)
        self.assertEqual(summary_path.read_text(encoding="utf-8"), before_summary)

    def test_source_file_and_stdin_are_mutually_exclusive(self) -> None:
        self.init_project()
        source_path = self.write_source("summary.md", rolling_summary_body())

        proc = self.run_dispatcher(
            "write",
            str(self.project),
            "--type",
            "current-state",
            "--source-file",
            str(source_path),
            "--stdin",
            "--dry-run",
            "--json",
            input_text=rolling_summary_body(),
        )

        self.assertEqual(proc.returncode, 2, msg=proc.stdout + "\n" + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["blocked_reason"], "invalid_prepared_input")
        self.assertEqual(payload["details"]["input_contract"], "source-file_xor_stdin")
        self.assertTrue(payload["package_support"]["allowed"])

    def test_stdin_dry_run_reports_input_mode_stdin(self) -> None:
        self.init_project()
        self.seed_current_state()

        payload = self.run_dispatcher_json(
            "write",
            str(self.project),
            "--type",
            "current-state",
            "--stdin",
            "--dry-run",
            input_text=rolling_summary_body(),
        )

        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["input_mode"], "stdin")
        self.assertTrue(payload["package_support"]["allowed"])

    def test_helper_failure_json_includes_package_support(self) -> None:
        self.init_project()
        self.seed_current_state()
        bad_source_path = self.write_source("bad-summary.md", "not a managed body\n")

        proc = self.run_dispatcher(
            "write",
            str(self.project),
            "--type",
            "current-state",
            "--source-file",
            str(bad_source_path),
            "--json",
        )

        self.assertEqual(proc.returncode, 2, msg=proc.stdout + "\n" + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["blocked_reason"], "invalid_prepared_input")
        self.assertTrue(payload["package_support"]["allowed"])

    def test_write_blocks_single_absolute_path_line_in_prepared_body(self) -> None:
        self.init_project()
        self.seed_current_state()
        source_path = self.write_source(
            "path-leak-summary.md",
            "\n".join(
                [
                    "<!-- section: current_state -->",
                    "/home/tester/private/notes.txt",
                    "",
                    "<!-- section: active_judgments -->",
                    "- Hold the line on public paths.",
                    "",
                    "<!-- section: risks_open_questions -->",
                    "- None.",
                    "",
                    "<!-- section: next_step -->",
                    "- Keep attached-text safety strict.",
                    "",
                    "<!-- section: recent_pivots -->",
                    "- Added a single-line path regression.",
                    "",
                ]
            ),
        )

        proc = self.run_dispatcher(
            "write",
            str(self.project),
            "--type",
            "current-state",
            "--source-file",
            str(source_path),
            "--json",
        )

        self.assertEqual(proc.returncode, 2, msg=proc.stdout + "\n" + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["blocked_reason"], "attach_scan_blocked")
        self.assertIn("absolute_path_dump", payload["details"]["hard_block_reasons"])

    def test_write_blocks_backticked_absolute_path_in_prepared_body(self) -> None:
        self.init_project()
        self.seed_current_state()
        source_path = self.write_source(
            "backtick-path-summary.md",
            "\n".join(
                [
                    "<!-- section: current_state -->",
                    "- Keep the review note at `/home/tester/private/notes.txt` out of managed text.",
                    "",
                    "<!-- section: active_judgments -->",
                    "- Keep public output project-relative.",
                    "",
                    "<!-- section: risks_open_questions -->",
                    "- None.",
                    "",
                    "<!-- section: next_step -->",
                    "- Continue the write dispatcher review.",
                    "",
                    "<!-- section: recent_pivots -->",
                    "- Added inline path coverage.",
                    "",
                ]
            ),
        )

        proc = self.run_dispatcher(
            "write",
            str(self.project),
            "--type",
            "current-state",
            "--source-file",
            str(source_path),
            "--json",
        )

        self.assertEqual(proc.returncode, 2, msg=proc.stdout + "\n" + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["blocked_reason"], "attach_scan_blocked")
        self.assertIn("absolute_path_dump", payload["details"]["hard_block_reasons"])

    def test_read_summary_only_preflight_blocks_dry_run_and_real_write_without_mutation(self) -> None:
        self.init_project()
        source_path = self.write_source("summary.md", rolling_summary_body())
        base_args = (
            "write",
            str(self.project),
            "--type",
            "current-state",
            "--source-file",
            str(source_path),
        )

        dry_run_payload = self.assert_write_blocked_without_mutation(
            *base_args,
            "--dry-run",
            expected_allowed_operation_level="read_summary_only",
        )
        real_payload = self.assert_write_blocked_without_mutation(
            *base_args,
            expected_allowed_operation_level="read_summary_only",
        )

        self.assertFalse(dry_run_payload["details"]["summary_stale"])
        self.assertFalse(real_payload["details"]["summary_stale"])

    def test_stale_summary_preflight_blocks_dry_run_and_real_write_without_mutation(self) -> None:
        self.init_project()
        self.seed_current_state()
        self.make_summary_stale()
        source_path = self.write_source("summary.md", rolling_summary_body())
        base_args = (
            "write",
            str(self.project),
            "--type",
            "current-state",
            "--source-file",
            str(source_path),
        )

        dry_run_payload = self.assert_write_blocked_without_mutation(
            *base_args,
            "--dry-run",
            expected_allowed_operation_level="read_current_state",
        )
        real_payload = self.assert_write_blocked_without_mutation(
            *base_args,
            expected_allowed_operation_level="read_current_state",
        )

        self.assertTrue(dry_run_payload["details"]["summary_stale"])
        self.assertTrue(real_payload["details"]["summary_stale"])


if __name__ == "__main__":
    unittest.main()
