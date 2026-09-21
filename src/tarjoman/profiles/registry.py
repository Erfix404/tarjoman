"""
Versioned Profile and Compliance Registries for Tarjoman.

Architecture Zero references:
  - §8.4 Profile taxonomy: DomainProfile, StyleProfile, WorkflowProfile,
    ReviewPolicy, PrivacyPolicy, ProviderPolicy, LicensePolicy, Capability Bundle.
  - §8.4 High-risk domain defaults: legal and medical require human review
    for APPROVED status by default; project owner overrides must be recorded in provenance.
  - §19 Locked Decisions:
      D11 — Separate registries with independent versions.
      D12 — High-risk domain review requirements.
      D13 — In-memory immutability once loaded.
      D40 — Distinct types for all profile and policy categories; CapabilityBundle
            is never a content profile.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import (
    Any,
    Dict,
    Generic,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from packaging.version import InvalidVersion, parse as parse_version
from pydantic import BaseModel, ValidationError

from tarjoman.core.errors import PolicyViolationError, TarjomanError
from tarjoman.profiles.models import (
    CapabilityBundle,
    DataManifest,
    DomainProfile,
    LicensePolicy,
    ModelManifest,
    PrivacyPolicy,
    ProviderPolicy,
    ReviewPolicy,
    ServiceManifest,
    StyleProfile,
    WorkflowProfile,
)

# Path to existing domain JSON definitions if present
DOMAINS_DATA_DIR = Path(__file__).parent.parent / "domains" / "registry"


# ---------------------------------------------------------------------------
# Registry Exception
# ---------------------------------------------------------------------------

class RegistryError(TarjomanError):
    """Exception raised for errors in versioned profile or compliance registries."""

    code: str = "REGISTRY_ERROR"
    exit_code: int = 2
    user_action: str = "check profile ID and version registration"


# ---------------------------------------------------------------------------
# Version Ordering Helper
# ---------------------------------------------------------------------------

def _parse_semver_fallback(v: str) -> Tuple[int, ...]:
    """Parse version string into tuple of ints with robust fallback."""
    parts: List[int] = []
    for segment in v.split("."):
        digits = "".join(c for c in segment if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) if parts else (0, 0, 0)


def _is_version_greater_or_equal(v1: str, v2: str) -> bool:
    """Return True if v1 >= v2 according to SemVer or fallback."""
    try:
        return parse_version(v1) >= parse_version(v2)
    except InvalidVersion:
        return _parse_semver_fallback(v1) >= _parse_semver_fallback(v2)


# ---------------------------------------------------------------------------
# Generic Versioned Registry (D11, D13, D40)
# ---------------------------------------------------------------------------

T = TypeVar("T")


class VersionedRegistry(Generic[T]):
    """Generic thread-safe, immutable in-memory registry for versioned entities.

    Invariants (Architecture Zero §8.4, D11, D13, D40):
      - Entities are indexed by (entity_id, version).
      - Multi-version retrieval and latest-version resolution.
      - Pydantic schema validation on registration.
      - Duplicate (entity_id, version) registration fails closed.
      - Once frozen (`freeze()`), mutations raise RegistryError.
    """

    def __init__(
        self,
        name: str = "VersionedRegistry",
        item_type: Optional[Type[T]] = None,
    ) -> None:
        self.name: str = name
        self.item_type: Optional[Type[T]] = item_type
        self._items: Dict[Tuple[str, str], T] = {}
        self._versions_by_id: Dict[str, List[str]] = {}
        self._latest_by_id: Dict[str, str] = {}
        self._frozen: bool = False

    def register(self, item: Union[T, Dict[str, Any]]) -> T:
        """Register a versioned entity with strict schema validation.

        Args:
            item: Instance of entity or dictionary to be validated.

        Returns:
            The validated and registered entity instance.

        Raises:
            RegistryError: If frozen, duplicate, missing ID, or type mismatch.
            pydantic.ValidationError: If schema validation fails.
        """
        if self._frozen:
            raise RegistryError(
                f"Registry '{self.name}' is frozen and immutable (D13). Cannot register new items.",
                details={"registry": self.name, "frozen": True},
            )

        # 1. Schema Validation
        validated: T
        if self.item_type is not None:
            if isinstance(item, dict):
                validated = self.item_type.model_validate(item)
            elif isinstance(item, self.item_type):
                # Ensure model was properly validated
                validated = item
            else:
                try:
                    validated = self.item_type.model_validate(item)
                except Exception as exc:
                    if isinstance(exc, ValidationError):
                        raise
                    raise RegistryError(
                        f"Registration failed: expected {self.item_type.__name__}, got {type(item).__name__}",
                        details={"expected_type": self.item_type.__name__, "actual_type": type(item).__name__},
                    ) from exc
        elif isinstance(item, BaseModel):
            validated = item  # type: ignore[assignment]
        else:
            raise RegistryError(
                f"Cannot register item of type {type(item).__name__} without schema validation.",
                details={"type": type(item).__name__},
            )

        # 2. Extract Entity ID
        entity_id = getattr(validated, "id", None)
        if not entity_id:
            for attr in (
                "domain_id",
                "style_id",
                "workflow_id",
                "policy_id",
                "bundle_id",
                "manifest_id",
            ):
                if hasattr(validated, attr):
                    val = getattr(validated, attr)
                    if isinstance(val, str) and val.strip():
                        entity_id = val.strip()
                        break

        if not entity_id or not isinstance(entity_id, str):
            raise RegistryError(
                f"Registered entity in '{self.name}' must have a valid non-empty string ID, got: {entity_id!r}",
                details={"registry": self.name, "entity_id": entity_id},
            )

        # 3. Extract Version
        version = str(getattr(validated, "version", "1.0.0")).strip()

        # 4. Duplicate Check
        key = (entity_id, version)
        if key in self._items:
            raise RegistryError(
                f"Duplicate registration: entity '{entity_id}' with version '{version}' already exists in registry '{self.name}'.",
                details={"registry": self.name, "entity_id": entity_id, "version": version},
            )

        # 5. Store and Index
        self._items[key] = validated
        if entity_id not in self._versions_by_id:
            self._versions_by_id[entity_id] = []
        self._versions_by_id[entity_id].append(version)

        # 6. Update Latest Version
        current_latest = self._latest_by_id.get(entity_id)
        if current_latest is None or _is_version_greater_or_equal(version, current_latest):
            self._latest_by_id[entity_id] = version

        return validated

    def get(self, entity_id: str, version: Optional[str] = None) -> T:
        """Retrieve a registered entity by ID and optional version.

        If version is omitted, returns the latest registered version.

        Args:
            entity_id: Target entity identifier.
            version: Optional explicit version string.

        Returns:
            The registered entity.

        Raises:
            RegistryError: If the entity or specified version is not found.
        """
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise RegistryError(
                f"Invalid entity_id: expected non-empty string, got {entity_id!r}",
                details={"registry": self.name, "entity_id": entity_id},
            )

        clean_id = entity_id.strip()

        if version is not None:
            clean_ver = version.strip()
            key = (clean_id, clean_ver)
            if key not in self._items:
                raise RegistryError(
                    f"Entity '{clean_id}' with version '{clean_ver}' not found in registry '{self.name}'.",
                    details={"registry": self.name, "entity_id": clean_id, "version": clean_ver},
                )
            return self._items[key]

        if clean_id not in self._latest_by_id:
            raise RegistryError(
                f"Entity '{clean_id}' not found in registry '{self.name}'.",
                details={"registry": self.name, "entity_id": clean_id},
            )

        latest_ver = self._latest_by_id[clean_id]
        return self._items[(clean_id, latest_ver)]

    def contains(self, entity_id: str, version: Optional[str] = None) -> bool:
        """Check whether an entity (or specific version) exists in the registry."""
        if not isinstance(entity_id, str):
            return False
        clean_id = entity_id.strip()
        if version is not None:
            return (clean_id, version.strip()) in self._items
        return clean_id in self._latest_by_id

    def list_all(self) -> List[T]:
        """Return latest version of all registered entities sorted by entity ID."""
        return [
            self._items[(eid, self._latest_by_id[eid])]
            for eid in sorted(self._latest_by_id.keys())
        ]

    def list_all_versions(self, entity_id: Optional[str] = None) -> List[T]:
        """Return all registered versions of an entity, or all entities if None."""
        if entity_id is not None:
            clean_id = entity_id.strip()
            versions = self._versions_by_id.get(clean_id, [])
            return [self._items[(clean_id, v)] for v in versions]
        return [self._items[k] for k in sorted(self._items.keys())]

    def list_versions(self, entity_id: str) -> List[str]:
        """Return list of all registered versions for an entity ID."""
        return list(self._versions_by_id.get(entity_id.strip(), []))

    def freeze(self) -> None:
        """Freeze the registry into an immutable state (D13)."""
        self._frozen = True

    @property
    def is_frozen(self) -> bool:
        """True if the registry has been frozen against runtime tampering."""
        return self._frozen

    def __len__(self) -> int:
        return len(self._latest_by_id)

    def __contains__(self, entity_id: str) -> bool:
        return self.contains(entity_id)

    def __getitem__(self, key: Union[str, Tuple[str, str]]) -> T:
        if isinstance(key, tuple):
            return self.get(key[0], key[1])
        return self.get(key)


# ---------------------------------------------------------------------------
# Specialized Typed Registries (D11, D40)
# ---------------------------------------------------------------------------

class DomainProfileRegistry(VersionedRegistry[DomainProfile]):
    """Registry for subject matter DomainProfiles (§8.4, D11, D12, D40)."""

    def __init__(self) -> None:
        super().__init__(name="DomainProfileRegistry", item_type=DomainProfile)

    def get_high_risk_domains(self) -> List[DomainProfile]:
        """Return all domains marked as high-risk (e.g. legal, medical)."""
        return [p for p in self.list_all() if p.is_high_risk]

    def is_high_risk(self, domain_id: str) -> bool:
        """Check whether a domain is designated as high-risk."""
        return self.get(domain_id).is_high_risk


class StyleProfileRegistry(VersionedRegistry[StyleProfile]):
    """Registry for language presentation StyleProfiles (§8.4, D11, D40)."""

    def __init__(self) -> None:
        super().__init__(name="StyleProfileRegistry", item_type=StyleProfile)


class WorkflowProfileRegistry(VersionedRegistry[WorkflowProfile]):
    """Registry for transformation shape WorkflowProfiles (§8.4, D11, D40)."""

    def __init__(self) -> None:
        super().__init__(name="WorkflowProfileRegistry", item_type=WorkflowProfile)


class ReviewPolicyRegistry(VersionedRegistry[ReviewPolicy]):
    """Registry for review and approval policies (§8.4, D11, D12, D40)."""

    def __init__(self) -> None:
        super().__init__(name="ReviewPolicyRegistry", item_type=ReviewPolicy)

    def get_strict_policy(self) -> ReviewPolicy:
        """Convenience accessor for high_risk_strict review policy."""
        return self.get("high_risk_strict")

    def get_standard_policy(self) -> ReviewPolicy:
        """Convenience accessor for standard_review policy."""
        return self.get("standard_review")


CompliancePolicyType = Union[PrivacyPolicy, ProviderPolicy, LicensePolicy]


class ComplianceRegistry(VersionedRegistry[CompliancePolicyType]):
    """Registry managing Privacy, Provider, and License policies (§8.4, D11, D40)."""

    def __init__(self) -> None:
        super().__init__(name="ComplianceRegistry", item_type=None)

    def register(self, item: Union[CompliancePolicyType, Dict[str, Any]]) -> CompliancePolicyType:
        """Register a privacy, provider, or license policy."""
        if self._frozen:
            raise RegistryError(
                f"Registry '{self.name}' is frozen and immutable (D13). Cannot register new items.",
                details={"registry": self.name, "frozen": True},
            )

        validated: CompliancePolicyType
        if isinstance(item, (PrivacyPolicy, ProviderPolicy, LicensePolicy)):
            validated = item
        elif isinstance(item, dict):
            # Discriminate by distinctive fields
            if "allow_external_apis" in item or "pii_redaction_required" in item:
                validated = PrivacyPolicy.model_validate(item)
            elif "allowed_providers" in item or "max_cost_per_request" in item:
                validated = ProviderPolicy.model_validate(item)
            elif "spdx_identifier" in item or "commercial_use_allowed" in item:
                validated = LicensePolicy.model_validate(item)
            else:
                raise RegistryError(
                    "Unable to determine compliance policy type from dict keys.",
                    details={"keys": list(item.keys())},
                )
        else:
            raise RegistryError(
                f"Expected PrivacyPolicy, ProviderPolicy, or LicensePolicy, got {type(item).__name__}",
                details={"type": type(item).__name__},
            )

        return super().register(validated)

    def register_privacy_policy(self, item: Union[PrivacyPolicy, Dict[str, Any]]) -> PrivacyPolicy:
        policy = PrivacyPolicy.model_validate(item) if isinstance(item, dict) else item
        super().register(policy)
        return policy

    def register_provider_policy(self, item: Union[ProviderPolicy, Dict[str, Any]]) -> ProviderPolicy:
        policy = ProviderPolicy.model_validate(item) if isinstance(item, dict) else item
        super().register(policy)
        return policy

    def register_license_policy(self, item: Union[LicensePolicy, Dict[str, Any]]) -> LicensePolicy:
        policy = LicensePolicy.model_validate(item) if isinstance(item, dict) else item
        super().register(policy)
        return policy

    def get_privacy_policy(self, policy_id: str, version: Optional[str] = None) -> PrivacyPolicy:
        item = self.get(policy_id, version)
        if not isinstance(item, PrivacyPolicy):
            raise RegistryError(
                f"Entity '{policy_id}' is of type {type(item).__name__}, not PrivacyPolicy.",
                details={"policy_id": policy_id, "actual_type": type(item).__name__},
            )
        return item

    def get_provider_policy(self, policy_id: str, version: Optional[str] = None) -> ProviderPolicy:
        item = self.get(policy_id, version)
        if not isinstance(item, ProviderPolicy):
            raise RegistryError(
                f"Entity '{policy_id}' is of type {type(item).__name__}, not ProviderPolicy.",
                details={"policy_id": policy_id, "actual_type": type(item).__name__},
            )
        return item

    def get_license_policy(self, policy_id: str, version: Optional[str] = None) -> LicensePolicy:
        item = self.get(policy_id, version)
        if not isinstance(item, LicensePolicy):
            raise RegistryError(
                f"Entity '{policy_id}' is of type {type(item).__name__}, not LicensePolicy.",
                details={"policy_id": policy_id, "actual_type": type(item).__name__},
            )
        return item


class CapabilityBundleRegistry(VersionedRegistry[CapabilityBundle]):
    """Registry for release/installation CapabilityBundles (§8.4, D11, D40)."""

    def __init__(self) -> None:
        super().__init__(name="CapabilityBundleRegistry", item_type=CapabilityBundle)


ManifestItemType = Union[ModelManifest, DataManifest, ServiceManifest]


class ManifestRegistry(VersionedRegistry[ManifestItemType]):
    """Registry for ModelManifest, DataManifest, and ServiceManifest entities (D27)."""

    def __init__(self) -> None:
        super().__init__(name="ManifestRegistry", item_type=None)

    def register(self, item: Union[ManifestItemType, Dict[str, Any]]) -> ManifestItemType:
        if self._frozen:
            raise RegistryError(
                f"Registry '{self.name}' is frozen and immutable (D13). Cannot register new items.",
                details={"registry": self.name, "frozen": True},
            )

        validated: ManifestItemType
        if isinstance(item, (ModelManifest, DataManifest, ServiceManifest)):
            validated = item
        elif isinstance(item, dict):
            # Default to ModelManifest if ambiguous
            manifest_type = item.get("manifest_type", "model")
            if manifest_type == "data":
                validated = DataManifest.model_validate(item)
            elif manifest_type == "service":
                validated = ServiceManifest.model_validate(item)
            else:
                validated = ModelManifest.model_validate(item)
        else:
            raise RegistryError(
                f"Expected ModelManifest, DataManifest, or ServiceManifest, got {type(item).__name__}",
                details={"type": type(item).__name__},
            )

        return super().register(validated)

    def register_model_manifest(self, item: Union[ModelManifest, Dict[str, Any]]) -> ModelManifest:
        manifest = ModelManifest.model_validate(item) if isinstance(item, dict) else item
        super().register(manifest)
        return manifest

    def register_data_manifest(self, item: Union[DataManifest, Dict[str, Any]]) -> DataManifest:
        manifest = DataManifest.model_validate(item) if isinstance(item, dict) else item
        super().register(manifest)
        return manifest

    def register_service_manifest(self, item: Union[ServiceManifest, Dict[str, Any]]) -> ServiceManifest:
        manifest = ServiceManifest.model_validate(item) if isinstance(item, dict) else item
        super().register(manifest)
        return manifest

    def get_model_manifest(self, manifest_id: str, version: Optional[str] = None) -> ModelManifest:
        item = self.get(manifest_id, version)
        if not isinstance(item, ModelManifest):
            raise RegistryError(
                f"Entity '{manifest_id}' is of type {type(item).__name__}, not ModelManifest.",
                details={"manifest_id": manifest_id, "actual_type": type(item).__name__},
            )
        return item

    def get_data_manifest(self, manifest_id: str, version: Optional[str] = None) -> DataManifest:
        item = self.get(manifest_id, version)
        if not isinstance(item, DataManifest):
            raise RegistryError(
                f"Entity '{manifest_id}' is of type {type(item).__name__}, not DataManifest.",
                details={"manifest_id": manifest_id, "actual_type": type(item).__name__},
            )
        return item

    def get_service_manifest(self, manifest_id: str, version: Optional[str] = None) -> ServiceManifest:
        item = self.get(manifest_id, version)
        if not isinstance(item, ServiceManifest):
            raise RegistryError(
                f"Entity '{manifest_id}' is of type {type(item).__name__}, not ServiceManifest.",
                details={"manifest_id": manifest_id, "actual_type": type(item).__name__},
            )
        return item


# ---------------------------------------------------------------------------
# Default Registry Factory Functions & Population (§8.4, D11, D12, D13)
# ---------------------------------------------------------------------------

def create_default_domain_registry(freeze: bool = True) -> DomainProfileRegistry:
    """Build and populate the default DomainProfileRegistry with all 11 domains.

    Includes the 10 standard domains plus general:
      - High-risk domains (legal, medical) are initialized with is_high_risk=True
        and default_review_policy_id='high_risk_strict'.
      - Standard domains (general, technical, literary, scientific, philosophy,
        media, financial, classical, transcreation) have is_high_risk=False.

    If freeze=True (default), locks the registry into an immutable state (D13).
    """
    registry = DomainProfileRegistry()

    # Standard domain definitions
    standard_domains = [
        ("general", "General", "عمومی", "متون عمومی، غیرتخصصی و روزمره"),
        ("literary", "Literary", "ادبی، رمان و داستان", "متون ادبی، رمان، داستان و نثر هنری"),
        ("scientific", "Scientific", "علمی، دانشگاهی و مقالات", "مقاله‌های علمی، پژوهشی و دانشگاهی داوری‌شده"),
        ("philosophy", "Philosophy", "فلسفه، اندیشه و علوم انسانی", "متون فلسفی، علوم انسانی، نظری و انتقادی"),
        ("legal", "Legal", "حقوقی، قراردادها و اسناد رسمی", "پروفایل متون حقوقی، معاهدات، قراردادهای تجاری و اسناد رسمی"),
        ("technical", "Technical", "فنی، نرم‌افزار و مهندسی", "مستندات مهندسی، برنامه‌نویسی، معماری سیستم و فناوری اطلاعات"),
        ("medical", "Medical", "پزشکی، بالینی و داروسازی", "پروفایل متون پزشکی، پرونده‌های بالینی، داروسازی و بهداشت"),
        ("media", "Media", "رسانه‌ای، اخبار و ژورنالیسم", "اخبار فوری، گزارش‌های خبری، مصاحبه‌ها و ژورنالیسم"),
        ("financial", "Financial", "اقتصاد، مالی و بازرگانی", "گزارش‌های مالی، صورت‌های سود و زیان، بورس و اقتصاد"),
        ("classical", "Classical", "متون کهن، تاریخی و متون مقدس", "متون کهن، رویدادنامه‌های تاریخی، متون مقدس و کلاسیک"),
        ("transcreation", "Transcreation", "بازآفرینی خلاق، برندینگ و تبلیغات", "شعارهای تبلیغاتی، متون بازاریابی، هویت برند و بازآفرینی خلاق"),
    ]

    for dom_id, name, title_fa, description in standard_domains:
        is_high_risk = dom_id in ("legal", "medical")
        review_policy = "high_risk_strict" if is_high_risk else "standard_review"

        terminology_map: Dict[str, str] = {}
        banned_calques: List[str] = []
        few_shot_examples: List[Dict[str, str]] = []
        metadata: Dict[str, Any] = {}

        # Enrich from domains/registry JSON file if available
        json_file = DOMAINS_DATA_DIR / f"{dom_id}.json"
        if json_file.exists():
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                terminology_map = data.get("terminology_map", {})
                banned_calques = data.get("banned_calques", [])
                few_shot_examples = data.get("few_shot_examples", [])
                metadata = {
                    "system_prompt": data.get("system_prompt", ""),
                    "typography": data.get("typography", {}),
                }
            except Exception:
                pass

        profile = DomainProfile(
            domain_id=dom_id,
            name=name,
            title_fa=title_fa,
            description=description,
            is_high_risk=is_high_risk,
            default_review_policy_id=review_policy,
            version="1.0.0",
            terminology_map=terminology_map,
            banned_calques=banned_calques,
            few_shot_examples=few_shot_examples,
            metadata=metadata,
        )
        registry.register(profile)

    if freeze:
        registry.freeze()

    return registry


def create_default_style_registry(freeze: bool = True) -> StyleProfileRegistry:
    """Build and populate the default StyleProfileRegistry."""
    registry = StyleProfileRegistry()

    styles = [
        StyleProfile(
            style_id="formal",
            name="Formal Persian",
            register="formal",
            audience="general_adult",
            digit_policy="persian",
            punctuation_policy={"enforce_quotes": True, "strict_zwnj": True},
            loanword_policy="minimize",
            terminology_guidance="Use formal Persian vocabulary and Academy-approved terminology.",
            version="1.0.0",
        ),
        StyleProfile(
            style_id="neutral",
            name="Neutral Persian",
            register="neutral",
            audience="general",
            digit_policy="persian",
            punctuation_policy={"enforce_quotes": True, "strict_zwnj": True},
            loanword_policy="standard",
            terminology_guidance=None,
            version="1.0.0",
        ),
        StyleProfile(
            style_id="conversational",
            name="Conversational Persian",
            register="conversational",
            audience="peers",
            digit_policy="persian",
            punctuation_policy={"strict_zwnj": True},
            loanword_policy="natural",
            terminology_guidance="Natural everyday spoken and colloquial phrasing.",
            version="1.0.0",
        ),
        StyleProfile(
            style_id="literary",
            name="Literary Persian",
            register="literary",
            audience="readers",
            digit_policy="persian",
            punctuation_policy={
                "em_dash": "eradicate",
                "enforce_quotes": True,
                "invert_dialogue_tags": True,
            },
            loanword_policy="minimize",
            terminology_guidance="Elevated literary diction, figurative expressions, and poetic rhythm.",
            version="1.0.0",
        ),
    ]

    for style in styles:
        registry.register(style)

    if freeze:
        registry.freeze()

    return registry


def create_default_workflow_registry(freeze: bool = True) -> WorkflowProfileRegistry:
    """Build and populate the default WorkflowProfileRegistry."""
    registry = WorkflowProfileRegistry()

    workflows = [
        WorkflowProfile(
            workflow_id="translation",
            name="Universal 5-Pass Translation",
            stages=["extract", "translate", "reflect", "audit", "compose"],
            version="1.0.0",
        ),
        WorkflowProfile(
            workflow_id="subtitle",
            name="Subtitle Translation & Timing",
            stages=["parse_srt", "translate", "time_align", "audit", "export_srt"],
            version="1.0.0",
        ),
        WorkflowProfile(
            workflow_id="meeting",
            name="Meeting Transcription & Minutes",
            stages=["ingest_audio", "asr", "diarize", "clean_persian", "summarize", "formal_minutes"],
            version="1.0.0",
        ),
        WorkflowProfile(
            workflow_id="lecture_notes",
            name="Lecture Notes Generation",
            stages=["ingest_audio", "asr", "clean_persian", "structure_notes", "compose"],
            version="1.0.0",
        ),
        WorkflowProfile(
            workflow_id="formal_minutes",
            name="Formal Administrative Minutes",
            stages=["ingest_notes", "clean_persian", "formalize", "action_items", "compose"],
            version="1.0.0",
        ),
        WorkflowProfile(
            workflow_id="audiobook",
            name="Audiobook Narration Pipeline",
            stages=["parse_book", "segment_dialogue", "prosody_tag", "tts_synthesize", "package_audio"],
            version="1.0.0",
        ),
        WorkflowProfile(
            workflow_id="polish_only",
            name="Persian Polish & Audit Only",
            stages=["clean_persian", "anti_calque", "grammar_audit", "compose"],
            version="1.0.0",
        ),
    ]

    for wf in workflows:
        registry.register(wf)

    if freeze:
        registry.freeze()

    return registry


def create_default_review_policy_registry(freeze: bool = True) -> ReviewPolicyRegistry:
    """Build and populate default ReviewPolicyRegistry (§8.4, D12)."""
    registry = ReviewPolicyRegistry()

    policies = [
        ReviewPolicy(
            policy_id="standard_review",
            name="Standard Review Policy",
            requires_human_approval_for_approved_status=False,
            allow_auto_approval=True,
            high_risk_override_allowed=True,
            version="1.0.0",
            metadata={"description": "Standard review allowing automated approval for non-high-risk domains."},
        ),
        ReviewPolicy(
            policy_id="high_risk_strict",
            name="High-Risk Strict Review Policy",
            requires_human_approval_for_approved_status=True,
            allow_auto_approval=False,
            high_risk_override_allowed=True,
            version="1.0.0",
            metadata={
                "description": "Strict human review required for APPROVED status per Architecture Zero §8.4 and D12."
            },
        ),
    ]

    for pol in policies:
        registry.register(pol)

    if freeze:
        registry.freeze()

    return registry


def create_default_compliance_registry(freeze: bool = True) -> ComplianceRegistry:
    """Build and populate default ComplianceRegistry."""
    registry = ComplianceRegistry()

    privacy_policies = [
        PrivacyPolicy(
            policy_id="privacy_local_only",
            name="Local Only Privacy Policy",
            allow_external_apis=False,
            data_retention_days=0,
            pii_redaction_required=True,
            version="1.0.0",
        ),
        PrivacyPolicy(
            policy_id="privacy_external_standard",
            name="External Standard Privacy Policy",
            allow_external_apis=True,
            data_retention_days=30,
            pii_redaction_required=True,
            version="1.0.0",
        ),
    ]

    provider_policies = [
        ProviderPolicy(
            policy_id="provider_standard",
            name="Standard Provider Policy",
            allowed_providers=["local_mock", "openai", "anthropic"],
            max_cost_per_request=1.0,
            version="1.0.0",
        ),
        ProviderPolicy(
            policy_id="provider_local_strict",
            name="Local Strict Provider Policy",
            allowed_providers=["local_mock", "ollama", "vllm"],
            max_cost_per_request=0.0,
            version="1.0.0",
        ),
    ]

    license_policies = [
        LicensePolicy(
            policy_id="license_commercial_approved",
            name="Commercial Approved Policy",
            spdx_identifier="Apache-2.0",
            commercial_use_allowed=True,
            attribution_required=True,
            version="1.0.0",
        ),
        LicensePolicy(
            policy_id="license_research_only",
            name="Research Only Policy",
            spdx_identifier="CC-BY-NC-4.0",
            commercial_use_allowed=False,
            attribution_required=True,
            version="1.0.0",
        ),
    ]

    for pol in privacy_policies:
        registry.register_privacy_policy(pol)
    for pol in provider_policies:
        registry.register_provider_policy(pol)
    for pol in license_policies:
        registry.register_license_policy(pol)

    if freeze:
        registry.freeze()

    return registry


def create_default_capability_registry(freeze: bool = True) -> CapabilityBundleRegistry:
    """Build and populate default CapabilityBundleRegistry (D40)."""
    registry = CapabilityBundleRegistry()

    bundles = [
        CapabilityBundle(
            bundle_id="core",
            name="Core Universal Engine",
            components=["ir", "normalizer", "calque_detector", "pipeline", "sqlite_tm"],
            is_content_profile=False,
            version="1.0.0",
        ),
        CapabilityBundle(
            bundle_id="asr",
            name="Audio Speech Recognition",
            components=["whisper", "audio_preprocessor"],
            is_content_profile=False,
            version="1.0.0",
        ),
        CapabilityBundle(
            bundle_id="tts",
            name="Text to Speech Narration",
            components=["farsi_tts", "audio_synthesizer"],
            is_content_profile=False,
            version="1.0.0",
        ),
        CapabilityBundle(
            bundle_id="server",
            name="FastAPI & MCP Interfaces",
            components=["fastapi_app", "mcp_server", "task_queue"],
            is_content_profile=False,
            version="1.0.0",
        ),
    ]

    for b in bundles:
        registry.register(b)

    if freeze:
        registry.freeze()

    return registry


def create_default_manifest_registry(freeze: bool = True) -> ManifestRegistry:
    """Build and populate default ManifestRegistry (D27)."""
    registry = ManifestRegistry()

    manifests = [
        ModelManifest(
            manifest_id="nimaone/persian_tts",
            name="Pocket Farsi TTS v2",
            source_revision="v2.0",
            license="CC-BY-NC-4.0",
            license_status="approved",
            purpose="tts",
            redistribution_status="attribution_required",
            is_commercial_eligible=False,
            version="1.0.0",
            metadata={"notes": "Research/non-commercial default per D26"},
        ),
        ModelManifest(
            manifest_id="unverified/persian_llm",
            name="Unverified LLM Model",
            source_revision="unknown",
            license="unknown",
            license_status="unknown",
            purpose="translation",
            redistribution_status="unknown",
            is_commercial_eligible=False,
            version="1.0.0",
        ),
    ]

    for m in manifests:
        registry.register_model_manifest(m)

    if freeze:
        registry.freeze()

    return registry


# ---------------------------------------------------------------------------
# Global Singletons & Convenience Accessors
# ---------------------------------------------------------------------------

_DOMAIN_REGISTRY: Optional[DomainProfileRegistry] = None
_STYLE_REGISTRY: Optional[StyleProfileRegistry] = None
_WORKFLOW_REGISTRY: Optional[WorkflowProfileRegistry] = None
_REVIEW_POLICY_REGISTRY: Optional[ReviewPolicyRegistry] = None
_COMPLIANCE_REGISTRY: Optional[ComplianceRegistry] = None
_CAPABILITY_REGISTRY: Optional[CapabilityBundleRegistry] = None
_MANIFEST_REGISTRY: Optional[ManifestRegistry] = None


def get_domain_registry() -> DomainProfileRegistry:
    """Get the immutable singleton DomainProfileRegistry."""
    global _DOMAIN_REGISTRY
    if _DOMAIN_REGISTRY is None:
        _DOMAIN_REGISTRY = create_default_domain_registry(freeze=True)
    return _DOMAIN_REGISTRY


def get_style_registry() -> StyleProfileRegistry:
    """Get the immutable singleton StyleProfileRegistry."""
    global _STYLE_REGISTRY
    if _STYLE_REGISTRY is None:
        _STYLE_REGISTRY = create_default_style_registry(freeze=True)
    return _STYLE_REGISTRY


def get_workflow_registry() -> WorkflowProfileRegistry:
    """Get the immutable singleton WorkflowProfileRegistry."""
    global _WORKFLOW_REGISTRY
    if _WORKFLOW_REGISTRY is None:
        _WORKFLOW_REGISTRY = create_default_workflow_registry(freeze=True)
    return _WORKFLOW_REGISTRY


def get_review_policy_registry() -> ReviewPolicyRegistry:
    """Get the immutable singleton ReviewPolicyRegistry."""
    global _REVIEW_POLICY_REGISTRY
    if _REVIEW_POLICY_REGISTRY is None:
        _REVIEW_POLICY_REGISTRY = create_default_review_policy_registry(freeze=True)
    return _REVIEW_POLICY_REGISTRY


def get_compliance_registry() -> ComplianceRegistry:
    """Get the immutable singleton ComplianceRegistry."""
    global _COMPLIANCE_REGISTRY
    if _COMPLIANCE_REGISTRY is None:
        _COMPLIANCE_REGISTRY = create_default_compliance_registry(freeze=True)
    return _COMPLIANCE_REGISTRY


def get_capability_registry() -> CapabilityBundleRegistry:
    """Get the immutable singleton CapabilityBundleRegistry."""
    global _CAPABILITY_REGISTRY
    if _CAPABILITY_REGISTRY is None:
        _CAPABILITY_REGISTRY = create_default_capability_registry(freeze=True)
    return _CAPABILITY_REGISTRY


def get_manifest_registry() -> ManifestRegistry:
    """Get the immutable singleton ManifestRegistry."""
    global _MANIFEST_REGISTRY
    if _MANIFEST_REGISTRY is None:
        _MANIFEST_REGISTRY = create_default_manifest_registry(freeze=True)
    return _MANIFEST_REGISTRY


def reset_registries() -> None:
    """Reset all cached global registry singletons. Useful for testing."""
    global _DOMAIN_REGISTRY, _STYLE_REGISTRY, _WORKFLOW_REGISTRY
    global _REVIEW_POLICY_REGISTRY, _COMPLIANCE_REGISTRY
    global _CAPABILITY_REGISTRY, _MANIFEST_REGISTRY

    _DOMAIN_REGISTRY = None
    _STYLE_REGISTRY = None
    _WORKFLOW_REGISTRY = None
    _REVIEW_POLICY_REGISTRY = None
    _COMPLIANCE_REGISTRY = None
    _CAPABILITY_REGISTRY = None
    _MANIFEST_REGISTRY = None


# ---------------------------------------------------------------------------
# High-Risk Domain Compliance Resolver & Assertion Helpers (§8.4, D12)
# ---------------------------------------------------------------------------

def resolve_domain_review_policy(
    domain: Union[str, DomainProfile],
    *,
    domain_registry: Optional[DomainProfileRegistry] = None,
    review_registry: Optional[ReviewPolicyRegistry] = None,
) -> ReviewPolicy:
    """Resolve the authoritative ReviewPolicy for a given domain profile or ID.

    Architecture Zero §8.4 & D12:
      High-risk domains (legal, medical) resolve by default to a policy requiring
      human review for APPROVED status.
    """
    dom_reg = domain_registry or get_domain_registry()
    rev_reg = review_registry or get_review_policy_registry()

    domain_profile = domain if isinstance(domain, DomainProfile) else dom_reg.get(domain)
    policy_id = domain_profile.default_review_policy_id
    return rev_reg.get(policy_id)


def assert_high_risk_compliance(
    domain: Union[str, DomainProfile],
    *,
    domain_registry: Optional[DomainProfileRegistry] = None,
    review_registry: Optional[ReviewPolicyRegistry] = None,
    allow_override: bool = False,
    override_reason: Optional[str] = None,
) -> bool:
    """Assert high-risk domain review policy compliance (§8.4, D12).

    Returns True if compliance is met.
    Raises PolicyViolationError if an attempt is made to approve a high-risk
    output automatically without human review or without explicit override reason.
    """
    dom_reg = domain_registry or get_domain_registry()
    domain_profile = domain if isinstance(domain, DomainProfile) else dom_reg.get(domain)

    if not domain_profile.is_high_risk:
        return True

    policy = resolve_domain_review_policy(
        domain_profile,
        domain_registry=domain_registry,
        review_registry=review_registry,
    )

    if policy.requires_human_approval_for_approved_status and not allow_override:
        # Strict human approval is mandated by policy
        return True

    if allow_override:
        if not policy.high_risk_override_allowed:
            raise PolicyViolationError(
                f"High-risk override is prohibited by review policy '{policy.policy_id}'.",
                details={"domain": domain_profile.domain_id, "policy": policy.policy_id},
            )
        if not override_reason or not override_reason.strip():
            raise PolicyViolationError(
                f"High-risk domain '{domain_profile.domain_id}' override requires an explicit non-empty override_reason for audit provenance (§8.4).",
                details={"domain": domain_profile.domain_id, "policy": policy.policy_id},
            )
        return True

    return False
