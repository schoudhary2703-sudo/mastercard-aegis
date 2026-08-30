"""Per-family GenAI coverage, and the multi-family guided-generation path.

Two things are pinned here.

**Coverage honesty** (`aegis.genai.coverage`): a family counts as covered only
when its artifact is live *and* schema-valid, coverage never leaks across
families, and every gap carries a reason instead of a blank.

**Multi-family plumbing** (`scripts.run_genai_guided_generation`): the guided
pipeline dispatches to each family's own generator and evaluator. These tests
use a TEST-ONLY `BlindSpotAnalystResponse` built in memory -- nothing here is
persisted as GenAI evidence, no provider is constructed, and no live artifact
is implied for any family.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from scripts.run_genai_guided_generation import _build_generator, _fidelity_of, _fraud_count_of

from aegis.genai.contracts import BlindSpotAnalystResponse, BoundedMutationProposal
from aegis.genai.coverage import (
    ATTACK_ANALYST_STAGE,
    BLIND_SPOT_ANALYST_STAGE,
    build_family_coverage,
)
from aegis.genai.handoff_contracts import GenAIHandoffProvenance
from aegis.identify import build_synthetic_identity_blueprint
from aegis.loop.genai_handoff import apply_blind_spot_proposals
from aegis.shared.contracts import AttackBlueprint
from aegis.shared.enums import AttackFamily, MutationDirection

MULE_CONFRONTATION = Path("data/synthetic/mule_confrontations/mule-confrontation-020370716736fb95")
ADAPTIVE_CONFRONTATION = Path(
    "data/synthetic/adaptive_evasion_confrontations/"
    "adaptive-evasion-confrontation-e4a1c07bb4038843"
)
SNAPSHOT = Path("data/reports/generation_reference_snapshot.json")
SEED = 20261101


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------


def _run_artifact(
    root: Path,
    *,
    stage: str,
    run_id: str,
    family: AttackFamily,
    live: bool = True,
    schema_valid: bool = True,
) -> None:
    path = root / "data" / "genai" / stage / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "stage": stage,
                "created_at": "2026-08-29T21:00:00Z",
                "provenance": {
                    "provider": "anthropic" if live else "recorded",
                    "model": "claude-opus-5",
                    "prompt_version": "genai-prompts-v1",
                    "live": live,
                    "attempts": 1,
                },
                "request": {"attack_family": family.value},
                "response": {"attack_family": family.value},
                "schema_valid": schema_valid,
            }
        ),
        encoding="utf-8",
    )


def _guided_artifact(
    root: Path, *, family: AttackFamily, applied: int = 1, generation_id: str = "gen-1"
) -> None:
    path = root / "data" / "genai" / "guided_generations" / f"{generation_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    mutations = [
        {
            "parameter": f"p{index}",
            "direction": "increase",
            "magnitude": 0.2,
            "from_value": 1.0,
            "to_value": 2.0,
        }
        for index in range(applied)
    ]
    path.write_text(
        json.dumps(
            {
                "generation_id": generation_id,
                "created_at": "2026-08-29T22:00:00Z",
                "attack_family": family.value,
                "provenance": {
                    "genai_run_id": "blind-1",
                    "provider": "anthropic",
                    "model": "claude-opus-5",
                    "prompt_version": "genai-prompts-v1",
                    "live": True,
                    "seed": SEED,
                    "detector_model_version": "xgboost-hardened-crossfamily-20260301",
                },
                "applied_mutations": mutations,
                "rejected_mutations": [],
                "scenario_id": "scenario-fixture",
                "fraud_count": 3,
                "caught_count": 2,
                "escaped_count": 1,
                "recall": 0.667,
                "fidelity_score": 0.88,
                "runtime_seconds": 0.2,
                "hardest_survivor": {"transaction_id": "txn-1"},
                "dry_run": False,
            }
        ),
        encoding="utf-8",
    )


class TestCoverageReadsOnlyWhatExists:
    def test_empty_root_reports_three_uncovered_families(self, tmp_path: Path) -> None:
        summary = build_family_coverage(tmp_path)
        assert len(summary.families) == 3
        assert summary.live_family_count == 0
        assert summary.guided_family_count == 0
        assert all(not f.has_live_genai for f in summary.families)
        assert all(f.attack_analyst.reason for f in summary.families)

    def test_live_run_covers_only_its_own_family(self, tmp_path: Path) -> None:
        _run_artifact(
            tmp_path,
            stage=ATTACK_ANALYST_STAGE,
            run_id="attack-1",
            family=AttackFamily.MULE_NETWORK_STRUCTURING,
        )
        by_family = {f.attack_family: f for f in build_family_coverage(tmp_path).families}

        assert by_family[AttackFamily.MULE_NETWORK_STRUCTURING].attack_analyst.available is True
        assert by_family[AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT].attack_analyst.available is False
        assert by_family[AttackFamily.ADAPTIVE_DETECTOR_EVASION].attack_analyst.available is False

    def test_recorded_run_is_never_counted_as_covered(self, tmp_path: Path) -> None:
        _run_artifact(
            tmp_path,
            stage=BLIND_SPOT_ANALYST_STAGE,
            run_id="blind-recorded",
            family=AttackFamily.MULE_NETWORK_STRUCTURING,
            live=False,
        )
        summary = build_family_coverage(tmp_path)
        blind = next(
            f for f in summary.families if f.attack_family is AttackFamily.MULE_NETWORK_STRUCTURING
        ).blind_spot_analyst

        assert blind.available is False
        assert "live" in blind.reason
        assert summary.live_family_count == 0

    def test_failed_run_is_never_counted_as_covered(self, tmp_path: Path) -> None:
        _run_artifact(
            tmp_path,
            stage=BLIND_SPOT_ANALYST_STAGE,
            run_id="blind-failed",
            family=AttackFamily.ADAPTIVE_DETECTOR_EVASION,
            schema_valid=False,
        )
        summary = build_family_coverage(tmp_path)
        assert summary.live_family_count == 0

    def test_full_coverage_requires_all_three_stages(self, tmp_path: Path) -> None:
        family = AttackFamily.ADAPTIVE_DETECTOR_EVASION
        _run_artifact(tmp_path, stage=ATTACK_ANALYST_STAGE, run_id="a", family=family)
        _run_artifact(tmp_path, stage=BLIND_SPOT_ANALYST_STAGE, run_id="b", family=family)
        partial = build_family_coverage(tmp_path)
        assert partial.fully_covered_family_count == 0

        _guided_artifact(tmp_path, family=family)
        full = build_family_coverage(tmp_path)
        assert full.fully_covered_family_count == 1
        assert full.guided_family_count == 1

    def test_guided_without_a_surviving_mutation_is_not_covered(self, tmp_path: Path) -> None:
        family = AttackFamily.MULE_NETWORK_STRUCTURING
        _guided_artifact(tmp_path, family=family, applied=0)
        guided = next(
            f for f in build_family_coverage(tmp_path).families if f.attack_family is family
        ).guided_generation
        assert guided.available is False
        assert "no mutation survived" in guided.reason

    def test_every_gap_carries_a_reason(self, tmp_path: Path) -> None:
        for family in build_family_coverage(tmp_path).families:
            assert family.attack_analyst.reason
            assert family.blind_spot_analyst.reason
            assert family.guided_generation.reason

    def test_malformed_artifact_is_skipped_not_counted(self, tmp_path: Path) -> None:
        path = tmp_path / "data" / "genai" / ATTACK_ANALYST_STAGE / "broken.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        assert build_family_coverage(tmp_path).live_family_count == 0


# ---------------------------------------------------------------------------
# multi-family guided plumbing
# ---------------------------------------------------------------------------


def _response(*proposals: BoundedMutationProposal) -> BlindSpotAnalystResponse:
    """TEST-ONLY. Never persisted; implies no live artifact for any family."""
    return BlindSpotAnalystResponse(
        blind_spot_hypothesis="Test-only hypothesis for the dispatch plumbing.",
        mutation_proposals=list(proposals),
        confidence=0.5,
    )


def _increase(parameter: str, magnitude: float = 0.2) -> BoundedMutationProposal:
    return BoundedMutationProposal(
        parameter=parameter,
        direction=MutationDirection.INCREASE,
        magnitude=magnitude,
        rationale="test-only bounded step",
    )


def _provenance() -> GenAIHandoffProvenance:
    return GenAIHandoffProvenance(
        genai_run_id="test-only-fixture",
        provider="test",
        model="test-model",
        prompt_version="test",
        live=False,
    )


def _blueprint(confrontation_dir: Path) -> AttackBlueprint:
    for name in ("blueprint.json", "adapted_blueprint.json"):
        path = confrontation_dir / name
        if path.is_file():
            return AttackBlueprint.model_validate_json(path.read_text(encoding="utf-8"))
    raise AssertionError(f"no blueprint artifact in {confrontation_dir}")


def _first_mutable_numeric(blueprint: AttackBlueprint) -> str:
    for name, spec in blueprint.parameters.items():
        if spec.mutable and spec.minimum is not None and spec.maximum is not None:
            return name
    raise AssertionError(f"{blueprint.attack_id} declares no bounded mutable parameter")


needs_mule = pytest.mark.skipif(
    not (MULE_CONFRONTATION / "confrontation.json").is_file(),
    reason="mule confrontation artifact not in this checkout",
)
needs_adaptive = pytest.mark.skipif(
    not (ADAPTIVE_CONFRONTATION / "confrontation.json").is_file(),
    reason="adaptive-evasion confrontation artifact not in this checkout",
)
needs_snapshot = pytest.mark.skipif(
    not SNAPSHOT.is_file(), reason="generation reference snapshot not in this checkout"
)


class TestMultiFamilyGuidedPlumbing:
    """Proves the dispatch works for all three families without any live call."""

    def _child(self, confrontation_dir: Path) -> AttackBlueprint:
        parent = _blueprint(confrontation_dir)
        result = apply_blind_spot_proposals(
            _response(_increase(_first_mutable_numeric(parent))),
            parent,
            seed=SEED,
            provenance=_provenance(),
        )
        assert result.blueprint is not None, [r.reason for r in result.rejected]
        return result.blueprint

    @needs_mule
    def test_mule_blueprint_accepts_a_bounded_mutation(self) -> None:
        child = self._child(MULE_CONFRONTATION)
        assert child.attack_family is AttackFamily.MULE_NETWORK_STRUCTURING
        assert child.generation == _blueprint(MULE_CONFRONTATION).generation + 1

    @needs_adaptive
    def test_adaptive_blueprint_accepts_a_bounded_mutation(self) -> None:
        child = self._child(ADAPTIVE_CONFRONTATION)
        assert child.attack_family is AttackFamily.ADAPTIVE_DETECTOR_EVASION

    @pytest.mark.parametrize(
        "family",
        [
            AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT,
            AttackFamily.MULE_NETWORK_STRUCTURING,
            AttackFamily.ADAPTIVE_DETECTOR_EVASION,
        ],
    )
    @needs_snapshot
    def test_every_family_has_a_generator(self, family: AttackFamily, tmp_path: Path) -> None:
        from aegis.generate import GenerationReferenceSnapshot

        snapshot = GenerationReferenceSnapshot.model_validate_json(
            SNAPSHOT.read_text(encoding="utf-8")
        )
        generator = _build_generator(
            family, snapshot=snapshot, processed_dir=tmp_path, reference_max_rows=None
        )
        assert generator is not None

    def test_unknown_family_is_refused(self, tmp_path: Path) -> None:
        from scripts.run_genai_guided_generation import GenAIGuidedGenerationError

        class _NotAFamily:
            pass

        with pytest.raises(GenAIGuidedGenerationError, match="no guided-generation path"):
            _build_generator(
                _NotAFamily(),  # type: ignore[arg-type]
                snapshot=None,
                processed_dir=tmp_path,
                reference_max_rows=None,
            )


class TestNormalizers:
    """Each family names its fraud counter and fidelity differently."""

    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            ("fraudulent_bustout_count", 3),
            ("fraudulent_structuring_count", 6),
            ("fraudulent_perturbation_count", 4),
        ],
    )
    def test_fraud_counter_is_read_per_family(self, field: str, expected: int) -> None:
        scenario: Any = type("S", (), {field: expected})()
        assert _fraud_count_of(scenario) == expected

    def test_unknown_scenario_shape_is_refused(self) -> None:
        from scripts.run_genai_guided_generation import GenAIGuidedGenerationError

        with pytest.raises(GenAIGuidedGenerationError, match="no recognized fraud counter"):
            _fraud_count_of(type("S", (), {})())

    def test_fidelity_prefers_the_direct_field(self) -> None:
        scenario: Any = type(
            "S", (), {"fidelity_score": 0.9, "fidelity_summary": {"overall_fidelity_score": 0.1}}
        )()
        assert _fidelity_of(scenario) == 0.9

    def test_fidelity_falls_back_to_the_summary(self) -> None:
        scenario: Any = type("S", (), {"fidelity_summary": {"overall_fidelity_score": 0.42}})()
        assert _fidelity_of(scenario) == 0.42

    def test_missing_fidelity_is_none_not_zero(self) -> None:
        assert _fidelity_of(type("S", (), {})()) is None


# ---------------------------------------------------------------------------
# the adaptive-evasion empty-proposal case
# ---------------------------------------------------------------------------

def _empty_proposal_artifact(tmp_path: Path) -> Path:
    """A live, schema-valid Blind-Spot artifact whose proposal array is empty.

    Written as a fixture rather than read from `data/genai/`: a live artifact
    is legitimately re-run (the real adaptive one was, and now carries six
    proposals), so pinning a file's transient contents would make this suite
    depend on which call happened last. The *behaviour* is what must hold.
    """
    path = tmp_path / "blind_spot_empty.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "blind_spot_analyst-emptyfixture",
                "stage": "blind_spot_analyst",
                "created_at": "2026-08-29T23:00:00Z",
                "provenance": {
                    "provider": "anthropic",
                    "model": "claude-opus-5",
                    "prompt_version": "genai-prompts-v1",
                    "live": True,
                    "attempts": 1,
                },
                "request": {"attack_family": AttackFamily.ADAPTIVE_DETECTOR_EVASION.value},
                "response": {
                    "blind_spot_hypothesis": (
                        "The analyst reasoned about the gap but committed no structured "
                        "proposals."
                    ),
                    "evidence": ["All caught events saturated the score."],
                    "mutation_proposals": [],
                    "expected_trade_offs": ["Described in prose only."],
                    "safety_constraints": ["Parameter-level only."],
                    "confidence": 0.66,
                },
                "schema_valid": True,
            }
        ),
        encoding="utf-8",
    )
    return path


class TestEmptyProposalsAreNotABoundsRejection:
    """A model that proposes nothing must not be reported as a rejection.

    The live adaptive-evasion call once returned a full hypothesis and evidence
    with an empty `mutation_proposals` array. Reporting that as "no proposal
    survived the bounds check" blamed the guardrails for a model decision.
    """

    def test_empty_proposals_produce_no_applied_and_no_rejected(self, tmp_path: Path) -> None:
        """Nothing is dropped silently: there was simply nothing to evaluate."""
        from aegis.genai.contracts import GenAIRunArtifact

        artifact = GenAIRunArtifact.model_validate_json(
            _empty_proposal_artifact(tmp_path).read_text(encoding="utf-8")
        )
        assert artifact.schema_valid is True
        assert artifact.provenance.live is True
        response = BlindSpotAnalystResponse.model_validate(artifact.response)
        assert response.mutation_proposals == []
        # The reasoning itself is present -- only the structured array is empty.
        assert response.blind_spot_hypothesis

        result = apply_blind_spot_proposals(
            response,
            build_synthetic_identity_blueprint(),
            seed=SEED,
            provenance=_provenance(),
        )
        assert result.applied == []
        assert result.rejected == []
        assert result.blueprint is None

    @needs_adaptive
    def test_driver_names_the_empty_array_not_the_bounds_check(self, tmp_path: Path) -> None:
        from scripts.run_genai_guided_generation import (
            GenAIGuidedConfig,
            GenAIGuidedGenerationError,
            run_genai_guided_generation,
        )

        config = GenAIGuidedConfig(
            genai_artifact=_empty_proposal_artifact(tmp_path),
            confrontation_dir=ADAPTIVE_CONFRONTATION,
            processed_dir=tmp_path / "processed",
            model_dir=tmp_path / "model",
            artifact_dir=tmp_path / "out",
            evidence_dir=tmp_path / "evidence",
            seed=SEED,
        )
        with pytest.raises(GenAIGuidedGenerationError) as excinfo:
            run_genai_guided_generation(config)

        message = str(excinfo.value)
        assert "zero mutation proposals" in message
        assert "empty `mutation_proposals` array" in message
        assert "survived the bounds check" not in message
        # It fails before touching the detector or writing anything.
        assert not (tmp_path / "out").exists()

    def test_the_real_adaptive_artifact_now_carries_proposals(self) -> None:
        """Guards the freeze: the shipped adaptive artifact is the re-run one."""
        from aegis.genai.contracts import GenAIRunArtifact

        path = Path("data/genai/blind_spot_analyst/blind_spot_analyst-4b8eb2bd2d7ef387.json")
        if not path.is_file():
            pytest.skip("adaptive blind-spot artifact not in this checkout")
        artifact = GenAIRunArtifact.model_validate_json(path.read_text(encoding="utf-8"))
        response = BlindSpotAnalystResponse.model_validate(artifact.response)
        assert artifact.provenance.live is True
        assert response.mutation_proposals, "shipped adaptive artifact must carry proposals"


class TestEveryProposalIsAccountedFor:
    """applied + rejected == proposals, always. No proposal is dropped."""

    @needs_adaptive
    def test_mixed_proposals_are_all_accounted_for(self) -> None:
        blueprint = _blueprint(ADAPTIVE_CONFRONTATION)
        proposals = [
            _increase("inter_event_delay_hours"),
            _increase("not_a_declared_parameter"),
            _increase("max_parameter_changes"),
            BoundedMutationProposal(
                parameter="destination_diversity",
                direction=MutationDirection.SET,
                proposed_value=5,
                magnitude=0.2,
                rationale="unsupported direction",
            ),
        ]
        result = apply_blind_spot_proposals(
            _response(*proposals), blueprint, seed=SEED, provenance=_provenance()
        )

        assert len(result.applied) + len(result.rejected) == len(proposals)
        assert all(rejected.reason for rejected in result.rejected)

    @needs_adaptive
    def test_an_in_bounds_adaptive_proposal_still_survives(self) -> None:
        blueprint = _blueprint(ADAPTIVE_CONFRONTATION)
        result = apply_blind_spot_proposals(
            _response(_increase("inter_event_delay_hours")),
            blueprint,
            seed=SEED,
            provenance=_provenance(),
        )
        applied = result.applied[0]
        spec = blueprint.parameters["inter_event_delay_hours"]
        assert spec.maximum is not None
        assert applied.from_value == float(spec.default)
        assert applied.to_value > applied.from_value
        assert applied.to_value <= spec.maximum

    @needs_adaptive
    def test_out_of_bounds_is_still_rejected_not_clamped(self) -> None:
        blueprint = _blueprint(ADAPTIVE_CONFRONTATION)
        result = apply_blind_spot_proposals(
            _response(_increase("max_parameter_changes")),
            blueprint,
            seed=SEED,
            provenance=_provenance(),
        )
        assert result.applied == []
        assert "structural" in result.rejected[0].reason

    @needs_adaptive
    def test_the_same_seed_reproduces_the_same_adaptive_child(self) -> None:
        blueprint = _blueprint(ADAPTIVE_CONFRONTATION)
        children = [
            apply_blind_spot_proposals(
                _response(_increase("inter_event_delay_hours")),
                blueprint,
                seed=SEED,
                provenance=_provenance(),
            ).blueprint
            for _ in range(2)
        ]
        assert children[0] is not None and children[1] is not None
        assert children[0].attack_id == children[1].attack_id
