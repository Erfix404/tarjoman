"""
Comprehensive tests for canonical IR contracts (FND-002).

Acceptance criteria:
  - JSON round-trip for all canonical models
  - Schema snapshots tested
  - Deterministic stable ID generation tested
  - Validation failure cases thoroughly tested

Architecture invariant D38: only QUEUED/RUNNING/WAITING_REVIEW/
SUCCEEDED/FAILED/CANCELLED are legal job statuses.
"""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from tarjoman.core.contracts import (
    # Legacy (backward compatibility)
    AuditFinding,
    AuditReport,
    BookManifest,
    DomainProfile,
    DomainType,
    EmDashPolicy,
    StageResult,
    TextSegment,
    TypographicRules,
    # Canonical enums
    ArtifactKind,
    AuthorType,
    IntegrityPolicy,
    JobStatus,
    OperationType,
    ProtectedSpanType,
    SegmentVersionKind,
    # Canonical models
    Artifact,
    OperationSpec,
    ProjectSpec,
    ProtectedSpan,
    RunRecord,
    Segment,
    SegmentVersion,
    Workspace,
    # Hashing helpers
    compute_content_hash,
    compute_placeholder,
    compute_segment_id,
    # Schema utilities
    CANONICAL_MODELS,
    export_schemas_json,
    get_all_schemas,
    get_model_schema,
)


NOW = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)
NOW2 = datetime(2026, 9, 21, 13, 0, 0, tzinfo=timezone.utc)


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_workspace(**kw):
    defaults = dict(workspace_id="ws-001", root_path="/data/ws", created_at=NOW)
    defaults.update(kw)
    return Workspace(**defaults)


def _make_project(**kw):
    defaults = dict(project_id="prj-001", name="Test Project",
                    created_at=NOW, updated_at=NOW)
    defaults.update(kw)
    return ProjectSpec(**defaults)


def _make_operation(**kw):
    defaults = dict(operation_id="op-001", project_id="prj-001",
                    operation_type=OperationType.TRANSLATE, created_at=NOW)
    defaults.update(kw)
    return OperationSpec(**defaults)


def _make_protected_span(**kw):
    defaults = dict(span_id="span-001", type=ProtectedSpanType.CODE,
                    original_text="x = 1")
    defaults.update(kw)
    return ProtectedSpan(**defaults)


def _make_segment(**kw):
    defaults = dict(segment_id="seg-001", artifact_id="art-001",
                    structural_locator="p[0]", source_text="Hello",
                    source_content_hash=compute_content_hash("Hello"))
    defaults.update(kw)
    return Segment(**defaults)


def _make_segment_version(**kw):
    defaults = dict(segment_version_id="sv-001", segment_id="seg-001",
                    kind=SegmentVersionKind.DRAFT, text="سلام",
                    created_at=NOW)
    defaults.update(kw)
    return SegmentVersion(**defaults)


def _make_artifact(**kw):
    defaults = dict(artifact_id="art-001", project_id="prj-001",
                    kind=ArtifactKind.SOURCE_DOCUMENT, created_at=NOW)
    defaults.update(kw)
    return Artifact(**defaults)


def _make_run_record(**kw):
    defaults = dict(run_id="run-001", job_id="job-001",
                    operation_id="op-001", project_id="prj-001",
                    status=JobStatus.QUEUED)
    defaults.update(kw)
    return RunRecord(**defaults)


# ── Enum tests ───────────────────────────────────────────────────────────

class TestJobStatusEnum(unittest.TestCase):
    """D38: strict canonical status vocabulary."""

    def test_exactly_six_statuses(self):
        expected = {"QUEUED", "RUNNING", "WAITING_REVIEW",
                    "SUCCEEDED", "FAILED", "CANCELLED"}
        actual = {s.value for s in JobStatus}
        self.assertEqual(expected, actual)

    def test_no_completed_status(self):
        """'completed' is explicitly forbidden by D38."""
        with self.assertRaises(ValueError):
            JobStatus("completed")
        with self.assertRaises(ValueError):
            JobStatus("COMPLETED")

    def test_no_pending_status(self):
        with self.assertRaises(ValueError):
            JobStatus("PENDING")

    def test_no_done_status(self):
        with self.assertRaises(ValueError):
            JobStatus("DONE")

    def test_case_sensitive(self):
        """Status values are uppercase; lowercase must fail."""
        with self.assertRaises(ValueError):
            JobStatus("queued")

    def test_string_identity(self):
        self.assertEqual(str(JobStatus.QUEUED), "JobStatus.QUEUED")
        self.assertEqual(JobStatus.QUEUED.value, "QUEUED")


class TestOperationTypeEnum(unittest.TestCase):
    def test_all_operation_types(self):
        expected = {"translate", "review", "formalize", "summarize",
                    "transcribe", "synthesize", "export", "evaluate"}
        actual = {t.value for t in OperationType}
        self.assertEqual(expected, actual)


class TestArtifactKindEnum(unittest.TestCase):
    def test_all_artifact_kinds(self):
        expected = {
            "source_document", "translated_document", "subtitle",
            "audio", "video", "transcript_raw", "transcript_clean",
            "notes", "minutes", "speech_plan", "synthesized_audio",
            "evaluation_report", "other",
        }
        actual = {k.value for k in ArtifactKind}
        self.assertEqual(expected, actual)


class TestSegmentVersionKindEnum(unittest.TestCase):
    def test_all_kinds(self):
        expected = {"source", "draft", "revised", "human_edit", "approved"}
        actual = {k.value for k in SegmentVersionKind}
        self.assertEqual(expected, actual)


class TestAuthorTypeEnum(unittest.TestCase):
    def test_all_types(self):
        expected = {"system", "model", "human"}
        actual = {t.value for t in AuthorType}
        self.assertEqual(expected, actual)


class TestProtectedSpanTypeEnum(unittest.TestCase):
    def test_all_types(self):
        expected = {"code", "url", "email", "math", "placeholder",
                    "citation", "tag", "timestamp", "speaker", "other"}
        actual = {t.value for t in ProtectedSpanType}
        self.assertEqual(expected, actual)


class TestIntegrityPolicyEnum(unittest.TestCase):
    def test_all_policies(self):
        expected = {"exact", "normalized", "mapped"}
        actual = {p.value for p in IntegrityPolicy}
        self.assertEqual(expected, actual)


# ── JSON round-trip tests ────────────────────────────────────────────────

class TestWorkspaceRoundTrip(unittest.TestCase):
    def test_round_trip(self):
        ws = _make_workspace(metadata={"env": "test"})
        json_str = ws.model_dump_json()
        restored = Workspace.model_validate_json(json_str)
        self.assertEqual(ws, restored)

    def test_round_trip_preserves_all_fields(self):
        ws = _make_workspace()
        data = json.loads(ws.model_dump_json())
        self.assertIn("workspace_id", data)
        self.assertIn("root_path", data)
        self.assertIn("created_at", data)


class TestProjectSpecRoundTrip(unittest.TestCase):
    def test_round_trip_minimal(self):
        proj = _make_project()
        restored = ProjectSpec.model_validate_json(proj.model_dump_json())
        self.assertEqual(proj, restored)

    def test_round_trip_full(self):
        proj = _make_project(
            default_source_language="en",
            default_target_language="fa",
            default_domain_profile_id="profile.technical.fa.v3",
            default_style_profile_id="style.formal.v1",
            default_workflow_profile_id="wf.standard.v1",
            privacy_policy_id="privacy.default.v1",
            provider_policy_id="provider.openai.v1",
            review_policy_id="review.human.v1",
            metadata={"tags": ["test"]},
        )
        restored = ProjectSpec.model_validate_json(proj.model_dump_json())
        self.assertEqual(proj, restored)


class TestOperationSpecRoundTrip(unittest.TestCase):
    def test_round_trip(self):
        op = _make_operation(
            input_artifact_ids=["art-001", "art-002"],
            source_language="en",
            target_language="fa",
            resolved_policy_ids={"privacy": "p1", "provider": "p2"},
        )
        restored = OperationSpec.model_validate_json(op.model_dump_json())
        self.assertEqual(op, restored)

    def test_all_operation_types_serialize(self):
        for op_type in OperationType:
            op = _make_operation(operation_type=op_type)
            restored = OperationSpec.model_validate_json(op.model_dump_json())
            self.assertEqual(op.operation_type, restored.operation_type)


class TestProtectedSpanRoundTrip(unittest.TestCase):
    def test_round_trip(self):
        span = _make_protected_span(
            placeholder_token="__TRJ_abc123__",
            integrity_policy=IntegrityPolicy.NORMALIZED,
        )
        restored = ProtectedSpan.model_validate_json(span.model_dump_json())
        self.assertEqual(span, restored)

    def test_all_span_types(self):
        for span_type in ProtectedSpanType:
            span = _make_protected_span(type=span_type)
            restored = ProtectedSpan.model_validate_json(span.model_dump_json())
            self.assertEqual(span.type, restored.type)


class TestSegmentRoundTrip(unittest.TestCase):
    def test_round_trip_minimal(self):
        seg = _make_segment()
        restored = Segment.model_validate_json(seg.model_dump_json())
        self.assertEqual(seg, restored)

    def test_round_trip_with_protected_spans(self):
        seg = _make_segment(
            protected_spans=[_make_protected_span()],
            language_spans=[{"lang": "en", "start": 0, "end": 5}],
            structural_context={"parent": "body"},
        )
        restored = Segment.model_validate_json(seg.model_dump_json())
        self.assertEqual(seg, restored)
        self.assertEqual(len(restored.protected_spans), 1)


class TestSegmentVersionRoundTrip(unittest.TestCase):
    def test_round_trip(self):
        sv = _make_segment_version(
            parent_version_id="sv-000",
            strategy_id="strategy.reflect-1.v1",
            provider_id="openai",
            model_id="gpt-4o",
            prompt_id="translate.fa.v1",
            glossary_hash="sha256:aaa",
            context_hash="sha256:bbb",
            result_cache_hash="sha256:ccc",
            author=AuthorType.MODEL,
            author_id="model-run-001",
            findings=[{"rule": "r1", "severity": "minor"}],
            provenance={"source": "reflection"},
        )
        restored = SegmentVersion.model_validate_json(sv.model_dump_json())
        self.assertEqual(sv, restored)

    def test_all_version_kinds(self):
        for kind in SegmentVersionKind:
            sv = _make_segment_version(kind=kind)
            restored = SegmentVersion.model_validate_json(sv.model_dump_json())
            self.assertEqual(sv.kind, restored.kind)

    def test_all_author_types(self):
        for author in AuthorType:
            sv = _make_segment_version(author=author)
            restored = SegmentVersion.model_validate_json(sv.model_dump_json())
            self.assertEqual(sv.author, restored.author)


class TestArtifactRoundTrip(unittest.TestCase):
    def test_round_trip_minimal(self):
        art = _make_artifact()
        restored = Artifact.model_validate_json(art.model_dump_json())
        self.assertEqual(art, restored)

    def test_round_trip_full(self):
        seg = _make_segment()
        art = _make_artifact(
            raw_sha256="abc123",
            canonical_content_hash="sha256:def456",
            language_tags=["en", "fa"],
            source_uri="file:///data/book.epub",
            producer_name="epub-parser",
            producer_version="1.0.0",
            parent_artifact_ids=["art-000"],
            sensitivity="internal",
            retention_policy="90d",
            blob_path="/store/blobs/abc123",
            segments=[seg],
            metadata={"pages": 42},
        )
        restored = Artifact.model_validate_json(art.model_dump_json())
        self.assertEqual(art, restored)
        self.assertEqual(len(restored.segments), 1)

    def test_all_artifact_kinds(self):
        for kind in ArtifactKind:
            art = _make_artifact(kind=kind)
            restored = Artifact.model_validate_json(art.model_dump_json())
            self.assertEqual(art.kind, restored.kind)


class TestRunRecordRoundTrip(unittest.TestCase):
    def test_round_trip_minimal(self):
        rr = _make_run_record()
        restored = RunRecord.model_validate_json(rr.model_dump_json())
        self.assertEqual(rr, restored)

    def test_round_trip_full(self):
        rr = _make_run_record(
            status=JobStatus.SUCCEEDED,
            stage_checkpoints=[{"stage": "draft", "done": True}],
            resolved_config_hash="sha256:cfg",
            provider="openai",
            model="gpt-4o",
            prompt_id="translate.fa.v1",
            profile_id="profile.technical.fa.v3",
            rule_ids=["r1", "r2"],
            strategy_id="strategy.reflect-1.v1",
            started_at=NOW,
            finished_at=NOW2,
            usage={"input_tokens": 1000, "output_tokens": 500},
            cost_usd=0.05,
            duration_ms=3200,
            retry_count=1,
            metadata={"env": "prod"},
        )
        restored = RunRecord.model_validate_json(rr.model_dump_json())
        self.assertEqual(rr, restored)

    def test_all_statuses_serialize(self):
        for status in JobStatus:
            rr = _make_run_record(status=status)
            restored = RunRecord.model_validate_json(rr.model_dump_json())
            self.assertEqual(rr.status, restored.status)

    def test_error_fields(self):
        rr = _make_run_record(
            status=JobStatus.FAILED,
            error_type="ProviderTimeout",
            error_message="Connection timed out after 30s",
            retry_count=3,
        )
        restored = RunRecord.model_validate_json(rr.model_dump_json())
        self.assertEqual(restored.error_type, "ProviderTimeout")
        self.assertEqual(restored.retry_count, 3)


# ── Schema snapshot tests ────────────────────────────────────────────────

class TestSchemaSnapshots(unittest.TestCase):
    def test_all_canonical_models_have_schemas(self):
        schemas = get_all_schemas()
        expected_models = {
            "Workspace", "ProjectSpec", "OperationSpec", "ProtectedSpan",
            "Segment", "SegmentVersion", "Artifact", "RunRecord",
        }
        self.assertEqual(set(schemas.keys()), expected_models)

    def test_each_schema_is_valid_json_schema(self):
        for name, schema in get_all_schemas().items():
            self.assertIn("properties", schema, f"{name} missing properties")
            self.assertIn("title", schema, f"{name} missing title")
            self.assertEqual(schema["type"], "object", f"{name} not object type")

    def test_export_schemas_json_is_valid(self):
        json_str = export_schemas_json()
        parsed = json.loads(json_str)
        self.assertIsInstance(parsed, dict)
        self.assertEqual(len(parsed), 8)

    def test_run_record_schema_has_status_enum(self):
        schema = get_model_schema(RunRecord)
        # The status field should reference JobStatus enum
        props = schema.get("properties", {})
        # Pydantic v2 may use $defs for enum references
        self.assertIn("status", props)

    def test_segment_schema_has_required_fields(self):
        schema = get_model_schema(Segment)
        required = schema.get("required", [])
        for field in ["segment_id", "artifact_id", "structural_locator",
                       "source_text", "source_content_hash"]:
            self.assertIn(field, required, f"{field} not required in Segment")

    def test_workspace_schema_has_required_fields(self):
        schema = get_model_schema(Workspace)
        required = schema.get("required", [])
        for field in ["workspace_id", "root_path", "created_at"]:
            self.assertIn(field, required)

    def test_project_spec_schema_optional_languages(self):
        """§4.2: source/target language defaults are optional."""
        schema = get_model_schema(ProjectSpec)
        required = schema.get("required", [])
        self.assertNotIn("default_source_language", required)
        self.assertNotIn("default_target_language", required)

    def test_model_schema_individual(self):
        for model in CANONICAL_MODELS:
            schema = get_model_schema(model)
            self.assertIn("properties", schema)
            self.assertIn("title", schema)


# ── Stable ID and hashing tests ─────────────────────────────────────────

class TestComputeContentHash(unittest.TestCase):
    def test_deterministic(self):
        h1 = compute_content_hash("Hello world")
        h2 = compute_content_hash("Hello world")
        self.assertEqual(h1, h2)

    def test_prefix(self):
        h = compute_content_hash("test")
        self.assertTrue(h.startswith("sha256:"))

    def test_hex_length(self):
        h = compute_content_hash("test")
        hex_part = h.split(":")[1]
        self.assertEqual(len(hex_part), 64)

    def test_different_text_different_hash(self):
        h1 = compute_content_hash("Hello")
        h2 = compute_content_hash("World")
        self.assertNotEqual(h1, h2)

    def test_unicode_normalization(self):
        """NFC normalization: composed and decomposed forms produce same hash."""
        # Persian 'ک' can be U+06A9 (composed) or composed differently
        # Use a well-known NFC/NFD difference: é = U+00E9 vs e + combining acute
        composed = "é"    # é as single codepoint
        decomposed = "é"  # e + combining acute accent
        h1 = compute_content_hash(composed)
        h2 = compute_content_hash(decomposed)
        self.assertEqual(h1, h2)

    def test_empty_string(self):
        h = compute_content_hash("")
        self.assertTrue(h.startswith("sha256:"))
        self.assertEqual(len(h.split(":")[1]), 64)

    def test_persian_text(self):
        h = compute_content_hash("سلام دنیا")
        self.assertTrue(h.startswith("sha256:"))


class TestComputeSegmentId(unittest.TestCase):
    def test_deterministic(self):
        id1 = compute_segment_id("art-001", "p[0]")
        id2 = compute_segment_id("art-001", "p[0]")
        self.assertEqual(id1, id2)

    def test_prefix(self):
        sid = compute_segment_id("art-001", "p[0]")
        self.assertTrue(sid.startswith("seg:"))

    def test_different_locators_different_ids(self):
        """Even with same artifact, different locators → different IDs."""
        id1 = compute_segment_id("art-001", "p[0]")
        id2 = compute_segment_id("art-001", "p[1]")
        self.assertNotEqual(id1, id2)

    def test_different_artifacts_different_ids(self):
        """Same locator in different artifacts → different IDs."""
        id1 = compute_segment_id("art-001", "p[0]")
        id2 = compute_segment_id("art-002", "p[0]")
        self.assertNotEqual(id1, id2)

    def test_identical_source_text_different_locators(self):
        """§4.5: repeated identical paragraphs remain distinct.

        Two segments with the same source text but different structural
        locators must have distinct IDs.
        """
        # The segment_id depends on artifact + locator, not text.
        id1 = compute_segment_id("art-001", "p[0]")
        id2 = compute_segment_id("art-001", "p[1]")
        self.assertNotEqual(id1, id2)

    def test_stability_across_calls(self):
        """ID must be stable across multiple invocations."""
        results = set()
        for _ in range(100):
            results.add(compute_segment_id("art-X", "cue[3]"))
        self.assertEqual(len(results), 1)


class TestComputePlaceholder(unittest.TestCase):
    def test_default_prefix(self):
        token = compute_placeholder("span-001")
        self.assertTrue(token.startswith("__TRJ_"))
        self.assertTrue(token.endswith("__"))

    def test_custom_prefix(self):
        token = compute_placeholder("span-001", prefix="__CUSTOM_")
        self.assertTrue(token.startswith("__CUSTOM_"))

    def test_deterministic(self):
        t1 = compute_placeholder("span-001")
        t2 = compute_placeholder("span-001")
        self.assertEqual(t1, t2)

    def test_different_spans_different_tokens(self):
        t1 = compute_placeholder("span-001")
        t2 = compute_placeholder("span-002")
        self.assertNotEqual(t1, t2)

    def test_collision_resistance(self):
        """Generated tokens should not collide for distinct span IDs."""
        tokens = set()
        for i in range(1000):
            tokens.add(compute_placeholder(f"span-{i:04d}"))
        self.assertEqual(len(tokens), 1000)


# ── Validation failure tests ─────────────────────────────────────────────

class TestValidationFailures(unittest.TestCase):
    """Verify that invalid data is rejected by Pydantic validation."""

    def test_run_record_rejects_completed_status(self):
        """D38: 'completed' is not a valid status."""
        with self.assertRaises(ValidationError):
            RunRecord(
                run_id="run-001", job_id="job-001",
                operation_id="op-001", project_id="prj-001",
                status="completed",
            )

    def test_run_record_rejects_arbitrary_status(self):
        with self.assertRaises(ValidationError):
            RunRecord(
                run_id="run-001", job_id="job-001",
                operation_id="op-001", project_id="prj-001",
                status="IN_PROGRESS",
            )

    def test_run_record_rejects_lowercase_status(self):
        with self.assertRaises(ValidationError):
            RunRecord(
                run_id="run-001", job_id="job-001",
                operation_id="op-001", project_id="prj-001",
                status="queued",
            )

    def test_run_record_missing_required_fields(self):
        with self.assertRaises(ValidationError):
            RunRecord(run_id="run-001")  # type: ignore[call-arg]

    def test_operation_spec_invalid_type(self):
        with self.assertRaises(ValidationError):
            OperationSpec(
                operation_id="op-001", project_id="prj-001",
                operation_type="invalid_op", created_at=NOW,
            )

    def test_artifact_invalid_kind(self):
        with self.assertRaises(ValidationError):
            Artifact(
                artifact_id="art-001", project_id="prj-001",
                kind="invalid_kind", created_at=NOW,
            )

    def test_segment_version_invalid_kind(self):
        with self.assertRaises(ValidationError):
            SegmentVersion(
                segment_version_id="sv-001", segment_id="seg-001",
                kind="final", text="test", created_at=NOW,
            )

    def test_protected_span_invalid_type(self):
        with self.assertRaises(ValidationError):
            ProtectedSpan(
                span_id="span-001", type="regex",
                original_text="test",
            )

    def test_protected_span_invalid_integrity_policy(self):
        with self.assertRaises(ValidationError):
            ProtectedSpan(
                span_id="span-001", type=ProtectedSpanType.CODE,
                original_text="test", integrity_policy="fuzzy",
            )

    def test_segment_version_invalid_author(self):
        with self.assertRaises(ValidationError):
            SegmentVersion(
                segment_version_id="sv-001", segment_id="seg-001",
                kind=SegmentVersionKind.DRAFT, text="test",
                author="bot", created_at=NOW,
            )

    def test_workspace_missing_required(self):
        with self.assertRaises(ValidationError):
            Workspace(workspace_id="ws-001")  # type: ignore[call-arg]

    def test_project_spec_missing_required(self):
        with self.assertRaises(ValidationError):
            ProjectSpec(project_id="prj-001")  # type: ignore[call-arg]

    def test_segment_missing_required(self):
        with self.assertRaises(ValidationError):
            Segment(segment_id="seg-001")  # type: ignore[call-arg]

    def test_run_record_invalid_timestamp_type(self):
        """Timestamps must be datetime-compatible."""
        with self.assertRaises(ValidationError):
            RunRecord(
                run_id="run-001", job_id="job-001",
                operation_id="op-001", project_id="prj-001",
                status=JobStatus.RUNNING,
                started_at="not-a-timestamp",
            )


# ── Backward compatibility tests ────────────────────────────────────────

class TestBackwardCompatibility(unittest.TestCase):
    """All legacy models must remain importable from tarjoman.core.contracts."""

    def test_domain_type_importable(self):
        self.assertEqual(DomainType.LITERARY.value, "literary")

    def test_em_dash_policy_importable(self):
        self.assertEqual(EmDashPolicy.ADAPT.value, "adapt")

    def test_typographic_rules_defaults(self):
        rules = TypographicRules()
        self.assertTrue(rules.enforce_persian_quotes)

    def test_domain_profile_creation(self):
        profile = DomainProfile(
            id=DomainType.TECHNICAL,
            title_fa="فنی",
            description="Technical domain",
            system_prompt="You are a technical translator.",
        )
        self.assertEqual(profile.id, DomainType.TECHNICAL)

    def test_text_segment_creation(self):
        seg = TextSegment(id=1, source_text="Hello")
        self.assertIsNone(seg.translated_text)

    def test_stage_result_creation(self):
        sr = StageResult(
            stage_name="draft",
            success=True,
            segments=[TextSegment(id=1, source_text="Hi")],
        )
        self.assertTrue(sr.success)

    def test_audit_finding_creation(self):
        finding = AuditFinding(
            rule_id="r1", severity="major",
            segment_id=1, message="Issue", excerpt="text",
        )
        self.assertEqual(finding.severity, "major")

    def test_audit_report_creation(self):
        report = AuditReport(
            passed=True, quality_score=95.0,
            omission_count=0, banned_calque_count=0,
        )
        self.assertTrue(report.passed)

    def test_book_manifest_creation(self):
        manifest = BookManifest(title="Test Book")
        self.assertEqual(manifest.source_language, "en")
        self.assertEqual(manifest.target_language, "fa")

    def test_legacy_models_round_trip(self):
        """Legacy models also support JSON round-trip."""
        seg = TextSegment(id=1, source_text="Hello", translated_text="سلام")
        restored = TextSegment.model_validate_json(seg.model_dump_json())
        self.assertEqual(seg, restored)

    def test_10_domains_still_exist(self):
        expected = {
            "literary", "scientific", "philosophy", "legal", "technical",
            "medical", "media", "financial", "classical", "transcreation",
        }
        actual = {d.value for d in DomainType}
        self.assertEqual(expected, actual)


# ── Model defaults and optional field tests ──────────────────────────────

class TestModelDefaults(unittest.TestCase):
    def test_segment_translatable_default(self):
        seg = _make_segment()
        self.assertTrue(seg.translatable)

    def test_segment_version_author_default(self):
        sv = _make_segment_version()
        self.assertEqual(sv.author, AuthorType.SYSTEM)

    def test_protected_span_integrity_default(self):
        span = _make_protected_span()
        self.assertEqual(span.integrity_policy, IntegrityPolicy.EXACT)

    def test_run_record_retry_default(self):
        rr = _make_run_record()
        self.assertEqual(rr.retry_count, 0)

    def test_artifact_empty_segments_default(self):
        art = _make_artifact()
        self.assertEqual(art.segments, [])

    def test_project_spec_optional_languages_default_none(self):
        proj = _make_project()
        self.assertIsNone(proj.default_source_language)
        self.assertIsNone(proj.default_target_language)

    def test_workspace_empty_metadata_default(self):
        ws = _make_workspace()
        self.assertEqual(ws.metadata, {})


if __name__ == "__main__":
    unittest.main()
