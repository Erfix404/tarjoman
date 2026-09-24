"""Pack A: technical/scientific dual-level terminology, reverse technical
calques, and bidi-isolate linting."""
from __future__ import annotations

import unittest

from tarjoman import linter
from tarjoman.core.contracts import DomainType
from tarjoman.domains import DomainRegistry, DomainRouter
from tarjoman.stages.anti_calque import AntiCalqueEngine, LINT_CALQUE_PATTERNS


class TestDualLevelTerminology(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = DomainRegistry()
        self.router = DomainRouter(registry=self.registry)

    def test_technical_levels_differ(self) -> None:
        tech = self.registry.get(DomainType.TECHNICAL)
        sys_terms = tech.get_terms("system-docs")
        jrn_terms = tech.get_terms("journal")
        self.assertEqual(sys_terms["node"], "node")
        self.assertEqual(jrn_terms["node"], "گره (Node)")
        self.assertEqual(sys_terms["deployment"], "deployment")
        self.assertIn("استقرار", jrn_terms["deployment"])
        self.assertEqual(sys_terms["runtime"], "runtime")
        self.assertIn("محیط اجرا", jrn_terms["runtime"])

    def test_scientific_levels_differ(self) -> None:
        sci = self.registry.get(DomainType.SCIENTIFIC)
        sys_terms = sci.get_terms("system-docs")
        jrn_terms = sci.get_terms("journal")
        self.assertEqual(sys_terms["deploy"], "deploy")
        self.assertIn("استقرار", jrn_terms["deploy"])
        self.assertIn("فرضیه", jrn_terms["hypothesis"])
        self.assertIn("همبستگی معنادار", jrn_terms["correlation"])

    def test_backward_compat_base_map(self) -> None:
        tech = self.registry.get(DomainType.TECHNICAL)
        base = tech.get_terms()
        self.assertEqual(base, tech.terminology_map)
        self.assertEqual(tech.get_terms("unknown-level"), tech.terminology_map)

    def test_router_level_resolution(self) -> None:
        profile, conf = self.router.route("x", override="technical", level="journal")
        self.assertEqual(profile.id, DomainType.TECHNICAL)
        self.assertEqual(conf, 1.0)
        self.assertIn("گره", profile.get_terms("journal")["node"])
        self.assertRaises(ValueError, self.registry.get, "technical", "nope")


class TestReverseTechnicalCalques(unittest.TestCase):
    def test_lint_patterns_registered(self) -> None:
        labels = " ".join(name for name, _ in LINT_CALQUE_PATTERNS)
        for token in ("بر روی", "اتصال", "استقرار", "ارور"):
            self.assertIn(token, labels)

    def test_detection_and_lint(self) -> None:
        for text in (
            "دستور را اجرا کردن بر روی سرور.",
            "به دیتابیس اتصال زد.",
            "او ارور گرفت.",
            "فایل را استقرار داد بر روی سرور.",
            "سرویس را بالا آورد بر روی سرور.",
        ):
            self.assertTrue(AntiCalqueEngine.detect_calques(text), text)
            cats = {i.category for i in linter.lint_text(text)}
            self.assertIn("calque", cats, text)

    def test_elimination(self) -> None:
        self.assertEqual(
            AntiCalqueEngine.eliminate_calques("دستور را اجرا کردن بر روی سرور."),
            "دستور را روی سرور اجرا کردن.",
        )
        self.assertEqual(
            AntiCalqueEngine.eliminate_calques("به دیتابیس اتصال زد."),
            "به دیتابیس متصل شد.",
        )
        self.assertEqual(
            AntiCalqueEngine.eliminate_calques("او ارور گرفت."), "او خطا گرفت."
        )
        self.assertEqual(
            AntiCalqueEngine.eliminate_calques("فایل را استقرار داد."),
            "فایل را مستقر کرد.",
        )
        cleaned = AntiCalqueEngine.eliminate_calques(
            "سرویس را استقرار داد بر روی سرور."
        )
        self.assertNotIn("بر روی", cleaned)
        self.assertNotIn("استقرار داد", cleaned)


class TestBidiIsolateLinting(unittest.TestCase):
    def test_unbalanced_isolate(self) -> None:
        issues = linter.lint_text("متن فارسی ⁦node بدون پایان.")
        cats = {i.category for i in issues}
        self.assertIn("bidi-isolate", cats)
        self.assertIn("Unbalanced", issues[0].message)

    def test_unisolated_risky_latin_token(self) -> None:
        issues = linter.lint_text("سرویس روی node:v18 اجرا شد.")
        self.assertTrue([i for i in issues if i.category == "bidi-isolate"])

    def test_plain_token_only_when_enforced(self) -> None:
        self.assertFalse(
            [i for i in linter.lint_text("سرویس روی node اجرا شد.")
             if i.category == "bidi-isolate"]
        )
        self.assertTrue(
            [
                i
                for i in linter.lint_text(
                    "سرویس روی node اجرا شد.", enforce_bidi_isolation=True
                )
                if i.category == "bidi-isolate"
            ]
        )

    def test_isolated_and_latin_only_clean(self) -> None:
        self.assertFalse(
            [i for i in linter.lint_text("سرویس روی ⁦node:v18⁩ اجرا شد.")
             if i.category == "bidi-isolate"]
        )
        self.assertFalse(
            [i for i in linter.lint_text("node:v18 is here.")
             if i.category == "bidi-isolate"]
        )


if __name__ == "__main__":
    unittest.main()
