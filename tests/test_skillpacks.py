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
import re
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

    def test_claude_skill_stays_lean(self) -> None:
        """SKILL.md is loaded for every text, so it stays short and routes to one guide."""
        skill_path = os.path.join(PROJECT_ROOT, ".claude", "skills", "tarjoman", "SKILL.md")
        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertLessEqual(len(content.splitlines()), 110)
        refs_dir = os.path.join(PROJECT_ROOT, ".claude", "skills", "tarjoman", "references")
        for name in re.findall(r"references/([a-z\-]+\.md)", content):
            self.assertTrue(os.path.exists(os.path.join(refs_dir, name)), name)

    def test_routed_guides_open_with_a_glance_section(self) -> None:
        """Progressive disclosure: every guide SKILL.md routes to starts with a short «در یک نگاه»."""
        skill_dir = os.path.join(PROJECT_ROOT, ".claude", "skills", "tarjoman")
        with open(os.path.join(skill_dir, "SKILL.md"), "r", encoding="utf-8") as f:
            skill = f.read()
        table = skill.split("## ۱.", 1)[1].split("**چقدر", 1)[0]
        routed = sorted(set(re.findall(r"references/([a-z\-]+\.md)", table)))
        self.assertGreaterEqual(len(routed), 14)
        for name in routed:
            with open(os.path.join(skill_dir, "references", name), "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
            head = "\n".join(lines[:8])
            self.assertIn("## در یک نگاه", head, name)
            start = lines.index("## در یک نگاه")
            end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("## "))
            bullets = [l for l in lines[start:end] if l.startswith("- ")]
            self.assertTrue(3 <= len(bullets) <= 8, f"{name}: {len(bullets)} bullets")

    def test_routed_guides_are_written_in_persian(self) -> None:
        """The agent reads these guides; English-only prose was the old marketing style."""
        refs = os.path.join(PROJECT_ROOT, ".claude", "skills", "tarjoman", "references")
        for name in ["scientific.md", "financial.md", "philosophy.md", "classical.md", "transcreation.md"]:
            with open(os.path.join(refs, name), "r", encoding="utf-8") as f:
                text = f.read()
            self.assertNotIn("## Overview", text, name)
            fa = len(re.findall(r"[\u0600-\u06FF]", text))
            latin = len(re.findall(r"[A-Za-z]", text))
            self.assertGreater(fa, 2 * latin, name)

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
        """Verify the domain guides plus the on-demand reference guides exist."""
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
