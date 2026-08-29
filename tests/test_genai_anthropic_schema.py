"""Anthropic structured-output request compatibility, and the bounds it must not weaken.

Two live-call blockers are pinned here, both purely about what the Anthropic
adapter puts on the wire.

1. The compiler accepts only a subset of JSON Schema and rejects numeric
   bounds outright::

       output_config.format.schema: For 'number' type, properties maximum,
       minimum are not supported

   Pydantic emits exactly those bounds from `Field(ge=..., le=...)`, so the
   strict schema cannot be transmitted verbatim. The adapter strips the
   unsupported annotations from the *transmitted* schema only.

2. `output_config.format` accepts exactly `type` and `schema`
   (`anthropic.types.JSONOutputFormatParam`). A `name` key fails with::

       output_config.format.name: Extra inputs are not permitted

   `schema_name` therefore stays a local label and never goes on the wire.

3. Every subschema needs an explicit type. `proposed_value: Any` rendered as
   `{title, description, default}` with none, and failed with::

       Invalid schema: Schema type is missing for schema: {...}

   It is now a scalar union (`bool | int | float | str | None`), which also
   makes handing over a list or dict of transaction rows a validation error.

Everything in this file exists to prove that compatibility was not bought with
safety: the Pydantic models keep their bounds, an out-of-range reply is still
rejected locally, mutation limits still hold, and no other provider or contract
ever sees a sanitized schema. No test here makes a network call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from aegis.genai import (
    MAX_MUTATION_MAGNITUDE,
    MAX_MUTATION_PROPOSALS,
    AttackAnalystResponse,
    BlindSpotAnalystResponse,
    GenAISchemaError,
    MutationBoundsError,
    RecordedProvider,
    run_attack_analyst,
    run_blind_spot_analyst,
)
from aegis.genai.contracts import BoundedMutationProposal
from aegis.genai.provider import (
    UNSUPPORTED_SCHEMA_KEYWORDS,
    iter_unsupported_schema_keywords,
    sanitize_json_schema_for_anthropic,
)
from aegis.shared.enums import MutationDirection
from tests.test_genai import (
    VALID_ATTACK_RESPONSE,
    VALID_BLIND_SPOT_RESPONSE,
    FakeProvider,
    _attack_request,
    _blind_spot_request,
)

RESPONSE_MODELS: list[Any] = [AttackAnalystResponse, BlindSpotAnalystResponse]


def _keys_anywhere(payload: Any) -> set[str]:
    """Every mapping key appearing anywhere in `payload`, at any depth."""
    found: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            found.add(key)
            found |= _keys_anywhere(value)
    elif isinstance(payload, list):
        for item in payload:
            found |= _keys_anywhere(item)
    return found


# ---------------------------------------------------------------------------
# 1. the transmitted schema is compatible
# ---------------------------------------------------------------------------


class TestTransmittedSchemaIsCompatible:
    @pytest.mark.parametrize("model_cls", RESPONSE_MODELS)
    def test_sanitized_schema_has_no_unsupported_keywords(self, model_cls: Any) -> None:
        sanitized = sanitize_json_schema_for_anthropic(model_cls.model_json_schema())
        assert list(iter_unsupported_schema_keywords(sanitized)) == []

    @pytest.mark.parametrize("model_cls", RESPONSE_MODELS)
    def test_sanitized_schema_carries_no_bounds_at_any_depth(self, model_cls: Any) -> None:
        sanitized = sanitize_json_schema_for_anthropic(model_cls.model_json_schema())
        assert _keys_anywhere(sanitized) & UNSUPPORTED_SCHEMA_KEYWORDS == set()

    def test_the_exact_fields_that_broke_the_live_call_are_the_ones_stripped(self) -> None:
        """`confidence`, `magnitude`, `mutation_proposals`, plus min-length strings."""
        strict = BlindSpotAnalystResponse.model_json_schema()
        stripped = {keyword for _, keyword in iter_unsupported_schema_keywords(strict)}
        assert stripped == {"minimum", "maximum", "minLength", "maxItems"}

        sanitized = sanitize_json_schema_for_anthropic(strict)
        proposal = sanitized["$defs"]["BoundedMutationProposal"]["properties"]
        assert "maximum" not in proposal["magnitude"]["anyOf"][0]
        assert "minimum" not in proposal["magnitude"]["anyOf"][0]
        assert "maxItems" not in sanitized["properties"]["mutation_proposals"]

    @pytest.mark.parametrize("model_cls", RESPONSE_MODELS)
    def test_sanitation_preserves_the_described_shape(self, model_cls: Any) -> None:
        """Only annotations go. Types, names, required and $refs are untouched."""
        strict = model_cls.model_json_schema()
        sanitized = sanitize_json_schema_for_anthropic(strict)

        assert sanitized["type"] == "object"
        assert sanitized["additionalProperties"] is False
        assert sanitized["required"] == strict["required"]
        assert sanitized["properties"].keys() == strict["properties"].keys()
        assert sanitized["$defs"].keys() == strict["$defs"].keys()
        for name, subschema in strict["$defs"].items():
            assert sanitized["$defs"][name].get("type") == subschema.get("type")

    def test_a_property_literally_named_minimum_survives(self) -> None:
        """The stripper removes keywords, not user-chosen property names."""
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "minimum": {"type": "number", "minimum": 0.0},
                "maximum": {"type": "integer", "maximum": 10},
            },
            "required": ["minimum"],
        }
        sanitized = sanitize_json_schema_for_anthropic(schema)

        assert sanitized["properties"].keys() == {"minimum", "maximum"}
        assert sanitized["properties"]["minimum"] == {"type": "number"}
        assert sanitized["properties"]["maximum"] == {"type": "integer"}

    def test_literal_default_values_are_not_walked_into(self) -> None:
        schema = {
            "type": "object",
            "properties": {"bounds": {"type": "object", "default": {"minimum": 1, "maximum": 2}}},
        }
        sanitized = sanitize_json_schema_for_anthropic(schema)
        assert sanitized["properties"]["bounds"]["default"] == {"minimum": 1, "maximum": 2}


# ---------------------------------------------------------------------------
# 2. the validating schema is untouched
# ---------------------------------------------------------------------------


class TestStrictSchemaIsUnchanged:
    def test_attack_analyst_schema_keeps_its_confidence_bounds(self) -> None:
        confidence = AttackAnalystResponse.model_json_schema()["properties"]["confidence"]
        assert confidence["minimum"] == 0.0
        assert confidence["maximum"] == 1.0

    def test_blind_spot_schema_keeps_its_mutation_bounds(self) -> None:
        schema = BlindSpotAnalystResponse.model_json_schema()
        magnitude = schema["$defs"]["BoundedMutationProposal"]["properties"]["magnitude"]
        numeric = magnitude["anyOf"][0]
        assert numeric["minimum"] == 0.0
        assert numeric["maximum"] == MAX_MUTATION_MAGNITUDE
        assert schema["properties"]["mutation_proposals"]["maxItems"] == MAX_MUTATION_PROPOSALS

    @pytest.mark.parametrize("model_cls", RESPONSE_MODELS)
    def test_sanitize_does_not_mutate_its_input(self, model_cls: Any) -> None:
        strict = model_cls.model_json_schema()
        before = json.dumps(strict, sort_keys=True)
        sanitize_json_schema_for_anthropic(strict)
        assert json.dumps(strict, sort_keys=True) == before

    @pytest.mark.parametrize("model_cls", RESPONSE_MODELS)
    def test_sanitation_does_not_leak_back_into_the_model(self, model_cls: Any) -> None:
        """A freshly generated schema still carries bounds after a sanitation pass."""
        sanitize_json_schema_for_anthropic(model_cls.model_json_schema())
        regenerated = model_cls.model_json_schema()
        assert {keyword for _, keyword in iter_unsupported_schema_keywords(regenerated)}


# ---------------------------------------------------------------------------
# 3. local validation is still strict
# ---------------------------------------------------------------------------


class TestLocalValidationStaysStrict:
    def test_valid_attack_response_still_succeeds(self, tmp_path: Path) -> None:
        provider = FakeProvider(json.dumps(VALID_ATTACK_RESPONSE))
        outcome = run_attack_analyst(_attack_request(), provider, root=tmp_path)
        assert outcome.artifact.schema_valid is True
        assert outcome.response.confidence == VALID_ATTACK_RESPONSE["confidence"]

    def test_valid_blind_spot_response_still_succeeds(self, tmp_path: Path) -> None:
        provider = FakeProvider(json.dumps(VALID_BLIND_SPOT_RESPONSE))
        outcome = run_blind_spot_analyst(_blind_spot_request(), provider, root=tmp_path)
        assert outcome.artifact.schema_valid is True
        assert outcome.response.mutation_proposals[0].magnitude == 0.2

    def test_out_of_range_confidence_is_rejected(self, tmp_path: Path) -> None:
        payload = {**VALID_ATTACK_RESPONSE, "confidence": 1.4}
        provider = FakeProvider(json.dumps(payload))
        with pytest.raises(GenAISchemaError):
            run_attack_analyst(_attack_request(), provider, root=tmp_path)

    def test_negative_confidence_is_rejected(self, tmp_path: Path) -> None:
        payload = {**VALID_BLIND_SPOT_RESPONSE, "confidence": -0.1}
        with pytest.raises(GenAISchemaError):
            run_blind_spot_analyst(
                _blind_spot_request(), FakeProvider(json.dumps(payload)), root=tmp_path
            )

    def test_over_magnitude_mutation_is_rejected(self, tmp_path: Path) -> None:
        proposal = {**VALID_BLIND_SPOT_RESPONSE["mutation_proposals"][0], "magnitude": 0.9}
        payload = {**VALID_BLIND_SPOT_RESPONSE, "mutation_proposals": [proposal]}
        with pytest.raises(GenAISchemaError):
            run_blind_spot_analyst(
                _blind_spot_request(), FakeProvider(json.dumps(payload)), root=tmp_path
            )

    def test_rejection_is_recorded_as_a_failed_run_on_disk(self, tmp_path: Path) -> None:
        """A rejected reply leaves a failure artifact, never a silent clamp."""
        proposal = {
            **VALID_BLIND_SPOT_RESPONSE["mutation_proposals"][0],
            "magnitude": MAX_MUTATION_MAGNITUDE + 0.01,
        }
        payload = {**VALID_BLIND_SPOT_RESPONSE, "mutation_proposals": [proposal]}
        with pytest.raises(GenAISchemaError):
            run_blind_spot_analyst(
                _blind_spot_request(), FakeProvider(json.dumps(payload)), root=tmp_path
            )

        written = list(tmp_path.rglob("*.json"))
        assert len(written) == 1
        artifact = json.loads(written[0].read_text(encoding="utf-8"))
        assert artifact["schema_valid"] is False
        assert artifact["response"] is None
        assert "schema_error" in artifact["failure"]

    def test_too_many_mutation_proposals_is_rejected(self, tmp_path: Path) -> None:
        template = VALID_BLIND_SPOT_RESPONSE["mutation_proposals"][0]
        proposals = [
            {**template, "parameter": f"destination_diversity_{index}"}
            for index in range(MAX_MUTATION_PROPOSALS + 1)
        ]
        payload = {**VALID_BLIND_SPOT_RESPONSE, "mutation_proposals": proposals}
        with pytest.raises(GenAISchemaError):
            run_blind_spot_analyst(
                _blind_spot_request(), FakeProvider(json.dumps(payload)), root=tmp_path
            )

    def test_non_mutable_parameter_is_still_rejected(self, tmp_path: Path) -> None:
        proposal = {
            **VALID_BLIND_SPOT_RESPONSE["mutation_proposals"][0],
            "parameter": "detector_threshold",
        }
        payload = {**VALID_BLIND_SPOT_RESPONSE, "mutation_proposals": [proposal]}
        with pytest.raises(MutationBoundsError):
            run_blind_spot_analyst(
                _blind_spot_request(), FakeProvider(json.dumps(payload)), root=tmp_path
            )

    def test_raw_transaction_payload_is_still_rejected(self, tmp_path: Path) -> None:
        payload = {
            **VALID_ATTACK_RESPONSE,
            "recommended_simulator_parameters": [
                {
                    "name": "transactions",
                    "value": "[{amount: 500.0}]",
                    "rationale": "Hands back rows instead of parameters.",
                    "unit": None,
                }
            ],
        }
        with pytest.raises(GenAISchemaError):
            run_attack_analyst(_attack_request(), FakeProvider(json.dumps(payload)), root=tmp_path)


# ---------------------------------------------------------------------------
# 4. sanitation is confined to the Anthropic adapter
# ---------------------------------------------------------------------------


class TestProposedValueIsStructurallyTyped:
    """`proposed_value: Any` rendered as a schema with no `type`, which the
    compiler rejects with "Schema type is missing for schema". It is now a
    scalar union, so every branch carries an explicit type."""

    def _proposed_value_schema(self, *, sanitized: bool) -> dict[str, Any]:
        schema = BlindSpotAnalystResponse.model_json_schema()
        if sanitized:
            schema = sanitize_json_schema_for_anthropic(schema)
        field: dict[str, Any] = schema["$defs"]["BoundedMutationProposal"]["properties"][
            "proposed_value"
        ]
        return field

    @pytest.mark.parametrize("sanitized", [False, True], ids=["strict", "transmitted"])
    def test_proposed_value_declares_explicit_types(self, sanitized: bool) -> None:
        field = self._proposed_value_schema(sanitized=sanitized)
        assert "anyOf" in field
        assert [branch["type"] for branch in field["anyOf"]] == [
            "boolean",
            "integer",
            "number",
            "string",
            "null",
        ]

    def test_no_transmitted_subschema_is_typeless(self) -> None:
        """The general form of the failure: any node with no type/$ref/anyOf."""
        structural = {"type", "anyOf", "allOf", "oneOf", "$ref", "enum", "const"}

        def typeless(node: Any, pointer: str) -> list[str]:
            found: list[str] = []
            if isinstance(node, list):
                for index, item in enumerate(node):
                    found += typeless(item, f"{pointer}/{index}")
                return found
            if not isinstance(node, dict):
                return found
            for key, value in node.items():
                if key in {"properties", "$defs"} and isinstance(value, dict):
                    for name, sub in value.items():
                        if isinstance(sub, dict) and not structural & sub.keys():
                            found.append(f"{pointer}/{key}/{name}")
                        found += typeless(sub, f"{pointer}/{key}/{name}")
                elif key == "items" and isinstance(value, dict):
                    if not structural & value.keys():
                        found.append(f"{pointer}/items")
                    found += typeless(value, f"{pointer}/items")
                elif isinstance(value, (dict, list)) and key not in {"default", "enum", "const"}:
                    found += typeless(value, f"{pointer}/{key}")
            return found

        for model_cls in RESPONSE_MODELS:
            sanitized = sanitize_json_schema_for_anthropic(model_cls.model_json_schema())
            assert typeless(sanitized, "") == []

    def test_sanitizer_leaves_the_typed_union_intact(self) -> None:
        assert self._proposed_value_schema(sanitized=True)["anyOf"] == (
            self._proposed_value_schema(sanitized=False)["anyOf"]
        )

    @pytest.mark.parametrize(
        ("value", "expected_type"),
        [(7, int), (7.5, float), ("mobile", str), (True, bool)],
    )
    def test_scalar_set_values_validate_and_keep_their_type(
        self, value: Any, expected_type: type
    ) -> None:
        proposal = BoundedMutationProposal(
            parameter="destination_diversity",
            direction=MutationDirection.SET,
            proposed_value=value,
            magnitude=0.1,
            rationale="A scalar the parameter could legally take.",
        )
        assert type(proposal.proposed_value) is expected_type

    @pytest.mark.parametrize(
        "payload",
        [
            [{"amount": 900, "to": "acct-1"}],
            {"transactions": [{"amount": 900}]},
            [1, 2, 3],
            {},
        ],
        ids=["rows-list", "rows-dict", "scalar-list", "empty-dict"],
    )
    def test_container_values_are_rejected(self, payload: Any) -> None:
        with pytest.raises(ValidationError):
            BoundedMutationProposal(
                parameter="destination_diversity",
                direction=MutationDirection.SET,
                proposed_value=payload,
                magnitude=0.1,
                rationale="Hands over rows instead of a direction.",
            )

    def test_a_transaction_shaped_response_is_rejected_end_to_end(self, tmp_path: Path) -> None:
        proposal = {
            **VALID_BLIND_SPOT_RESPONSE["mutation_proposals"][0],
            "direction": "set",
            "proposed_value": [{"amount": 900.0, "to": "acct-1"}],
        }
        payload = {**VALID_BLIND_SPOT_RESPONSE, "mutation_proposals": [proposal]}
        with pytest.raises(GenAISchemaError):
            run_blind_spot_analyst(
                _blind_spot_request(), FakeProvider(json.dumps(payload)), root=tmp_path
            )

    def test_set_still_requires_a_value(self) -> None:
        with pytest.raises(ValidationError):
            BoundedMutationProposal(
                parameter="destination_diversity",
                direction=MutationDirection.SET,
                proposed_value=None,
                magnitude=0.1,
                rationale="SET with nothing to set.",
            )

    @pytest.mark.parametrize(
        "direction", [MutationDirection.INCREASE, MutationDirection.DECREASE]
    )
    def test_directional_proposals_still_need_no_value(
        self, direction: MutationDirection
    ) -> None:
        proposal = BoundedMutationProposal(
            parameter="destination_diversity",
            direction=direction,
            magnitude=0.2,
            rationale="Direction and magnitude only; the optimizer computes the value.",
        )
        assert proposal.proposed_value is None
        assert proposal.magnitude == 0.2

    def test_magnitude_ceiling_is_unaffected_by_the_retype(self) -> None:
        with pytest.raises(ValidationError):
            BoundedMutationProposal(
                parameter="destination_diversity",
                direction=MutationDirection.INCREASE,
                magnitude=MAX_MUTATION_MAGNITUDE + 0.01,
                rationale="Over the ceiling.",
            )


class TestSanitationDoesNotLeak:
    def test_blind_spot_stage_hands_providers_the_strict_schema(self, tmp_path: Path) -> None:
        """The stage passes the unsanitized schema; only Anthropic rewrites it."""
        provider = FakeProvider(json.dumps(VALID_BLIND_SPOT_RESPONSE))
        run_blind_spot_analyst(_blind_spot_request(), provider, root=tmp_path)

        assert provider.json_schema is not None
        magnitude = provider.json_schema["$defs"]["BoundedMutationProposal"]["properties"][
            "magnitude"
        ]
        assert magnitude["anyOf"][0]["maximum"] == MAX_MUTATION_MAGNITUDE

    def test_attack_stage_hands_providers_the_strict_schema(self, tmp_path: Path) -> None:
        provider = FakeProvider(json.dumps(VALID_ATTACK_RESPONSE))
        run_attack_analyst(_attack_request(), provider, root=tmp_path)

        assert provider.json_schema is not None
        assert provider.json_schema["properties"]["confidence"]["maximum"] == 1.0

    def test_schema_name_still_reaches_non_anthropic_providers(self, tmp_path: Path) -> None:
        """`schema_name` stays part of the provider interface; only the wire drops it."""
        provider = FakeProvider(json.dumps(VALID_ATTACK_RESPONSE))
        result = provider.complete_json(
            system_prompt="s",
            user_prompt="u",
            schema_name="attack_analyst_response",
            json_schema=AttackAnalystResponse.model_json_schema(),
        )
        assert result.provider == "fake"

    def test_recorded_provider_is_unaffected(self, tmp_path: Path) -> None:
        recorded = run_attack_analyst(
            _attack_request(), FakeProvider(json.dumps(VALID_ATTACK_RESPONSE)), root=tmp_path
        ).artifact_path

        outcome = run_attack_analyst(
            _attack_request(), RecordedProvider(recorded), root=tmp_path / "replay"
        )

        assert outcome.artifact.schema_valid is True
        assert outcome.artifact.provenance.live is False
        assert outcome.artifact.provenance.provider == "recorded"

    def test_contracts_module_exposes_no_sanitation_hook(self) -> None:
        """Provider-specific rewriting must not migrate into the shared contracts."""
        from aegis.genai import contracts

        assert [name for name in dir(contracts) if "sanitiz" in name.lower()] == []


# ---------------------------------------------------------------------------
# 5. what actually goes on the wire
# ---------------------------------------------------------------------------

pytest.importorskip("anthropic", reason="requires the optional `genai` extra")


class _StubTextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _StubResponse:
    stop_reason = "end_turn"
    _request_id = "req_stub_1"

    def __init__(self, text: str) -> None:
        self.content = [_StubTextBlock(text)]


class _RecordingMessages:
    def __init__(self, text: str) -> None:
        self.text = text
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> _StubResponse:
        self.kwargs = kwargs
        return _StubResponse(self.text)


class _RecordingClient:
    def __init__(self, text: str) -> None:
        self.messages = _RecordingMessages(text)


class TestAnthropicRequestPayload:
    """Asserts on the request dict handed to the SDK. Nothing leaves the process."""

    def _provider(self, monkeypatch: pytest.MonkeyPatch, text: str) -> Any:
        from aegis.genai.provider import AnthropicProvider

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-sent")
        monkeypatch.setattr(AnthropicProvider, "_build_client", lambda self: _RecordingClient(text))
        return AnthropicProvider()

    def test_request_schema_is_sanitized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = self._provider(monkeypatch, json.dumps(VALID_BLIND_SPOT_RESPONSE))
        strict = BlindSpotAnalystResponse.model_json_schema()

        provider.complete_json(
            system_prompt="s",
            user_prompt="u",
            schema_name="blind_spot_analyst_response",
            json_schema=strict,
        )

        sent = provider._client.messages.kwargs["output_config"]["format"]
        assert list(iter_unsupported_schema_keywords(sent["schema"])) == []
        # the caller's copy is still strict
        assert {keyword for _, keyword in iter_unsupported_schema_keywords(strict)}

    def test_format_object_carries_no_name_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`output_config.format.name` is rejected: Extra inputs are not permitted."""
        provider = self._provider(monkeypatch, json.dumps(VALID_BLIND_SPOT_RESPONSE))

        provider.complete_json(
            system_prompt="s",
            user_prompt="u",
            schema_name="blind_spot_analyst_response",
            json_schema=BlindSpotAnalystResponse.model_json_schema(),
        )

        sent = provider._client.messages.kwargs["output_config"]["format"]
        assert "name" not in sent
        assert "blind_spot_analyst_response" not in json.dumps(
            provider._client.messages.kwargs["output_config"]
        )

    def test_format_object_shape_is_exact(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Exactly the two keys `anthropic.types.JSONOutputFormatParam` declares."""
        provider = self._provider(monkeypatch, json.dumps(VALID_ATTACK_RESPONSE))

        provider.complete_json(
            system_prompt="s",
            user_prompt="u",
            schema_name="attack_analyst_response",
            json_schema=AttackAnalystResponse.model_json_schema(),
        )

        output_config = provider._client.messages.kwargs["output_config"]
        assert set(output_config) == {"format"}
        assert set(output_config["format"]) == {"type", "schema"}
        assert output_config["format"]["type"] == "json_schema"

    def test_format_matches_the_sdk_param_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Guards against drift: the wire keys must stay a subset of the SDK's."""
        from anthropic.types import JSONOutputFormatParam

        provider = self._provider(monkeypatch, json.dumps(VALID_ATTACK_RESPONSE))
        provider.complete_json(
            system_prompt="s",
            user_prompt="u",
            schema_name="attack_analyst_response",
            json_schema=AttackAnalystResponse.model_json_schema(),
        )

        sent = provider._client.messages.kwargs["output_config"]["format"]
        assert set(sent) <= set(JSONOutputFormatParam.__annotations__)

    def test_full_request_payload_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = self._provider(monkeypatch, json.dumps(VALID_ATTACK_RESPONSE))

        provider.complete_json(
            system_prompt="system text",
            user_prompt="user text",
            schema_name="attack_analyst_response",
            json_schema=AttackAnalystResponse.model_json_schema(),
        )

        request = provider._client.messages.kwargs
        assert set(request) == {
            "model",
            "max_tokens",
            "system",
            "messages",
            "thinking",
            "output_config",
        }
        assert request["system"] == "system text"
        assert request["messages"] == [{"role": "user", "content": "user text"}]
        assert request["thinking"] == {"type": "adaptive"}

    def test_provider_metadata_survives_the_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = self._provider(monkeypatch, json.dumps(VALID_ATTACK_RESPONSE))

        result = provider.complete_json(
            system_prompt="s",
            user_prompt="u",
            schema_name="attack_analyst_response",
            json_schema=AttackAnalystResponse.model_json_schema(),
        )

        assert result.provider == "anthropic"
        assert result.model == provider.model
        assert result.live is True
        assert result.request_id == "req_stub_1"
        assert result.attempts == 1

    def test_request_schema_still_describes_every_field(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = self._provider(monkeypatch, json.dumps(VALID_ATTACK_RESPONSE))
        strict = AttackAnalystResponse.model_json_schema()

        provider.complete_json(
            system_prompt="s",
            user_prompt="u",
            schema_name="attack_analyst_response",
            json_schema=strict,
        )

        sent = provider._client.messages.kwargs["output_config"]["format"]["schema"]
        assert sent["properties"].keys() == strict["properties"].keys()
        assert sent["required"] == strict["required"]
        assert sent["additionalProperties"] is False

    def test_no_output_config_when_no_schema_is_given(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = self._provider(monkeypatch, json.dumps(VALID_ATTACK_RESPONSE))
        provider.complete_json(system_prompt="s", user_prompt="u", schema_name="x")
        assert "output_config" not in provider._client.messages.kwargs
