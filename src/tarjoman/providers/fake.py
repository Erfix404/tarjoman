"""
Test and fake model providers for the Model Harness.

Architecture Zero §6.2 — Built-in provider order:
  - FakeProvider — configurable canned responses and failure injection.
  - EchoProvider — returns source text with test warnings; never production.
  - CallableProvider — accepts sync/async callable for custom mock injection.

Architecture Zero §6.3 — Fail-fast rule:
  EchoProvider always emits ``warnings=["TEST_ONLY: EchoProvider used"]``.

Work Package: TRN-001 — Provider port/capabilities.
"""
from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Sequence, Union

from tarjoman.core.errors import (
    ProviderPermanentError,
    ProviderRateLimitError,
    ProviderTransientError,
)
from tarjoman.core.ports import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    TaskType,
)


# ---------------------------------------------------------------------------
# FakeProvider (§6.2)
# ---------------------------------------------------------------------------

class FakeProvider(ModelProvider):
    """Fully configurable fake provider for testing.

    Features:
      - Canned response queue (FIFO) or dictionary keyed by task_type.
      - Failure injection: raise on Nth request or always.
      - Configurable latency simulation.
      - Call history tracking for assertions.

    All instances are local-only and never make network calls.
    """

    def __init__(
        self,
        *,
        responses: Optional[Sequence[Union[str, ModelResponse]]] = None,
        response_map: Optional[Dict[TaskType, Union[str, ModelResponse]]] = None,
        default_text: str = "fake translation output",
        structured_payloads: Optional[Sequence[Optional[Dict[str, Any]]]] = None,
        fail_on_call: Optional[int] = None,
        fail_always: bool = False,
        failure_error: Optional[Exception] = None,
        latency_ms: float = 0.0,
        model_name: str = "fake-model",
        supported_tasks: Optional[List[TaskType]] = None,
        supports_structured_output: bool = True,
        max_context_window: int = 8192,
    ) -> None:
        self._response_queue: Deque[Union[str, ModelResponse]] = deque(
            responses or []
        )
        self._response_map: Dict[TaskType, Union[str, ModelResponse]] = (
            dict(response_map) if response_map else {}
        )
        self._structured_queue: Deque[Optional[Dict[str, Any]]] = deque(
            structured_payloads or []
        )
        self._default_text = default_text
        self._fail_on_call = fail_on_call
        self._fail_always = fail_always
        self._failure_error = failure_error or ProviderTransientError(
            "Injected fake failure"
        )
        self._latency_ms = latency_ms
        self._model_name = model_name
        self._supported_tasks = supported_tasks or list(TaskType)
        self._supports_structured_output = supports_structured_output
        self._max_context_window = max_context_window

        # Call tracking
        self.call_count: int = 0
        self.recorded_requests: List[ModelRequest] = []

    @property
    def is_local(self) -> bool:
        return True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=False,
            supports_structured_output=self._supports_structured_output,
            supports_vision=False,
            max_context_window=self._max_context_window,
            supported_tasks=self._supported_tasks,
        )

    async def generate(self, request: ModelRequest) -> ModelResponse:
        start = time.monotonic()
        self.call_count += 1
        self.recorded_requests.append(request)

        # Simulate latency
        if self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000.0)

        # Failure injection
        if self._fail_always or (
            self._fail_on_call is not None
            and self.call_count == self._fail_on_call
        ):
            raise self._failure_error

        # Resolve response text
        text = self._default_text
        structured_payload: Optional[Dict[str, Any]] = None

        if self._response_queue:
            item = self._response_queue.popleft()
            if isinstance(item, ModelResponse):
                elapsed = (time.monotonic() - start) * 1000
                return item.model_copy(
                    update={
                        "latency_ms": elapsed,
                        "request_id": uuid.uuid4().hex,
                    }
                )
            text = item
        elif request.task_type in self._response_map:
            item = self._response_map[request.task_type]
            if isinstance(item, ModelResponse):
                elapsed = (time.monotonic() - start) * 1000
                return item.model_copy(
                    update={
                        "latency_ms": elapsed,
                        "request_id": uuid.uuid4().hex,
                    }
                )
            text = item

        if self._structured_queue:
            structured_payload = self._structured_queue.popleft()

        elapsed = (time.monotonic() - start) * 1000
        return ModelResponse(
            text=text,
            structured_payload=structured_payload,
            provider=self.name,
            model=self._model_name,
            usage={
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
                "cost_estimate": 0.0001,
            },
            finish_reason="stop",
            latency_ms=elapsed,
            request_id=uuid.uuid4().hex,
        )


# ---------------------------------------------------------------------------
# EchoProvider (§6.2, §6.3)
# ---------------------------------------------------------------------------

class EchoProvider(ModelProvider):
    """Test-only provider that echoes source text with a test prefix.

    Always emits ``warnings=["TEST_ONLY: EchoProvider used"]`` per §6.3
    fail-fast rule: this provider must never be silently used in production.
    """

    @property
    def is_local(self) -> bool:
        return True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=False,
            supports_structured_output=False,
            supports_vision=False,
            max_context_window=4096,
            supported_tasks=list(TaskType),
        )

    async def generate(self, request: ModelRequest) -> ModelResponse:
        start = time.monotonic()
        source_parts = []
        for msg in request.messages:
            content = msg.get("content", "")
            if content:
                source_parts.append(content)
        source_text = " ".join(source_parts) if source_parts else "(empty)"
        echo_text = f"[ECHO:{request.target_language}] {source_text}"

        elapsed = (time.monotonic() - start) * 1000
        return ModelResponse(
            text=echo_text,
            provider=self.name,
            model="echo",
            usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            finish_reason="stop",
            latency_ms=elapsed,
            request_id=uuid.uuid4().hex,
            warnings=["TEST_ONLY: EchoProvider used"],
        )


# ---------------------------------------------------------------------------
# CallableProvider (§6.2)
# ---------------------------------------------------------------------------

class CallableProvider(ModelProvider):
    """Provider backed by a user-supplied callable.

    Accepts a sync ``(ModelRequest) -> ModelResponse`` or async
    ``(ModelRequest) -> ModelResponse`` callable for custom mock injection
    in tests and integration scenarios.
    """

    def __init__(
        self,
        fn: Callable[..., Any],
        *,
        provider_name: str = "CallableProvider",
        is_local: bool = True,
        supported_tasks: Optional[List[TaskType]] = None,
    ) -> None:
        self._fn = fn
        self._provider_name = provider_name
        self._is_local_flag = is_local
        self._supported_tasks = supported_tasks or list(TaskType)

    @property
    def name(self) -> str:
        return self._provider_name

    @property
    def is_local(self) -> bool:
        return self._is_local_flag

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=False,
            supports_structured_output=True,
            supports_vision=False,
            max_context_window=4096,
            supported_tasks=self._supported_tasks,
        )

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if inspect.iscoroutinefunction(self._fn):
            return await self._fn(request)
        return self._fn(request)


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    "FakeProvider",
    "EchoProvider",
    "CallableProvider",
]
