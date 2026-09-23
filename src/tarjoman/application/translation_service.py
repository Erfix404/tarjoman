"""
Application-layer translation service — use-case orchestration boundary.

Architecture Zero §22 — Dependency law:
  §22.1 — Application may import core, never concrete infrastructure.
  §22.2 — Application owns use cases and transaction boundaries.

Architecture Zero §6 — Model Harness:
  §6.4 — Harness responsibilities: capability validation before run,
         policy enforcement, no secrets in logs.

Architecture Zero §4.3 — OperationSpec & provenance:
  Every operation binds correlation/operation provenance context.

This module imports port contracts from ``tarjoman.core.ports`` (not from
``tarjoman.providers``) to satisfy the architecture conformance boundary.
Concrete provider instances are injected at construction time.

Work Package: TRN-001 — Provider port/capabilities.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from tarjoman.core.errors import (
    CapabilityUnavailableError,
    PolicyViolationError,
)
from tarjoman.core.logging import bind_provenance
from tarjoman.core.ports import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    TaskType,
)

# Avoid importing from tarjoman.profiles at module level — use lazy import
# to keep the application layer decoupled from the profiles infrastructure.
# PrivacyPolicy and ProviderPolicy are accepted as duck-typed objects with
# the required attributes.

logger = logging.getLogger("tarjoman.application.translation_service")


class TranslationService:
    """Application service coordinating translation use cases.

    Wraps a ``ModelProvider`` port with capability validation, policy
    enforcement, and provenance tracking.  All provider interactions
    go through this service boundary.

    Args:
        provider: Injected ``ModelProvider`` implementation.
        provider_policy: Optional policy restricting allowed providers.
            Must have ``allowed_providers: List[str]`` attribute.
        privacy_policy: Optional policy restricting external API usage.
            Must have ``allow_external_apis: bool`` attribute.
    """

    def __init__(
        self,
        provider: ModelProvider,
        *,
        provider_policy: Optional[Any] = None,
        privacy_policy: Optional[Any] = None,
    ) -> None:
        self._provider = provider
        self._provider_policy = provider_policy
        self._privacy_policy = privacy_policy

    # -- Policy & Capability Validation (§6.4) ----------------------------

    def _validate_policies(self) -> None:
        """Enforce provider and privacy policies before execution.

        Raises:
            PolicyViolationError: If the provider is not in the allowed list
                or if external APIs are disallowed and the provider is remote.
        """
        if self._provider_policy is not None:
            allowed = getattr(self._provider_policy, "allowed_providers", [])
            if allowed and self._provider.name not in allowed:
                raise PolicyViolationError(
                    f"Provider '{self._provider.name}' is not in the allowed "
                    f"providers list: {allowed}",
                    details={
                        "provider": self._provider.name,
                        "allowed_providers": list(allowed),
                    },
                )

        if self._privacy_policy is not None:
            allow_external = getattr(
                self._privacy_policy, "allow_external_apis", True
            )
            if not allow_external and not self._provider.is_local:
                raise PolicyViolationError(
                    f"Privacy policy forbids external APIs, but provider "
                    f"'{self._provider.name}' is not local",
                    details={
                        "provider": self._provider.name,
                        "is_local": self._provider.is_local,
                        "allow_external_apis": False,
                    },
                )

    def _validate_capabilities(self, request: ModelRequest) -> None:
        """Check that the provider supports the requested task type (§6.4).

        Raises:
            CapabilityUnavailableError: If the provider does not list the
                requested task type in its supported_tasks.
        """
        caps = self._provider.capabilities()
        if caps.supported_tasks and request.task_type not in caps.supported_tasks:
            raise CapabilityUnavailableError(
                f"Provider '{self._provider.name}' does not support task "
                f"'{request.task_type.value}'; supported: "
                f"{[t.value for t in caps.supported_tasks]}",
                details={
                    "provider": self._provider.name,
                    "requested_task": request.task_type.value,
                    "supported_tasks": [t.value for t in caps.supported_tasks],
                },
            )

    # -- Core Execution (§6.4, §4.3) --------------------------------------

    async def execute_task(self, request: ModelRequest) -> ModelResponse:
        """Execute an arbitrary model task with validation and provenance.

        Validates policies and capabilities, binds provenance context,
        delegates to the provider, and returns the typed response.

        Args:
            request: Typed model request.

        Returns:
            Typed model response with provenance fields populated.

        Raises:
            PolicyViolationError: Policy check failed.
            CapabilityUnavailableError: Provider lacks required capability.
            ProviderTransientError: Temporary upstream failure.
            ProviderPermanentError: Unrecoverable upstream failure.
        """
        self._validate_policies()
        self._validate_capabilities(request)

        operation_id = uuid.uuid4().hex
        correlation_id = request.metadata.get(
            "correlation_id", uuid.uuid4().hex
        )

        with bind_provenance(
            correlation_id=correlation_id,
            operation_id=operation_id,
            metadata={
                "task_type": request.task_type.value,
                "provider": self._provider.name,
                "source_language": request.source_language,
                "target_language": request.target_language,
            },
        ):
            logger.debug(
                "Executing task %s via provider %s",
                request.task_type.value,
                self._provider.name,
            )
            response = await self._provider.generate(request)
            logger.debug(
                "Task completed: request_id=%s latency_ms=%.1f",
                response.request_id,
                response.latency_ms,
            )
            return response

    def execute_task_sync(self, request: ModelRequest) -> ModelResponse:
        """Synchronous wrapper around ``execute_task()``.

        See ``ModelProvider.generate_sync()`` for event-loop handling.
        """
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self.execute_task(request))
                return future.result()
        else:
            return asyncio.run(self.execute_task(request))

    # -- Translation Convenience Methods -----------------------------------

    async def translate_text(
        self,
        text: str,
        source_lang: str = "en",
        target_lang: str = "fa",
        *,
        metadata: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
        privacy_class: Optional[str] = None,
    ) -> ModelResponse:
        """Translate a text string.

        Convenience method that builds a ``ModelRequest`` for translation
        and delegates to ``execute_task()``.

        Args:
            text: Source text to translate.
            source_lang: Source language code.
            target_lang: Target language code.
            metadata: Optional metadata dict.
            temperature: Optional generation temperature.
            timeout: Optional request timeout.
            privacy_class: Optional privacy classification.

        Returns:
            Typed model response containing the translation.
        """
        request = ModelRequest(
            task_type=TaskType.TRANSLATE,
            source_language=source_lang,
            target_language=target_lang,
            messages=[
                {"role": "user", "content": text},
            ],
            temperature=temperature,
            timeout=timeout,
            privacy_class=privacy_class,
            metadata=metadata or {},
        )
        return await self.execute_task(request)

    def translate_text_sync(
        self,
        text: str,
        source_lang: str = "en",
        target_lang: str = "fa",
        **kwargs: Any,
    ) -> ModelResponse:
        """Synchronous wrapper around ``translate_text()``."""
        import asyncio

        async def _run() -> ModelResponse:
            return await self.translate_text(
                text, source_lang, target_lang, **kwargs
            )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _run())
                return future.result()
        else:
            return asyncio.run(_run())


__all__ = [
    "TranslationService",
]
