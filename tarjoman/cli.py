"""
Command Line Interface for Tarjoman Universal Translation Engine.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import click

from tarjoman.composers.bilingual_md import BilingualMarkdownComposer
from tarjoman.composers.epub3 import Epub3Composer
from tarjoman.composers.html_reader import HtmlReaderComposer
from tarjoman.composers.typst_pdf import TypstPdfComposer
from tarjoman.core.contracts import BookManifest, TextSegment
from tarjoman.core.pipeline import TranslationPipeline
from tarjoman.domains.router import DomainRegistry, DomainRouter
from tarjoman.linter import format_report, lint_text
from tarjoman.memory import BookManifestManager, CharacterBible, Termbase
from tarjoman.stages.stage5_audit import AuditStage


@click.group()
@click.version_option(version="1.0.0", prog_name="tarjoman")
def cli() -> None:
    """Tarjoman: Universal Persian Translation Engine & Multi-Agent Skillpack."""
    pass


# -----------------------------------------------------------------------------
# route subcommand
# -----------------------------------------------------------------------------
@cli.command("route")
@click.argument("text_or_file", type=str)
def route_cmd(text_or_file: str) -> None:
    """Detect domain of a given text string or file path."""
    p = Path(text_or_file)
    if p.is_file():
        content = p.read_text(encoding="utf-8")
    else:
        content = text_or_file

    router = DomainRouter()
    profile, confidence = router.route(content)

    click.echo(f"Domain: {profile.id.value}")
    click.echo(f"Persian Title: {profile.title_fa}")
    click.echo(f"Confidence: {confidence * 100:.1f}% ({confidence:.2f})")


# -----------------------------------------------------------------------------
# translate subcommand
# -----------------------------------------------------------------------------
@cli.command("translate")
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-d", "--domain", default=None, help="Domain override (e.g. literary, scientific, legal)")
@click.option("-o", "--output", "output_path", default=None, type=click.Path(dir_okay=False, path_type=Path), help="Path to write translation output")
@click.option(
    "--composer",
    type=click.Choice(["none", "bilingual", "html", "typst", "epub"], case_sensitive=False),
    default="none",
    help="Publishing composer format (none, bilingual, html, typst, epub)",
)
def translate_cmd(
    input_file: Path,
    domain: Optional[str],
    output_path: Optional[Path],
    composer: str,
) -> None:
    """Run translation pipeline on input_file and optionally write composed output."""
    src_text = input_file.read_text(encoding="utf-8")

    router = DomainRouter()
    if domain:
        profile, _ = router.route(src_text, override=domain)
    else:
        profile, _ = router.route(src_text)

    pipeline = TranslationPipeline()
    segments, report = pipeline.run(src_text, profile)
    target_text = "\n\n".join(seg.polished_text or "" for seg in segments)

    composer_choice = composer.lower()
    if composer_choice == "bilingual":
        result = BilingualMarkdownComposer().compose(src_text, target_text)
    elif composer_choice == "html":
        result = HtmlReaderComposer().compose(src_text, target_text, title=f"ترجمه: {profile.title_fa}")
    elif composer_choice == "typst":
        result = TypstPdfComposer().compose(target_text, title=f"ترجمه: {profile.title_fa}")
    elif composer_choice == "epub":
        epub_bytes = Epub3Composer().compose(
            target_text, title=f"ترجمه: {profile.title_fa}"
        )
        if output_path and str(output_path).lower().endswith(".epub"):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(epub_bytes)
            click.echo(
                f"Translation saved to {output_path} "
                f"(Domain: {profile.id.value}, Score: {report.quality_score:.1f})"
            )
            return
        result = (
            f"[EPUB: {len(epub_bytes)} bytes — write to a .epub path with -o to save]"
        )
    else:
        result = target_text

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result, encoding="utf-8")
        click.echo(f"Translation saved to {output_path} (Domain: {profile.id.value}, Score: {report.quality_score:.1f})")
    else:
        click.echo(result)


# -----------------------------------------------------------------------------
# compose command group
# -----------------------------------------------------------------------------
@cli.group("compose")
def compose_group() -> None:
    """Compose source and translated texts into publishing formats."""
    pass


@compose_group.command("bilingual")
@click.argument("src_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("target_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--output", "output_path", required=True, type=click.Path(dir_okay=False, path_type=Path), help="Output path for Markdown table")
def compose_bilingual_cmd(src_file: Path, target_file: Path, output_path: Path) -> None:
    """Compose bilingual side-by-side Markdown comparison table."""
    src_text = src_file.read_text(encoding="utf-8")
    target_text = target_file.read_text(encoding="utf-8")
    composer = BilingualMarkdownComposer()
    result = composer.compose(src_text, target_text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result, encoding="utf-8")
    click.echo(f"Bilingual Markdown composed: {output_path}")


@compose_group.command("html")
@click.argument("src_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("target_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--output", "output_path", required=True, type=click.Path(dir_okay=False, path_type=Path), help="Output path for HTML reader")
@click.option("--title", default=None, help="Document title for HTML reader")
def compose_html_cmd(
    src_file: Path,
    target_file: Path,
    output_path: Path,
    title: Optional[str],
) -> None:
    """Compose interactive standalone HTML reader."""
    src_text = src_file.read_text(encoding="utf-8")
    target_text = target_file.read_text(encoding="utf-8")
    composer = HtmlReaderComposer()
    kwargs = {}
    if title:
        kwargs["title"] = title
    result = composer.compose(src_text, target_text, **kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result, encoding="utf-8")
    click.echo(f"HTML Reader composed: {output_path}")


@compose_group.command("typst")
@click.argument("target_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-s", "--style", type=click.Choice(["book", "paper"], case_sensitive=False), default="book", help="Layout style (book/paper)")
@click.option("-o", "--output", "output_path", required=True, type=click.Path(dir_okay=False, path_type=Path), help="Output path for Typst document")
@click.option("--compile", "compile_pdf", is_flag=True, default=False, help="Compile Typst source to PDF")
def compose_typst_cmd(
    target_file: Path,
    style: str,
    output_path: Path,
    compile_pdf: bool,
) -> None:
    """Compose publication-grade Typst document and optionally compile PDF."""
    target_text = target_file.read_text(encoding="utf-8")
    composer = TypstPdfComposer()
    typst_code = composer.compose(target_text, style=style)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(typst_code, encoding="utf-8")
    click.echo(f"Typst source composed: {output_path}")

    if compile_pdf:
        pdf_path = str(output_path.with_suffix(".pdf"))
        ok = composer.compile_pdf(typst_code, pdf_path)
        if ok:
            click.echo(f"PDF compiled successfully: {pdf_path}")
        else:
            click.echo(f"Failed to compile PDF: {pdf_path}", err=True)


@compose_group.command("epub")
@click.argument("target_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--output", "output_path", required=True, type=click.Path(dir_okay=False, path_type=Path), help="Output path for EPUB 3 e-book (.epub)")
@click.option("--title", default=None, help="Book title")
@click.option("--author", default=None, help="Author or translator attribution")
def compose_epub_cmd(
    target_file: Path,
    output_path: Path,
    title: Optional[str],
    author: Optional[str],
) -> None:
    """Compose a W3C EPUB 3 e-book (strict RTL Persian) from translated text."""
    target_text = target_file.read_text(encoding="utf-8")
    composer = Epub3Composer()
    out = output_path if str(output_path).lower().endswith(".epub") else output_path.with_suffix(".epub")
    composer.compose_to_file(target_text, out, title=title, author=author)
    click.echo(f"EPUB 3 composed: {out}")


# -----------------------------------------------------------------------------
# audit subcommand
# -----------------------------------------------------------------------------
@cli.command("audit")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-d", "--domain", default=None, help="Domain profile for MQM rules")
@click.option("-s", "--src", "src_file", default=None, type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Source English file for omission and digit checking")
def audit_cmd(file: Path, domain: Optional[str], src_file: Optional[Path]) -> None:
    """Run Stage 5 MQM Quality Audit on translated file."""
    target_text = file.read_text(encoding="utf-8")
    src_text = src_file.read_text(encoding="utf-8") if src_file else ""

    router = DomainRouter()
    if domain:
        profile, _ = router.route(target_text, override=domain)
    else:
        profile, _ = router.route(target_text)

    segment = TextSegment(id=1, source_text=src_text, polished_text=target_text)
    stage5 = AuditStage()
    report = stage5.audit([segment], profile)

    status_str = "PASSED" if report.passed else "FAILED"
    click.echo(f"Tarjoman MQM Audit: {file.name}")
    click.echo("=" * 40)
    click.echo(f"Status: {status_str}")
    click.echo(f"Quality Score: {report.quality_score:.1f} / 100.0")
    click.echo(f"Omissions: {report.omission_count}")
    click.echo(f"Banned Calques: {report.banned_calque_count}")
    click.echo(f"Findings: {len(report.findings)}")

    if report.findings:
        click.echo("\nDetailed Findings:")
        for idx, finding in enumerate(report.findings, start=1):
            click.echo(f"  {idx}. [{finding.severity.upper()}] {finding.rule_id}: {finding.message}")
            if finding.excerpt:
                click.echo(f"     Excerpt: {finding.excerpt}")


# -----------------------------------------------------------------------------
# lint subcommand
# -----------------------------------------------------------------------------
@cli.command("lint")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def lint_cmd(file: Path) -> None:
    """Run Persian linguistic & typography linter on a file."""
    content = file.read_text(encoding="utf-8")
    issues = lint_text(content)
    report = format_report(str(file), issues)
    click.echo(report)
    if issues:
        sys.exit(1)


# -----------------------------------------------------------------------------
# book command group
# -----------------------------------------------------------------------------
@cli.group("book")
def book_group() -> None:
    """Manage long-form book translation projects."""
    pass


@book_group.command("init")
@click.argument("title", type=str)
@click.option("-o", "--out-dir", "out_dir", default=None, type=click.Path(path_type=Path), help="Output directory for book project")
def book_init_cmd(title: str, out_dir: Optional[Path]) -> None:
    """Initialize a new book translation project with manifest.json and terms.tsv."""
    if out_dir is None:
        safe_slug = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_") or "book_project"
        target_dir = Path(safe_slug)
    else:
        target_dir = out_dir

    target_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = target_dir / "manifest.json"
    terms_path = target_dir / "terms.tsv"

    manifest = BookManifest(
        title=title,
        source_language="en",
        target_language="fa",
        total_chapters=1,
        current_chapter=0,
        total_segments=0,
        translated_segments=0,
        terms_count=0,
        metadata={"created_with": "tarjoman-cli"},
    )
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    if not terms_path.exists():
        tsv_header = "english_term\tpersian_term\tdomain\tnotes\n"
        terms_path.write_text(tsv_header, encoding="utf-8")

    click.echo(f"Book project initialized at: {target_dir.resolve()}")
    click.echo(f"  - Manifest: {manifest_path}")
    click.echo(f"  - Termbase: {terms_path}")


@book_group.command("status")
@click.argument("project_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
def book_status_cmd(project_dir: Path) -> None:
    """Display translation progress statistics for a book project."""
    manifest_path = project_dir / "manifest.json"
    if not manifest_path.exists():
        click.echo(f"Error: manifest.json not found in {project_dir}", err=True)
        sys.exit(1)

    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = BookManifest.model_validate(manifest_data)
    except Exception as exc:
        click.echo(f"Error parsing manifest.json: {exc}", err=True)
        sys.exit(1)

    terms_path = project_dir / "terms.tsv"
    terms_count = 0
    if terms_path.exists():
        with open(terms_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("english_term\t") or line.startswith("#"):
                    continue
                terms_count += 1
    else:
        terms_count = manifest.terms_count

    percent = (
        (manifest.translated_segments / manifest.total_segments * 100.0)
        if manifest.total_segments > 0
        else 0.0
    )

    click.echo(f"Book Project Status: {manifest.title}")
    click.echo("=" * 40)
    click.echo(f"Languages: {manifest.source_language} -> {manifest.target_language}")
    click.echo(f"Chapters: {manifest.current_chapter} / {manifest.total_chapters}")
    click.echo(f"Segments: {manifest.translated_segments} / {manifest.total_segments} ({percent:.1f}%)")
    click.echo(f"Dynamic Terms: {terms_count}")


@book_group.command("manifest")
@click.argument("project_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
def book_manifest_cmd(project_dir: Path) -> None:
    """Display SHA-256 resumable manifest (v2) stats for a book project."""
    project = Path(project_dir)
    v2_path = project / "manifest.v2.json"
    if v2_path.exists():
        mgr = BookManifestManager(manifest_path=v2_path)
        stats = mgr.get_stats()
        click.echo(f"Book Manifest (v2): {stats['title'] or project.name}")
        click.echo("=" * 40)
        click.echo(f"Chapters: {stats['total_chapters']}")
        click.echo(
            f"Chunks: {stats['translated_chunks']} / {stats['total_chunks']} "
            f"({stats['progress'] * 100:.1f}%)"
        )
        click.echo(f"Pending chunks: {stats['pending_chunks']}")
        click.echo(f"Words: {stats['translated_words']} / {stats['source_words']}")
        return

    # Fall back to the v1 manifest.json view.
    manifest_path = project / "manifest.json"
    if not manifest_path.exists():
        click.echo(f"Error: manifest.json not found in {project_dir}", err=True)
        sys.exit(1)
    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        click.echo(f"Error parsing manifest.json: {exc}", err=True)
        sys.exit(1)
    click.echo(f"Book Manifest (v1): {manifest_data.get('title', project.name)}")
    click.echo("=" * 40)
    click.echo(
        f"Segments: {manifest_data.get('translated_segments', 0)} / "
        f"{manifest_data.get('total_segments', 0)}"
    )


@book_group.command("characters")
@click.argument("project_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--add", "add_spec", default=None, help="Add character: NAME[:FA_NAME[:TONE[:ADDRESS]]]")
@click.option("--list", "list_only", is_flag=True, default=False, help="List all characters")
def book_characters_cmd(project_dir: Path, add_spec: Optional[str], list_only: bool) -> None:
    """Manage the character bible (voices, transliterations, تو/شما) for a book."""
    project = Path(project_dir)
    bible_path = project / "characters.json"
    bible = CharacterBible(bible_path=bible_path if bible_path.exists() else None)
    if bible_path.exists():
        bible = CharacterBible(bible_path=bible_path)

    if add_spec:
        parts = [p.strip() for p in add_spec.split(":")]
        name = parts[0] if len(parts) > 0 else ""
        fa_name = parts[1] if len(parts) > 1 else ""
        tone = parts[2] if len(parts) > 2 else ""
        address = parts[3] if len(parts) > 3 else "شما"
        if not name:
            click.echo("Error: character NAME is required for --add.", err=True)
            sys.exit(1)
        bible.record_character(name, persian_name=fa_name, tone=tone, default_address=address)
        bible.save(bible_path)
        click.echo(f"Character recorded: {name}" + (f" ({fa_name})" if fa_name else ""))
        return

    characters = bible.list_characters()
    if not characters:
        click.echo("Character bible is empty. Use --add NAME[:FA[:TONE[:ADDRESS]]].")
        return
    click.echo(f"Character Bible: {project.name} ({len(characters)} characters)")
    click.echo("=" * 40)
    for char in characters:
        extra = " / ".join(x for x in (char.persian_name, char.tone, char.default_address) if x)
        click.echo(f"- {char.name}" + (f" — {extra}" if extra else ""))


@book_group.command("terms")
@click.argument("project_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--add", "add_spec", default=None, help="Add term: EN=FA[:DOMAIN]")
@click.option("--search", "query", default=None, help="Search terms")
@click.option("--cascades", is_flag=True, default=False, help="Show pending cascade re-translations")
def book_terms_cmd(
    project_dir: Path, add_spec: Optional[str], query: Optional[str], cascades: bool
) -> None:
    """Manage the SQLite termbase (domain-tagged) for a book project."""
    project = Path(project_dir)
    termbase = Termbase(db_path=project / "terms.db")

    if add_spec:
        if "=" not in add_spec:
            click.echo("Error: --add expects EN=FA[:DOMAIN].", err=True)
            sys.exit(1)
        left, _, right = add_spec.partition("=")
        fa, _, domain = right.partition(":")
        if not left.strip() or not fa.strip():
            click.echo("Error: both EN and FA are required.", err=True)
            sys.exit(1)
        termbase.record_term(left.strip(), fa.strip(), domain=domain.strip())
        click.echo(f"Term recorded: {left.strip()} -> {fa.strip()}")
        termbase.close()
        return

    if query:
        hits = termbase.search(query)
        termbase.close()
        if not hits:
            click.echo(f"No terms match: {query}")
            return
        for hit in hits:
            tag = f" [{hit.domain}]" if hit.domain else ""
            click.echo(f"- {hit.en_term} -> {hit.fa_term}{tag}")
        return

    if cascades:
        events = termbase.pending_cascades()
        termbase.close()
        if not events:
            click.echo("No pending cascade re-translations.")
            return
        for event in events:
            segs = ", ".join(f"{c}:{s}" for c, s in event.affected_segments) or "—"
            click.echo(f"- {event.en_term}: {event.old_fa_term} -> {event.new_fa_term} [{segs}]")
        return

    total = termbase.count()
    termbase.close()
    click.echo(f"Termbase: {project.name} ({total} terms)")


# -----------------------------------------------------------------------------
# epub command group (roundtrip)
# -----------------------------------------------------------------------------
@cli.group("epub")
def epub_group() -> None:
    """Roundtrip translation of EPUB e-books."""
    pass


@epub_group.command("roundtrip")
@click.argument("input_epub", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--output", "output_epub", default=None, type=click.Path(dir_okay=False, path_type=Path), help="Output translated EPUB path")
@click.option("--domain", default="literary", help="Translation domain")
def epub_roundtrip_cmd(input_epub: Path, output_epub: Optional[Path], domain: str) -> None:
    """Parse input EPUB, translate text nodes, and compose a translated EPUB."""
    from tarjoman.composers.epub_roundtrip import EpubRoundtripComposer
    from tarjoman.parsers.epub_parser import EpubParser

    parsed = EpubParser().parse(input_epub)
    translations = {
        node.id: node.html_content
        for chapter in parsed.chapters
        for node in chapter.text_nodes
    }
    out = output_epub or input_epub.with_name(f"{input_epub.stem}_translated.epub")
    EpubRoundtripComposer().compose(parsed, translations=translations, output_path=out)
    click.echo(f"EPUB roundtrip (domain: {domain})")
    click.echo(f"Chapters: {len(parsed.chapters)}")
    click.echo(f"Text nodes: {len(translations)}")
    click.echo(f"Output: {out}")


# -----------------------------------------------------------------------------
# scene command group (continuity tracker)
# -----------------------------------------------------------------------------
@cli.group("scene")
def scene_group() -> None:
    """Track narrative scene continuity (POV, location, atmosphere, pronouns)."""
    pass


def _load_scene_tracker(state_file: Optional[Path] = None):
    from tarjoman.memory import SceneContinuityTracker

    path = Path(state_file) if state_file else Path("scene_state.json")
    if path.exists():
        return SceneContinuityTracker(state_path=path)
    return SceneContinuityTracker(state_path=path)


@scene_group.command("status")
@click.option("--state-file", "state_file", default=None, type=click.Path(path_type=Path), help="Tracker state file")
def scene_status_cmd(state_file: Optional[Path]) -> None:
    """Display current POV, location, atmosphere, and pronoun references."""
    tracker = _load_scene_tracker(state_file)
    state = tracker.get_current_state()
    if state is None:
        click.echo("No scene recorded yet.")
        return
    click.echo(f"POV: {state.pov}")
    click.echo(f"Location: {state.location}")
    click.echo(f"Atmosphere: {state.atmosphere}")
    click.echo(f"Pronouns: {state.pronoun_references}")


@scene_group.command("record")
@click.option("--chapter", default="", help="Chapter id")
@click.option("--pov", default="third_person", help="Point of view")
@click.option("--location", default="", help="Spatial location")
@click.option("--atmosphere", default="", help="Atmosphere/mood")
@click.option("--state-file", "state_file", default=None, type=click.Path(path_type=Path), help="Tracker state file")
def scene_record_cmd(chapter: str, pov: str, location: str, atmosphere: str, state_file: Optional[Path]) -> None:
    """Record a scene state."""
    tracker = _load_scene_tracker(state_file)
    tracker.record_scene(chapter_id=chapter, pov=pov, location=location, atmosphere=atmosphere)
    tracker.save()
    click.echo(f"Scene recorded: chapter={chapter} pov={pov}")


@scene_group.command("check")
@click.option("--state-file", "state_file", default=None, type=click.Path(path_type=Path), help="Tracker state file")
def scene_check_cmd(state_file: Optional[Path]) -> None:
    """Check continuity against the last recorded state."""
    tracker = _load_scene_tracker(state_file)
    state = tracker.get_current_state()
    if state is None:
        click.echo("No scene recorded yet.")
        return
    warnings = tracker.check_continuity(state)
    if not warnings:
        click.echo("Continuity OK.")
    else:
        for warning in warnings:
            click.echo(f"Warning: {warning}")


@scene_group.command("reset")
@click.option("--state-file", "state_file", default=None, type=click.Path(path_type=Path), help="Tracker state file")
def scene_reset_cmd(state_file: Optional[Path]) -> None:
    """Reset/clear the tracker state."""
    from tarjoman.memory import SceneContinuityTracker

    path = Path(state_file) if state_file else Path("scene_state.json")
    fresh = SceneContinuityTracker(state_path=path)
    fresh.save(path)
    click.echo("Scene tracker reset.")


if __name__ == "__main__":
    cli()
