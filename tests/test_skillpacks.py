"""
Tests for Tarjoman Native Agent Skillpacks and Quality Tools.

Covers:
- Claude Code skillpack (.claude/skills/tarjoman/SKILL.md) & frontmatter
- 12 domain reference guides in .claude/skills/tarjoman/references/
- Hermes Agent skillpack (agent-packs/hermes/SKILL.md)
- Cursor rules (agent-packs/cursor/.cursorrules)
- Linter CLI script (.claude/skills/tarjoman/scripts/linter.py) on clean and faulty texts
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestSkillpacks(unittest.TestCase):
    """Test suite for agent skillpacks, reference documentation, and linter."""

    def test_claude_skill_exists_with_frontmatter(self) -> None:
        """Verify Claude Code SKILL.md exists and has valid YAML frontmatter."""
        skill_path = os.path.join(PROJECT_ROOT, ".claude", "skills", "tarjoman", "SKILL.md")
        self.assertTrue(os.path.exists(skill_path), f"File not found: {skill_path}")
        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertTrue(content.startswith("---"), "SKILL.md must begin with YAML frontmatter delimiter '---'")
        parts = content.split("---", 2)
        self.assertGreaterEqual(len(parts), 3, "SKILL.md must have closing frontmatter delimiter '---'")
        frontmatter = parts[1]
        self.assertIn("name: tarjoman", frontmatter)
        self.assertIn("description:", frontmatter)
        # Content verification
        self.assertIn("5-pass", content.lower())
        self.assertIn("anti-calque", content.lower())

    def test_hermes_skill_exists_and_configured(self) -> None:
        """Verify Hermes Agent SKILL.md exists and has runtime instructions."""
        hermes_path = os.path.join(PROJECT_ROOT, "agent-packs", "hermes", "SKILL.md")
        self.assertTrue(os.path.exists(hermes_path), f"File not found: {hermes_path}")
        with open(hermes_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertTrue(content.startswith("---"), "Hermes SKILL.md must begin with YAML frontmatter")
        self.assertIn("hermes", content.lower())
        self.assertIn("tarjoman", content.lower())

    def test_cursorrules_exists_and_configured(self) -> None:
        """Verify Cursor .cursorrules exists with Persian typography and translation rules."""
        cursor_path = os.path.join(PROJECT_ROOT, "agent-packs", "cursor", ".cursorrules")
        self.assertTrue(os.path.exists(cursor_path), f"File not found: {cursor_path}")
        with open(cursor_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertGreater(len(content.strip()), 100)
        self.assertIn("em-dash", content.lower())
        self.assertIn("«", content)
        self.assertIn("»", content)

    def test_all_12_reference_guides_exist(self) -> None:
        """Verify all 10 domain guides plus anti-calque and mqm-taxonomy guides exist."""
        refs_dir = os.path.join(PROJECT_ROOT, ".claude", "skills", "tarjoman", "references")
        self.assertTrue(os.path.isdir(refs_dir), f"Directory not found: {refs_dir}")

        expected_files = [
            "literary.md",
            "colloquial.md",
            "editor.md",
            "book.md",
            "scientific.md",
            "philosophy.md",
            "legal.md",
            "technical.md",
            "medical.md",
            "media.md",
            "financial.md",
            "classical.md",
            "transcreation.md",
            "anti-calque.md",
            "mqm-taxonomy.md",
            "genre-fiction.md",
            "subtitles.md",
            "terminology-sources.md",
        ]

        for filename in expected_files:
            file_path = os.path.join(refs_dir, filename)
            self.assertTrue(os.path.exists(file_path), f"Reference guide missing: {filename}")
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            self.assertGreater(len(content), 100, f"Reference guide is too short: {filename}")

    def test_linter_script_exists_and_callable(self) -> None:
        """Verify linter.py exists and functions correctly on clean and faulty texts."""
        linter_path = os.path.join(PROJECT_ROOT, ".claude", "skills", "tarjoman", "scripts", "linter.py")
        self.assertTrue(os.path.exists(linter_path), f"Linter script missing: {linter_path}")

        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

        # Clean text test
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as f:
            f.write("او با لبخندی آرام گفت: «این یک متن کاملاً پاکیزه و بدون کوچک‌ترین ایراد نگارشی است.»\n")
            clean_file = f.name

        try:
            res_clean = subprocess.run(
                [sys.executable, linter_path, clean_file],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
            )
            self.assertEqual(res_clean.returncode, 0, f"Clean text failed linter: {res_clean.stdout} {res_clean.stderr}")
            self.assertIn("PASSED", res_clean.stdout.upper())
        finally:
            if os.path.exists(clean_file):
                os.unlink(clean_file)

        # Faulty text test
        faulty_text = (
            "این متن — با خط تیره کشیده است.\n"
            "این موضوع توسط وزیر اعلام گردید.\n"
            "شما نباید روی دیگران حساب کنید.\n"
            "او گفت: «این نقل‌قول گیومه بسته ندارد.\n"
            "يك كتاب عربي با ك و ي عربي.\n"
        )
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as f:
            f.write(faulty_text)
            faulty_file = f.name

        try:
            res_faulty = subprocess.run(
                [sys.executable, linter_path, faulty_file],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
            )
            self.assertNotEqual(res_faulty.returncode, 0, "Faulty text must return non-zero exit code")
            output = (res_faulty.stdout or "") + (res_faulty.stderr or "")
            self.assertIn("em-dash", output.lower())
            self.assertIn("calque", output.lower())
            self.assertIn("quote", output.lower())
            self.assertIn("arabic", output.lower())
        finally:
            if os.path.exists(faulty_file):
                os.unlink(faulty_file)

    def test_linter_programmatic_api(self) -> None:
        """Verify lint_text function directly flags all required categories."""
        import importlib.util

        linter_path = os.path.join(PROJECT_ROOT, ".claude", "skills", "tarjoman", "scripts", "linter.py")
        spec = importlib.util.spec_from_file_location("tarjoman_linter", linter_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        linter_module = importlib.util.module_from_spec(spec)
        sys.modules["tarjoman_linter"] = linter_module
        try:
            spec.loader.exec_module(linter_module)

            clean = "او گفت: «سلام بر دوستان.»"
            issues_clean = linter_module.lint_text(clean)
            self.assertEqual(len(issues_clean), 0)

            faulty = "جمله — با توسط دیگران و حساب کردن روی آن‌ها و «گیومه باز و ك و ي."
            issues_faulty = linter_module.lint_text(faulty)
            categories = {issue.category for issue in issues_faulty}
            self.assertIn("em-dash", categories)
            self.assertIn("calque", categories)
            self.assertIn("quote", categories)
            self.assertIn("arabic", categories)

            # Test skipping fenced code blocks
            code_block_text = (
                "این متن اصلی است.\n"
                "```python\n"
                "# Faulty code with em-dash — and calque توسط\n"
                "x = 'ك'\n"
                "```\n"
                "این بخش پایانی است.\n"
            )
            issues_skipped = linter_module.lint_text(code_block_text, skip_code_blocks=True)
            self.assertEqual(len(issues_skipped), 0)

            issues_not_skipped = linter_module.lint_text(code_block_text, skip_code_blocks=False)
            self.assertGreater(len(issues_not_skipped), 0)
        finally:
            sys.modules.pop("tarjoman_linter", None)


if __name__ == "__main__":
    unittest.main()
