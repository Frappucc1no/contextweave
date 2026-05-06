from __future__ import annotations

from datetime import date, timedelta
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
            "- Added privacy regressions.",
            "",
            "<!-- section: confirmed_facts -->",
            "- Default JSON output should stay project-relative.",
            "",
            "<!-- section: key_decisions -->",
            "- Keep absolute paths out of success payloads.",
            "",
            "<!-- section: risks_blockers -->",
            "- None.",
            "",
            "<!-- section: recommended_next_step -->",
            "- Run query and status privacy checks.",
            "",
        ]
    )


class PrivacyOutputTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp(prefix="recallloom-privacy-output-"))
        self.project = self._tmpdir / "project"
        self.project.mkdir(parents=True)
        subprocess.run(["git", "init", str(self.project)], text=True, capture_output=True, check=True)
        (self.project / "AGENTS.md").write_text("# Test Project\n", encoding="utf-8")
        self.project = self.project.resolve()
        self.env = helper_env(self._tmpdir)
        self.init_payload = self.run_dispatcher_json("init", str(self.project))
        self.run_dispatcher_json(
            "append",
            str(self.project),
            "--stdin",
            input_text=valid_daily_log_entry_text(),
        )

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

    def run_json(
        self,
        script_name: str,
        *args: str,
        input_text: str | None = None,
    ) -> dict:
        proc = self.run_script(script_name, *args, "--json", input_text=input_text)
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + "\n" + proc.stderr)
        return json.loads(proc.stdout)

    def run_failure_json(
        self,
        script_name: str,
        *args: str,
        input_text: str | None = None,
    ) -> dict:
        proc = self.run_script(script_name, *args, "--json", input_text=input_text)
        self.assertNotEqual(proc.returncode, 0, msg=proc.stdout + "\n" + proc.stderr)
        return json.loads(proc.stdout)

    def run_dispatcher_json(
        self,
        command: str,
        *args: str,
        input_text: str | None = None,
    ) -> dict:
        return self.run_json("recallloom.py", command, *args, input_text=input_text)

    def assert_public_path(self, value: str | None) -> None:
        if value is None:
            return
        self.assertFalse(Path(value).is_absolute(), msg=value)
        self.assertFalse(value.startswith(self.project.as_posix()), msg=value)

    def assert_no_workspace_leak(self, payload: dict) -> None:
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(self.project.as_posix(), serialized)
        self.assertNotIn(self._tmpdir.as_posix(), serialized)
        self.assertNotIn(REPO_ROOT.resolve().as_posix(), serialized)
        self.assertNotIn(Path.home().as_posix(), serialized)

    def write_temp_input(self, name: str, body: str) -> Path:
        path = self._tmpdir / name
        path.write_text(body, encoding="utf-8")
        return path

    def write_symlink(self, path: Path, target: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.symlink_to(target)
        except OSError as exc:
            self.skipTest(f"Symlink creation is unavailable in this environment: {exc}")

    def storage_root(self) -> Path:
        return self.project / ".recallloom"

    def review_source_text(self, proposal_name: str) -> str:
        return "\n".join(
            [
                "## proposal reference",
                f"- {proposal_name}",
                "",
                "## review outcome",
                "- approved for promotion after manual review.",
                "",
                "## approved items",
                "- rolling_summary.md keeps the durable current-state update.",
                "",
                "## rejected items",
                "- none.",
                "",
                "## promotion status",
                "- no items remain hint-only.",
                "",
                "## next action",
                "- commit the reviewed update with the normal write helpers.",
                "",
            ]
        )

    def test_init_dispatcher_json_uses_project_relative_paths(self) -> None:
        payload = self.init_payload

        self.assertEqual(payload["command"], "init")
        self.assertEqual(payload["project_root"], self.project.name)
        self.assertEqual(payload["storage_root"], ".recallloom")
        self.assertEqual(payload["init"]["project_root"], self.project.name)
        self.assertEqual(payload["init"]["storage_root"], ".recallloom")
        self.assertEqual(payload["validate"]["project_root"], self.project.name)
        self.assertEqual(payload["validate"]["storage_root"], ".recallloom")
        for field in ("project_root", "storage_root"):
            self.assert_public_path(payload.get(field))
            self.assert_public_path(payload["init"].get(field))
            self.assert_public_path(payload["validate"].get(field))
        for field in ("created", "skipped"):
            for item in payload["init"][field]:
                self.assert_public_path(item)
        for finding in payload["validate"]["findings"]:
            self.assert_public_path(finding.get("path"))
        self.assert_no_workspace_leak(payload)

    def test_init_helper_json_uses_project_relative_paths(self) -> None:
        payload = self.run_json("init_context.py", str(self.project))

        self.assertEqual(payload["project_root"], self.project.name)
        self.assertEqual(payload["storage_root"], ".recallloom")
        for field in ("project_root", "storage_root"):
            self.assert_public_path(payload.get(field))
        for field in ("created", "skipped"):
            for item in payload[field]:
                self.assert_public_path(item)
        self.assert_no_workspace_leak(payload)

    def test_validate_dispatcher_json_uses_project_relative_paths(self) -> None:
        payload = self.run_dispatcher_json("validate", str(self.project))

        self.assertEqual(payload["project_root"], self.project.name)
        self.assertEqual(payload["storage_root"], ".recallloom")
        self.assert_public_path(payload["storage_root"])
        for finding in payload["findings"]:
            self.assert_public_path(finding.get("path"))
        self.assert_no_workspace_leak(payload)

    def test_validate_helper_json_uses_project_relative_paths(self) -> None:
        payload = self.run_json("validate_context.py", str(self.project))

        self.assertEqual(payload["project_root"], self.project.name)
        self.assertEqual(payload["storage_root"], ".recallloom")
        self.assert_public_path(payload["storage_root"])
        for finding in payload["findings"]:
            self.assert_public_path(finding.get("path"))
        self.assert_no_workspace_leak(payload)

    def test_status_helper_json_uses_project_relative_paths(self) -> None:
        payload = self.run_json("summarize_continuity_status.py", str(self.project))

        self.assertEqual(payload["project_root"], self.project.name)
        self.assertEqual(payload["storage_root"], ".recallloom")
        for field in ("storage_root", "latest_workspace_artifact", "latest_active_daily_log"):
            self.assert_public_path(payload.get(field))
        self.assertEqual(payload["continuity_snapshot"]["project_root"], self.project.name)
        self.assertEqual(payload["continuity_snapshot"]["storage_root"], ".recallloom")
        self.assert_public_path(payload["continuity_snapshot"].get("latest_active_daily_log_seen"))
        self.assert_no_workspace_leak(payload)

    def test_query_helper_json_uses_project_relative_paths(self) -> None:
        payload = self.run_json("query_continuity.py", str(self.project), "--query", "privacy regressions")

        self.assertEqual(payload["project_root"], self.project.name)
        self.assertEqual(payload["storage_root"], ".recallloom")
        self.assert_public_path(payload["storage_root"])
        self.assert_public_path(payload["continuity_snapshot"].get("latest_active_daily_log_seen"))
        self.assert_public_path(payload["continuity_snapshot"].get("latest_workspace_artifact_seen"))
        self.assert_public_path(payload["freshness_state"].get("latest_workspace_artifact"))
        for collection_name in ("sources_considered", "hits", "citations", "supporting_context_window"):
            for item in payload[collection_name]:
                self.assert_public_path(item.get("path"))
        for item in payload["override_review_targets"]:
            self.assert_public_path(item.get("path"))
        self.assert_no_workspace_leak(payload)

    def test_recommend_workday_helper_json_uses_project_relative_paths(self) -> None:
        payload = self.run_json("recommend_workday.py", str(self.project))

        self.assertEqual(payload["project_root"], self.project.name)
        self.assertEqual(payload["storage_root"], ".recallloom")
        for field in ("project_root", "storage_root", "latest_active_daily_log"):
            self.assert_public_path(payload.get(field))
        self.assert_no_workspace_leak(payload)

    def test_query_helper_blocks_single_absolute_path_line_from_managed_content(self) -> None:
        summary_path = self.storage_root() / "rolling_summary.md"
        original = summary_path.read_text(encoding="utf-8")
        summary_path.write_text(
            original.replace(
                "<!-- section: current_state -->\n",
                "<!-- section: current_state -->\n/home/tester/private/continuity-path.txt\n",
                1,
            ),
            encoding="utf-8",
        )

        payload = self.run_failure_json(
            "query_continuity.py",
            str(self.project),
            "--query",
            "continuity-path",
        )

        self.assertEqual(payload["blocked_reason"], "attach_scan_blocked")
        self.assertIn("absolute_path_dump", payload["details"]["hard_block_reasons"])
        self.assert_no_workspace_leak(payload)

    def test_query_helper_blocks_label_prefixed_private_tmp_path_from_managed_content(self) -> None:
        summary_path = self.storage_root() / "rolling_summary.md"
        original = summary_path.read_text(encoding="utf-8")
        summary_path.write_text(
            original.replace(
                "<!-- section: current_state -->\n",
                "<!-- section: current_state -->\nPath: /private/tmp/continuity-path.txt\n",
                1,
            ),
            encoding="utf-8",
        )

        payload = self.run_failure_json(
            "query_continuity.py",
            str(self.project),
            "--query",
            "continuity-path",
        )

        self.assertEqual(payload["blocked_reason"], "attach_scan_blocked")
        self.assertIn("absolute_path_dump", payload["details"]["hard_block_reasons"])
        self.assert_no_workspace_leak(payload)

    def test_query_helper_blocks_file_url_and_volumes_path_from_managed_content(self) -> None:
        summary_path = self.storage_root() / "rolling_summary.md"
        original = summary_path.read_text(encoding="utf-8")
        blocked_cases = (
            "Leak: file:///private/var/tmp/continuity-path.txt\n",
            "Path: /Volumes/SecretDrive/continuity-path.txt\n",
        )

        for leaked_line in blocked_cases:
            with self.subTest(leaked_line=leaked_line):
                summary_path.write_text(
                    original.replace(
                        "<!-- section: current_state -->\n",
                        f"<!-- section: current_state -->\n{leaked_line}",
                        1,
                    ),
                    encoding="utf-8",
                )

                payload = self.run_failure_json(
                    "query_continuity.py",
                    str(self.project),
                    "--query",
                    "continuity-path",
                )

                self.assertEqual(payload["blocked_reason"], "attach_scan_blocked")
                self.assertIn("absolute_path_dump", payload["details"]["hard_block_reasons"])
                self.assert_no_workspace_leak(payload)

    def test_direct_helper_json_redacts_private_paths_for_archive_lock_remove_detect_and_bridge(self) -> None:
        archive_payload = self.run_json("archive_logs.py", str(self.project))
        self.assertEqual(archive_payload["project_root"], self.project.name)
        self.assertEqual(archive_payload["storage_root"], ".recallloom")
        for field in ("project_root", "storage_root", "update_protocol"):
            self.assert_public_path(archive_payload.get(field))
        for item in archive_payload["archived_targets"]:
            self.assert_public_path(item)
        self.assert_no_workspace_leak(archive_payload)

        lock_payload = self.run_json("unlock_write_lock.py", str(self.project))
        self.assertEqual(lock_payload["project_root"], self.project.name)
        self.assert_public_path(lock_payload.get("lock_path"))
        self.assert_no_workspace_leak(lock_payload)

        detect_payload = self.run_json("detect_project_root.py", str(self.project))
        self.assertTrue(detect_payload["found"])
        for field in ("start_path", "project_root", "storage_root", "config_path"):
            self.assert_public_path(detect_payload.get(field))
        self.assert_no_workspace_leak(detect_payload)

        bridge_payload = self.run_json("manage_entry_bridge.py", str(self.project))
        self.assertEqual(bridge_payload["project_root"], self.project.name)
        self.assertEqual(bridge_payload["storage_root"], ".recallloom")
        for field in ("project_root", "storage_root"):
            self.assert_public_path(bridge_payload.get(field))
        for result in bridge_payload["results"]:
            self.assert_public_path(result.get("target"))
            attach_scan = result.get("attach_scan") or {}
            self.assert_public_path(attach_scan.get("target"))
        self.assert_no_workspace_leak(bridge_payload)

        remove_payload = self.run_json("remove_context.py", str(self.project))
        self.assertEqual(remove_payload["project_root"], self.project.name)
        self.assertEqual(remove_payload["storage_root"], ".recallloom")
        for field in ("project_root", "storage_root", "tombstone_path"):
            self.assert_public_path(remove_payload.get(field))
        for item in remove_payload["unknown_assets"]:
            self.assert_public_path(item)
        self.assert_no_workspace_leak(remove_payload)

    def test_generate_coldstart_helper_json_uses_public_paths(self) -> None:
        payload = self.run_json("generate_coldstart_proposal.py", str(self.project))

        self.assertEqual(payload["project_root"], self.project.name)
        self.assertEqual(payload["storage_root"], ".recallloom")
        for field in ("project_root", "storage_root"):
            self.assert_public_path(payload.get(field))
        adapter = payload.get("host_memory_adapter") or {}
        self.assert_public_path(adapter.get("path"))
        for item in payload["sources_considered"]:
            self.assert_public_path(item.get("path"))
        self.assert_no_workspace_leak(payload)

    def test_generate_coldstart_skips_external_symlink_candidates_without_path_leakage(self) -> None:
        external_dir = self._tmpdir / "external-coldstart"
        external_dir.mkdir(parents=True)
        external_readme = external_dir / "external-readme.md"
        external_readme.write_text("EXTERNAL README SECRET\n", encoding="utf-8")
        external_architecture = external_dir / "external-architecture.txt"
        external_architecture.write_text("EXTERNAL TXT SECRET\n", encoding="utf-8")
        external_progress = external_dir / "external-progress.md"
        external_progress.write_text("EXTERNAL MD SECRET\n", encoding="utf-8")

        self.write_symlink(self.project / "README.md", external_readme)
        self.write_symlink(self.project / "docs" / "architecture.txt", external_architecture)
        self.write_symlink(self.project / "progress.md", external_progress)

        payload = self.run_json("generate_coldstart_proposal.py", str(self.project))

        relative_paths = {item["relative_path"] for item in payload["sources_considered"]}
        self.assertNotIn("README.md", relative_paths)
        self.assertNotIn("docs/architecture.txt", relative_paths)
        self.assertNotIn("progress.md", relative_paths)
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("EXTERNAL README SECRET", serialized)
        self.assertNotIn("EXTERNAL TXT SECRET", serialized)
        self.assertNotIn("EXTERNAL MD SECRET", serialized)
        self.assert_no_workspace_leak(payload)

    def test_generate_coldstart_dedupes_internal_symlink_aliases(self) -> None:
        canonical = self.project / "docs" / "project-progress.md"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text("Canonical progress note\n- One durable status line.\n", encoding="utf-8")
        alias = self.project / "docs" / "team-progress-alias.md"
        self.write_symlink(alias, canonical)

        payload = self.run_json("generate_coldstart_proposal.py", str(self.project))

        progress_entries = [
            item
            for item in payload["sources_considered"]
            if item["relative_path"] in {"docs/project-progress.md", "docs/team-progress-alias.md"}
        ]
        self.assertEqual(len(progress_entries), 1)
        self.assertEqual(progress_entries[0]["relative_path"], "docs/project-progress.md")
        self.assertIn("Canonical progress note", progress_entries[0]["excerpt_lines"])
        self.assert_no_workspace_leak(payload)

    def test_recovery_helpers_json_use_public_paths(self) -> None:
        generated = self.run_json("generate_coldstart_proposal.py", str(self.project))
        proposal_source = self.write_temp_input("prepared-proposal.md", generated["proposal_markdown"])
        stage_payload = self.run_json(
            "stage_recovery_proposal.py",
            str(self.project),
            "--source-file",
            str(proposal_source),
            "--proposal-id",
            "privacy-check",
            "--filename-stamp",
            "2026-05-04-101500",
        )

        self.assert_public_path(stage_payload.get("proposal_path"))
        self.assert_public_path(stage_payload.get("source_file"))
        self.assert_no_workspace_leak(stage_payload)

        proposal_path = self.project / stage_payload["proposal_path"]
        review_source = self.write_temp_input(
            "prepared-review.md",
            self.review_source_text(proposal_path.name),
        )
        record_payload = self.run_json(
            "record_recovery_review.py",
            str(self.project),
            "--proposal-file",
            str(proposal_path),
            "--source-file",
            str(review_source),
        )

        for field in ("proposal_path", "review_path", "source_file"):
            self.assert_public_path(record_payload.get(field))
        self.assert_no_workspace_leak(record_payload)

        review_path = self.project / record_payload["review_path"]
        prepare_payload = self.run_json(
            "prepare_recovery_promotion.py",
            str(self.project),
            "--proposal-file",
            str(proposal_path),
            "--review-file",
            str(review_path),
        )

        self.assertEqual(prepare_payload["project_root"], self.project.name)
        self.assertEqual(prepare_payload["storage_root"], ".recallloom")
        for field in ("project_root", "storage_root", "proposal_path", "review_path"):
            self.assert_public_path(prepare_payload.get(field))
        safe_write_context = prepare_payload.get("safe_write_context") or {}
        commit_context = safe_write_context.get("commit_context_file") or {}
        for item in commit_context.values():
            if isinstance(item, dict):
                self.assert_public_path(item.get("path"))
        append_context = safe_write_context.get("append_daily_log_entry") or {}
        self.assert_public_path(append_context.get("latest_file"))
        self.assert_no_workspace_leak(prepare_payload)

    def test_append_failure_json_redacts_path_bearing_error_and_recovery_command(self) -> None:
        daily_logs_dir = self.storage_root() / "daily_logs"
        current_log = sorted(daily_logs_dir.glob("*.md"))[-1]
        future_date = date.fromisoformat(current_log.stem) + timedelta(days=2)
        future_log = daily_logs_dir / f"{future_date.isoformat()}.md"
        future_log.write_text(current_log.read_text(encoding="utf-8"), encoding="utf-8")
        entry_file = self.write_temp_input("future-entry.md", valid_daily_log_entry_text())

        payload = self.run_failure_json(
            "append_daily_log_entry.py",
            str(self.project),
            "--entry-file",
            str(entry_file),
        )

        self.assertEqual(payload["blocked_reason"], "project_time_policy_review_required")
        self.assertIn(f".recallloom/daily_logs/{future_date.isoformat()}.md", payload["error"])
        self.assertNotIn(future_log.as_posix(), payload["error"])
        self.assertNotIn(self.project.as_posix(), payload["recovery_command"])
        self.assert_no_workspace_leak(payload)

    def test_install_native_commands_json_redacts_package_and_home_paths(self) -> None:
        for host in ("claude-code", "opencode"):
            with self.subTest(host=host, scope="project"):
                project_scope_payload = self.run_json(
                    "install_native_commands.py",
                    str(self.project),
                    "--host",
                    host,
                )
                self.assertEqual(project_scope_payload["project_root"], self.project.name)
                for host_payload in project_scope_payload["host_results"]:
                    self.assert_public_native_command_payload(host_payload)
                self.assert_no_workspace_leak(project_scope_payload)

            with self.subTest(host=host, scope="user"):
                user_scope_payload = self.run_json(
                    "install_native_commands.py",
                    str(self.project),
                    "--host",
                    host,
                    "--scope",
                    "user",
                )
                self.assertEqual(user_scope_payload["project_root"], self.project.name)
                for host_payload in user_scope_payload["host_results"]:
                    self.assert_public_native_command_payload(host_payload)
                self.assert_no_workspace_leak(user_scope_payload)

    def assert_public_native_command_payload(self, host_payload: dict) -> None:
        self.assert_public_path(host_payload.get("destination_dir"))
        dispatcher_command = host_payload.get("dispatcher_command")
        self.assertIsInstance(dispatcher_command, str)
        self.assertNotIn(REPO_ROOT.resolve().as_posix(), dispatcher_command)
        self.assertNotIn(Path.home().as_posix(), dispatcher_command)
        for result in host_payload["results"]:
            self.assert_public_path(result.get("file"))

    def test_status_helper_no_project_failure_json_redacts_absolute_paths(self) -> None:
        missing_project = self._tmpdir / "missing-project"
        missing_project.mkdir(parents=True)

        payload = self.run_failure_json("summarize_continuity_status.py", str(missing_project))

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["blocked_reason"], "no_project_root")
        self.assertNotIn(missing_project.as_posix(), json.dumps(payload, ensure_ascii=False))
        self.assertNotIn(REPO_ROOT.resolve().as_posix(), json.dumps(payload, ensure_ascii=False))

    def test_query_helper_no_project_failure_json_redacts_absolute_paths(self) -> None:
        missing_project = self._tmpdir / "missing-query-project"
        missing_project.mkdir(parents=True)

        payload = self.run_failure_json(
            "query_continuity.py",
            str(missing_project),
            "--query",
            "privacy",
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["blocked_reason"], "no_project_root")
        self.assertNotIn(missing_project.as_posix(), json.dumps(payload, ensure_ascii=False))
        self.assertNotIn(REPO_ROOT.resolve().as_posix(), json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
