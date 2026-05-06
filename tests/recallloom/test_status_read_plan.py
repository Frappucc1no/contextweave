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


def helper_env(tmpdir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env["PYTHONUTF8"] = "1"
    env["RECALLLOOM_SUPPORT_ADVISORY_FILE"] = str(RELEASE_ADVISORY_PATH)
    env["RECALLLOOM_SUPPORT_CACHE_DIR"] = str(tmpdir / "support-cache")
    env["RECALLLOOM_SUPPORT_DATE"] = "2026-05-04"
    return env


def valid_daily_log_entry_text() -> str:
    return "\n".join(
        [
            "<!-- section: work_completed -->",
            "- Added read-plan coverage.",
            "",
            "<!-- section: confirmed_facts -->",
            "- status and resume now expose bounded read guidance.",
            "",
            "<!-- section: key_decisions -->",
            "- Keep read_plan additive on the status helper payload.",
            "",
            "<!-- section: risks_blockers -->",
            "- None.",
            "",
            "<!-- section: recommended_next_step -->",
            "- Run the focused read-plan regressions.",
            "",
        ]
    )


class StatusReadPlanTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp(prefix="recallloom-status-read-plan-"))
        self.project = self._tmpdir / "project"
        self.project.mkdir(parents=True)
        subprocess.run(["git", "init", str(self.project)], text=True, capture_output=True, check=True)
        (self.project / "AGENTS.md").write_text("# Test Project\n", encoding="utf-8")
        self.project = self.project.resolve()
        self.env = helper_env(self._tmpdir)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def run_script(
        self,
        script_name: str,
        *args: str,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            helper_command(SCRIPTS_DIR, script_name, *args),
            cwd=REPO_ROOT,
            env=self.env,
            text=True,
            input=input_text,
            capture_output=True,
            check=False,
        )

    def run_dispatcher_json(
        self,
        command: str,
        *args: str,
        input_text: str | None = None,
    ) -> dict:
        proc = self.run_script("recallloom.py", command, *args, "--json", input_text=input_text)
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"recallloom.py {command} failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )
        return json.loads(proc.stdout)

    def storage_root(self) -> Path:
        return self.project / ".recallloom"

    def project_relative(self, path: Path) -> str:
        return path.relative_to(self.project).as_posix()

    def seed_latest_daily_log(self) -> dict:
        return self.run_dispatcher_json(
            "append",
            str(self.project),
            "--stdin",
            input_text=valid_daily_log_entry_text(),
        )

    def assert_relative_plan_files(self, payload: dict) -> None:
        storage_prefix = self.storage_root().relative_to(self.project).as_posix()
        for tier in ("minimal", "standard", "comprehensive"):
            files = payload["read_plan"][tier]["files"]
            self.assertTrue(files, msg=tier)
            for rel_path in files:
                self.assertFalse(Path(rel_path).is_absolute(), msg=rel_path)
                self.assertFalse(rel_path.startswith("/"), msg=rel_path)
                self.assertTrue((self.project / rel_path).exists(), msg=rel_path)
                self.assertTrue(rel_path.startswith(f"{storage_prefix}/"), msg=rel_path)

    def assert_review_before_write(self, payload: dict) -> None:
        for tier in ("minimal", "standard", "comprehensive"):
            self.assertIn("review-before-write", payload["read_plan"][tier]["reason"], msg=tier)

    def test_seeded_status_read_plan_exposes_tiers_relative_paths_and_monotonic_tokens(self) -> None:
        self.run_dispatcher_json("init", str(self.project))
        self.seed_latest_daily_log()

        payload = self.run_dispatcher_json("status", str(self.project))

        self.assertIn("read_plan", payload)
        self.assertEqual(payload["estimated_tokens"], payload["read_plan"]["standard"]["estimated_tokens"])
        self.assert_relative_plan_files(payload)

        minimal = payload["read_plan"]["minimal"]["estimated_tokens"]
        standard = payload["read_plan"]["standard"]["estimated_tokens"]
        comprehensive = payload["read_plan"]["comprehensive"]["estimated_tokens"]
        self.assertLessEqual(minimal, standard)
        self.assertLessEqual(standard, comprehensive)

        summary_rel = self.project_relative(self.storage_root() / "rolling_summary.md")
        state_rel = self.project_relative(self.storage_root() / "state.json")
        self.assertIn(summary_rel, payload["read_plan"]["minimal"]["files"])
        self.assertIn(state_rel, payload["read_plan"]["minimal"]["files"])

    def test_stale_summary_read_plan_requires_review_before_write(self) -> None:
        self.run_dispatcher_json("init", str(self.project))
        state_path = self.storage_root() / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["workspace_revision"] = state["workspace_revision"] + 1
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        payload = self.run_dispatcher_json("status", str(self.project))

        self.assertTrue(payload["summary_stale"])
        self.assert_review_before_write(payload)
        summary_rel = self.project_relative(self.storage_root() / "rolling_summary.md")
        state_rel = self.project_relative(state_path)
        for tier in ("minimal", "standard", "comprehensive"):
            self.assertIn(summary_rel, payload["read_plan"][tier]["files"])
            self.assertIn(state_rel, payload["read_plan"][tier]["files"])

    def test_update_protocol_presence_is_called_out_before_write(self) -> None:
        self.run_dispatcher_json("init", str(self.project))
        update_protocol_path = self.storage_root() / "update_protocol.md"
        self.assertTrue(update_protocol_path.is_file())

        payload = self.run_dispatcher_json("status", str(self.project))

        self.assert_review_before_write(payload)
        update_protocol_rel = self.project_relative(update_protocol_path)
        for tier in ("minimal", "standard", "comprehensive"):
            self.assertIn(update_protocol_rel, payload["read_plan"][tier]["files"])

    def test_empty_shell_read_plan_stays_bounded_and_points_at_core_files(self) -> None:
        self.run_dispatcher_json("init", str(self.project))

        payload = self.run_dispatcher_json("status", str(self.project))

        self.assertEqual(payload["continuity_state"], "initialized_empty_shell")
        summary_rel = self.project_relative(self.storage_root() / "rolling_summary.md")
        state_rel = self.project_relative(self.storage_root() / "state.json")
        context_rel = self.project_relative(self.storage_root() / "context_brief.md")
        update_protocol_rel = self.project_relative(self.storage_root() / "update_protocol.md")

        self.assertIn(summary_rel, payload["read_plan"]["minimal"]["files"])
        self.assertIn(state_rel, payload["read_plan"]["minimal"]["files"])
        self.assertIn(context_rel, payload["read_plan"]["standard"]["files"])
        self.assertIn(update_protocol_rel, payload["read_plan"]["standard"]["files"])

    def test_resume_reuses_read_plan_without_making_status_resume_like(self) -> None:
        self.run_dispatcher_json("init", str(self.project))
        self.seed_latest_daily_log()

        status_payload = self.run_dispatcher_json("status", str(self.project))
        resume_payload = self.run_dispatcher_json("resume", str(self.project))

        self.assertIn("read_plan", status_payload)
        self.assertNotIn("command", status_payload)
        self.assertNotIn("routing_target", status_payload)
        self.assertNotIn("resume_ready", status_payload)

        self.assertEqual(resume_payload["command"], "resume")
        self.assertEqual(resume_payload["routing_target"], "rl-resume")
        self.assertIn("resume_ready", resume_payload)
        self.assertEqual(resume_payload["read_plan"], status_payload["read_plan"])
        self.assertEqual(
            resume_payload["estimated_tokens"],
            status_payload["estimated_tokens"],
        )


if __name__ == "__main__":
    unittest.main()
