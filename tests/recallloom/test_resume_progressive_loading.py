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
            "- Seeded progressive resume coverage.",
            "",
            "<!-- section: confirmed_facts -->",
            "- resume fast/full surfaces stay bounded by current-state files.",
            "",
            "<!-- section: key_decisions -->",
            "- Keep daily-log evidence behind query_continuity.py.",
            "",
            "<!-- section: risks_blockers -->",
            "- None.",
            "",
            "<!-- section: recommended_next_step -->",
            "- Run focused progressive loading regressions.",
            "",
        ]
    )


class ResumeProgressiveLoadingTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp(prefix="recallloom-resume-progressive-"))
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

    def seed_project_with_log(self) -> dict:
        self.run_dispatcher_json("init", str(self.project))
        return self.run_dispatcher_json(
            "append",
            str(self.project),
            "--stdin",
            input_text=valid_daily_log_entry_text(),
        )

    def assert_no_daily_log_read_path(self, plan: dict) -> None:
        serialized = json.dumps(plan, ensure_ascii=False)
        self.assertNotIn("daily_logs", serialized)
        self.assertNotIn("daily_logs/", serialized)

    def test_fast_json_succeeds_without_reading_damaged_latest_daily_log(self) -> None:
        append_payload = self.seed_project_with_log()
        (self.project / append_payload["target_path"]).write_text(
            "damaged daily log without entry marker\n",
            encoding="utf-8",
        )

        payload = self.run_dispatcher_json("resume", str(self.project), "--fast")

        self.assertEqual(payload["schema_version"], "1.1")
        self.assertEqual(payload["command"], "resume")
        self.assertEqual(payload["resume_mode"], "fast")
        self.assertEqual(payload["routing_target"], "rl-resume")
        self.assertIn("resume_ready", payload)
        self.assertEqual(payload["project_root"], self.project.name)
        self.assertEqual(payload["storage_root"], ".recallloom")
        self.assertNotIn("read_plan", payload)
        self.assertEqual(payload["progressive_read_plan"]["mode"], "fast")
        self.assert_no_daily_log_read_path(payload["progressive_read_plan"])

    def test_full_json_succeeds_without_reading_damaged_latest_daily_log(self) -> None:
        append_payload = self.seed_project_with_log()
        (self.project / append_payload["target_path"]).write_text(
            "damaged daily log without entry marker\n",
            encoding="utf-8",
        )

        payload = self.run_dispatcher_json("resume", str(self.project), "--full")

        self.assertEqual(payload["schema_version"], "1.1")
        self.assertEqual(payload["command"], "resume")
        self.assertEqual(payload["resume_mode"], "full")
        self.assertEqual(payload["routing_target"], "rl-resume")
        self.assertIn("resume_ready", payload)
        self.assertNotIn("read_plan", payload)
        self.assertEqual(payload["progressive_read_plan"]["mode"], "full")
        self.assert_no_daily_log_read_path(payload["progressive_read_plan"])

    def test_fast_payload_exposes_bounded_current_state_envelope(self) -> None:
        self.seed_project_with_log()

        payload = self.run_dispatcher_json("resume", str(self.project), "--fast")

        state_rel = self.project_relative(self.storage_root() / "state.json")
        summary_rel = self.project_relative(self.storage_root() / "rolling_summary.md")
        self.assertEqual(payload["resume_mode"], "fast")
        self.assertIn("current_state", payload)
        self.assertIn("freshness", payload)
        self.assertIn("trust", payload)
        self.assertNotIn("read_plan", payload)
        self.assertEqual(payload["progressive_read_plan"]["files"], [state_rel, summary_rel])
        self.assertTrue(payload["progressive_read_plan"]["bounded"])
        self.assertIn("query_continuity.py", " ".join(payload["next_actions"]))
        self.assertEqual(payload["continuity_state"], "initialized_seeded")
        self.assertNotEqual(payload["summary"]["phase"], "unseeded")

    def test_full_json_adds_context_and_update_protocol_without_daily_log_read_set(self) -> None:
        self.seed_project_with_log()

        payload = self.run_dispatcher_json("resume", str(self.project), "--full")

        context_rel = self.project_relative(self.storage_root() / "context_brief.md")
        update_protocol_rel = self.project_relative(self.storage_root() / "update_protocol.md")
        self.assertEqual(payload["schema_version"], "1.1")
        self.assertEqual(payload["command"], "resume")
        self.assertEqual(payload["resume_mode"], "full")
        self.assertEqual(payload["routing_target"], "rl-resume")
        self.assertNotIn("read_plan", payload)
        self.assertIn(context_rel, payload["progressive_read_plan"]["files"])
        self.assertIn(update_protocol_rel, payload["progressive_read_plan"]["files"])
        self.assertTrue(payload["context_brief"]["available"])
        self.assertEqual(payload["context_brief"]["path"], context_rel)
        self.assertTrue(payload["update_protocol_guidance"]["available"])
        self.assertEqual(payload["update_protocol_guidance"]["path"], update_protocol_rel)
        self.assertIn("reason", payload["expansion"])
        self.assertFalse(payload["expansion"]["default_reads_daily_log_content"])
        self.assert_no_daily_log_read_path(payload["progressive_read_plan"])

    def test_no_project_fast_and_full_only_return_public_init_guidance(self) -> None:
        for mode_flag in ("--fast", "--full"):
            with self.subTest(mode_flag=mode_flag):
                payload = self.run_dispatcher_json("resume", str(self.project), mode_flag)
                self.assertEqual(payload["project_root"], self.project.name)
                self.assertIsNone(payload["storage_root"])
                self.assertEqual(payload["next_actions"], ["rl-init", "choose_project_root"])
                self.assertNotIn("query_continuity.py", " ".join(payload["next_actions"]))

    def test_human_fast_and_full_output_names_mode_and_bounded_read(self) -> None:
        self.seed_project_with_log()

        fast = self.run_script("recallloom.py", "resume", str(self.project), "--fast")
        full = self.run_script("recallloom.py", "resume", str(self.project), "--full")

        self.assertEqual(fast.returncode, 0, msg=fast.stdout + "\n" + fast.stderr)
        self.assertEqual(full.returncode, 0, msg=full.stdout + "\n" + full.stderr)
        self.assertIn("Resume mode: fast", fast.stdout)
        self.assertIn("Bounded read:", fast.stdout)
        self.assertIn("Resume mode: full", full.stdout)
        self.assertIn("Bounded read:", full.stdout)
        self.assertIn("Bounded expansion reason:", full.stdout)
        self.assertIn("Update protocol guidance:", full.stdout)

    def test_status_json_does_not_gain_resume_only_fields(self) -> None:
        self.seed_project_with_log()

        payload = self.run_dispatcher_json("status", str(self.project))

        self.assertNotIn("command", payload)
        self.assertNotIn("routing_target", payload)
        self.assertNotIn("resume_ready", payload)
        self.assertNotIn("resume_mode", payload)

    def test_status_and_bare_resume_keep_three_tier_read_plan(self) -> None:
        self.seed_project_with_log()

        status_payload = self.run_dispatcher_json("status", str(self.project))
        resume_payload = self.run_dispatcher_json("resume", str(self.project))

        for payload in (status_payload, resume_payload):
            self.assertIn("read_plan", payload)
            self.assertEqual(set(payload["read_plan"]), {"minimal", "standard", "comprehensive"})
            self.assertEqual(payload["estimated_tokens"], payload["read_plan"]["standard"]["estimated_tokens"])
            self.assertNotIn("progressive_read_plan", payload)


if __name__ == "__main__":
    unittest.main()
