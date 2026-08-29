"""GenAI -> deterministic mutation handoff (`aegis.loop.genai_handoff`).

These are the safety tests for the one place model output is allowed to
influence what gets generated. Every fixture here is **test-only**: the
`_synthetic_blind_spot_response` helper builds a `BlindSpotAnalystResponse`
in memory to exercise the adapter, and nothing in this file is ever written
to `data/genai/` or rendered as a GenAI artifact. A validated response object
is not a model call, and this suite never claims otherwise.

The load-bearing property under test: bounds are enforced by *rejection*, not
by clamping, and a scenario may only be labeled "GenAI-guided" when the
provenance needed to audit that claim is actually present.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from aegis.genai.contracts import (
    MAX_MUTATION_MAGNITUDE,
    MAX_MUTATION_PROPOSALS,
    BlindSpotAnalystResponse,
    BoundedMutationProposal,
)
from aegis.genai.handoff_contracts import GenAIGuidedGeneration, GenAIHandoffProvenance
from aegis.loop.genai_handoff import (
    GenAIHandoffError,
    apply_blind_spot_proposals,
)
from aegis.shared.contracts import AttackBlueprint, ParameterSpec
from aegis.shared.enums import AttackFamily, MutationDirection, ParameterType

SEED = 20260101


def _blueprint() -> AttackBlueprint:
    """A parent blueprint with one mutable numeric knob, one immutable knob,
    one unbounded knob, and one non-numeric knob -- so every rejection rule
    has something real to fire on."""
    return AttackBlueprint(
        attack_id="synthetic-identity-bustout-v1",
        attack_family=AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT,
        description="Test parent blueprint.",
        objective="Exercise the handoff adapter.",
        parameters={
            "destination_diversity": ParameterSpec(
                name="destination_diversity",
                param_type=ParameterType.INT,
                default=3,
                minimum=1,
                maximum=12,
                mutable=True,
            ),
            "bustout_amount_multiplier": ParameterSpec(
                name="bustout_amount_multiplier",
                param_type=ParameterType.FLOAT,
                default=8.0,
                minimum=1.0,
                maximum=20.0,
                mutable=True,
            ),
            "randomness_seed_offset": ParameterSpec(
                name="randomness_seed_offset",
                param_type=ParameterType.INT,
                default=0,
                minimum=0,
                maximum=100,
                mutable=False,
            ),
            "unbounded_knob": ParameterSpec(
                name="unbounded_knob",
                param_type=ParameterType.FLOAT,
                default=1.0,
                mutable=True,
            ),
            "channel_label": ParameterSpec(
                name="channel_label",
                param_type=ParameterType.STRING,
                default="mobile",
                mutable=True,
            ),
        },
    )


def _provenance(**overrides: Any) -> GenAIHandoffProvenance:
    payload: dict[str, Any] = {
        "genai_run_id": "blind_spot_analyst-testfixture",
        "provider": "anthropic",
        "model": "claude-opus-5",
        "prompt_version": "genai-prompts-v1",
        "live": True,
        "source_confrontation_id": "confrontation-test",
        "detector_model_version": "xgboost-hardened-crossfamily-20260301",
    }
    payload.update(overrides)
    return GenAIHandoffProvenance(**payload)


def _synthetic_blind_spot_response(
    proposals: list[BoundedMutationProposal],
) -> BlindSpotAnalystResponse:
    """TEST-ONLY validated response. Never persisted, never rendered."""
    return BlindSpotAnalystResponse(
        blind_spot_hypothesis="Velocity features under-weight bursts spread across destinations.",
        evidence=["All evasions scored below threshold despite high amounts."],
        mutation_proposals=proposals,
        expected_trade_offs=["More destinations may reduce fidelity."],
        confidence=0.55,
    )


def _increase(parameter: str, magnitude: float = 0.2) -> BoundedMutationProposal:
    return BoundedMutationProposal(
        parameter=parameter,
        direction=MutationDirection.INCREASE,
        magnitude=magnitude,
        rationale="Spread the burst.",
        confidence=0.6,
    )


# ---------------------------------------------------------------------------
# integration: validated response -> adapter -> deterministic blueprint
# ---------------------------------------------------------------------------


class TestHandoffIntegration:
    def test_validated_response_produces_mutated_blueprint(self) -> None:
        parent = _blueprint()
        response = _synthetic_blind_spot_response([_increase("destination_diversity")])

        result = apply_blind_spot_proposals(
            response, parent, seed=SEED, provenance=_provenance()
        )

        assert result.blueprint is not None
        child = result.blueprint
        # Deterministic lineage, one generation on.
        assert child.parent_blueprint_id == parent.attack_id
        assert child.generation == parent.generation + 1
        assert child.attack_family is parent.attack_family
        # The knob actually moved, upward, and stayed inside its declared span.
        spec = parent.parameters["destination_diversity"]
        assert spec.maximum is not None
        new_value = child.parameters["destination_diversity"].default
        assert new_value > spec.default
        assert new_value <= spec.maximum

    def test_adapter_records_what_it_applied(self) -> None:
        response = _synthetic_blind_spot_response([_increase("destination_diversity")])
        result = apply_blind_spot_proposals(
            response, _blueprint(), seed=SEED, provenance=_provenance()
        )

        assert len(result.applied) == 1
        applied = result.applied[0]
        assert applied.parameter == "destination_diversity"
        assert applied.direction is MutationDirection.INCREASE
        assert applied.from_value == 3.0
        assert applied.to_value > applied.from_value
        assert applied.rationale

    def test_genai_never_supplies_the_new_value(self) -> None:
        """The adapter recomputes the value from direction+magnitude using the
        deterministic step, so the model cannot dictate a specific number."""
        parent = _blueprint()
        response = _synthetic_blind_spot_response([_increase("destination_diversity", 0.25)])
        result = apply_blind_spot_proposals(
            response, parent, seed=SEED, provenance=_provenance()
        )
        maximum = parent.parameters["destination_diversity"].maximum
        assert maximum is not None
        assert result.applied[0].to_value <= maximum

    def test_multiple_valid_proposals_all_apply(self) -> None:
        response = _synthetic_blind_spot_response(
            [_increase("destination_diversity"), _increase("bustout_amount_multiplier", 0.1)]
        )
        result = apply_blind_spot_proposals(
            response, _blueprint(), seed=SEED, provenance=_provenance()
        )
        assert {m.parameter for m in result.applied} == {
            "destination_diversity",
            "bustout_amount_multiplier",
        }


# ---------------------------------------------------------------------------
# rejection rules -- reject, never clamp
# ---------------------------------------------------------------------------


class TestMutationRejection:
    def test_unknown_parameter_is_rejected(self) -> None:
        response = _synthetic_blind_spot_response([_increase("not_a_real_parameter")])
        result = apply_blind_spot_proposals(
            response, _blueprint(), seed=SEED, provenance=_provenance()
        )
        assert result.applied == []
        assert result.blueprint is None
        assert "not declared" in result.rejected[0].reason

    def test_immutable_parameter_is_rejected(self) -> None:
        response = _synthetic_blind_spot_response([_increase("randomness_seed_offset")])
        result = apply_blind_spot_proposals(
            response, _blueprint(), seed=SEED, provenance=_provenance()
        )
        assert result.applied == []
        assert "structural" in result.rejected[0].reason

    def test_non_numeric_parameter_is_rejected(self) -> None:
        response = _synthetic_blind_spot_response([_increase("channel_label")])
        result = apply_blind_spot_proposals(
            response, _blueprint(), seed=SEED, provenance=_provenance()
        )
        assert result.applied == []
        assert "not numeric" in result.rejected[0].reason

    def test_unbounded_parameter_is_rejected(self) -> None:
        response = _synthetic_blind_spot_response([_increase("unbounded_knob")])
        result = apply_blind_spot_proposals(
            response, _blueprint(), seed=SEED, provenance=_provenance()
        )
        assert result.applied == []
        assert "no declared bounds" in result.rejected[0].reason

    def test_out_of_range_magnitude_is_rejected_at_the_type(self) -> None:
        with pytest.raises(ValueError):
            BoundedMutationProposal(
                parameter="destination_diversity",
                direction=MutationDirection.INCREASE,
                magnitude=MAX_MUTATION_MAGNITUDE + 0.05,
                rationale="too big",
            )

    def test_out_of_range_magnitude_is_rejected_by_the_adapter_too(self) -> None:
        """Defence in depth: a hand-built object bypassing the field
        constraint must still be refused at the enforcement point."""
        proposal = _increase("destination_diversity")
        object.__setattr__(proposal, "__dict__", {**proposal.__dict__, "magnitude": 0.9})
        response = _synthetic_blind_spot_response([])
        object.__setattr__(
            response, "__dict__", {**response.__dict__, "mutation_proposals": [proposal]}
        )

        result = apply_blind_spot_proposals(
            response, _blueprint(), seed=SEED, provenance=_provenance()
        )
        assert result.applied == []
        assert "outside" in result.rejected[0].reason

    def test_bounds_violation_is_rejected_not_clamped(self) -> None:
        """A clamped mutation would look compliant on disk while still letting
        the model steer the search space."""
        response = _synthetic_blind_spot_response([_increase("randomness_seed_offset")])
        result = apply_blind_spot_proposals(
            response, _blueprint(), seed=SEED, provenance=_provenance()
        )
        assert result.applied == []
        assert result.rejected
        assert result.blueprint is None

    @pytest.mark.parametrize(
        "direction", [MutationDirection.SET, MutationDirection.JITTER, MutationDirection.RESAMPLE]
    )
    def test_unsupported_directions_are_rejected(self, direction: MutationDirection) -> None:
        proposal = BoundedMutationProposal(
            parameter="destination_diversity",
            direction=direction,
            proposed_value=7 if direction is MutationDirection.SET else None,
            magnitude=0.2,
            rationale="unsupported direction",
        )
        result = apply_blind_spot_proposals(
            _synthetic_blind_spot_response([proposal]),
            _blueprint(),
            seed=SEED,
            provenance=_provenance(),
        )
        assert result.applied == []
        assert "not supported" in result.rejected[0].reason

    @pytest.mark.parametrize(
        "payload",
        [
            [{"amount": 900, "to": "acct-1"}, {"amount": 950, "to": "acct-2"}],
            {"transactions": [{"amount": 900}]},
        ],
        ids=["list-of-rows", "dict-of-rows"],
    )
    def test_raw_transaction_payload_never_validates(self, payload: Any) -> None:
        """The one shape that could smuggle rows through: a structured
        `proposed_value` instead of a direction.

        `proposed_value` is a scalar union, so a container is now refused at
        construction -- one layer earlier than the adapter check below.
        """
        with pytest.raises(ValidationError):
            BoundedMutationProposal(
                parameter="destination_diversity",
                direction=MutationDirection.SET,
                proposed_value=payload,
                magnitude=0.1,
                rationale="trying to hand over transaction rows",
            )

    @pytest.mark.parametrize(
        "payload",
        [
            [{"amount": 900, "to": "acct-1"}, {"amount": 950, "to": "acct-2"}],
            {"transactions": [{"amount": 900}]},
        ],
        ids=["list-of-rows", "dict-of-rows"],
    )
    def test_adapter_still_rejects_a_structured_payload(self, payload: Any) -> None:
        """Defence in depth: even a proposal built past validation is refused.

        `model_construct` skips validation the way a hand-built object or a
        future contract loosening would, so the adapter's own structural guard
        stays exercised rather than becoming dead code.
        """
        proposal = BoundedMutationProposal.model_construct(
            parameter="destination_diversity",
            direction=MutationDirection.SET,
            proposed_value=payload,
            magnitude=0.1,
            rationale="trying to hand over transaction rows",
            confidence=0.5,
        )
        result = apply_blind_spot_proposals(
            _synthetic_blind_spot_response([proposal]),
            _blueprint(),
            seed=SEED,
            provenance=_provenance(),
        )
        assert result.applied == []
        assert result.blueprint is None
        assert "structured payload" in result.rejected[0].reason

    def test_one_bad_proposal_does_not_discard_the_good_ones(self) -> None:
        response = _synthetic_blind_spot_response(
            [_increase("destination_diversity"), _increase("randomness_seed_offset")]
        )
        result = apply_blind_spot_proposals(
            response, _blueprint(), seed=SEED, provenance=_provenance()
        )
        assert [m.parameter for m in result.applied] == ["destination_diversity"]
        assert len(result.rejected) == 1


class TestMutationCountLimit:
    def test_too_many_proposals_is_fatal(self) -> None:
        proposals = [
            BoundedMutationProposal(
                parameter=f"knob_{i}",
                direction=MutationDirection.INCREASE,
                magnitude=0.1,
                rationale="filler",
            )
            for i in range(MAX_MUTATION_PROPOSALS + 1)
        ]
        # The response model caps the list too; build past it deliberately.
        response = _synthetic_blind_spot_response([])
        object.__setattr__(
            response, "__dict__", {**response.__dict__, "mutation_proposals": proposals}
        )
        with pytest.raises(GenAIHandoffError):
            apply_blind_spot_proposals(
                response, _blueprint(), seed=SEED, provenance=_provenance()
            )

    def test_response_model_caps_proposal_count(self) -> None:
        with pytest.raises(ValueError):
            BlindSpotAnalystResponse(
                blind_spot_hypothesis="too many",
                mutation_proposals=[
                    BoundedMutationProposal(
                        parameter=f"knob_{i}",
                        direction=MutationDirection.INCREASE,
                        magnitude=0.1,
                        rationale="filler",
                    )
                    for i in range(MAX_MUTATION_PROPOSALS + 1)
                ],
                confidence=0.5,
            )

    def test_custom_lower_limit_is_honoured(self) -> None:
        response = _synthetic_blind_spot_response(
            [_increase("destination_diversity"), _increase("bustout_amount_multiplier", 0.1)]
        )
        with pytest.raises(GenAIHandoffError):
            apply_blind_spot_proposals(
                response,
                _blueprint(),
                seed=SEED,
                provenance=_provenance(),
                max_proposals=1,
            )


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_seed_and_mutation_reproduce_the_same_blueprint(self) -> None:
        parent = _blueprint()
        response = _synthetic_blind_spot_response([_increase("destination_diversity")])

        first = apply_blind_spot_proposals(
            response, parent, seed=SEED, provenance=_provenance()
        )
        second = apply_blind_spot_proposals(
            response, parent, seed=SEED, provenance=_provenance()
        )

        assert first.blueprint is not None and second.blueprint is not None
        assert first.blueprint.attack_id == second.blueprint.attack_id
        assert first.blueprint.default_parameters() == second.blueprint.default_parameters()

    def test_different_seed_yields_a_different_blueprint_id(self) -> None:
        parent = _blueprint()
        response = _synthetic_blind_spot_response([_increase("destination_diversity")])
        a = apply_blind_spot_proposals(response, parent, seed=SEED, provenance=_provenance())
        b = apply_blind_spot_proposals(response, parent, seed=SEED + 1, provenance=_provenance())
        assert a.blueprint is not None and b.blueprint is not None
        assert a.blueprint.attack_id != b.blueprint.attack_id
        # Same parameter values -- only the identity differs, as intended.
        assert a.blueprint.default_parameters() == b.blueprint.default_parameters()

    def test_seed_is_recorded_on_provenance(self) -> None:
        result = apply_blind_spot_proposals(
            _synthetic_blind_spot_response([_increase("destination_diversity")]),
            _blueprint(),
            seed=SEED,
            provenance=_provenance(),
        )
        assert result.provenance.seed == SEED


# ---------------------------------------------------------------------------
# dry-run / preview
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_still_previews_the_blueprint(self) -> None:
        result = apply_blind_spot_proposals(
            _synthetic_blind_spot_response([_increase("destination_diversity")]),
            _blueprint(),
            seed=SEED,
            provenance=_provenance(),
            dry_run=True,
        )
        assert result.dry_run is True
        assert result.blueprint is not None
        assert result.applied

    def test_dry_run_matches_the_real_run_exactly(self) -> None:
        parent = _blueprint()
        response = _synthetic_blind_spot_response([_increase("destination_diversity")])
        preview = apply_blind_spot_proposals(
            response, parent, seed=SEED, provenance=_provenance(), dry_run=True
        )
        real = apply_blind_spot_proposals(
            response, parent, seed=SEED, provenance=_provenance(), dry_run=False
        )
        assert preview.blueprint is not None and real.blueprint is not None
        assert preview.blueprint.attack_id == real.blueprint.attack_id


# ---------------------------------------------------------------------------
# provenance
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_provider_model_prompt_and_source_survive_the_adapter(self) -> None:
        result = apply_blind_spot_proposals(
            _synthetic_blind_spot_response([_increase("destination_diversity")]),
            _blueprint(),
            seed=SEED,
            provenance=_provenance(),
        )
        p = result.provenance
        assert p.genai_run_id == "blind_spot_analyst-testfixture"
        assert p.provider == "anthropic"
        assert p.model == "claude-opus-5"
        assert p.prompt_version == "genai-prompts-v1"
        assert p.source_confrontation_id == "confrontation-test"
        assert p.detector_model_version == "xgboost-hardened-crossfamily-20260301"

    def test_provenance_is_stamped_onto_the_child_blueprint(self) -> None:
        result = apply_blind_spot_proposals(
            _synthetic_blind_spot_response([_increase("destination_diversity")]),
            _blueprint(),
            seed=SEED,
            provenance=_provenance(),
        )
        assert result.blueprint is not None
        meta = result.blueprint.metadata
        assert meta["genai_guided"] is True
        assert meta["genai_run_id"] == "blind_spot_analyst-testfixture"
        assert meta["genai_model"] == "claude-opus-5"
        assert meta["genai_prompt_version"] == "genai-prompts-v1"
        assert meta["mutation_seed"] == SEED

    def test_missing_provenance_blocks_genai_guided_labeling(self) -> None:
        """No run id / provider / model / prompt version means nothing can be
        audited, so the result is a mutation -- not a GenAI-guided one."""
        result = apply_blind_spot_proposals(
            _synthetic_blind_spot_response([_increase("destination_diversity")]),
            _blueprint(),
            seed=SEED,
            provenance=GenAIHandoffProvenance(),
        )
        assert result.applied
        assert result.provenance.is_complete is False
        assert result.is_genai_guided is False
        assert result.blueprint is not None
        assert result.blueprint.metadata["genai_guided"] is False

    @pytest.mark.parametrize(
        "missing", ["genai_run_id", "provider", "model", "prompt_version"]
    )
    def test_any_single_missing_provenance_field_blocks_the_label(self, missing: str) -> None:
        result = apply_blind_spot_proposals(
            _synthetic_blind_spot_response([_increase("destination_diversity")]),
            _blueprint(),
            seed=SEED,
            provenance=_provenance(**{missing: ""}),
        )
        assert result.is_genai_guided is False

    def test_no_applied_mutation_blocks_the_label_even_with_provenance(self) -> None:
        result = apply_blind_spot_proposals(
            _synthetic_blind_spot_response([_increase("randomness_seed_offset")]),
            _blueprint(),
            seed=SEED,
            provenance=_provenance(),
        )
        assert result.provenance.is_complete is True
        assert result.is_genai_guided is False

    def test_recorded_reasoning_cannot_be_presented_as_live(self) -> None:
        """A replayed run keeps live=False all the way through the adapter."""
        result = apply_blind_spot_proposals(
            _synthetic_blind_spot_response([_increase("destination_diversity")]),
            _blueprint(),
            seed=SEED,
            provenance=_provenance(provider="recorded", live=False),
        )
        assert result.provenance.live is False
        assert result.provenance.is_live_genai is False
        # Still auditable and still guided -- just not a live model call.
        assert result.is_genai_guided is True
        assert result.blueprint is not None
        assert result.blueprint.metadata["genai_live"] is False

    def test_live_flag_requires_complete_provenance(self) -> None:
        incomplete_but_live = GenAIHandoffProvenance(live=True)
        assert incomplete_but_live.is_live_genai is False


class TestGuidedGenerationArtifact:
    def test_artifact_requires_provenance_and_mutations_to_be_labelled(self) -> None:
        record = GenAIGuidedGeneration(
            generation_id="gen-1",
            provenance=GenAIHandoffProvenance(),
            applied_mutations=[],
        )
        assert record.is_genai_guided is False

    def test_artifact_defaults_to_dry_run(self) -> None:
        record = GenAIGuidedGeneration(
            generation_id="gen-1", provenance=_provenance()
        )
        assert record.dry_run is True
        assert record.scenario_id is None
