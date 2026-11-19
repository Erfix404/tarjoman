"""Tests for Phase 2: enhanced fidelity/consistency, book context, EPUB extract/merge, VTT, i18n, and MCP server."""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Iterator

from click.testing import CliRunner

from tarjoman.cli import cli
from tarjoman.composers.epub3 import Epub3Composer
from tarjoman.mcp_server import TarjomanMcpServer
from tarjoman.memory import build_book_context
from tarjoman.memory.consistency import check_characters, check_terms
from tarjoman.memory.fidelity import check_fidelity
from tarjoman.parsers.epub_workflow import extract_epub_for_translation, merge_epub_translation
from tarjoman.parsers.i18n import check_i18n, check_i18n_maps, load_i18n_file
from tarjoman.parsers.srt import check_srt, extract_for_translation, merge_translation, parse_srt


@contextlib.contextmanager
def _temp_cwd() -> Iterator[Path]:
    prev = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            yield Path(tmp)
        finally:
            os.chdir(prev)


def _make_sample_epub(path: Path) -> None:
    container = (
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Book</dc:title><dc:language>en</dc:language>"
        "<dc:creator>Author</dc:creator></metadata>"
        '<manifest><item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/></manifest>'
        '<spine><itemref idref="ch1"/></spine></package>'
    )
    ch1 = (
        "<html><head><title>Chapter 1</title></head>"
        "<body><h1>Chapter One</h1><p>Hello <em>world</em>.</p></body></html>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/ch1.xhtml", ch1)


class TestEnhancedFidelityAndConsistency(unittest.TestCase):
    def test_fidelity_latex_placeholders_headings_tables(self) -> None:
        src = (
            "# Title\n\n"
            "Formula $E=mc^2$ and \\cite{einstein1905} with {count} items and $1,250 price.\n\n"
            "| Col A | Col B |\n|---|---|\n| 10 | 20 |\n"
        )
        ok_tgt = (
            "# عنوان\n\n"
            "فرمول $E=mc^2$ و \\cite{einstein1905} با {count} مورد و قیمت ۱٬۲۵۰ دلار.\n\n"
            "| ستون اول | ستون دوم |\n|---|---|\n| ۱۰ | ۲۰ |\n"
        )
        self.assertEqual(check_fidelity(src, ok_tgt), [])

        bad_tgt = (
            "عنوان بدون مارک‌داون\n\n"
            "فرمول تغییر کرده و موارد و قیمت ۱٬۲۵۰ دلار.\n\n"
            "| ستون |\n|---|\n| ۱۰ |\n"
        )
        cats = {f.category for f in check_fidelity(src, bad_tgt)}
        self.assertTrue({"latex", "placeholder", "headings", "tables"} <= cats)

    def test_consistency_occurrence_drift_vs_twomentions(self) -> None:
        # 2 occurrences in source, 1 in Persian translation (pronoun drop) -> OK
        self.assertEqual(
            check_terms("The wand glowed. The wand hummed.", "چوب‌دستی درخشید و وزوز کرد.", {"wand": "چوب‌دستی"}),
            [],
        )
        # 4 occurrences in source, 1 in target -> drift flagged
        drift = check_terms(
            "The wand fell. The wand broke. The wand sparked. The wand vanished.",
            "چوب‌دستی افتاد. عصا شکست. ترکه جرقه زد. چوب ناپدید شد.",
            {"wand": "چوب‌دستی"},
        )
        self.assertEqual([f.category for f in drift], ["term"])

        char_drift = check_characters(
            "Alice ran. Alice stopped. Alice laughed. Alice cried.",
            "آلیس دوید. دختر ایستاد. او خندید. کودک گریه کرد.",
            [("Alice", "آلیس")],
        )
        self.assertEqual([f.category for f in char_drift], ["character"])


class TestBookContext(unittest.TestCase):
    def test_build_book_context_and_cli(self) -> None:
        runner = CliRunner()
        with _temp_cwd():
            proj = Path("novel")
            runner.invoke(cli, ["book", "init", "My Novel", "-o", str(proj)])
            runner.invoke(cli, ["book", "terms", str(proj), "--add", "wand=چوب‌دستی:literary"])
            runner.invoke(cli, ["book", "terms", str(proj), "--add", "potion=معجون:literary"])
            runner.invoke(cli, ["book", "characters", str(proj), "--add", "Alice:آلیس:formal:تو"])
            runner.invoke(cli, ["book", "characters", str(proj), "--add", "Bob:باب:colloquial:شما"])
            runner.invoke(
                cli,
                [
                    "scene",
                    "record",
                    "--chapter",
                    "ch1",
                    "--pov",
                    "third_person",
                    "--location",
                    "Hall",
                    "--state-file",
                    str(proj / "scene_state.json"),
                ],
            )
            chunk = Path("ch2.en.md")
            chunk.write_text("Alice picked up the wand quietly.", encoding="utf-8")
            prev = Path("ch1.fa.md")
            prev.write_text("پاراگراف اول.\n\nپاراگراف دوم.\n\nپاراگراف پایانی.", encoding="utf-8")

            ctx = build_book_context(proj, chunk.read_text(encoding="utf-8"), prev.read_text(encoding="utf-8"), tail_paragraphs=2)
            self.assertEqual([t["en"] for t in ctx["matched_terms"]], ["wand"])
            self.assertEqual([c["name"] for c in ctx["matched_characters"]], ["Alice"])
            self.assertEqual(ctx["scene"]["location"], "Hall")
            self.assertEqual(ctx["previous_tail"], "پاراگراف دوم.\n\nپاراگراف پایانی.")

            res = runner.invoke(
                cli,
                ["book", "context", str(proj), str(chunk), "--prev", str(prev), "--tail", "1", "--json"],
            )
            self.assertEqual(res.exit_code, 0, res.output)
            data = json.loads(res.output)
            self.assertEqual(data["previous_tail"], "پاراگراف پایانی.")


class TestEpubExtractMergeAndVtt(unittest.TestCase):
    def test_epub_extract_merge_roundtrip_and_refusal(self) -> None:
        runner = CliRunner()
        with _temp_cwd():
            src_epub = Path("story.epub")
            _make_sample_epub(src_epub)
            out_dir = Path("extracted")

            ext_res = runner.invoke(cli, ["epub", "extract", str(src_epub), "-o", str(out_dir), "--json"])
            self.assertEqual(ext_res.exit_code, 0, ext_res.output)
            ext_info = json.loads(ext_res.output)
            self.assertEqual(ext_info["total_nodes"], 2)
            md_file = Path(ext_info["files"][0])
            self.assertTrue((out_dir / "epub_manifest.json").exists())

            md_file.write_text(
                "[#ch1_node_0]\nفصل یک\n\n[#ch1_node_1]\nسلام <em>دنیا</em>.\n",
                encoding="utf-8",
            )
            merged_epub = Path("story.fa.epub")
            merge_res = runner.invoke(
                cli, ["epub", "merge", str(src_epub), str(out_dir), "-o", str(merged_epub), "--json"]
            )
            self.assertEqual(merge_res.exit_code, 0, merge_res.output)
            self.assertTrue(merged_epub.exists())
            report = Epub3Composer.inspect_epub(merged_epub.read_bytes())
            self.assertTrue(report["mimetype_ok"])
            with zipfile.ZipFile(merged_epub, "r") as zf:
                opf_xml = zf.read("OEBPS/content.opf").decode("utf-8")
                self.assertIn('page-progression-direction="rtl"', opf_xml)
                ch1_html = zf.read("OEBPS/ch1.xhtml").decode("utf-8")
                self.assertIn('dir="rtl"', ch1_html)
                self.assertIn("سلام <em>دنیا</em>.", ch1_html)

            # Broken marker must be refused
            md_file.write_text("[#ch1_node_0]\nفصل یک\n", encoding="utf-8")
            bad = runner.invoke(cli, ["epub", "merge", str(src_epub), str(out_dir), "-o", "bad.epub"])
            self.assertNotEqual(bad.exit_code, 0)
            self.assertIn("missing markers", bad.output)

    def test_webvtt_extract_merge_and_check(self) -> None:
        vtt = (
            "WEBVTT\n\n"
            "NOTE comment block\n\n"
            "00:01.000 --> 00:04.500 align:start\n"
            "Hello there.\n\n"
            "00:05.000 --> 00:08.000\n"
            "How are you?\n"
        )
        cues = parse_srt(vtt)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0].settings, "align:start")

        extracted = extract_for_translation(vtt)
        self.assertIn("[#1]\nHello there.", extracted)
        fa_cues = "[#1]\nسلام.\n\n[#2]\nحالت چطوره؟\n"
        merged = merge_translation(vtt, fa_cues)
        self.assertTrue(merged.startswith("WEBVTT\n\n"))
        self.assertIn("00:00:01.000 --> 00:00:04.500 align:start", merged)
        self.assertEqual(check_srt(vtt, merged), [])


class TestI18nChecker(unittest.TestCase):
    def test_json_arb_po_yaml_checks_and_cli(self) -> None:
        runner = CliRunner()
        with _temp_cwd():
            # JSON / ARB with nested dict & @metadata
            src_json = Path("en.arb")
            tgt_json = Path("fa.arb")
            src_json.write_text(
                json.dumps(
                    {
                        "@@locale": "en",
                        "files": "{count} files remaining",
                        "@files": {"description": "count"},
                        "greet": "Hello <b>{name}</b>",
                        "nested": {"ok": "Save changes"},
                    }
                ),
                encoding="utf-8",
            )
            tgt_json.write_text(
                json.dumps(
                    {
                        "@@locale": "fa",
                        "files": "{count} فایل‌ها باقی مانده",
                        "greet": "سلام {name}",
                        "nested": {"ok": "Save changes"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            findings = check_i18n(src_json, tgt_json)
            cats = {f.category for f in findings}
            self.assertEqual(cats, {"count-plural", "html-tag", "untranslated"})

            res = runner.invoke(cli, ["i18n", "check", str(src_json), str(tgt_json), "--json"])
            self.assertEqual(res.exit_code, 1)
            self.assertFalse(json.loads(res.output)["passed"])

            # PO format
            src_po = Path("en.po")
            tgt_po = Path("fa.po")
            src_po.write_text(
                'msgid ""\nmsgstr "Content-Type: text/plain; charset=UTF-8\\n"\n\n'
                'msgid "Welcome %s"\nmsgstr "Welcome %s"\n',
                encoding="utf-8",
            )
            tgt_po.write_text(
                'msgid ""\nmsgstr "Content-Type: text/plain; charset=UTF-8\\n"\n\n'
                'msgid "Welcome %s"\nmsgstr "خوش آمدید %s"\n',
                encoding="utf-8",
            )
            self.assertEqual(check_i18n(src_po, tgt_po), [])

            # YAML format
            src_yml = Path("en.yml")
            tgt_yml = Path("fa.yml")
            src_yml.write_text("app:\n  title: Settings\n  cta: Save\n", encoding="utf-8")
            tgt_yml.write_text("app:\n  title: تنظیمات\n  cta: ذخیره\n", encoding="utf-8")
            self.assertEqual(load_i18n_file(src_yml), {"app.title": "Settings", "app.cta": "Save"})
            res_ok = runner.invoke(cli, ["i18n", "check", str(src_yml), str(tgt_yml), "--json"])
            self.assertEqual(res_ok.exit_code, 0)
            self.assertTrue(json.loads(res_ok.output)["passed"])

            # Length ratio check
            ratio_findings = check_i18n_maps(
                {"btn": "Short label here"},
                {"btn": "این یک متن بسیار طولانی برای دکمه‌ی کوچک بازی است"},
                max_length_ratio=1.5,
            )
            self.assertEqual([f.category for f in ratio_findings], ["length"])


class TestMcpServer(unittest.TestCase):
    def test_initialize_tools_list_and_all_7_tools(self) -> None:
        server = TarjomanMcpServer()
        init = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert init is not None
        self.assertEqual(init["result"]["serverInfo"]["name"], "tarjoman")
        self.assertIsNone(
            server.handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"})
        )

        tools = server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert tools is not None
        names = {t["name"] for t in tools["result"]["tools"]}
        self.assertEqual(
            names,
            {
                "tarjoman_route_guide",
                "tarjoman_lint",
                "tarjoman_fix_safe",
                "tarjoman_verify",
                "tarjoman_book_context",
                "tarjoman_srt_check",
                "tarjoman_i18n_check",
            },
        )

        def _call(name: str, arguments: dict) -> dict:
            resp = server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 99,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                }
            )
            assert resp is not None
            self.assertFalse(resp["result"]["isError"], resp)
            return resp["result"]["structuredContent"]

        routed = _call("tarjoman_route_guide", {"text": "The court hereby orders indemnification."})
        self.assertEqual(routed["domain"], "legal")
        self.assertTrue(routed["guides"][0]["glance"])

        fixed = _call("tarjoman_fix_safe", {"text": "لطفا كتاب را می خوانم ,"})
        self.assertEqual(fixed["text"], "لطفاً کتاب را می‌خوانم،")

        linted = _call("tarjoman_lint", {"text": "این کار توسط او انجام شد.", "errors_only": True})
        self.assertTrue(linted["passed"])

        verified = _call("tarjoman_verify", {"source": "Year 2026", "target": "سال ۲۰۲۶"})
        self.assertTrue(verified["passed"])

        srt_res = _call(
            "tarjoman_srt_check",
            {"target_text": "1\n00:00:01,000 --> 00:00:03,000\nسلام.\n"},
        )
        self.assertTrue(srt_res["passed"])

        with _temp_cwd() as tmp:
            proj = tmp / "bk"
            CliRunner().invoke(cli, ["book", "init", "B", "-o", str(proj)])
            CliRunner().invoke(cli, ["book", "terms", str(proj), "--add", "wand=چوب‌دستی"])
            ctx = _call(
                "tarjoman_book_context",
                {"project_dir": str(proj), "source_chunk": "A wand fell."},
            )
            self.assertEqual(ctx["matched_terms"][0]["fa"], "چوب‌دستی")

            en_f = tmp / "en.json"
            fa_f = tmp / "fa.json"
            en_f.write_text('{"hi": "Hello {name}"}', encoding="utf-8")
            fa_f.write_text('{"hi": "سلام {name}"}', encoding="utf-8")
            i18n_res = _call(
                "tarjoman_i18n_check",
                {"source_path": str(en_f), "target_path": str(fa_f)},
            )
            self.assertTrue(i18n_res["passed"])

        unknown_method = server.handle_request({"jsonrpc": "2.0", "id": 3, "method": "nope"})
        assert unknown_method is not None
        self.assertEqual(unknown_method["error"]["code"], -32601)

    def test_stdio_roundtrip(self) -> None:
        stdin = io.StringIO(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n"
            + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
            + "{bad json\n"
        )
        stdout = io.StringIO()
        TarjomanMcpServer().serve_stdio(stdin=stdin, stdout=stdout)
        lines = [json.loads(line) for line in stdout.getvalue().strip().splitlines()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["result"], {})
        self.assertEqual(lines[1]["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()
