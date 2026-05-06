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


def valid_daily_log_entry_text() -> str:
    return "\n".join(
        [
            "<!-- section: work_completed -->",
            "- Added dispatcher append coverage.",
            "",
            "<!-- section: confirmed_facts -->",
            "- recallloom.py append routes to append_daily_log_entry.py.",
            "",
            "<!-- section: key_decisions -->",
            "- Keep the dispatcher surface minimal in M1.",
            "",
            "<!-- section: risks_blockers -->",
            "- None.",
            "",
            "<!-- section: recommended_next_step -->",
            "- Validate quick-summary and append together.",
            "",
        ]
    )


class RecallLoomQuickSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp(prefix="recallloom-quick-summary-"))
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

    def run_script(self, script_name: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            helper_command(SCRIPT_ROOT, script_name, *args),
            text=True,
            capture_output=True,
            check=False,
            env=self.env,
        )

    def run_dispatcher(self, command: str, *args: str) -> subprocess.CompletedProcess:
        return self.run_script("recallloom.py", command, *args)

    def run_dispatcher_json(self, command: str, *args: str) -> dict:
        proc = self.run_dispatcher(command, *args, "--json")
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"recallloom.py {command} failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )
        return json.loads(proc.stdout)

    def run_helper_json(self, script_name: str, *args: str) -> dict:
        proc = self.run_script(script_name, *args, "--json")
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"{script_name} failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )
        return json.loads(proc.stdout)

    def public_path(self, path: Path) -> str:
        return path.relative_to(self.project).as_posix()

    def test_quick_summary_hidden_sidecar_is_bounded_and_side_effect_free(self) -> None:
        self.run_dispatcher_json("init", str(self.project))
        nested = self.project / "src" / "worker"
        nested.mkdir(parents=True)

        storage_root = self.project / ".recallloom"
        summary_path = storage_root / "rolling_summary.md"
        state_path = storage_root / "state.json"
        before_summary = summary_path.read_text(encoding="utf-8")
        before_state = state_path.read_text(encoding="utf-8")

        payload = self.run_dispatcher_json("quick-summary", str(nested))

        self.assertEqual(payload["schema_version"], "1.1")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "quick-summary")
        self.assertEqual(payload["project_root"], self.project.name)
        self.assertEqual(payload["storage_root"], ".recallloom")
        self.assertEqual(payload["summary"]["project"], self.project.name)
        self.assertEqual(payload["summary"]["phase"], "unseeded")
        self.assertIsNone(payload["summary"]["next_step"])
        self.assertEqual(payload["summary"]["confidence"], "medium")
        self.assertEqual(payload["continuity_state"], "initialized_empty_shell")
        self.assertFalse(payload["continuity_seeded"])
        self.assertEqual(payload["freshness"]["workspace_revision"], 1)
        self.assertEqual(payload["freshness"]["rolling_summary_revision"], 1)
        self.assertFalse(payload["freshness"]["summary_stale"])
        self.assertEqual(payload["freshness"]["freshness_risk_level"], "medium")
        self.assertIn("seed_initial_continuity", payload["next_actions"])
        self.assertEqual(summary_path.read_text(encoding="utf-8"), before_summary)
        self.assertEqual(state_path.read_text(encoding="utf-8"), before_state)

    def test_quick_summary_detects_visible_sidecar_from_descendant(self) -> None:
        self.run_dispatcher_json("init", str(self.project), "--storage-mode", "visible")
        nested = self.project / "apps" / "agent"
        nested.mkdir(parents=True)

        payload = self.run_dispatcher_json("quick-summary", str(nested))

        self.assertEqual(payload["project_root"], self.project.name)
        self.assertEqual(payload["storage_root"], "recallloom")
        self.assertEqual(payload["summary"]["project"], self.project.name)
        self.assertEqual(payload["summary"]["phase"], "unseeded")
        self.assertEqual(payload["next_actions"], ["seed_initial_continuity", "review_update_protocol_before_write"])

    def test_quick_summary_returns_structured_no_project_result(self) -> None:
        payload = self.run_dispatcher_json("quick-summary", str(self.project))

        self.assertEqual(payload["schema_version"], "1.1")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "quick-summary")
        self.assertEqual(payload["project_root"], self.project.name)
        self.assertIsNone(payload["storage_root"])
        self.assertIsNone(payload["summary"]["project"])
        self.assertEqual(payload["summary"]["phase"], "no_project")
        self.assertIsNone(payload["summary"]["next_step"])
        self.assertEqual(payload["summary"]["confidence"], "none")
        self.assertFalse(payload["freshness"]["summary_stale"])
        self.assertEqual(payload["freshness"]["freshness_risk_level"], "not_applicable")
        self.assertEqual(payload["next_actions"], ["rl-init", "choose_project_root"])
        self.assertTrue(payload["package_support"]["allowed"])
        self.assertEqual(payload["package_support"]["source"], "file")
        self.assertNotIn("cache_path", payload["package_support"])
        self.assertNotIn("package_path", payload["package_support"])

    def test_quick_summary_marks_stale_summary_and_recommends_review(self) -> None:
        self.run_dispatcher_json("init", str(self.project))
        state_path = self.project / ".recallloom" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["workspace_revision"] = 2
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        payload = self.run_dispatcher_json("quick-summary", str(self.project))

        self.assertEqual(payload["summary"]["confidence"], "low")
        self.assertTrue(payload["freshness"]["summary_stale"])
        self.assertEqual(payload["freshness"]["workspace_revision"], 2)
        self.assertEqual(payload["freshness"]["rolling_summary_revision"], 1)
        self.assertEqual(payload["freshness"]["freshness_risk_level"], "medium")
        self.assertIn("refresh_or_review_summary_before_write", payload["next_actions"])
        self.assertIn("review_update_protocol_before_write", payload["next_actions"])

    def test_quick_summary_treats_init_plus_append_workspace_as_seeded_even_with_template_summary(self) -> None:
        self.run_dispatcher_json("init", str(self.project))
        proc = subprocess.run(
            helper_command(
                SCRIPT_ROOT,
                "recallloom.py",
                "append",
                str(self.project),
                "--stdin",
                "--json",
            ),
            input=valid_daily_log_entry_text(),
            text=True,
            capture_output=True,
            check=False,
            env=self.env,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + "\n" + proc.stderr)

        payload = self.run_dispatcher_json("quick-summary", str(self.project))

        self.assertEqual(payload["continuity_state"], "initialized_seeded")
        self.assertTrue(payload["continuity_seeded"])
        self.assertNotEqual(payload["summary"]["phase"], "unseeded")
        self.assertNotIn("seed_initial_continuity", payload["next_actions"])
        self.assertEqual(payload["next_actions"][0], "read_rolling_summary")

    def test_quick_summary_fails_closed_on_damaged_sidecar(self) -> None:
        self.run_dispatcher_json("init", str(self.project))
        (self.project / ".recallloom" / "config.json").unlink()

        proc = self.run_dispatcher("quick-summary", str(self.project), "--json")

        self.assertEqual(proc.returncode, 2, msg=proc.stdout + "\n" + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["blocked_reason"], "damaged_sidecar")
        self.assertTrue(payload["package_support"]["allowed"])
        self.assertIn("repair_existing_sidecar", payload["next_actions"])

    def test_quick_summary_fails_closed_on_malformed_managed_file(self) -> None:
        self.run_dispatcher_json("init", str(self.project))
        summary_path = self.project / ".recallloom" / "rolling_summary.md"
        summary_path.write_text("broken summary\n", encoding="utf-8")

        proc = self.run_dispatcher("quick-summary", str(self.project), "--json")

        self.assertEqual(proc.returncode, 2, msg=proc.stdout + "\n" + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["blocked_reason"], "malformed_managed_file")
        self.assertTrue(payload["package_support"]["allowed"])
        self.assertIn("validate_context.py", payload["recovery_command"])

    def test_validate_bad_path_helper_failure_does_not_gain_package_support(self) -> None:
        missing = self._tmpdir / "missing-project"

        helper_proc = self.run_script("validate_context.py", str(missing), "--json")
        dispatcher_proc = self.run_dispatcher("validate", str(missing), "--json")

        self.assertNotEqual(helper_proc.returncode, 0, msg=helper_proc.stdout + "\n" + helper_proc.stderr)
        self.assertEqual(
            dispatcher_proc.returncode,
            helper_proc.returncode,
            msg=dispatcher_proc.stdout + "\n" + dispatcher_proc.stderr,
        )
        helper_payload = json.loads(helper_proc.stdout)
        dispatcher_payload = json.loads(dispatcher_proc.stdout)
        self.assertNotIn("package_support", helper_payload)
        self.assertNotIn("package_support", dispatcher_payload)
        self.assertEqual(dispatcher_payload, helper_payload)

    def test_dispatcher_append_delegates_to_append_daily_log_entry(self) -> None:
        self.run_dispatcher_json("init", str(self.project))

        proc = subprocess.run(
            helper_command(
                SCRIPT_ROOT,
                "recallloom.py",
                "append",
                str(self.project),
                "--stdin",
                "--json",
            ),
            input=valid_daily_log_entry_text(),
            text=True,
            capture_output=True,
            check=False,
            env=self.env,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"recallloom.py append failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )
        payload = json.loads(proc.stdout)

        self.assertTrue(payload["package_support"]["allowed"])
        self.assertEqual(payload["input_mode"], "stdin")
        self.assertTrue(payload["auto_detect"]["date_used"])
        self.assertTrue(payload["auto_detect"]["workspace_revision_used"])
        self.assertEqual(payload["auto_detect"]["date_resolution_source"], "auto_logical_workday")
        self.assertEqual(payload["auto_detect"]["workspace_revision_source"], "state_current")
        self.assertEqual(
            payload["target_path"],
            self.public_path(
                self.project
                / ".recallloom"
                / "daily_logs"
                / f"{payload['auto_detect']['resolved_date']}.md"
            ),
        )
        self.assertEqual(payload["new_workspace_revision"], 2)
        self.assertTrue((self.project / payload["target_path"]).is_file())

    def test_dispatcher_append_failure_json_includes_package_support(self) -> None:
        self.run_dispatcher_json("init", str(self.project))

        proc = self.run_dispatcher(
            "append",
            str(self.project),
            "--json",
        )

        self.assertEqual(proc.returncode, 2, msg=proc.stdout + "\n" + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["blocked_reason"], "invalid_prepared_input")
        self.assertTrue(payload["package_support"]["allowed"])
        self.assertIn("--entry-file", payload["recovery_command"])

    def test_status_and_resume_json_surfaces_remain_stable(self) -> None:
        self.run_dispatcher_json("init", str(self.project))

        status_payload = self.run_dispatcher_json("status", str(self.project))
        self.assertTrue(status_payload["package_support"]["allowed"])
        self.assertIn(status_payload["package_support"]["source"], {"file", "cache_today"})
        self.assertNotIn("cache_path", status_payload["package_support"])
        self.assertNotIn("package_path", status_payload["package_support"])
        self.assertEqual(status_payload["continuity_snapshot"]["task_type"], "status_review")
        self.assertNotIn("command", status_payload)
        self.assertNotIn("routing_target", status_payload)

        resume_payload = self.run_dispatcher_json("resume", str(self.project))
        self.assertTrue(resume_payload["package_support"]["allowed"])
        self.assertIn(resume_payload["package_support"]["source"], {"file", "cache_today"})
        self.assertNotIn("cache_path", resume_payload["package_support"])
        self.assertNotIn("package_path", resume_payload["package_support"])
        self.assertEqual(resume_payload["command"], "resume")
        self.assertEqual(resume_payload["routing_target"], "rl-resume")
        self.assertFalse(resume_payload["resume_ready"])
        self.assertEqual(resume_payload["continuity_snapshot"]["task_type"], "resume_checkpoint")
        self.assertEqual(resume_payload["continuity_state"], status_payload["continuity_state"])

    def test_init_suggests_bridge_preview_before_apply(self) -> None:
        payload = self.run_dispatcher_json("init", str(self.project))

        self.assertIn("review_bridge_candidates", payload["suggested_next_actions"])
        self.assertNotIn("rl-bridge --file AGENTS.md", payload["suggested_next_actions"])
        self.assertEqual(payload["bridge_action_surface"]["action_label"], "rl-bridge")
        self.assertEqual(payload["bridge_action_surface"]["surface"], "dispatcher/helper")
        self.assertFalse(payload["bridge_action_surface"]["wrapper_guaranteed"])
        self.assertEqual(payload["bridge_action_surface"]["suggested_target"], "AGENTS.md")


if __name__ == "__main__":
    unittest.main()
