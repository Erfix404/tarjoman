"""
Versioned Profile and Compliance Models for Tarjoman.

Architecture Zero references:
  - §8.4 Profile taxonomy: DomainProfile, StyleProfile, WorkflowProfile,
    ReviewPolicy, PrivacyPolicy, ProviderPolicy, LicensePolicy, Capability Bundle.
  - §8.4 High-risk domain defaults: legal and medical require human review
    for APPROVED status by default; project owner overrides must be recorded in provenance.
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

import json
import warnings
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tarjoman.core.contracts._hashing import compute_content_hash
from tarjoman.core.errors import LicensePolicyError, PolicyViolationError

# Filter Pydantic's warning about StyleProfile.register shadowing ABCMeta.register
warnings.filterwarnings(
    "ignore",
    message=r'Field name "register" in .* shadows an attribute',
    category=UserWarning,
)


# ---------------------------------------------------------------------------
# Base Versioned Entity
# ---------------------------------------------------------------------------

class VersionedEntity(BaseModel):
    """Base class for all versioned profile and policy entities (D13, D23)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = "1.0.0"

    def compute_checksum(self) -> str:
        """Compute canonical deterministic SHA-256 checksum of NFC-normalized JSON."""
        dumped = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return compute_content_hash(dumped)

    @property
    def checksum(self) -> str:
        """Convenience property returning the content-addressed SHA-256 checksum."""
        return self.compute_checksum()


# ---------------------------------------------------------------------------
# DomainProfile (§8.4, D12, D40)
# ---------------------------------------------------------------------------

class DomainProfile(VersionedEntity):
    """Subject matter domain profile (§8.4).

    Standard domains: general, literary, scientific, philosophy, legal,
    technical, medical, media, financial, classical, transcreation.
    High-risk domains (legal, medical) default to strict human review.
    """

    domain_id: str
    name: str
    title_fa: str
    description: str
    is_high_risk: bool = False
    default_review_policy_id: str = "standard_review"
    terminology_map: Dict[str, str] = Field(default_factory=dict)
    banned_calques: List[str] = Field(default_factory=list)
    few_shot_examples: List[Dict[str, str]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _apply_high_risk_policy_default(cls, data: Any) -> Any:
        """Ensure high-risk domains default to high_risk_strict review policy (§8.4)."""
        if isinstance(data, dict):
            is_high = data.get("is_high_risk", False)
            domain_id = data.get("domain_id", "")
            # Auto-flag known high-risk domains if not explicitly set
            if domain_id in ("legal", "medical") and "is_high_risk" not in data:
                is_high = True
                data["is_high_risk"] = True
            if is_high and "default_review_policy_id" not in data:
                data["default_review_policy_id"] = "high_risk_strict"
        return data

    @property
    def id(self) -> str:
        return self.domain_id


# ---------------------------------------------------------------------------
# StyleProfile (§8.4, D40)
# ---------------------------------------------------------------------------

class StyleProfile(VersionedEntity):
    """Language presentation style profile (§8.4).

    Registers: formal, neutral, conversational, literary.
    Digit policy: persian, english, preserve.
    """

    style_id: str
    name: str
    register: str
    audience: str
    digit_policy: Literal["persian", "english", "preserve"] = "persian"
    punctuation_policy: Dict[str, Any] = Field(default_factory=dict)
    loanword_policy: str = "minimize"
    terminology_guidance: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.style_id


# ---------------------------------------------------------------------------
# WorkflowProfile (§8.4, D40)
# ---------------------------------------------------------------------------

class WorkflowProfile(VersionedEntity):
    """Transformation shape workflow profile (§8.4).

    Standard shapes: translation, subtitle, meeting, lecture_notes,
    formal_minutes, audiobook, polish_only.
    """

    workflow_id: str
    name: str
    stages: List[str]
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.workflow_id


# ---------------------------------------------------------------------------
# ReviewPolicy (§8.4, D12, D40)
# ---------------------------------------------------------------------------

class ReviewPolicy(VersionedEntity):
    """Human-in-the-loop and automated review policy (§8.4, D12).

    High-risk domains (legal, medical) require human approval by default for
    APPROVED status. Automated approval without human review is prohibited
    unless an explicit owner override is recorded with provenance.
    """

    policy_id: str
    name: str
    requires_human_approval_for_approved_status: bool = False
    allow_auto_approval: bool = True
    high_risk_override_allowed: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.policy_id


# ---------------------------------------------------------------------------
# Compliance Policies (PrivacyPolicy, ProviderPolicy, LicensePolicy) (§8.4, D40)
# ---------------------------------------------------------------------------

class PrivacyPolicy(VersionedEntity):
    """Security and data retention boundaries (§8.4, D16)."""

    policy_id: str
    name: str = ""
    allow_external_apis: bool = False
    data_retention_days: int = 0
    pii_redaction_required: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.policy_id


class ProviderPolicy(VersionedEntity):
    """Model provider whitelist and quota policy (§8.4)."""

    policy_id: str
    name: str = ""
    allowed_providers: List[str] = Field(default_factory=list)
    max_cost_per_request: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.policy_id


class LicensePolicy(VersionedEntity):
    """License eligibility and commercial redistribution constraints (§8.4, D27)."""

    policy_id: str
    name: str = ""
    spdx_identifier: str
    commercial_use_allowed: bool = False
    attribution_required: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.policy_id


# ---------------------------------------------------------------------------
# Capability Bundle (§8.4, D40)
# ---------------------------------------------------------------------------

class CapabilityBundle(VersionedEntity):
    """Release and install capability grouping (core, asr, tts, server).

    Strict D40 Invariant: CapabilityBundle is an installation/release
    grouping and is NEVER a content profile.
    """

    bundle_id: str
    name: str
    components: List[str]
    is_content_profile: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("is_content_profile")
    @classmethod
    def _validate_never_content_profile(cls, v: bool) -> bool:
        if v is not False:
            raise ValueError(
                "CapabilityBundle is an installation/release grouping, NEVER a content profile (D40)."
            )
        return v

    @property
    def id(self) -> str:
        return self.bundle_id


# ---------------------------------------------------------------------------
# Manifest Models (ModelManifest, DataManifest, ServiceManifest) (D27, WORKPACKAGES FND-010)
# ---------------------------------------------------------------------------

class ModelManifest(VersionedEntity):
    """Machine-readable external model and weights manifest (D27)."""

    manifest_id: str
    name: str
    source_revision: str
    license: str
    license_status: str = "unknown"  # "approved" | "unapproved" | "unknown" | "prohibited"
    purpose: str
    redistribution_status: str = "unknown"  # "allowed" | "prohibited" | "attribution_required"
    is_commercial_eligible: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.manifest_id


class DataManifest(VersionedEntity):
    """Machine-readable dataset and corpus manifest (D27)."""

    manifest_id: str
    name: str
    source_revision: str
    license: str
    license_status: str = "unknown"
    purpose: str
    redistribution_status: str = "unknown"
    is_commercial_eligible: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.manifest_id


class ServiceManifest(VersionedEntity):
    """Machine-readable external service and adapter manifest (D27)."""

    manifest_id: str
    name: str
    source_revision: str
    license: str
    license_status: str = "unknown"
    purpose: str
    redistribution_status: str = "unknown"
    is_commercial_eligible: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.manifest_id


# ---------------------------------------------------------------------------
# License Evaluation & Fail-Closed Gate Primitives (WORKPACKAGES FND-010)
# ---------------------------------------------------------------------------

ManifestType = Union[ModelManifest, DataManifest, ServiceManifest]


def evaluate_manifest_license(
    manifest: ManifestType,
    policy: Optional[LicensePolicy] = None,
    commercial_context: bool = False,
) -> bool:
    """Evaluate whether an external manifest satisfies license policy.

    Fails closed (returns False) under any of:
      - Unknown, blank, or unapproved license status.
      - Non-commercial license in a commercial context.
      - Manifest incompatible with an explicit LicensePolicy.
    """
    status = (manifest.license_status or "unknown").strip().lower()
    if status in ("unknown", "unapproved", "prohibited", "incompatible", "unspecified", ""):
        return False

    if not manifest.license or manifest.license.strip().lower() in ("unknown", "none", ""):
        return False

    if commercial_context and not manifest.is_commercial_eligible:
        return False

    if policy is not None:
        if policy.commercial_use_allowed and not manifest.is_commercial_eligible:
            return False

    return True


def enforce_license_gate(
    manifest: ManifestType,
    policy: Optional[LicensePolicy] = None,
    commercial_context: bool = False,
) -> None:
    """Strict assertion gate for manifest license compliance.

    Raises LicensePolicyError if the manifest fails closed.
    """
    if not evaluate_manifest_license(
        manifest, policy=policy, commercial_context=commercial_context
    ):
        raise LicensePolicyError(
            f"License policy gate rejected manifest '{manifest.manifest_id}': "
            f"license='{manifest.license}', status='{manifest.license_status}', "
            f"commercial_eligible={manifest.is_commercial_eligible}. "
            f"(commercial_context={commercial_context})",
            details={
                "manifest_id": manifest.manifest_id,
                "license": manifest.license,
                "license_status": manifest.license_status,
                "commercial_eligible": manifest.is_commercial_eligible,
                "commercial_context": commercial_context,
            },
        )


# ---------------------------------------------------------------------------
# Provenance Reference Record (Architecture Zero §8.4, D23)
# ---------------------------------------------------------------------------

class ProvenanceReference(BaseModel):
    """Immutable audit record referencing a specific versioned entity and checksum."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_type: str
    entity_id: str
    version: str
    checksum: str
    override_applied: bool = False
    override_reason: Optional[str] = None
    override_actor: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


def create_provenance_reference(
    entity: Any,
    *,
    override_applied: bool = False,
    override_reason: Optional[str] = None,
    override_actor: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ProvenanceReference:
    """Create a tamper-evident ProvenanceReference for an entity.

    Architecture Zero §8.4:
      If a high-risk domain default is overridden, an explicit override_reason
      is mandatory and recorded in the audit trail.
    """
    entity_type = entity.__class__.__name__
    entity_id = getattr(entity, "id", None) or getattr(entity, "domain_id", "unknown")
    version = getattr(entity, "version", "1.0.0")

    if hasattr(entity, "compute_checksum"):
        checksum = entity.compute_checksum()
    elif hasattr(entity, "checksum"):
        checksum = entity.checksum
    else:
        checksum = compute_content_hash(str(entity))

    if override_applied and (not override_reason or not override_reason.strip()):
        raise PolicyViolationError(
            f"High-risk override on {entity_type} '{entity_id}' requires an explicit non-empty override_reason.",
            details={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "override_applied": override_applied,
            },
        )

    return ProvenanceReference(
        entity_type=entity_type,
        entity_id=entity_id,
        version=version,
        checksum=checksum,
        override_applied=override_applied,
        override_reason=override_reason,
        override_actor=override_actor,
        metadata=metadata or {},
    )
