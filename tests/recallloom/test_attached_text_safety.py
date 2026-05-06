from __future__ import annotations

import sys
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "skills" / "recallloom" / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from core.safety.attached_text import scan_auto_attached_context_text


class AttachedTextSafetyTests(unittest.TestCase):
    def test_blocks_sensitive_env_assignment_dump(self) -> None:
        payload = scan_auto_attached_context_text(
            "OPENAI_API_KEY=sk-live-secret\nSESSION_TOKEN=abc123\n"
        )

        self.assertTrue(payload["blocked"])
        self.assertIn("sensitive_env_assignment_dump", payload["hard_block_reasons"])

    def test_blocks_environment_listing_dump_with_paths(self) -> None:
        payload = scan_auto_attached_context_text(
            "HOME=/home/tester\nPATH=/usr/local/bin:/usr/bin\nPWD=/home/tester/project\n"
        )

        self.assertTrue(payload["blocked"])
        self.assertIn("environment_variable_listing_dump", payload["hard_block_reasons"])

    def test_blocks_absolute_path_dump(self) -> None:
        blocked_cases = (
            "/home/tester/project/.recallloom/state.json\n",
            "- /home/tester/private-handoff.md\n",
            "Path: /private/tmp/recallloom-leak.txt\n",
            "Path: /private/var/tmp/secret.txt\n",
            "Path: /Volumes/SecretDrive/private.txt\n",
            "Path: /Applications/RecallLoom.app\n",
            "Path: /Library/LaunchDaemons/com.example.recallloom.plist\n",
            "Relevant file: `/usr/local/bin/recallloom`\n",
            "See /opt/recallloom/runtime-config.yaml before writing.\n",
            "C:\\Temp\\tester\\private\\handoff.txt\n",
            "\\\\server\\share\\private\\handoff.txt\n",
            "Leak: file:///home/tester/private/handoff.txt\n",
            "Leak: file:///tmp/recallloom-leak.txt\n",
            "Leak: file:///private/var/tmp/secret.txt\n",
            "Leak: file:///Volumes/SecretDrive/private.txt\n",
            "Leak: file:///C:/Temp/tester/private/handoff.txt\n",
            "Leak: file://localhost/C:/Temp/tester/private/handoff.txt\n",
            "Leak: file://server/share/private/handoff.txt\n",
        )

        for text in blocked_cases:
            with self.subTest(text=text):
                payload = scan_auto_attached_context_text(text)
                self.assertTrue(payload["blocked"])
                self.assertIn("absolute_path_dump", payload["hard_block_reasons"])

    def test_normal_project_context_stays_allowed(self) -> None:
        payload = scan_auto_attached_context_text(
            "Current task: patch the resume flow.\nRelevant file: `skills/recallloom/scripts/recallloom.py`.\n"
        )

        self.assertFalse(payload["blocked"])

    def test_urls_and_normal_slash_delimited_text_stay_allowed(self) -> None:
        payload = scan_auto_attached_context_text(
            "Reference docs: https://example.com/usr/local/bin/guide\n"
            "Normal notes: compare foo/bar/baz with skills/recallloom/scripts/recallloom.py.\n"
        )

        self.assertFalse(payload["blocked"])


if __name__ == "__main__":
    unittest.main()
