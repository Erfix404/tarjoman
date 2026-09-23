"""
Model Harness provider ports and typed contracts.

Architecture Zero §6 — Model Harness:
  §6.1 — Required interface: ModelProvider protocol with generate/capabilities.
  §6.2 — Built-in provider order: FakeProvider, EchoProvider, CallableProvider.
  §6.3 — Fail-fast rule: no silent source echo in production.
  §6.4 — Harness responsibilities: capability validation, policy enforcement,
         structured-output validation, no secrets in logs.

Architecture Zero §22 — Dependency law:
  §22.1 — Core defines ports; infrastructure/adapters implement them.
  §22.2 — providers package owns LLM provider adapters; must not own
           business decisions or UI.

The canonical type definitions live in ``tarjoman.core.ports`` so that both
the application layer and the providers layer can import them without
violating architecture conformance boundaries.  This module re-exports
everything for convenience and backward compatibility — callers may import
from either location.

Work Package: TRN-001 — Provider port/capabilities.
"""
from tarjoman.core.ports import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    TaskType,
)

__all__ = [
    "TaskType",
    "ModelRequest",
    "ModelResponse",
    "ProviderCapabilities",
    "ModelProvider",
]
