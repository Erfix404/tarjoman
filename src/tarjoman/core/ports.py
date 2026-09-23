"""
Model Harness port contracts — stable protocol types for provider abstraction.

Architecture Zero §6 — Model Harness:
  §6.1 — Required interface: ModelProvider protocol with generate/capabilities.
  §6.4 — Harness responsibilities: capability validation, policy enforcement,
         structured-output validation, no secrets in logs.

Architecture Zero §22 — Dependency law:
  §22.1 — Core defines ports; infrastructure/adapters implement them.
  §22.2 — providers package owns LLM provider adapters and implements these ports.
           application depends on these port contracts, never on concrete providers.

This module is intentionally under ``tarjoman.core`` (outside the base-core
isolation prefixes) so that both ``application`` and ``providers`` can import
from it without violating the architecture conformance rules.

Work Package: TRN-001 — Provider port/capabilities.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Task Type Vocabulary (§6.1)
# ---------------------------------------------------------------------------

class TaskType(str, Enum):
    """Enumeration of model task types supported by the harness (§6.1)."""

    TRANSLATE = "translate"
    CRITIQUE = "critique"
    REVISE = "revise"
    SUMMARIZE = "summarize"
    EXTRACT_TERMS = "extract_terms"
    FORMALIZE = "formalize"


# ---------------------------------------------------------------------------
# Request / Response Contracts (§6.1)
# ---------------------------------------------------------------------------

class ModelRequest(BaseModel):
    """Typed request to a model provider (§6.1).

    Includes task type, language pair, messages, schema constraints,
    generation parameters, privacy classification, and metadata.
    """

    model_config = ConfigDict(extra="forbid")

    task_type: TaskType = TaskType.TRANSLATE
    source_language: str = "en"
    target_language: str = "fa"
    messages: List[Dict[str, str]] = Field(default_factory=list)
    required_output_schema: Optional[Dict[str, Any]] = None
    temperature: Optional[float] = None
    seed: Optional[int] = None
    timeout: Optional[float] = None
    privacy_class: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ModelResponse(BaseModel):
    """Typed response from a model provider (§6.1).

    Includes generated text, optional structured payload, provider/model
    identification, usage accounting, finish reason, latency, request
    correlation ID, and warnings.
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    structured_payload: Optional[Dict[str, Any]] = None
    provider: str
    model: str
    usage: Dict[str, Any] = Field(default_factory=dict)
    finish_reason: str = "stop"
    latency_ms: float = 0.0
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    warnings: List[str] = Field(default_factory=list)


class ProviderCapabilities(BaseModel):
    """Declared capabilities of a model provider (§6.1).

    Used by the harness for capability validation before a run (§6.4).
    """

    model_config = ConfigDict(extra="forbid")

    supports_streaming: bool = False
    supports_structured_output: bool = False
    supports_vision: bool = False
    max_context_window: int = 4096
    supported_tasks: List[TaskType] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Provider Port — Abstract Base (§6.1, §22.2)
# ---------------------------------------------------------------------------

class ModelProvider(ABC):
    """Abstract port for model providers (§6.1).

    Concrete adapters implement this in the providers package.
    Application services depend only on this interface, never on
    concrete provider implementations (§22.1 dependency rule).

    Interface:
        - ``generate(request)`` — async generation call.
        - ``capabilities()`` — declared provider capabilities.
        - ``generate_sync(request)`` — sync convenience wrapper.
        - ``name`` — stable provider identifier for policy checks.
        - ``is_local`` — whether the provider runs locally (privacy policy).
    """

    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Execute a generation request and return a typed response.

        Implementations must:
          - populate ``request_id`` and ``latency_ms`` on every response,
          - raise typed errors from ``tarjoman.core.errors`` on failure,
          - never log secrets or raw source content (§23.2, D16).
        """

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Return the provider's declared capabilities.

        The harness checks these before dispatching a request (§6.4).
        """

    @property
    def name(self) -> str:
        """Stable provider identifier for policy checks."""
        return self.__class__.__name__

    @property
    def is_local(self) -> bool:
        """Whether this provider runs locally (no external API calls).

        Used by privacy policy enforcement (§6.4, D16).
        Defaults to False; test/fake providers override to True.
        """
        return False

    def generate_sync(self, request: ModelRequest) -> ModelResponse:
        """Synchronous convenience wrapper around ``generate()``.

        Safely handles the event loop: uses the running loop if available
        (via ``asyncio.run`` in a new thread), or creates a new one.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self.generate(request))
                return future.result()
        else:
            return asyncio.run(self.generate(request))


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    "TaskType",
    "ModelRequest",
    "ModelResponse",
    "ProviderCapabilities",
    "ModelProvider",
]
