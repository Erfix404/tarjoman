"""
Tarjoman providers package — Model Harness adapters (Architecture Zero §6, §22).

Re-exports port contracts from ``tarjoman.core.ports`` and test/fake
provider implementations.  Application code should import port types
(``ModelProvider``, ``ModelRequest``, ``ModelResponse``, etc.) from
``tarjoman.core.ports`` to avoid layer violations; this re-export exists
for convenience in infrastructure and interface code.

Work Package: TRN-001 — Provider port/capabilities.
"""

from tarjoman.providers.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    TaskType,
)
from tarjoman.providers.fake import (
    CallableProvider,
    EchoProvider,
    FakeProvider,
)

__all__ = [
    # Port contracts (canonical definitions in tarjoman.core.ports)
    "ModelProvider",
    "ModelRequest",
    "ModelResponse",
    "ProviderCapabilities",
    "TaskType",
    # Test/Fake providers
    "FakeProvider",
    "EchoProvider",
    "CallableProvider",
]
