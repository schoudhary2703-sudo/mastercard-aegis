"""Provider abstraction for the GenAI reasoning layer.

Two implementations ship today:

* `AnthropicProvider` -- a real call to the Claude API. Requires the optional
  `genai` extra (`pip install -e ".[genai]"`) and `ANTHROPIC_API_KEY`.
* `RecordedProvider` -- replays a previously persisted run artifact. Exists so
  the demo can be shown without a network or a key, and it is *always*
  labeled: everything it returns carries `live=False`.

There is deliberately no third "offline default" implementation that
synthesizes plausible reasoning. If no provider is configured, the layer
raises `GenAIConfigurationError` rather than inventing an answer -- a canned
paragraph presented as model reasoning is exactly the failure this project
cannot afford.

This module is also where *provider-specific* schema quirks are absorbed.
Anthropic's structured-output compiler accepts only a subset of JSON Schema
and rejects annotations such as `minimum`/`maximum`; the strict Pydantic
schema is therefore sanitized on its way out to that one provider, and
nowhere else. See `sanitize_json_schema_for_anthropic`.
"""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aegis.genai.errors import GenAIConfigurationError, GenAIProviderError

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MAX_TOKENS = 16000

_API_KEY_ENV = "ANTHROPIC_API_KEY"
_MODEL_ENV = "AEGIS_GENAI_MODEL"
_PROVIDER_ENV = "AEGIS_GENAI_PROVIDER"


@dataclass(frozen=True)
class ProviderResult:
    """One raw completion, plus what is needed to attribute it."""

    text: str
    provider: str
    model: str
    live: bool
    request_id: str | None = None
    latency_ms: float | None = None
    attempts: int = 1


class GenAIProvider(ABC):
    """Anything that can turn a system+user prompt into raw JSON text.

    Kept deliberately narrow: the provider returns *text*, and schema
    validation happens one layer up (`aegis.genai.analysts`). That split is
    what lets the malformed-response path be exercised in tests without a
    network, and keeps a provider swap from changing validation behavior.
    """

    name: str
    model: str

    @abstractmethod
    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, Any] | None = None,
    ) -> ProviderResult:
        """Return the model's raw response text. Raises `GenAIProviderError`."""


# ---------------------------------------------------------------------------
# Anthropic-specific JSON Schema sanitation
# ---------------------------------------------------------------------------
#
# Anthropic's structured-output compiler supports a *subset* of JSON Schema.
# Numeric bounds are rejected outright:
#
#     output_config.format.schema: For 'number' type, properties maximum,
#     minimum are not supported
#
# The same applies to string-length and array-length constraints. Pydantic
# emits all of them from `Field(ge=..., le=..., min_length=..., max_length=...)`,
# so the strict schema cannot be transmitted verbatim.
#
# The resolution is deliberately one-directional: the *transmitted* schema is
# stripped of annotations this one provider cannot compile; the *validating*
# schema -- the Pydantic model itself -- is untouched. Every bound removed here
# is still enforced in `aegis.genai.analysts._parse_response`, which validates
# the model's reply against the original strict model before anything
# downstream sees it. A response with `confidence: 1.4` or a mutation
# `magnitude: 0.9` is therefore still rejected locally; the model simply is not
# told about the ceiling in-band.
#
# This lives in the Anthropic adapter on purpose. It is not a property of the
# contracts (`aegis.genai.contracts`), and no other provider sees a sanitized
# schema.

_UNSUPPORTED_NUMERIC_KEYWORDS: frozenset[str] = frozenset(
    {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"}
)
"""Numeric bounds. These are what the live call currently fails on."""

_UNSUPPORTED_STRING_KEYWORDS: frozenset[str] = frozenset({"minLength", "maxLength"})
"""String-length constraints; emitted by `Field(min_length=...)`."""

_UNSUPPORTED_ARRAY_KEYWORDS: frozenset[str] = frozenset(
    {"minItems", "maxItems", "uniqueItems", "minContains", "maxContains"}
)
"""Array cardinality constraints; emitted by `Field(max_length=...)` on a list."""

UNSUPPORTED_SCHEMA_KEYWORDS: frozenset[str] = (
    _UNSUPPORTED_NUMERIC_KEYWORDS | _UNSUPPORTED_STRING_KEYWORDS | _UNSUPPORTED_ARRAY_KEYWORDS
)
"""Every annotation stripped from a schema before it is sent to Anthropic."""

# Keys whose *values* are maps of name -> subschema. Their keys are user-chosen
# names, so a property legitimately named "minimum" must survive.
_SUBSCHEMA_MAP_KEYS: frozenset[str] = frozenset(
    {"properties", "$defs", "definitions", "patternProperties"}
)

# Keys whose values are literal data, not schemas. Never walked into: a
# `default` object may contain a key that happens to be called "maximum".
_LITERAL_VALUE_KEYS: frozenset[str] = frozenset({"default", "const", "enum", "examples"})


def _sanitize_node(node: Any) -> Any:
    """Recursively rebuild `node` without the unsupported keywords."""
    if isinstance(node, list):
        return [_sanitize_node(item) for item in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in UNSUPPORTED_SCHEMA_KEYWORDS:
            continue
        if key in _LITERAL_VALUE_KEYS:
            out[key] = deepcopy(value)
        elif key in _SUBSCHEMA_MAP_KEYS and isinstance(value, dict):
            out[key] = {name: _sanitize_node(sub) for name, sub in value.items()}
        else:
            out[key] = _sanitize_node(value)
    return out


def sanitize_json_schema_for_anthropic(json_schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of `json_schema` that Anthropic's compiler will accept.

    Removes only annotations -- no type, property, `required` entry, `$ref` or
    `additionalProperties: false` is touched, so the transmitted schema still
    describes exactly the same shape. The input dict is never mutated: callers
    keep handing the strict Pydantic schema to validation.
    """
    sanitized = _sanitize_node(json_schema)
    if not isinstance(sanitized, dict):  # pragma: no cover - a schema is always an object
        msg = f"json schema must be an object, got {type(json_schema).__name__}"
        raise GenAIProviderError(msg)
    return sanitized


def iter_unsupported_schema_keywords(json_schema: dict[str, Any]) -> Iterator[tuple[str, str]]:
    """Yield `(json_pointer, keyword)` for every unsupported annotation present.

    Used by the regression tests to assert the transmitted schema is clean and
    the original is not.
    """

    def walk(node: Any, pointer: str) -> Iterator[tuple[str, str]]:
        if isinstance(node, list):
            for index, item in enumerate(node):
                yield from walk(item, f"{pointer}/{index}")
            return
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            child = f"{pointer}/{key}"
            if key in UNSUPPORTED_SCHEMA_KEYWORDS:
                yield (pointer or "/", key)
                continue
            if key in _LITERAL_VALUE_KEYS:
                continue
            yield from walk(value, child)

    yield from walk(json_schema, "")


class AnthropicProvider(GenAIProvider):
    """Live Claude API provider.

    The `anthropic` SDK is imported lazily so the rest of AEGIS -- and the
    whole test suite -- keeps working without the optional extra installed.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self.name = "anthropic"
        self.model = model or os.environ.get(_MODEL_ENV) or DEFAULT_MODEL
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, max_attempts)
        self.max_tokens = max_tokens
        self._api_key = api_key or os.environ.get(_API_KEY_ENV) or ""
        if not self._api_key:
            msg = (
                f"{_API_KEY_ENV} is not set. Export a real key to run live GenAI analysis, "
                "or pass --provider recorded to replay a persisted run artifact. "
                "AEGIS never fabricates GenAI reasoning when a key is missing."
            )
            raise GenAIConfigurationError(msg)
        self._client = self._build_client()

    def _build_client(self) -> Any:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            msg = (
                "the `anthropic` package is required for live GenAI analysis; "
                'install the optional extra: pip install -e ".[genai]"'
            )
            raise GenAIConfigurationError(msg) from exc
        # SDK-level retries are disabled: this class owns the retry policy so
        # the attempt count that lands on the run artifact is the true one.
        return anthropic.Anthropic(
            api_key=self._api_key, timeout=self.timeout_seconds, max_retries=0
        )

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, Any] | None = None,
    ) -> ProviderResult:
        import anthropic

        # Retried: transient transport/server conditions. Not retried: 4xx
        # other than 429, which will fail identically on a second attempt.
        retryable = (
            anthropic.APITimeoutError,
            anthropic.APIConnectionError,
            anthropic.RateLimitError,
            anthropic.InternalServerError,
        )
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "thinking": {"type": "adaptive"},
        }
        if json_schema is not None:
            # `output_config.format` accepts exactly two keys -- `type` and
            # `schema` (anthropic.types.JSONOutputFormatParam). Anything else,
            # `name` included, is rejected with "Extra inputs are not
            # permitted", so `schema_name` stays a local label: it names the
            # stage in prompts and artifacts and never goes on the wire.
            #
            # The schema is sanitized on the way out only. `json_schema` itself
            # is left alone, and the reply is validated against the strict
            # Pydantic model one layer up regardless of what was transmitted.
            request["output_config"] = {
                "format": {
                    "type": "json_schema",
                    "schema": sanitize_json_schema_for_anthropic(json_schema),
                }
            }

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            started = time.perf_counter()
            try:
                response = self._client.messages.create(**request)
            except retryable as exc:
                last_error = exc
                if attempt < self.max_attempts:
                    time.sleep(min(2.0**attempt, 8.0))
                    continue
                raise GenAIProviderError(
                    f"anthropic call failed after {attempt} attempt(s): {exc}", attempts=attempt
                ) from exc
            except anthropic.APIStatusError as exc:
                raise GenAIProviderError(
                    f"anthropic call failed ({exc.status_code}): {exc}", attempts=attempt
                ) from exc

            latency_ms = (time.perf_counter() - started) * 1000.0
            if getattr(response, "stop_reason", None) == "refusal":
                raise GenAIProviderError(
                    "anthropic declined this request (stop_reason=refusal)", attempts=attempt
                )
            text = "".join(
                block.text for block in response.content if getattr(block, "type", "") == "text"
            )
            if not text.strip():
                raise GenAIProviderError(
                    "anthropic returned no text content", attempts=attempt
                )
            return ProviderResult(
                text=text,
                provider=self.name,
                model=self.model,
                live=True,
                request_id=getattr(response, "_request_id", None),
                latency_ms=latency_ms,
                attempts=attempt,
            )

        # Unreachable: the loop either returns or raises.
        raise GenAIProviderError(
            f"anthropic call failed: {last_error}", attempts=self.max_attempts
        )


class RecordedProvider(GenAIProvider):
    """Replays the `response` block of a persisted `GenAIRunArtifact`.

    Used for offline demos and for tests. Everything it produces is stamped
    `live=False` and `provider="recorded"`, and the artifact it replays is
    named in the new run's `source_artifacts`, so a replayed answer is always
    distinguishable from a fresh one on disk.
    """

    def __init__(self, artifact_path: Path) -> None:
        self.name = "recorded"
        self.artifact_path = Path(artifact_path)
        if not self.artifact_path.is_file():
            msg = f"recorded artifact not found: {self.artifact_path}"
            raise GenAIConfigurationError(msg)
        try:
            payload = json.loads(self.artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            msg = f"recorded artifact is unreadable: {self.artifact_path}: {exc}"
            raise GenAIConfigurationError(msg) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("response"), dict):
            msg = (
                f"recorded artifact {self.artifact_path} has no usable `response` object; "
                "it cannot be replayed"
            )
            raise GenAIConfigurationError(msg)
        self._payload: dict[str, Any] = payload
        provenance = payload.get("provenance")
        recorded_model = (
            provenance.get("model") if isinstance(provenance, dict) else None
        ) or "unknown"
        self.model = str(recorded_model)

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, Any] | None = None,
    ) -> ProviderResult:
        return ProviderResult(
            text=json.dumps(self._payload["response"]),
            provider=self.name,
            model=self.model,
            live=False,
            request_id=None,
            latency_ms=None,
            attempts=1,
        )


def build_provider(
    name: str | None = None,
    *,
    model: str | None = None,
    recorded_artifact: Path | None = None,
) -> GenAIProvider:
    """Construct the configured provider, or raise explaining what is missing."""
    resolved = (name or os.environ.get(_PROVIDER_ENV) or "anthropic").strip().lower()
    if resolved == "anthropic":
        return AnthropicProvider(model=model)
    if resolved == "recorded":
        if recorded_artifact is None:
            msg = "provider 'recorded' requires --recorded-artifact pointing at a prior run"
            raise GenAIConfigurationError(msg)
        return RecordedProvider(recorded_artifact)
    msg = f"unknown GenAI provider {resolved!r}; expected 'anthropic' or 'recorded'"
    raise GenAIConfigurationError(msg)


__all__ = [
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT_SECONDS",
    "UNSUPPORTED_SCHEMA_KEYWORDS",
    "AnthropicProvider",
    "GenAIProvider",
    "ProviderResult",
    "RecordedProvider",
    "build_provider",
    "iter_unsupported_schema_keywords",
    "sanitize_json_schema_for_anthropic",
]
