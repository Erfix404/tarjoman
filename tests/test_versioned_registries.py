"""
Unit and integration tests for Tarjoman Versioned Behavior and Compliance Registries.

Architecture Zero references:
  - §8.4 Profile taxonomy: DomainProfile, StyleProfile, WorkflowProfile,
    ReviewPolicy, PrivacyPolicy, ProviderPolicy, LicensePolicy, Capability Bundle.
  - §8.4 High-risk domain defaults: legal and medical require human review
    for APPROVED status by default.
  - §19 Locked Decisions:
      D11 — Separate registries with independent versions.
      D12 — High-risk domain review requirements.
      D13 — In-memory immutability once loaded.
      D23 — Prompts, profiles, rules, schemas, and strategy versions are immutable
            identifiers recorded in every run.
      D27 — Every external model/voice/dataset has a machine-readable ModelManifest
            and passes license gate before production use or redistribution.
      D40 — Distinct types for all profile and policy categories; CapabilityBundle
            is never a content profile.
"""
import unittest

from pydantic import ValidationError

from tarjoman.core.errors import LicensePolicyError, PolicyViolationError
from tarjoman.profiles import (
    CapabilityBundle,
    CapabilityBundleRegistry,
    ComplianceRegistry,
    DataManifest,
    DomainProfile,
    DomainProfileRegistry,
    LicensePolicy,
    ManifestRegistry,
    ModelManifest,
    PrivacyPolicy,
    ProviderPolicy,
    ProvenanceReference,
    RegistryError,
    ReviewPolicy,
    ReviewPolicyRegistry,
    ServiceManifest,
    StyleProfile,
    StyleProfileRegistry,
    VersionedEntity,
    VersionedRegistry,
    WorkflowProfile,
    WorkflowProfileRegistry,
    assert_high_risk_compliance,
    create_default_domain_registry,
    create_provenance_reference,
    enforce_license_gate,
    evaluate_manifest_license,
    get_capability_registry,
    get_compliance_registry,
    get_domain_registry,
    get_manifest_registry,
    get_review_policy_registry,
    get_style_registry,
    get_workflow_registry,
    reset_registries,
    resolve_domain_review_policy,
)


class TestRegistrySchemaValidation(unittest.TestCase):
    """Test schema validation, duplicate protection, versioning, and immutability (D13)."""

    def setUp(self) -> None:
        reset_registries()

    def test_invalid_profile_model_fails_validation_on_registration(self) -> None:
        """Invalid profile data must fail Pydantic validation on registration."""
        registry = VersionedRegistry[DomainProfile](name="TestDomainRegistry", item_type=DomainProfile)

        # Missing required fields
        with self.assertRaises(ValidationError):
            registry.register({"domain_id": "test_domain"})  # Missing name, title_fa, description

        # Invalid digit policy in StyleProfile
        style_reg = VersionedRegistry[StyleProfile](name="TestStyleRegistry", item_type=StyleProfile)
        with self.assertRaises(ValidationError):
            style_reg.register({
                "style_id": "bad_style",
                "name": "Bad",
                "register": "formal",
                "audience": "all",
                "digit_policy": "invalid_policy_name",  # Only 'persian', 'english', 'preserve' allowed
            })

    def test_duplicate_registration_same_version_fails(self) -> None:
        """Registering an entity with duplicate ID and same version must raise RegistryError."""
        registry = VersionedRegistry[DomainProfile](name="TestReg", item_type=DomainProfile)
        p1 = DomainProfile(
            domain_id="custom",
            name="Custom",
            title_fa="سفارشی",
            description="پروفایل سفارشی",
            version="1.0.0",
        )
        registry.register(p1)

        # Attempt to re-register same ID and same version
        p1_dup = DomainProfile(
            domain_id="custom",
            name="Custom Duplicate",
            title_fa="سفارشی",
            description="پروفایل تکراری",
            version="1.0.0",
        )
        with self.assertRaises(RegistryError) as ctx:
            registry.register(p1_dup)
        self.assertIn("already exists", str(ctx.exception))

    def test_registration_different_versions_succeeds_and_resolves_latest(self) -> None:
        """Different versions of the same ID succeed and resolve specifically or as latest."""
        registry = VersionedRegistry[DomainProfile](name="TestReg", item_type=DomainProfile)
        v1 = DomainProfile(
            domain_id="econ",
            name="Economy v1",
            title_fa="اقتصاد ۱",
            description="نسخه ۱",
            version="1.0.0",
        )
        v2 = DomainProfile(
            domain_id="econ",
            name="Economy v2",
            title_fa="اقتصاد ۲",
            description="نسخه ۲",
            version="1.1.0",
        )
        v3 = DomainProfile(
            domain_id="econ",
            name="Economy v3",
            title_fa="اقتصاد ۳",
            description="نسخه ۳",
            version="2.0.0",
        )

        registry.register(v1)
        registry.register(v3)  # Register v3 before v2 to test version ordering
        registry.register(v2)

        # Retrieve specific versions
        self.assertEqual(registry.get("econ", "1.0.0").name, "Economy v1")
        self.assertEqual(registry.get("econ", "1.1.0").name, "Economy v2")
        self.assertEqual(registry.get("econ", "2.0.0").name, "Economy v3")

        # Resolves latest (2.0.0) when version is omitted
        latest = registry.get("econ")
        self.assertEqual(latest.version, "2.0.0")
        self.assertEqual(latest.name, "Economy v3")

        # List all versions
        versions = registry.list_versions("econ")
        self.assertEqual(len(versions), 3)
        self.assertIn("1.0.0", versions)
        self.assertIn("1.1.0", versions)
        self.assertIn("2.0.0", versions)

    def test_immutability_after_freeze(self) -> None:
        """Registering on a frozen registry must raise RegistryError (D13)."""
        registry = VersionedRegistry[DomainProfile](name="FrozenRegistry", item_type=DomainProfile)
        p = DomainProfile(
            domain_id="test",
            name="Test",
            title_fa="آزمون",
            description="آزمون انجماد",
            version="1.0.0",
        )
        registry.register(p)
        self.assertFalse(registry.is_frozen)

        # Freeze the registry
        registry.freeze()
        self.assertTrue(registry.is_frozen)

        # Attempt to register on frozen registry
        p2 = DomainProfile(
            domain_id="test2",
            name="Test 2",
            title_fa="آزمون ۲",
            description="آزمون انجماد ۲",
            version="1.0.0",
        )
        with self.assertRaises(RegistryError) as ctx:
            registry.register(p2)
        self.assertIn("frozen", str(ctx.exception).lower())

    def test_model_in_memory_attribute_immutability(self) -> None:
        """Model instances are immutable (frozen) in memory (D13)."""
        p = DomainProfile(
            domain_id="test",
            name="Test",
            title_fa="آزمون",
            description="آزمون انجماد فیلد",
            version="1.0.0",
        )
        # Attempt to mutate attributes directly
        with self.assertRaises((ValidationError, TypeError)):
            p.name = "MutatedName"  # type: ignore[misc]

        with self.assertRaises((ValidationError, TypeError)):
            p.is_high_risk = True  # type: ignore[misc]


class TestProfileLookups(unittest.TestCase):
    """Test lookup across all profile taxonomies (§8.4)."""

    def setUp(self) -> None:
        reset_registries()

    def test_lookup_all_10_standard_domains_plus_general(self) -> None:
        """All 10 standard domains + general must be present and retrievable."""
        domain_reg = get_domain_registry()
        expected_domains = [
            "general",
            "literary",
            "scientific",
            "philosophy",
            "legal",
            "technical",
            "medical",
            "media",
            "financial",
            "classical",
            "transcreation",
        ]
        self.assertEqual(len(domain_reg), 11)

        for dom_id in expected_domains:
            self.assertTrue(domain_reg.contains(dom_id), f"Missing domain: {dom_id}")
            profile = domain_reg.get(dom_id)
            self.assertEqual(profile.domain_id, dom_id)
            self.assertTrue(len(profile.name) > 0)
            self.assertTrue(len(profile.title_fa) > 0)
            self.assertTrue(len(profile.description) > 0)
            self.assertTrue(len(profile.checksum) > 0)

    def test_lookup_style_profiles(self) -> None:
        """All 4 standard style profiles must be retrievable."""
        style_reg = get_style_registry()
        expected_styles = ["formal", "neutral", "conversational", "literary"]
        for style_id in expected_styles:
            self.assertTrue(style_reg.contains(style_id))
            style = style_reg.get(style_id)
            self.assertEqual(style.style_id, style_id)
            self.assertIn(style.digit_policy, ("persian", "english", "preserve"))

    def test_lookup_workflow_profiles(self) -> None:
        """All 7 standard workflow profiles must be retrievable."""
        wf_reg = get_workflow_registry()
        expected_workflows = [
            "translation",
            "subtitle",
            "meeting",
            "lecture_notes",
            "formal_minutes",
            "audiobook",
            "polish_only",
        ]
        for wf_id in expected_workflows:
            self.assertTrue(wf_reg.contains(wf_id))
            wf = wf_reg.get(wf_id)
            self.assertEqual(wf.workflow_id, wf_id)
            self.assertGreaterEqual(len(wf.stages), 3)

    def test_lookup_review_policies(self) -> None:
        """Review policies must be retrievable by ID."""
        rev_reg = get_review_policy_registry()
        self.assertTrue(rev_reg.contains("standard_review"))
        self.assertTrue(rev_reg.contains("high_risk_strict"))

    def test_lookup_compliance_and_capabilities(self) -> None:
        """Compliance and capability registries must be retrievable."""
        comp_reg = get_compliance_registry()
        self.assertTrue(comp_reg.contains("privacy_local_only"))
        self.assertTrue(comp_reg.contains("provider_standard"))
        self.assertTrue(comp_reg.contains("license_commercial_approved"))

        cap_reg = get_capability_registry()
        self.assertTrue(cap_reg.contains("core"))
        self.assertTrue(cap_reg.contains("asr"))
        self.assertTrue(cap_reg.contains("tts"))
        self.assertTrue(cap_reg.contains("server"))

    def test_unknown_id_and_version_raise_registry_error(self) -> None:
        """Looking up unknown ID or unknown version must raise RegistryError."""
        domain_reg = get_domain_registry()
        with self.assertRaises(RegistryError):
            domain_reg.get("nonexistent_domain_xyz")

        with self.assertRaises(RegistryError):
            domain_reg.get("legal", "99.99.99")

        self.assertFalse(domain_reg.contains("nonexistent_domain_xyz"))
        self.assertFalse(domain_reg.contains("legal", "99.99.99"))


class TestHighRiskDomainDefaultAssertions(unittest.TestCase):
    """Test high-risk domain defaults (legal and medical) per §8.4, D12."""

    def setUp(self) -> None:
        reset_registries()
        self.domain_reg = get_domain_registry()
        self.review_reg = get_review_policy_registry()

    def test_legal_domain_high_risk_defaults(self) -> None:
        """Legal domain must have is_high_risk=True and require human approval."""
        legal = self.domain_reg.get("legal")
        self.assertTrue(legal.is_high_risk)
        self.assertEqual(legal.default_review_policy_id, "high_risk_strict")

        policy = resolve_domain_review_policy(legal, review_registry=self.review_reg)
        self.assertEqual(policy.policy_id, "high_risk_strict")
        self.assertTrue(policy.requires_human_approval_for_approved_status)
        self.assertFalse(policy.allow_auto_approval)
        self.assertTrue(policy.high_risk_override_allowed)

    def test_medical_domain_high_risk_defaults(self) -> None:
        """Medical domain must have is_high_risk=True and require human approval."""
        medical = self.domain_reg.get("medical")
        self.assertTrue(medical.is_high_risk)
        self.assertEqual(medical.default_review_policy_id, "high_risk_strict")

        policy = resolve_domain_review_policy(medical, review_registry=self.review_reg)
        self.assertEqual(policy.policy_id, "high_risk_strict")
        self.assertTrue(policy.requires_human_approval_for_approved_status)
        self.assertFalse(policy.allow_auto_approval)
        self.assertTrue(policy.high_risk_override_allowed)

    def test_non_high_risk_domains_do_not_mandate_human_approval(self) -> None:
        """Non-high-risk domains (technical, general, etc.) allow automated approval."""
        standard_domains = [
            "general",
            "technical",
            "literary",
            "scientific",
            "philosophy",
            "media",
            "financial",
            "classical",
            "transcreation",
        ]
        for dom_id in standard_domains:
            prof = self.domain_reg.get(dom_id)
            self.assertFalse(prof.is_high_risk, f"Domain {dom_id} should not be high-risk")
            self.assertEqual(prof.default_review_policy_id, "standard_review")

            policy = resolve_domain_review_policy(prof, review_registry=self.review_reg)
            self.assertFalse(
                policy.requires_human_approval_for_approved_status,
                f"Domain {dom_id} should not mandate human approval",
            )
            self.assertTrue(policy.allow_auto_approval)

    def test_high_risk_override_behavior_and_provenance(self) -> None:
        """Project owner can override high-risk default, but must log provenance reason (§8.4)."""
        legal = self.domain_reg.get("legal")

        # 1. Standard compliance assertion without override
        self.assertTrue(assert_high_risk_compliance(legal))

        # 2. Override with valid reason succeeds
        self.assertTrue(
            assert_high_risk_compliance(
                legal,
                allow_override=True,
                override_reason="Expedited contract draft authorized by Lead Counsel",
            )
        )

        # 3. Override without reason fails closed with PolicyViolationError
        with self.assertRaises(PolicyViolationError) as ctx:
            assert_high_risk_compliance(
                legal,
                allow_override=True,
                override_reason="",  # Missing required reason
            )
        self.assertIn("override_reason", str(ctx.exception))

        # 4. ProvenanceReference creation with override records audit details
        provenance = create_provenance_reference(
            legal,
            override_applied=True,
            override_reason="Authorized batch internal review",
            override_actor="owner@workspace.local",
        )
        self.assertEqual(provenance.entity_id, "legal")
        self.assertTrue(provenance.override_applied)
        self.assertEqual(provenance.override_reason, "Authorized batch internal review")
        self.assertEqual(provenance.override_actor, "owner@workspace.local")
        self.assertTrue(provenance.checksum.startswith("sha256:"))

        # 5. ProvenanceReference creation with override_applied=True but no reason fails closed
        with self.assertRaises(PolicyViolationError):
            create_provenance_reference(
                legal,
                override_applied=True,
                override_reason=None,
            )


class TestD40ProfileTaxonomyDistinction(unittest.TestCase):
    """Test strict D40 separation of profile categories and capability bundles."""

    def test_capability_bundle_is_never_content_profile(self) -> None:
        """CapabilityBundle is an installation grouping, never a content profile (D40)."""
        bundle = CapabilityBundle(
            bundle_id="core",
            name="Core Engine",
            components=["ir", "normalizer"],
            version="1.0.0",
        )
        self.assertFalse(bundle.is_content_profile)

        # Attempting to declare CapabilityBundle as content profile must fail validation
        with self.assertRaises(ValidationError) as ctx:
            CapabilityBundle(
                bundle_id="core_invalid",
                name="Invalid",
                components=["ir"],
                is_content_profile=True,  # Violates D40 invariant
            )
        self.assertIn("NEVER a content profile", str(ctx.exception))

    def test_all_profile_types_are_distinct_classes(self) -> None:
        """All profile and policy categories are strictly distinct types (D40)."""
        types = [
            DomainProfile,
            StyleProfile,
            WorkflowProfile,
            ReviewPolicy,
            PrivacyPolicy,
            ProviderPolicy,
            LicensePolicy,
            CapabilityBundle,
            ModelManifest,
            DataManifest,
            ServiceManifest,
        ]
        # Assert none are subclasses of each other (except VersionedEntity base)
        for i, t1 in enumerate(types):
            for j, t2 in enumerate(types):
                if i != j:
                    self.assertFalse(
                        issubclass(t1, t2),
                        f"{t1.__name__} should not be a subclass of {t2.__name__}",
                    )


class TestLicenseGateAndManifestPolicies(unittest.TestCase):
    """Test machine-readable manifests and fail-closed license policies (D27, FND-010)."""

    def setUp(self) -> None:
        reset_registries()

    def test_unknown_license_status_fails_closed(self) -> None:
        """Unknown license status must fail closed under license policy (FND-010 acceptance)."""
        unknown_manifest = ModelManifest(
            manifest_id="unverified/llm",
            name="Unverified LLM",
            source_revision="commit_123",
            license="Unknown",
            license_status="unknown",
            purpose="translation",
            redistribution_status="unknown",
            is_commercial_eligible=False,
        )

        commercial_policy = LicensePolicy(
            policy_id="commercial_strict",
            name="Commercial Strict",
            spdx_identifier="Apache-2.0",
            commercial_use_allowed=True,
            attribution_required=True,
        )

        # evaluate_manifest_license returns False
        self.assertFalse(evaluate_manifest_license(unknown_manifest, policy=commercial_policy))
        self.assertFalse(evaluate_manifest_license(unknown_manifest, commercial_context=True))

        # enforce_license_gate raises LicensePolicyError
        with self.assertRaises(LicensePolicyError) as ctx:
            enforce_license_gate(unknown_manifest, policy=commercial_policy)
        self.assertIn("License policy gate rejected", str(ctx.exception))

    def test_research_only_manifest_fails_under_commercial_gate(self) -> None:
        """Non-commercial/research manifest passes research gate, fails commercial gate (D26, D27)."""
        tts_manifest = ModelManifest(
            manifest_id="nimaone/persian_tts",
            name="Pocket Farsi TTS v2",
            source_revision="v2.0",
            license="CC-BY-NC-4.0",
            license_status="approved",
            purpose="tts",
            redistribution_status="attribution_required",
            is_commercial_eligible=False,  # Research/non-commercial only per D26
        )

        research_policy = LicensePolicy(
            policy_id="research_eval",
            name="Research Policy",
            spdx_identifier="CC-BY-NC-4.0",
            commercial_use_allowed=False,
            attribution_required=True,
        )

        # Passes under research policy
        self.assertTrue(evaluate_manifest_license(tts_manifest, policy=research_policy))
        enforce_license_gate(tts_manifest, policy=research_policy)

        # Fails closed under commercial context
        self.assertFalse(evaluate_manifest_license(tts_manifest, commercial_context=True))
        with self.assertRaises(LicensePolicyError):
            enforce_license_gate(tts_manifest, commercial_context=True)

    def test_commercial_eligible_manifest_passes_commercial_gate(self) -> None:
        """Commercial-eligible manifest passes commercial policy gate."""
        approved_model = ModelManifest(
            manifest_id="approved/model",
            name="Approved Open Model",
            source_revision="sha256:abc1234",
            license="Apache-2.0",
            license_status="approved",
            purpose="translation",
            redistribution_status="allowed",
            is_commercial_eligible=True,
        )
        commercial_policy = LicensePolicy(
            policy_id="commercial_approved",
            spdx_identifier="Apache-2.0",
            commercial_use_allowed=True,
            attribution_required=True,
        )
        self.assertTrue(evaluate_manifest_license(approved_model, policy=commercial_policy))
        self.assertTrue(evaluate_manifest_license(approved_model, commercial_context=True))
        enforce_license_gate(approved_model, policy=commercial_policy, commercial_context=True)


class TestChecksumAndProvenance(unittest.TestCase):
    """Test deterministic checksum calculation and immutable provenance references (D23)."""

    def test_checksum_determinism_and_format(self) -> None:
        """Checksum must be deterministic, prefixed with sha256:, and vary with content."""
        p1 = DomainProfile(
            domain_id="test",
            name="Test",
            title_fa="آزمون",
            description="شرح آزمون",
            version="1.0.0",
        )
        p2 = DomainProfile(
            domain_id="test",
            name="Test",
            title_fa="آزمون",
            description="شرح آزمون",
            version="1.0.0",
        )
        p_diff = DomainProfile(
            domain_id="test",
            name="Test",
            title_fa="آزمون تغییر یافته",
            description="شرح آزمون",
            version="1.0.0",
        )

        # Checksum format
        self.assertTrue(p1.checksum.startswith("sha256:"))
        self.assertEqual(len(p1.checksum), 7 + 64)  # 'sha256:' + 64 hex chars

        # Determinism
        self.assertEqual(p1.checksum, p2.checksum)

        # Content sensitivity
        self.assertNotEqual(p1.checksum, p_diff.checksum)

    def test_provenance_reference_integrity(self) -> None:
        """ProvenanceReference captures immutable audit reference."""
        style = StyleProfile(
            style_id="formal",
            name="Formal Persian",
            register="formal",
            audience="general_adult",
            version="1.0.0",
        )
        prov = create_provenance_reference(style)
        self.assertEqual(prov.entity_type, "StyleProfile")
        self.assertEqual(prov.entity_id, "formal")
        self.assertEqual(prov.version, "1.0.0")
        self.assertEqual(prov.checksum, style.checksum)
        self.assertFalse(prov.override_applied)


if __name__ == "__main__":
    unittest.main()
