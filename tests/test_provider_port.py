"""
Tests for Work Package TRN-001: Provider port/capabilities.

Acceptance criteria (WORKPACKAGES.json):
  1. "component is reachable through application services"
  2. "fake-provider tests cover success and failure"
  3. "provenance and policy behavior are asserted"

Architecture Zero references:
  §6.1  — ModelProvider protocol, ModelRequest, ModelResponse, ProviderCapabilities.
  §6.2  — FakeProvider, EchoProvider, CallableProvider.
  §6.3  — Fail-fast rule: EchoProvider must warn.
  §6.4  — Capability validation, policy enforcement, provenance.
  §22.1 — Dependency rule: application imports core ports, not concrete providers.
  §22.2 — Package ownership: providers must not own business decisions.
"""
from __future__ import annotations

import asyncio
import unittest
import uuid
from typing import Any, Dict, List, Optional
from unittest import mock

from tarjoman.application import TranslationService
from tarjoman.application.translation_service import TranslationService as TS_direct
from tarjoman.core.errors import (
    CapabilityUnavailableError,
    PolicyViolationError,
    ProviderPermanentError,
    ProviderRateLimitError,
    ProviderTransientError,
)
from tarjoman.core.logging import get_provenance_context
from tarjoman.core.ports import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    TaskType,
)
from tarjoman.providers import (
    CallableProvider,
    EchoProvider,
    FakeProvider,
)
from tarjoman.providers.base import (
    ModelProvider as BaseModelProvider,
    ModelRequest as BaseModelRequest,
    ModelResponse as BaseModelResponse,
    ProviderCapabilities as BaseProviderCapabilities,
    TaskType as BaseTaskType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine synchronously for testing."""
    return asyncio.run(coro)


def _make_request(**kwargs) -> ModelRequest:
    """Build a ModelRequest with sensible defaults for testing."""
    defaults = {
        "messages": [{"role": "user", "content": "Hello, world!"}],
    }
    defaults.update(kwargs)
    return ModelRequest(**defaults)


class _StubProviderPolicy:
    """Minimal stub matching ProviderPolicy's interface for testing."""

    def __init__(self, allowed_providers: Optional[List[str]] = None):
        self.allowed_providers = allowed_providers or []


class _StubPrivacyPolicy:
    """Minimal stub matching PrivacyPolicy's interface for testing."""

    def __init__(self, allow_external_apis: bool = True):
        self.allow_external_apis = allow_external_apis


# ===========================================================================
# 1. Port Contracts — Type Identity and Schema
# ===========================================================================

class TestPortContracts(unittest.TestCase):
    """Verify port contract types are well-formed and usable."""

    def test_task_type_values(self):
        """All six Architecture Zero §6.1 task types exist."""
        expected = {"translate", "critique", "revise", "summarize",
                    "extract_terms", "formalize"}
        actual = {t.value for t in TaskType}
        self.assertEqual(actual, expected)

    def test_task_type_is_str_enum(self):
        """TaskType values are strings usable in JSON/dicts."""
        self.assertIsInstance(TaskType.TRANSLATE, str)
        self.assertEqual(TaskType.TRANSLATE, "translate")

    def test_model_request_defaults(self):
        """ModelRequest has sensible defaults per §6.1."""
        req = ModelRequest()
        self.assertEqual(req.task_type, TaskType.TRANSLATE)
        self.assertEqual(req.source_language, "en")
        self.assertEqual(req.target_language, "fa")
        self.assertEqual(req.messages, [])
        self.assertIsNone(req.required_output_schema)
        self.assertIsNone(req.temperature)
        self.assertIsNone(req.seed)
        self.assertIsNone(req.timeout)
        self.assertIsNone(req.privacy_class)
        self.assertEqual(req.metadata, {})

    def test_model_request_full(self):
        """ModelRequest accepts all fields per §6.1."""
        req = ModelRequest(
            task_type=TaskType.CRITIQUE,
            source_language="fa",
            target_language="en",
            messages=[{"role": "user", "content": "test"}],
            required_output_schema={"type": "object"},
            temperature=0.7,
            seed=42,
            timeout=30.0,
            privacy_class="confidential",
            metadata={"project": "test-proj"},
        )
        self.assertEqual(req.task_type, TaskType.CRITIQUE)
        self.assertEqual(req.source_language, "fa")
        self.assertEqual(req.temperature, 0.7)
        self.assertEqual(req.seed, 42)
        self.assertEqual(req.privacy_class, "confidential")

    def test_model_request_rejects_extra_fields(self):
        """ModelRequest uses extra='forbid' per contract strictness."""
        with self.assertRaises(Exception):
            ModelRequest(unknown_field="bad")

    def test_model_response_defaults(self):
        """ModelResponse has sensible defaults per §6.1."""
        resp = ModelResponse(text="hello", provider="test", model="test-model")
        self.assertEqual(resp.text, "hello")
        self.assertIsNone(resp.structured_payload)
        self.assertEqual(resp.finish_reason, "stop")
        self.assertGreater(len(resp.request_id), 0)
        self.assertEqual(resp.warnings, [])
        self.assertEqual(resp.usage, {})
        self.assertGreaterEqual(resp.latency_ms, 0.0)

    def test_model_response_rejects_extra_fields(self):
        """ModelResponse uses extra='forbid'."""
        with self.assertRaises(Exception):
            ModelResponse(text="t", provider="p", model="m", bogus=True)

    def test_provider_capabilities_defaults(self):
        """ProviderCapabilities has conservative defaults."""
        caps = ProviderCapabilities()
        self.assertFalse(caps.supports_streaming)
        self.assertFalse(caps.supports_structured_output)
        self.assertFalse(caps.supports_vision)
        self.assertEqual(caps.max_context_window, 4096)
        self.assertEqual(caps.supported_tasks, [])

    def test_provider_capabilities_with_tasks(self):
        """ProviderCapabilities accepts a list of TaskType."""
        caps = ProviderCapabilities(
            supported_tasks=[TaskType.TRANSLATE, TaskType.SUMMARIZE],
            max_context_window=128000,
        )
        self.assertIn(TaskType.TRANSLATE, caps.supported_tasks)
        self.assertEqual(caps.max_context_window, 128000)

    def test_model_request_json_round_trip(self):
        """ModelRequest survives JSON serialization/deserialization."""
        req = _make_request(task_type=TaskType.REVISE, seed=99)
        data = req.model_dump(mode="json")
        restored = ModelRequest(**data)
        self.assertEqual(restored.task_type, TaskType.REVISE)
        self.assertEqual(restored.seed, 99)

    def test_model_response_json_round_trip(self):
        """ModelResponse survives JSON serialization/deserialization."""
        resp = ModelResponse(
            text="translated",
            provider="fake",
            model="m",
            usage={"input_tokens": 10},
            latency_ms=42.5,
            request_id="abc123",
            warnings=["warn1"],
        )
        data = resp.model_dump(mode="json")
        restored = ModelResponse(**data)
        self.assertEqual(restored.text, "translated")
        self.assertEqual(restored.latency_ms, 42.5)
        self.assertEqual(restored.warnings, ["warn1"])

    def test_re_export_identity(self):
        """Types re-exported from providers.base are identical to core.ports."""
        self.assertIs(BaseModelProvider, ModelProvider)
        self.assertIs(BaseModelRequest, ModelRequest)
        self.assertIs(BaseModelResponse, ModelResponse)
        self.assertIs(BaseProviderCapabilities, ProviderCapabilities)
        self.assertIs(BaseTaskType, TaskType)


# ===========================================================================
# 2. FakeProvider — Success and Failure Coverage
# ===========================================================================

class TestFakeProviderSuccess(unittest.TestCase):
    """FakeProvider success paths — canned responses, structured output."""

    def test_default_text_response(self):
        """FakeProvider returns default text when no queue/map is set."""
        fp = FakeProvider(default_text="translated result")
        resp = _run(fp.generate(_make_request()))
        self.assertEqual(resp.text, "translated result")
        self.assertEqual(resp.provider, "FakeProvider")
        self.assertEqual(resp.model, "fake-model")
        self.assertEqual(resp.finish_reason, "stop")

    def test_response_queue_fifo(self):
        """FakeProvider dequeues responses in FIFO order."""
        fp = FakeProvider(responses=["first", "second", "third"])
        r1 = _run(fp.generate(_make_request()))
        r2 = _run(fp.generate(_make_request()))
        r3 = _run(fp.generate(_make_request()))
        self.assertEqual(r1.text, "first")
        self.assertEqual(r2.text, "second")
        self.assertEqual(r3.text, "third")

    def test_response_queue_exhausted_falls_back_to_default(self):
        """After queue empties, FakeProvider falls back to default_text."""
        fp = FakeProvider(responses=["only"], default_text="fallback")
        _run(fp.generate(_make_request()))
        resp = _run(fp.generate(_make_request()))
        self.assertEqual(resp.text, "fallback")

    def test_response_map_by_task_type(self):
        """FakeProvider resolves responses by task_type from response_map."""
        fp = FakeProvider(response_map={
            TaskType.TRANSLATE: "translated",
            TaskType.SUMMARIZE: "summarized",
        })
        t = _run(fp.generate(_make_request(task_type=TaskType.TRANSLATE)))
        s = _run(fp.generate(_make_request(task_type=TaskType.SUMMARIZE)))
        self.assertEqual(t.text, "translated")
        self.assertEqual(s.text, "summarized")

    def test_structured_payload(self):
        """FakeProvider can return structured JSON payloads."""
        payload = {"glossary": [{"term": "API", "translation": "رابط"}]}
        fp = FakeProvider(structured_payloads=[payload])
        resp = _run(fp.generate(_make_request()))
        self.assertEqual(resp.structured_payload, payload)

    def test_pre_built_model_response_in_queue(self):
        """FakeProvider queue can contain full ModelResponse objects."""
        custom = ModelResponse(
            text="custom",
            provider="custom-provider",
            model="custom-model",
            usage={"input_tokens": 100, "output_tokens": 200},
            finish_reason="length",
            warnings=["truncated"],
        )
        fp = FakeProvider(responses=[custom])
        resp = _run(fp.generate(_make_request()))
        self.assertEqual(resp.text, "custom")
        self.assertEqual(resp.provider, "custom-provider")
        self.assertEqual(resp.finish_reason, "length")
        # request_id and latency_ms are refreshed
        self.assertGreater(len(resp.request_id), 0)
        self.assertGreaterEqual(resp.latency_ms, 0.0)

    def test_usage_populated(self):
        """FakeProvider populates usage fields on every response."""
        fp = FakeProvider()
        resp = _run(fp.generate(_make_request()))
        self.assertIn("input_tokens", resp.usage)
        self.assertIn("output_tokens", resp.usage)
        self.assertIn("total_tokens", resp.usage)
        self.assertIn("cost_estimate", resp.usage)

    def test_request_id_populated(self):
        """Every response has a unique non-empty request_id."""
        fp = FakeProvider()
        r1 = _run(fp.generate(_make_request()))
        r2 = _run(fp.generate(_make_request()))
        self.assertGreater(len(r1.request_id), 0)
        self.assertGreater(len(r2.request_id), 0)
        self.assertNotEqual(r1.request_id, r2.request_id)

    def test_latency_ms_populated(self):
        """Every response has a non-negative latency_ms."""
        fp = FakeProvider()
        resp = _run(fp.generate(_make_request()))
        self.assertGreaterEqual(resp.latency_ms, 0.0)

    def test_call_tracking(self):
        """FakeProvider tracks call_count and recorded_requests."""
        fp = FakeProvider()
        req1 = _make_request(source_language="en")
        req2 = _make_request(source_language="de")
        _run(fp.generate(req1))
        _run(fp.generate(req2))
        self.assertEqual(fp.call_count, 2)
        self.assertEqual(len(fp.recorded_requests), 2)
        self.assertEqual(fp.recorded_requests[0].source_language, "en")
        self.assertEqual(fp.recorded_requests[1].source_language, "de")

    def test_capabilities(self):
        """FakeProvider reports configurable capabilities."""
        fp = FakeProvider(
            supported_tasks=[TaskType.TRANSLATE],
            supports_structured_output=True,
            max_context_window=16384,
        )
        caps = fp.capabilities()
        self.assertTrue(caps.supports_structured_output)
        self.assertFalse(caps.supports_streaming)
        self.assertEqual(caps.max_context_window, 16384)
        self.assertIn(TaskType.TRANSLATE, caps.supported_tasks)

    def test_is_local(self):
        """FakeProvider is always local."""
        fp = FakeProvider()
        self.assertTrue(fp.is_local)

    def test_generate_sync(self):
        """FakeProvider.generate_sync works outside an event loop."""
        fp = FakeProvider(default_text="sync result")
        resp = fp.generate_sync(_make_request())
        self.assertEqual(resp.text, "sync result")

    def test_name_property(self):
        """FakeProvider.name returns class name."""
        fp = FakeProvider()
        self.assertEqual(fp.name, "FakeProvider")


class TestFakeProviderFailure(unittest.TestCase):
    """FakeProvider failure injection — all error conditions."""

    def test_fail_always(self):
        """fail_always=True raises on every call."""
        fp = FakeProvider(fail_always=True)
        with self.assertRaises(ProviderTransientError):
            _run(fp.generate(_make_request()))

    def test_fail_on_nth_call(self):
        """fail_on_call=N raises only on the Nth call."""
        fp = FakeProvider(fail_on_call=2)
        _run(fp.generate(_make_request()))  # call 1: OK
        with self.assertRaises(ProviderTransientError):
            _run(fp.generate(_make_request()))  # call 2: FAIL
        _run(fp.generate(_make_request()))  # call 3: OK

    def test_custom_rate_limit_error(self):
        """Injected ProviderRateLimitError is raised."""
        err = ProviderRateLimitError("Rate limited", details={"retry_after": 60})
        fp = FakeProvider(fail_always=True, failure_error=err)
        with self.assertRaises(ProviderRateLimitError) as ctx:
            _run(fp.generate(_make_request()))
        self.assertIn("Rate limited", str(ctx.exception))

    def test_custom_permanent_error(self):
        """Injected ProviderPermanentError is raised."""
        err = ProviderPermanentError("Invalid model", details={"model": "gpt-99"})
        fp = FakeProvider(fail_always=True, failure_error=err)
        with self.assertRaises(ProviderPermanentError):
            _run(fp.generate(_make_request()))

    def test_custom_authentication_error(self):
        """Injected ProviderPermanentError (auth) is raised for authentication."""
        err = ProviderPermanentError(
            "Authentication failed",
            code="PROVIDER_PERMANENT_ERROR",
            details={"reason": "invalid_api_key"},
        )
        fp = FakeProvider(fail_always=True, failure_error=err)
        with self.assertRaises(ProviderPermanentError) as ctx:
            _run(fp.generate(_make_request()))
        self.assertIn("Authentication failed", str(ctx.exception))

    def test_custom_timeout_error(self):
        """Injected ProviderTransientError (timeout) is raised."""
        err = ProviderTransientError(
            "Request timed out",
            details={"timeout_seconds": 30},
        )
        fp = FakeProvider(fail_always=True, failure_error=err)
        with self.assertRaises(ProviderTransientError) as ctx:
            _run(fp.generate(_make_request()))
        self.assertIn("timed out", str(ctx.exception))

    def test_default_failure_is_transient(self):
        """Default failure_error is ProviderTransientError."""
        fp = FakeProvider(fail_always=True)
        with self.assertRaises(ProviderTransientError):
            _run(fp.generate(_make_request()))

    def test_call_count_tracks_through_failures(self):
        """call_count increments even on failed calls."""
        fp = FakeProvider(fail_on_call=1)
        with self.assertRaises(ProviderTransientError):
            _run(fp.generate(_make_request()))
        self.assertEqual(fp.call_count, 1)
        self.assertEqual(len(fp.recorded_requests), 1)


# ===========================================================================
# 3. EchoProvider
# ===========================================================================

class TestEchoProvider(unittest.TestCase):
    """EchoProvider — test-only echo with mandatory warning (§6.3)."""

    def test_echo_text(self):
        """EchoProvider returns prefixed source text."""
        ep = EchoProvider()
        req = _make_request(target_language="fa")
        resp = _run(ep.generate(req))
        self.assertIn("[ECHO:fa]", resp.text)
        self.assertIn("Hello, world!", resp.text)

    def test_echo_warning(self):
        """EchoProvider always emits TEST_ONLY warning (§6.3)."""
        ep = EchoProvider()
        resp = _run(ep.generate(_make_request()))
        self.assertIn("TEST_ONLY: EchoProvider used", resp.warnings)

    def test_echo_is_local(self):
        """EchoProvider is local."""
        ep = EchoProvider()
        self.assertTrue(ep.is_local)

    def test_echo_capabilities(self):
        """EchoProvider supports all task types."""
        ep = EchoProvider()
        caps = ep.capabilities()
        self.assertEqual(len(caps.supported_tasks), len(TaskType))
        self.assertFalse(caps.supports_structured_output)

    def test_echo_empty_messages(self):
        """EchoProvider handles empty messages gracefully."""
        ep = EchoProvider()
        req = ModelRequest()
        resp = _run(ep.generate(req))
        self.assertIn("(empty)", resp.text)

    def test_echo_request_id_and_latency(self):
        """EchoProvider populates request_id and latency_ms."""
        ep = EchoProvider()
        resp = _run(ep.generate(_make_request()))
        self.assertGreater(len(resp.request_id), 0)
        self.assertGreaterEqual(resp.latency_ms, 0.0)

    def test_echo_generate_sync(self):
        """EchoProvider.generate_sync works."""
        ep = EchoProvider()
        resp = ep.generate_sync(_make_request())
        self.assertIn("[ECHO:", resp.text)


# ===========================================================================
# 4. CallableProvider
# ===========================================================================

class TestCallableProvider(unittest.TestCase):
    """CallableProvider — custom callable injection (§6.2)."""

    def test_sync_callable(self):
        """CallableProvider wraps a sync callable."""
        def my_fn(req: ModelRequest) -> ModelResponse:
            return ModelResponse(
                text=f"custom: {req.source_language}->{req.target_language}",
                provider="my-fn",
                model="custom-1",
            )

        cp = CallableProvider(my_fn, provider_name="MyProvider")
        resp = _run(cp.generate(_make_request()))
        self.assertEqual(resp.text, "custom: en->fa")
        self.assertEqual(cp.name, "MyProvider")

    def test_async_callable(self):
        """CallableProvider wraps an async callable."""
        async def my_async_fn(req: ModelRequest) -> ModelResponse:
            return ModelResponse(
                text="async result",
                provider="async-fn",
                model="async-1",
            )

        cp = CallableProvider(my_async_fn)
        resp = _run(cp.generate(_make_request()))
        self.assertEqual(resp.text, "async result")

    def test_callable_is_local_default(self):
        """CallableProvider defaults to is_local=True."""
        cp = CallableProvider(lambda r: ModelResponse(
            text="t", provider="p", model="m"
        ))
        self.assertTrue(cp.is_local)

    def test_callable_is_local_override(self):
        """CallableProvider allows overriding is_local."""
        cp = CallableProvider(
            lambda r: ModelResponse(text="t", provider="p", model="m"),
            is_local=False,
        )
        self.assertFalse(cp.is_local)

    def test_callable_capabilities(self):
        """CallableProvider has configurable capabilities."""
        cp = CallableProvider(
            lambda r: ModelResponse(text="t", provider="p", model="m"),
            supported_tasks=[TaskType.TRANSLATE],
        )
        caps = cp.capabilities()
        self.assertEqual(caps.supported_tasks, [TaskType.TRANSLATE])


# ===========================================================================
# 5. TranslationService — Reachable Through Application Services
# ===========================================================================

class TestTranslationServiceReachability(unittest.TestCase):
    """TranslationService wraps provider port — acceptance criterion 1."""

    def test_import_from_application_package(self):
        """TranslationService is importable from tarjoman.application."""
        self.assertIs(TranslationService, TS_direct)

    def test_sync_translate(self):
        """translate_text_sync returns a valid ModelResponse."""
        fp = FakeProvider(default_text="ترجمه")
        svc = TranslationService(fp)
        resp = svc.translate_text_sync("Hello")
        self.assertEqual(resp.text, "ترجمه")
        self.assertIsInstance(resp, ModelResponse)
        self.assertEqual(resp.provider, "FakeProvider")

    def test_async_translate(self):
        """translate_text (async) returns a valid ModelResponse."""
        fp = FakeProvider(default_text="ترجمه آزمایشی")
        svc = TranslationService(fp)
        resp = _run(svc.translate_text("Hello", "en", "fa"))
        self.assertEqual(resp.text, "ترجمه آزمایشی")

    def test_execute_task_sync(self):
        """execute_task_sync delegates to provider."""
        fp = FakeProvider(default_text="result")
        svc = TranslationService(fp)
        req = _make_request(task_type=TaskType.SUMMARIZE)
        resp = svc.execute_task_sync(req)
        self.assertEqual(resp.text, "result")

    def test_execute_task_async(self):
        """execute_task (async) delegates to provider."""
        fp = FakeProvider(default_text="async result")
        svc = TranslationService(fp)
        req = _make_request()
        resp = _run(svc.execute_task(req))
        self.assertEqual(resp.text, "async result")

    def test_translate_text_builds_correct_request(self):
        """translate_text populates a ModelRequest with the right fields."""
        fp = FakeProvider()
        svc = TranslationService(fp)
        svc.translate_text_sync("Translate this", "de", "en")
        self.assertEqual(fp.call_count, 1)
        recorded = fp.recorded_requests[0]
        self.assertEqual(recorded.task_type, TaskType.TRANSLATE)
        self.assertEqual(recorded.source_language, "de")
        self.assertEqual(recorded.target_language, "en")
        self.assertEqual(recorded.messages[0]["content"], "Translate this")


# ===========================================================================
# 6. TranslationService — Capability Validation (§6.4)
# ===========================================================================

class TestCapabilityValidation(unittest.TestCase):
    """Provider capability checking before execution — §6.4."""

    def test_unsupported_task_raises(self):
        """Requesting a task not in supported_tasks raises CapabilityUnavailableError."""
        fp = FakeProvider(supported_tasks=[TaskType.TRANSLATE])
        svc = TranslationService(fp)
        req = _make_request(task_type=TaskType.SUMMARIZE)
        with self.assertRaises(CapabilityUnavailableError) as ctx:
            svc.execute_task_sync(req)
        self.assertIn("SUMMARIZE", str(ctx.exception).upper())

    def test_supported_task_passes(self):
        """Requesting a supported task proceeds normally."""
        fp = FakeProvider(supported_tasks=[TaskType.TRANSLATE, TaskType.CRITIQUE])
        svc = TranslationService(fp)
        req = _make_request(task_type=TaskType.TRANSLATE)
        resp = svc.execute_task_sync(req)
        self.assertEqual(resp.text, "fake translation output")

    def test_empty_supported_tasks_means_all_allowed(self):
        """Empty supported_tasks list means no restriction."""
        fp = FakeProvider(supported_tasks=[])
        # Override capabilities to return empty list
        original_caps = fp.capabilities
        fp.capabilities = lambda: ProviderCapabilities(supported_tasks=[])
        svc = TranslationService(fp)
        req = _make_request(task_type=TaskType.FORMALIZE)
        # Empty supported_tasks means no restriction
        resp = svc.execute_task_sync(req)
        self.assertIsInstance(resp, ModelResponse)


# ===========================================================================
# 7. TranslationService — Policy Enforcement (§6.4)
# ===========================================================================

class TestPolicyEnforcement(unittest.TestCase):
    """Provider and privacy policy enforcement — acceptance criterion 3."""

    def test_provider_policy_violation(self):
        """Unapproved provider raises PolicyViolationError."""
        fp = FakeProvider()
        policy = _StubProviderPolicy(allowed_providers=["OpenAIProvider"])
        svc = TranslationService(fp, provider_policy=policy)
        with self.assertRaises(PolicyViolationError) as ctx:
            svc.translate_text_sync("test")
        self.assertIn("FakeProvider", str(ctx.exception))
        self.assertIn("not in the allowed", str(ctx.exception))

    def test_provider_policy_allowed(self):
        """Approved provider passes policy check."""
        fp = FakeProvider()
        policy = _StubProviderPolicy(
            allowed_providers=["FakeProvider", "OpenAIProvider"]
        )
        svc = TranslationService(fp, provider_policy=policy)
        resp = svc.translate_text_sync("test")
        self.assertIsInstance(resp, ModelResponse)

    def test_provider_policy_empty_allows_all(self):
        """Empty allowed_providers list means no restriction."""
        fp = FakeProvider()
        policy = _StubProviderPolicy(allowed_providers=[])
        svc = TranslationService(fp, provider_policy=policy)
        resp = svc.translate_text_sync("test")
        self.assertIsInstance(resp, ModelResponse)

    def test_privacy_policy_external_forbidden(self):
        """Non-local provider with allow_external_apis=False raises."""
        cp = CallableProvider(
            lambda r: ModelResponse(text="t", provider="p", model="m"),
            is_local=False,
        )
        privacy = _StubPrivacyPolicy(allow_external_apis=False)
        svc = TranslationService(cp, privacy_policy=privacy)
        with self.assertRaises(PolicyViolationError) as ctx:
            svc.translate_text_sync("test")
        self.assertIn("external apis", str(ctx.exception).lower())

    def test_privacy_policy_local_provider_allowed(self):
        """Local provider passes privacy check even with allow_external_apis=False."""
        fp = FakeProvider()  # is_local=True
        privacy = _StubPrivacyPolicy(allow_external_apis=False)
        svc = TranslationService(fp, privacy_policy=privacy)
        resp = svc.translate_text_sync("test")
        self.assertIsInstance(resp, ModelResponse)

    def test_privacy_policy_external_allowed(self):
        """Non-local provider passes when allow_external_apis=True."""
        cp = CallableProvider(
            lambda r: ModelResponse(text="t", provider="p", model="m"),
            is_local=False,
        )
        privacy = _StubPrivacyPolicy(allow_external_apis=True)
        svc = TranslationService(cp, privacy_policy=privacy)
        resp = svc.translate_text_sync("test")
        self.assertIsInstance(resp, ModelResponse)

    def test_no_policies_no_restrictions(self):
        """Without policies, no restrictions apply."""
        fp = FakeProvider()
        svc = TranslationService(fp)
        resp = svc.translate_text_sync("test")
        self.assertIsInstance(resp, ModelResponse)

    def test_combined_policies(self):
        """Both provider and privacy policies are checked."""
        fp = FakeProvider()
        provider_pol = _StubProviderPolicy(allowed_providers=["FakeProvider"])
        privacy_pol = _StubPrivacyPolicy(allow_external_apis=False)
        svc = TranslationService(
            fp, provider_policy=provider_pol, privacy_policy=privacy_pol
        )
        # FakeProvider is allowed and local — should pass both
        resp = svc.translate_text_sync("test")
        self.assertIsInstance(resp, ModelResponse)

    def test_real_provider_policy_type(self):
        """TranslationService works with actual ProviderPolicy from profiles."""
        from tarjoman.profiles.models import ProviderPolicy
        policy = ProviderPolicy(
            policy_id="test-pol",
            allowed_providers=["FakeProvider"],
        )
        fp = FakeProvider()
        svc = TranslationService(fp, provider_policy=policy)
        resp = svc.translate_text_sync("test")
        self.assertIsInstance(resp, ModelResponse)

    def test_real_privacy_policy_type(self):
        """TranslationService works with actual PrivacyPolicy from profiles."""
        from tarjoman.profiles.models import PrivacyPolicy
        policy = PrivacyPolicy(
            policy_id="test-priv",
            allow_external_apis=False,
        )
        fp = FakeProvider()  # is_local=True
        svc = TranslationService(fp, privacy_policy=policy)
        resp = svc.translate_text_sync("test")
        self.assertIsInstance(resp, ModelResponse)


# ===========================================================================
# 8. Provenance and Traceability (§4.3)
# ===========================================================================

class TestProvenanceTracking(unittest.TestCase):
    """Provenance context binding during generation — acceptance criterion 3."""

    def test_bind_provenance_during_generate(self):
        """bind_provenance sets operation context during provider call."""
        captured_context = {}

        async def capturing_fn(req: ModelRequest) -> ModelResponse:
            captured_context.update(get_provenance_context())
            return ModelResponse(
                text="provenance test",
                provider="capturing",
                model="test",
            )

        cp = CallableProvider(capturing_fn)
        svc = TranslationService(cp)
        _run(svc.execute_task(_make_request()))

        self.assertIn("correlation_id", captured_context)
        self.assertIn("operation_id", captured_context)
        self.assertIn("metadata", captured_context)
        meta = captured_context["metadata"]
        self.assertEqual(meta["task_type"], "translate")
        self.assertEqual(meta["provider"], "CallableProvider")
        self.assertEqual(meta["source_language"], "en")
        self.assertEqual(meta["target_language"], "fa")

    def test_custom_correlation_id(self):
        """Custom correlation_id from request metadata is propagated."""
        captured_context = {}

        async def capturing_fn(req: ModelRequest) -> ModelResponse:
            captured_context.update(get_provenance_context())
            return ModelResponse(text="t", provider="p", model="m")

        cp = CallableProvider(capturing_fn)
        svc = TranslationService(cp)
        req = _make_request(metadata={"correlation_id": "custom-corr-123"})
        _run(svc.execute_task(req))
        self.assertEqual(captured_context["correlation_id"], "custom-corr-123")

    def test_response_has_request_id(self):
        """Every response from TranslationService has a request_id."""
        fp = FakeProvider()
        svc = TranslationService(fp)
        resp = svc.translate_text_sync("test")
        self.assertGreater(len(resp.request_id), 0)

    def test_response_has_latency_ms(self):
        """Every response from TranslationService has latency_ms >= 0."""
        fp = FakeProvider()
        svc = TranslationService(fp)
        resp = svc.translate_text_sync("test")
        self.assertGreaterEqual(resp.latency_ms, 0.0)

    def test_response_has_usage(self):
        """Every response from TranslationService has usage dict."""
        fp = FakeProvider()
        svc = TranslationService(fp)
        resp = svc.translate_text_sync("test")
        self.assertIsInstance(resp.usage, dict)
        self.assertIn("input_tokens", resp.usage)

    def test_provenance_context_restored_after_call(self):
        """Provenance context is restored after TranslationService call."""
        from tarjoman.core.logging import bind_provenance as bp

        with bp(correlation_id="outer-123"):
            outer_before = get_provenance_context()
            self.assertEqual(outer_before["correlation_id"], "outer-123")

            fp = FakeProvider()
            svc = TranslationService(fp)
            _run(svc.execute_task(_make_request()))

            outer_after = get_provenance_context()
            self.assertEqual(outer_after["correlation_id"], "outer-123")


# ===========================================================================
# 9. Architecture Conformance
# ===========================================================================

class TestArchitectureConformance(unittest.TestCase):
    """Architecture conformance — no new violations from TRN-001."""

    def test_conformance_check_passes(self):
        """ArchitectureConformanceChecker.enforce() passes cleanly."""
        from tarjoman.quality import ArchitectureConformanceChecker
        checker = ArchitectureConformanceChecker()
        # Should not raise
        checker.enforce()

    def test_application_does_not_import_providers(self):
        """application.translation_service imports from core.ports, not providers."""
        import ast
        from pathlib import Path

        src = Path(__file__).resolve().parent.parent / "src" / "tarjoman"
        ts_path = src / "application" / "translation_service.py"
        tree = ast.parse(ts_path.read_text())

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        for imp in imports:
            self.assertFalse(
                imp.startswith("tarjoman.providers"),
                f"application module imports from tarjoman.providers: {imp}",
            )

    def test_providers_base_imports_from_core_ports(self):
        """providers.base re-exports from core.ports, not its own definitions."""
        import ast
        from pathlib import Path

        src = Path(__file__).resolve().parent.parent / "src" / "tarjoman"
        base_path = src / "providers" / "base.py"
        tree = ast.parse(base_path.read_text())

        from_core_ports = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module == "tarjoman.core.ports":
                    from_core_ports = True

        self.assertTrue(
            from_core_ports,
            "providers.base must import from tarjoman.core.ports",
        )


# ===========================================================================
# 10. ModelProvider ABC Contract
# ===========================================================================

class TestModelProviderABC(unittest.TestCase):
    """ModelProvider abstract base class contract."""

    def test_cannot_instantiate_abc(self):
        """ModelProvider cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            ModelProvider()

    def test_subclass_must_implement_generate_and_capabilities(self):
        """Subclass without generate/capabilities cannot be instantiated."""
        class IncompleteProvider(ModelProvider):
            pass

        with self.assertRaises(TypeError):
            IncompleteProvider()

    def test_subclass_with_implementations_works(self):
        """Properly implemented subclass can be instantiated."""
        class GoodProvider(ModelProvider):
            async def generate(self, request):
                return ModelResponse(text="ok", provider="good", model="m")
            def capabilities(self):
                return ProviderCapabilities()

        provider = GoodProvider()
        self.assertIsNotNone(provider)
        self.assertEqual(provider.name, "GoodProvider")
        self.assertFalse(provider.is_local)

    def test_default_name_is_class_name(self):
        """Default name property returns class name."""
        fp = FakeProvider()
        self.assertEqual(fp.name, "FakeProvider")

    def test_default_is_local_false(self):
        """Default is_local is False for base ModelProvider."""
        class RemoteProvider(ModelProvider):
            async def generate(self, request):
                return ModelResponse(text="t", provider="r", model="m")
            def capabilities(self):
                return ProviderCapabilities()

        self.assertFalse(RemoteProvider().is_local)


if __name__ == "__main__":
    unittest.main()
