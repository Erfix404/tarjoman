"""
Tarjoman Versioned Behavior and Compliance Registries.

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
from __future__ import annotations

# -- Profile and Compliance Models (Architecture Zero §8.4, D40) ----------------
from tarjoman.profiles.models import (
    CapabilityBundle,
    DataManifest,
    DomainProfile,
    LicensePolicy,
    ModelManifest,
    PrivacyPolicy,
    ProviderPolicy,
    ProvenanceReference,
    ReviewPolicy,
    ServiceManifest,
    StyleProfile,
    VersionedEntity,
    WorkflowProfile,
    create_provenance_reference,
    enforce_license_gate,
    evaluate_manifest_license,
)

# -- Registries, Engines, and Factory Singletons (D11, D12, D13) -----------------
from tarjoman.profiles.registry import (
    CapabilityBundleRegistry,
    ComplianceRegistry,
    DomainProfileRegistry,
    ManifestRegistry,
    RegistryError,
    ReviewPolicyRegistry,
    StyleProfileRegistry,
    VersionedRegistry,
    WorkflowProfileRegistry,
    assert_high_risk_compliance,
    create_default_capability_registry,
    create_default_compliance_registry,
    create_default_domain_registry,
    create_default_manifest_registry,
    create_default_review_policy_registry,
    create_default_style_registry,
    create_default_workflow_registry,
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

__all__ = [
    # Models (§8.4, D40)
    "VersionedEntity",
    "DomainProfile",
    "StyleProfile",
    "WorkflowProfile",
    "ReviewPolicy",
    "PrivacyPolicy",
    "ProviderPolicy",
    "LicensePolicy",
    "CapabilityBundle",
    "ModelManifest",
    "DataManifest",
    "ServiceManifest",
    "ProvenanceReference",
    "create_provenance_reference",
    "evaluate_manifest_license",
    "enforce_license_gate",
    # Registries & Errors (D11, D13)
    "RegistryError",
    "VersionedRegistry",
    "DomainProfileRegistry",
    "StyleProfileRegistry",
    "WorkflowProfileRegistry",
    "ReviewPolicyRegistry",
    "ComplianceRegistry",
    "CapabilityBundleRegistry",
    "ManifestRegistry",
    # Factories
    "create_default_domain_registry",
    "create_default_style_registry",
    "create_default_workflow_registry",
    "create_default_review_policy_registry",
    "create_default_compliance_registry",
    "create_default_capability_registry",
    "create_default_manifest_registry",
    # Singletons & Accessors
    "get_domain_registry",
    "get_style_registry",
    "get_workflow_registry",
    "get_review_policy_registry",
    "get_compliance_registry",
    "get_capability_registry",
    "get_manifest_registry",
    "reset_registries",
    # Compliance helpers
    "resolve_domain_review_policy",
    "assert_high_risk_compliance",
]
