from __future__ import annotations

import shutil
import sys
from pathlib import Path
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "skills" / "recallloom" / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from core.coldstart.sources import tier_a_sources, tier_b_sources


class ColdstartSourceSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp(prefix="recallloom-coldstart-sources-"))
        self.project = self._tmpdir / "project"
        self.project.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def write_symlink(self, path: Path, target: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.symlink_to(target)
        except OSError as exc:
            self.skipTest(f"Symlink creation is unavailable in this environment: {exc}")

    def test_tier_a_dedupes_internal_symlink_aliases_and_prefers_canonical_file(self) -> None:
        canonical = self.project / "AGENTS.md"
        canonical.write_text("Canonical agent guide\n", encoding="utf-8")
        self.write_symlink(self.project / "README.md", canonical)

        sources = tier_a_sources(self.project)

        entry_candidates = [
            item for item in sources if item["relative_path"] in {"README.md", "AGENTS.md"}
        ]
        self.assertEqual(len(entry_candidates), 1)
        self.assertEqual(entry_candidates[0]["relative_path"], "AGENTS.md")
        self.assertIn("Canonical agent guide", entry_candidates[0]["excerpt_lines"])

    def test_tier_b_dedupes_internal_symlink_aliases_and_prefers_canonical_file(self) -> None:
        canonical = self.project / "docs" / "architecture.md"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text("Canonical architecture note\n", encoding="utf-8")
        self.write_symlink(self.project / "docs" / "architecture-alias.md", canonical)

        sources = tier_b_sources(self.project)

        entry_candidates = [
            item
            for item in sources
            if item["relative_path"] in {"docs/architecture.md", "docs/architecture-alias.md"}
        ]
        self.assertEqual(len(entry_candidates), 1)
        self.assertEqual(entry_candidates[0]["relative_path"], "docs/architecture.md")
        self.assertIn("Canonical architecture note", entry_candidates[0]["excerpt_lines"])


if __name__ == "__main__":
    unittest.main()
