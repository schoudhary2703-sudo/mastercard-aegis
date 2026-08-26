"""Tests for the GenAI reasoning layer (`aegis.genai`).

No test here makes a network call or needs `ANTHROPIC_API_KEY`. Provider
behaviour is exercised through small fakes implementing `GenAIProvider`, so
the schema-validation, bounds-enforcement, provenance, and failure paths are
all testable in a fresh clone with no optional extras installed.

The load-bearing assertion across this file is the one the judge-facing claim
depends on: there is no code path that returns plausible-looking reasoning
when the provider is missing, fails, or replies with junk.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aegis.genai import (
    MAX_MUTATION_MAGNITUDE,
    AttackAnalystRequest,
    AttackAnalystResponse,
    BlindSpotAnalystRequest,
    BlindSpotAnalystResponse,
    BoundedMutationProposal,
    GenAIConfigurationError,
    GenAIProviderError,
    GenAISchemaError,
    MutationBoundsError,
    ProviderResult,
    RecordedProvider,
    build_provider,
    build_run_id,
    read_run_artifact,
    run_attack_analyst,
    run_blind_spot_analyst,
)
from aegis.genai.analysts import (
    ATTACK_ANALYST_STAGE,
    BLIND_SPOT_ANALYST_STAGE,
    enforce_mutation_bounds,
)
from aegis.genai.prompts import (
    PROMPT_VERSION,
    attack_analyst_user_prompt,
    blind_spot_analyst_user_prompt,
)
from aegis.genai.provider import GenAIProvider
from aegis.shared.enums import AttackFamily, MutationDirection

# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------


class FakeProvider(GenAIProvider):
    """Returns a canned raw string; records the prompts it was given."""

    def __init__(self, text: str, *, live: bool = True, name: str = "fake") -> None:
        self.name = name
        self.model = "fake-model-1"
        self._text = text
        self.live = live
        self.system_prompt: str | None = None
        self.user_prompt: str | None = None
        self.json_schema: dict[str, Any] | None = None
        self.calls = 0

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, Any] | None = None,
    ) -> ProviderResult:
        self.calls += 1
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.json_schema = json_schema
        return ProviderResult(
            text=self._text,
            provider=self.name,
            model=self.model,
            live=self.live,
            request_id="req_fake_123",
            latency_ms=12.5,
            attempts=1,
        )


class FailingProvider(GenAIProvider):
    """Always raises, as a real provider would after exhausting retries."""

    def __init__(self, *, attempts: int = 3) -> None:
        self.name = "fake-failing"
        self.model = "fake-model-1"
        self._attempts = attempts

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, Any] | None = None,
    ) -> ProviderResult:
        raise GenAIProviderError("simulated upstream outage", attempts=self._attempts)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

MUTABLE_PARAMETERS = ["bustout_amount_multiplier", "bustout_window_hours", "destination_diversity"]


def _attack_request() -> AttackAnalystRequest:
    return AttackAnalystRequest(
        scenario_name="Synthetic identity bust-out",
        research_summary="An identity builds benign history, then drains value in a burst.",
        payment_context="A PaySim-derived mobile-money world.",
        known_constraints=["Synthetic data only."],
        available_simulator_parameters=MUTABLE_PARAMETERS,
    )


def _blind_spot_request(**overrides: Any) -> BlindSpotAnalystRequest:
    payload: dict[str, Any] = {
        "blueprint_id": "synthetic-identity-bustout-v1",
        "attack_family": AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT,
        "detector_model_version": "xgboost-baseline-fixture",
        "detector_threshold": 0.9885,
        "missed_transaction_count": 3,
        "caught_transaction_count": 0,
        "observed_risk_scores": [0.11, 0.36, 0.45],
        "important_signals": ["temporal.amount", "temporal.source_velocity_1h"],
        "fidelity_score": 0.83,
        "mutable_parameters": MUTABLE_PARAMETERS,
        "detector_context": "XGBoost over decision-time-safe temporal features.",
    }
    payload.update(overrides)
    return BlindSpotAnalystRequest(**payload)


VALID_ATTACK_RESPONSE: dict[str, Any] = {
    "attack_family": "synthetic_identity_bustout",
    "attack_hypothesis": "Cultivate benign history, then burst across diverse destinations.",
    "genai_enablement": "Generative tooling drafts plausible warm-up behaviour cheaply.",
    "payment_system_assumptions": ["Account tenure is treated as implicit trust."],
    "observable_signals": ["temporal.amount", "temporal.source_velocity_1h"],
    "recommended_simulator_parameters": [
        {
            "name": "bustout_amount_multiplier",
            "value": 6.5,
            "rationale": "Large enough to matter, small enough to stay plausible.",
            "unit": None,
        }
    ],
    "realism_risks": ["Too large a multiplier produces implausible amounts."],
    "safety_constraints": ["Synthetic data only."],
    "confidence": 0.62,
}

VALID_BLIND_SPOT_RESPONSE: dict[str, Any] = {
    "blind_spot_hypothesis": "Velocity features under-weight bursts spread across destinations.",
    "evidence": ["All three evasions scored below 0.5 despite high amounts."],
    "mutation_proposals": [
        {
            "parameter": "destination_diversity",
            "direction": "increase",
            "proposed_value": None,
            "magnitude": 0.2,
            "rationale": "Spread the burst so per-destination velocity stays low.",
            "confidence": 0.6,
        }
    ],
    "expected_trade_offs": ["More destinations may reduce fidelity."],
    "safety_constraints": ["Synthetic data only."],
    "confidence": 0.55,
}


# ---------------------------------------------------------------------------
# schema validation
# ---------------------------------------------------------------------------


class TestValidStructuredResponses:
    def test_attack_analyst_accepts_valid_response(self, tmp_path: Path) -> None:
        provider = FakeProvider(json.dumps(VALID_ATTACK_RESPONSE))
        outcome = run_attack_analyst(_attack_request(), provider, root=tmp_path)

        assert isinstance(outcome.response, AttackAnalystResponse)
        assert outcome.response.attack_family is AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT
        assert outcome.artifact.schema_valid is True
        assert outcome.artifact.failure is None

    def test_blind_spot_accepts_valid_response(self, tmp_path: Path) -> None:
        provider = FakeProvider(json.dumps(VALID_BLIND_SPOT_RESPONSE))
        outcome = run_blind_spot_analyst(_blind_spot_request(), provider, root=tmp_path)

        assert isinstance(outcome.response, BlindSpotAnalystResponse)
        assert outcome.response.mutation_proposals[0].parameter == "destination_diversity"
        assert outcome.artifact.schema_valid is True

    def test_markdown_fenced_json_is_tolerated(self, tmp_path: Path) -> None:
        fenced = "```json\n" + json.dumps(VALID_ATTACK_RESPONSE) + "\n```"
        outcome = run_attack_analyst(_attack_request(), FakeProvider(fenced), root=tmp_path)
        assert outcome.artifact.schema_valid is True

    def test_json_schema_is_passed_to_provider(self, tmp_path: Path) -> None:
        provider = FakeProvider(json.dumps(VALID_ATTACK_RESPONSE))
        run_attack_analyst(_attack_request(), provider, root=tmp_path)
        assert provider.json_schema is not None
        assert "attack_hypothesis" in provider.json_schema["properties"]


class TestMalformedResponseRejection:
    @pytest.mark.parametrize(
        "bad_text",
        [
            "this is not json at all",
            "[1, 2, 3]",
            '{"attack_family": "not_a_real_family"}',
            json.dumps({**VALID_ATTACK_RESPONSE, "confidence": 1.7}),
            json.dumps(
                {k: v for k, v in VALID_ATTACK_RESPONSE.items() if k != "attack_hypothesis"}
            ),
            json.dumps({**VALID_ATTACK_RESPONSE, "undeclared_extra_field": "smuggled"}),
        ],
    )
    def test_attack_analyst_rejects_malformed(self, tmp_path: Path, bad_text: str) -> None:
        with pytest.raises(GenAISchemaError):
            run_attack_analyst(_attack_request(), FakeProvider(bad_text), root=tmp_path)

    def test_rejects_response_that_smuggles_transaction_rows(self, tmp_path: Path) -> None:
        """The architectural rule: GenAI proposes parameters, never rows."""
        payload = {
            **VALID_ATTACK_RESPONSE,
            "recommended_simulator_parameters": [
                {
                    "name": "transactions",
                    "value": "[{amount: 900}, {amount: 950}]",
                    "rationale": "Trying to emit rows directly.",
                    "unit": None,
                }
            ],
        }
        with pytest.raises(GenAISchemaError):
            run_attack_analyst(_attack_request(), FakeProvider(json.dumps(payload)), root=tmp_path)

    def test_malformed_response_persists_failure_artifact_with_raw_text(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(GenAISchemaError):
            run_attack_analyst(_attack_request(), FakeProvider("garbage"), root=tmp_path)

        written = list((tmp_path / "data" / "genai" / ATTACK_ANALYST_STAGE).glob("*.json"))
        assert len(written) == 1
        artifact = read_run_artifact(written[0])
        assert artifact.schema_valid is False
        assert artifact.response is None
        assert artifact.failure is not None and artifact.failure.startswith("schema_error")
        # The exact text that failed is kept, not a paraphrase of it.
        assert artifact.raw_response_text == "garbage"


# ---------------------------------------------------------------------------
# provider configuration + failure
# ---------------------------------------------------------------------------


class TestMissingApiKeyBehaviour:
    def test_anthropic_provider_without_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("AEGIS_GENAI_PROVIDER", raising=False)
        with pytest.raises(GenAIConfigurationError) as excinfo:
            build_provider("anthropic")
        # The error must point the user at the two real options, not paper over it.
        assert "ANTHROPIC_API_KEY" in str(excinfo.value)
        assert "recorded" in str(excinfo.value)

    def test_missing_key_never_yields_a_working_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No silent fake fallback: absence of a key must not produce reasoning."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("AEGIS_GENAI_PROVIDER", raising=False)
        with pytest.raises(GenAIConfigurationError):
            build_provider(None)

    def test_unknown_provider_name_raises(self) -> None:
        with pytest.raises(GenAIConfigurationError):
            build_provider("some-other-llm")

    def test_recorded_provider_requires_an_artifact(self) -> None:
        with pytest.raises(GenAIConfigurationError):
            build_provider("recorded", recorded_artifact=None)


class TestProviderFailure:
    def test_provider_error_propagates(self, tmp_path: Path) -> None:
        with pytest.raises(GenAIProviderError):
            run_attack_analyst(_attack_request(), FailingProvider(), root=tmp_path)

    def test_provider_error_persists_failure_artifact_with_attempts(self, tmp_path: Path) -> None:
        with pytest.raises(GenAIProviderError):
            run_blind_spot_analyst(
                _blind_spot_request(), FailingProvider(attempts=3), root=tmp_path
            )

        written = list((tmp_path / "data" / "genai" / BLIND_SPOT_ANALYST_STAGE).glob("*.json"))
        assert len(written) == 1
        artifact = read_run_artifact(written[0])
        assert artifact.schema_valid is False
        assert artifact.response is None
        assert "provider_error" in (artifact.failure or "")
        # Retry/timeout accounting survives onto the artifact.
        assert artifact.provenance.attempts == 3

    def test_failure_artifact_carries_no_response_payload(self, tmp_path: Path) -> None:
        """A failed run must not leave anything a reader could mistake for output."""
        with pytest.raises(GenAIProviderError):
            run_attack_analyst(_attack_request(), FailingProvider(), root=tmp_path)
        written = list((tmp_path / "data" / "genai" / ATTACK_ANALYST_STAGE).glob("*.json"))
        payload = json.loads(written[0].read_text(encoding="utf-8"))
        assert payload["response"] is None
        assert payload["schema_valid"] is False


# ---------------------------------------------------------------------------
# mutation bounds
# ---------------------------------------------------------------------------


class TestMutationBounds:
    def test_magnitude_above_ceiling_is_rejected_at_the_type(self) -> None:
        with pytest.raises(ValueError):
            BoundedMutationProposal(
                parameter="destination_diversity",
                direction=MutationDirection.INCREASE,
                magnitude=MAX_MUTATION_MAGNITUDE + 0.01,
                rationale="too big",
            )

    def test_magnitude_at_ceiling_is_allowed(self) -> None:
        proposal = BoundedMutationProposal(
            parameter="destination_diversity",
            direction=MutationDirection.INCREASE,
            magnitude=MAX_MUTATION_MAGNITUDE,
            rationale="exactly at the bound",
        )
        assert proposal.magnitude == MAX_MUTATION_MAGNITUDE

    def test_oversized_magnitude_fails_the_whole_run(self, tmp_path: Path) -> None:
        payload = {
            **VALID_BLIND_SPOT_RESPONSE,
            "mutation_proposals": [
                {**VALID_BLIND_SPOT_RESPONSE["mutation_proposals"][0], "magnitude": 0.9}
            ],
        }
        with pytest.raises(GenAISchemaError):
            run_blind_spot_analyst(
                _blind_spot_request(), FakeProvider(json.dumps(payload)), root=tmp_path
            )

    def test_proposal_on_non_mutable_parameter_is_rejected(self, tmp_path: Path) -> None:
        payload = {
            **VALID_BLIND_SPOT_RESPONSE,
            "mutation_proposals": [
                {
                    **VALID_BLIND_SPOT_RESPONSE["mutation_proposals"][0],
                    "parameter": "randomness_seed_offset",
                }
            ],
        }
        with pytest.raises(MutationBoundsError):
            run_blind_spot_analyst(
                _blind_spot_request(), FakeProvider(json.dumps(payload)), root=tmp_path
            )

    def test_bounds_violation_is_rejected_not_clamped(self, tmp_path: Path) -> None:
        """Clamping would let the model steer while looking compliant on disk."""
        payload = {
            **VALID_BLIND_SPOT_RESPONSE,
            "mutation_proposals": [
                {
                    **VALID_BLIND_SPOT_RESPONSE["mutation_proposals"][0],
                    "parameter": "not_a_declared_parameter",
                }
            ],
        }
        with pytest.raises(MutationBoundsError):
            run_blind_spot_analyst(
                _blind_spot_request(), FakeProvider(json.dumps(payload)), root=tmp_path
            )
        written = list((tmp_path / "data" / "genai" / BLIND_SPOT_ANALYST_STAGE).glob("*.json"))
        artifact = read_run_artifact(written[0])
        assert artifact.response is None
        assert "mutation_bounds_error" in (artifact.failure or "")

    def test_proposals_without_any_mutable_parameters_are_rejected(self) -> None:
        response = BlindSpotAnalystResponse.model_validate(VALID_BLIND_SPOT_RESPONSE)
        with pytest.raises(MutationBoundsError):
            enforce_mutation_bounds(response, [])

    def test_duplicate_parameter_proposals_are_rejected(self) -> None:
        duplicate = VALID_BLIND_SPOT_RESPONSE["mutation_proposals"][0]
        with pytest.raises(ValueError):
            BlindSpotAnalystResponse.model_validate(
                {**VALID_BLIND_SPOT_RESPONSE, "mutation_proposals": [duplicate, duplicate]}
            )

    def test_set_direction_requires_a_value(self) -> None:
        with pytest.raises(ValueError):
            BoundedMutationProposal(
                parameter="destination_diversity",
                direction=MutationDirection.SET,
                rationale="no value supplied",
            )


# ---------------------------------------------------------------------------
# provenance + prompt versioning
# ---------------------------------------------------------------------------


class TestArtifactProvenance:
    def test_artifact_records_provider_model_and_liveness(self, tmp_path: Path) -> None:
        provider = FakeProvider(json.dumps(VALID_ATTACK_RESPONSE))
        outcome = run_attack_analyst(
            _attack_request(), provider, root=tmp_path, source_artifacts=["taxonomy:bustout"]
        )
        prov = outcome.artifact.provenance
        assert prov.provider == "fake"
        assert prov.model == "fake-model-1"
        assert prov.live is True
        assert prov.request_id == "req_fake_123"
        assert prov.latency_ms == 12.5
        assert prov.source_artifacts == ["taxonomy:bustout"]

    def test_prompt_version_is_persisted(self, tmp_path: Path) -> None:
        outcome = run_attack_analyst(
            _attack_request(), FakeProvider(json.dumps(VALID_ATTACK_RESPONSE)), root=tmp_path
        )
        assert outcome.artifact.provenance.prompt_version == PROMPT_VERSION
        on_disk = read_run_artifact(outcome.artifact_path)
        assert on_disk.provenance.prompt_version == PROMPT_VERSION

    def test_artifact_path_is_stage_scoped_and_round_trips(self, tmp_path: Path) -> None:
        outcome = run_blind_spot_analyst(
            _blind_spot_request(),
            FakeProvider(json.dumps(VALID_BLIND_SPOT_RESPONSE)),
            root=tmp_path,
        )
        assert outcome.artifact_path.parent.name == BLIND_SPOT_ANALYST_STAGE
        assert read_run_artifact(outcome.artifact_path).run_id == outcome.artifact.run_id

    def test_run_id_changes_with_prompt_version(self) -> None:
        request = {"scenario_name": "x"}
        first = build_run_id(
            stage="attack_analyst", request=request, prompt_version="v1", model="m"
        )
        second = build_run_id(
            stage="attack_analyst", request=request, prompt_version="v2", model="m"
        )
        assert first != second

    def test_run_id_changes_with_model(self) -> None:
        request = {"scenario_name": "x"}
        first = build_run_id(
            stage="attack_analyst", request=request, prompt_version="v1", model="model-a"
        )
        second = build_run_id(
            stage="attack_analyst", request=request, prompt_version="v1", model="model-b"
        )
        assert first != second

    def test_request_is_persisted_alongside_response(self, tmp_path: Path) -> None:
        outcome = run_attack_analyst(
            _attack_request(), FakeProvider(json.dumps(VALID_ATTACK_RESPONSE)), root=tmp_path
        )
        assert outcome.artifact.request["scenario_name"] == "Synthetic identity bust-out"
        assert outcome.artifact.response is not None


class TestRecordedProviderIsAlwaysLabelled:
    def _record(self, tmp_path: Path) -> Path:
        outcome = run_attack_analyst(
            _attack_request(), FakeProvider(json.dumps(VALID_ATTACK_RESPONSE)), root=tmp_path
        )
        return outcome.artifact_path

    def test_replayed_run_is_marked_not_live(self, tmp_path: Path) -> None:
        recorded_path = self._record(tmp_path)
        replay_root = tmp_path / "replay"
        provider = RecordedProvider(recorded_path)

        outcome = run_attack_analyst(_attack_request(), provider, root=replay_root)

        assert outcome.artifact.schema_valid is True
        # The judge-facing distinction: a replay can never look like a live call.
        assert outcome.artifact.provenance.live is False
        assert outcome.artifact.provenance.provider == "recorded"

    def test_recorded_provider_rejects_artifact_without_response(self, tmp_path: Path) -> None:
        broken = tmp_path / "broken.json"
        broken.write_text(json.dumps({"run_id": "x", "response": None}), encoding="utf-8")
        with pytest.raises(GenAIConfigurationError):
            RecordedProvider(broken)

    def test_recorded_provider_rejects_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(GenAIConfigurationError):
            RecordedProvider(tmp_path / "does-not-exist.json")


# ---------------------------------------------------------------------------
# prompt construction
# ---------------------------------------------------------------------------


class TestPrompts:
    def test_prompts_state_the_no_transaction_rows_rule(self, tmp_path: Path) -> None:
        provider = FakeProvider(json.dumps(VALID_ATTACK_RESPONSE))
        run_attack_analyst(_attack_request(), provider, root=tmp_path)
        assert provider.system_prompt is not None
        assert "never write transaction rows" in provider.system_prompt.lower()

    def test_blind_spot_prompt_names_the_allowed_parameters(self) -> None:
        prompt = blind_spot_analyst_user_prompt(_blind_spot_request())
        for name in MUTABLE_PARAMETERS:
            assert name in prompt

    def test_blind_spot_prompt_states_the_magnitude_ceiling(self) -> None:
        prompt = blind_spot_analyst_user_prompt(_blind_spot_request())
        assert str(MAX_MUTATION_MAGNITUDE) in prompt

    def test_attack_prompt_is_deterministic_for_identical_input(self) -> None:
        assert attack_analyst_user_prompt(_attack_request()) == attack_analyst_user_prompt(
            _attack_request()
        )
