"""Safety and provenance tests for the GenAI-guided generation driver.

`scripts/run_genai_guided_generation.py` is the only path where a live model's
reasoning reaches the deterministic simulator. These tests pin the properties
that make that admissible to a judge:

* a recorded replay can never be run as, or labeled, live;
* incomplete provenance blocks the "GenAI-guided" label entirely;
* out-of-bounds proposals are rejected, not clamped;
* the same seed reproduces the same child blueprint and the same scenario;
* the writer refuses to overwrite, so no historical artifact can be replaced.

Nothing here makes a network call, loads PaySim, or touches a model. The one
test that reads the real frozen detector skips when that artifact is absent.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from scripts.run_genai_guided_generation import (
    GenAIGuidedConfig,
    GenAIGuidedGenerationError,
    _build_provenance,
    _generation_id,
    _known_scenario_ids,
    _load_genai_artifact,
    _snapshot_training_skeletons,
    _stable_artifact_payload,
    run_genai_guided_generation,
)

from aegis.genai.contracts import BlindSpotAnalystResponse, BoundedMutationProposal
from aegis.genai.handoff_contracts import (
    AppliedMutation,
    GenAIGuidedGeneration,
    GenAIHandoffProvenance,
)
from aegis.generate import GenerationConfig, SyntheticIdentityBustOutGenerator
from aegis.generate.reference_snapshot import GenerationReferenceSnapshot
from aegis.identify import build_synthetic_identity_blueprint
from aegis.loop.genai_handoff import apply_blind_spot_proposals
from aegis.shared.contracts import AttackBlueprint, ParameterSpec
from aegis.shared.enums import AttackFamily, DataSplit, MutationDirection, ParameterType

SEED = 20260901
LIVE_ARTIFACT = Path("data/genai/blind_spot_analyst/blind_spot_analyst-4a31d071288af1f5.json")
DEFENDER_V3 = Path("models/xgboost-hardened-crossfamily-20260301")
GUIDED_DIR = Path("data/genai/guided_generations")


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _blueprint() -> AttackBlueprint:
    return AttackBlueprint(
        attack_id="synthetic-identity-bustout-v1",
        attack_family=AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT,
        description="Parent blueprint for the guided-generation tests.",
        objective="Exercise the driver's bounds and determinism.",
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
                maximum=1_000_000,
                mutable=False,
            ),
        },
    )


def _response(*proposals: BoundedMutationProposal) -> BlindSpotAnalystResponse:
    """TEST-ONLY validated response. Never persisted, never rendered as GenAI."""
    return BlindSpotAnalystResponse(
        blind_spot_hypothesis="Velocity features under-weight a diluted burst.",
        evidence=["All fraud events scored below the operating threshold."],
        mutation_proposals=list(proposals),
        confidence=0.6,
    )


def _increase(parameter: str, magnitude: float = 0.2) -> BoundedMutationProposal:
    return BoundedMutationProposal(
        parameter=parameter,
        direction=MutationDirection.INCREASE,
        magnitude=magnitude,
        rationale="Spread the burst across more destinations.",
        confidence=0.7,
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


def _artifact_payload(*, live: bool, schema_valid: bool = True) -> dict[str, Any]:
    return {
        "run_id": "blind_spot_analyst-fixture",
        "stage": "blind_spot_analyst",
        "created_at": "2026-08-29T21:04:46.668807Z",
        "provenance": {
            "provider": "recorded" if not live else "anthropic",
            "model": "claude-opus-5",
            "prompt_version": "genai-prompts-v1",
            "live": live,
            "attempts": 1,
        },
        "request": {},
        "response": _response(_increase("destination_diversity")).model_dump(mode="json"),
        "schema_valid": schema_valid,
    }


def _write_artifact(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _config(tmp_path: Path, artifact: Path, **overrides: Any) -> GenAIGuidedConfig:
    payload: dict[str, Any] = {
        "genai_artifact": artifact,
        "confrontation_dir": tmp_path / "confrontation",
        "processed_dir": tmp_path / "processed",
        "model_dir": tmp_path / "model",
        "artifact_dir": tmp_path / "out",
        "evidence_dir": tmp_path / "evidence",
        "seed": SEED,
    }
    payload.update(overrides)
    return GenAIGuidedConfig(**payload)


# ---------------------------------------------------------------------------
# a recorded replay is never live
# ---------------------------------------------------------------------------


class TestRecordedIsNeverLive:
    def test_recorded_artifact_is_refused_by_default(self, tmp_path: Path) -> None:
        artifact = _write_artifact(tmp_path, _artifact_payload(live=False))
        with pytest.raises(GenAIGuidedGenerationError, match="recorded replay"):
            run_genai_guided_generation(_config(tmp_path, artifact))

    def test_refusal_happens_before_anything_is_written(self, tmp_path: Path) -> None:
        artifact = _write_artifact(tmp_path, _artifact_payload(live=False))
        with pytest.raises(GenAIGuidedGenerationError):
            run_genai_guided_generation(_config(tmp_path, artifact))
        assert not (tmp_path / "out").exists()
        assert not (tmp_path / "evidence").exists()

    def test_recorded_provenance_stays_not_live_when_allowed(self, tmp_path: Path) -> None:
        """`--allow-recorded` applies it, but `live` is copied, never inferred."""
        artifact = _write_artifact(tmp_path, _artifact_payload(live=False))
        provenance = _build_provenance(
            _load_genai_artifact(artifact),
            artifact_path=artifact,
            confrontation_id="confrontation-test",
            source_artifact="confrontation-test/confrontation.json",
            detector_model_version="xgboost-hardened-crossfamily-20260301",
        )
        assert provenance.live is False
        assert provenance.is_complete is True
        assert provenance.is_live_genai is False

    def test_live_provenance_is_carried_through(self, tmp_path: Path) -> None:
        artifact = _write_artifact(tmp_path, _artifact_payload(live=True))
        provenance = _build_provenance(
            _load_genai_artifact(artifact),
            artifact_path=artifact,
            confrontation_id="confrontation-test",
            source_artifact="confrontation-test/confrontation.json",
            detector_model_version="xgboost-hardened-crossfamily-20260301",
        )
        assert provenance.is_live_genai is True
        assert provenance.genai_artifact == artifact.as_posix()

    def test_failed_run_artifact_is_refused(self, tmp_path: Path) -> None:
        payload = _artifact_payload(live=True, schema_valid=False)
        payload["response"] = None
        artifact = _write_artifact(tmp_path, payload)
        with pytest.raises(GenAIGuidedGenerationError, match="failed run"):
            _load_genai_artifact(artifact)

    def test_wrong_stage_is_refused(self, tmp_path: Path) -> None:
        payload = _artifact_payload(live=True)
        payload["stage"] = "attack_analyst"
        artifact = _write_artifact(tmp_path, payload)
        with pytest.raises(GenAIGuidedGenerationError, match="attack_analyst"):
            _load_genai_artifact(artifact)


# ---------------------------------------------------------------------------
# provenance gates the label
# ---------------------------------------------------------------------------


class TestProvenanceGatesTheLabel:
    @pytest.mark.parametrize(
        "missing", ["genai_run_id", "provider", "model", "prompt_version"]
    )
    def test_missing_field_blocks_genai_guided(self, missing: str) -> None:
        record = GenAIGuidedGeneration(
            generation_id="genai-guided-test",
            provenance=_provenance(**{missing: ""}),
            applied_mutations=[
                AppliedMutation(
                    parameter="destination_diversity",
                    direction=MutationDirection.INCREASE,
                    magnitude=0.2,
                    from_value=3.0,
                    to_value=5.0,
                )
            ],
        )
        assert record.provenance.is_complete is False
        assert record.is_genai_guided is False

    def test_complete_provenance_without_a_mutation_is_not_guided(self) -> None:
        record = GenAIGuidedGeneration(
            generation_id="genai-guided-test",
            provenance=_provenance(),
            applied_mutations=[],
        )
        assert record.provenance.is_complete is True
        assert record.is_genai_guided is False

    def test_complete_provenance_with_a_mutation_is_guided(self) -> None:
        record = GenAIGuidedGeneration(
            generation_id="genai-guided-test",
            provenance=_provenance(),
            applied_mutations=[
                AppliedMutation(
                    parameter="destination_diversity",
                    direction=MutationDirection.INCREASE,
                    magnitude=0.2,
                    from_value=3.0,
                    to_value=5.0,
                )
            ],
        )
        assert record.is_genai_guided is True


# ---------------------------------------------------------------------------
# bounds
# ---------------------------------------------------------------------------


class TestBoundsStillHold:
    def test_immutable_parameter_is_rejected(self) -> None:
        result = apply_blind_spot_proposals(
            _response(_increase("randomness_seed_offset")),
            _blueprint(),
            seed=SEED,
            provenance=_provenance(),
        )
        assert result.applied == []
        assert result.blueprint is None
        assert "structural" in result.rejected[0].reason

    def test_unknown_parameter_is_rejected(self) -> None:
        result = apply_blind_spot_proposals(
            _response(_increase("not_a_parameter")),
            _blueprint(),
            seed=SEED,
            provenance=_provenance(),
        )
        assert "not declared" in result.rejected[0].reason

    def test_a_bad_proposal_does_not_take_the_good_one_with_it(self) -> None:
        result = apply_blind_spot_proposals(
            _response(_increase("destination_diversity"), _increase("randomness_seed_offset")),
            _blueprint(),
            seed=SEED,
            provenance=_provenance(),
        )
        assert [m.parameter for m in result.applied] == ["destination_diversity"]
        assert len(result.rejected) == 1
        assert result.blueprint is not None

    def test_genai_never_supplies_the_value(self) -> None:
        """Only direction+magnitude cross the boundary; the step recomputes."""
        parent = _blueprint()
        result = apply_blind_spot_proposals(
            _response(_increase("destination_diversity", 0.25)),
            parent,
            seed=SEED,
            provenance=_provenance(),
        )
        spec = parent.parameters["destination_diversity"]
        assert spec.maximum is not None
        applied = result.applied[0]
        assert applied.from_value == float(spec.default)
        assert applied.to_value <= spec.maximum


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def _child(self, seed: int) -> AttackBlueprint:
        """Mutate the *canonical* blueprint, so the child is generatable."""
        result = apply_blind_spot_proposals(
            _response(_increase("destination_diversity"), _increase("bustout_amount_multiplier")),
            build_synthetic_identity_blueprint(),
            seed=seed,
            provenance=_provenance(),
        )
        assert result.blueprint is not None
        return result.blueprint

    def test_same_seed_reproduces_the_same_child_blueprint(self) -> None:
        first, second = self._child(SEED), self._child(SEED)
        # `created_at` is a wall clock; identity and parameters are the
        # reproducible part, and `attack_id` is a hash over exactly those.
        assert first.attack_id == second.attack_id
        assert first.model_dump(mode="json", exclude={"created_at"}) == second.model_dump(
            mode="json", exclude={"created_at"}
        )

    def test_a_different_seed_gives_a_different_child(self) -> None:
        assert self._child(SEED).attack_id != self._child(SEED + 1).attack_id

    def test_same_seed_reproduces_the_same_scenario(self) -> None:
        child = self._child(SEED)
        config = GenerationConfig(
            seed=SEED,
            n_scenarios=1,
            start_time=datetime(2026, 9, 1, tzinfo=timezone.utc),
            time_horizon=timedelta(days=120),
            split=DataSplit.TEST,
            generation=child.generation,
            deterministic=True,
        )
        first = SyntheticIdentityBustOutGenerator().generate(child, config)
        second = SyntheticIdentityBustOutGenerator().generate(child, config)

        assert first.scenario_ids == second.scenario_ids
        assert [t.transaction_id for t in first.transactions] == [
            t.transaction_id for t in second.transactions
        ]
        assert [t.amount for t in first.transactions] == [t.amount for t in second.transactions]

    def test_exactly_one_scenario_is_generated(self) -> None:
        child = self._child(SEED)
        batch = SyntheticIdentityBustOutGenerator().generate(
            child,
            GenerationConfig(
                seed=SEED,
                n_scenarios=1,
                start_time=datetime(2026, 9, 1, tzinfo=timezone.utc),
                time_horizon=timedelta(days=120),
                split=DataSplit.TEST,
                generation=child.generation,
                deterministic=True,
            ),
        )
        assert len(batch.scenario_ids) == 1

    def test_generation_id_is_a_function_of_run_seed_and_blueprint(self) -> None:
        baseline = _generation_id(genai_run_id="run-a", blueprint_id="bp-1", seed=SEED)
        assert _generation_id(genai_run_id="run-a", blueprint_id="bp-1", seed=SEED) == baseline
        assert _generation_id(genai_run_id="run-a", blueprint_id="bp-1", seed=SEED + 1) != baseline
        assert _generation_id(genai_run_id="run-b", blueprint_id="bp-1", seed=SEED) != baseline
        assert _generation_id(genai_run_id="run-a", blueprint_id="bp-2", seed=SEED) != baseline


# ---------------------------------------------------------------------------
# nothing historical is touched
# ---------------------------------------------------------------------------


class TestHistoricalArtifactsAreSafe:
    def test_prior_scenario_ids_are_detected(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "confrontations" / "confrontation-x"
        run_dir.mkdir(parents=True)
        (run_dir / "confrontation.json").write_text(
            json.dumps({"scenario_reports": [{"scenario_id": "scenario-already-used"}]}),
            encoding="utf-8",
        )
        assert _known_scenario_ids([tmp_path]) == {"scenario-already-used"}

    def test_unreadable_report_does_not_break_the_scan(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "confrontations" / "confrontation-y"
        run_dir.mkdir(parents=True)
        (run_dir / "confrontation.json").write_text("{not json", encoding="utf-8")
        assert _known_scenario_ids([tmp_path]) == set()

    @pytest.mark.skipif(
        not (GUIDED_DIR.is_dir() and any(GUIDED_DIR.glob("*.json"))),
        reason="no guided generation has been run in this checkout",
    )
    def test_persisted_guided_run_did_not_overwrite_its_source(self) -> None:
        """The parent confrontation it derives from is still on disk, intact."""
        for path in GUIDED_DIR.glob("*.json"):
            record = GenAIGuidedGeneration.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            source = Path(record.provenance.source_artifact)
            if source.name:
                assert source.is_file(), f"{record.generation_id} lost its source: {source}"
            assert Path(record.provenance.genai_artifact).is_file()

    @pytest.mark.skipif(
        not (DEFENDER_V3 / "model.json").is_file(), reason="Defender v3 artifact not in checkout"
    )
    @pytest.mark.skipif(
        not (GUIDED_DIR.is_dir() and any(GUIDED_DIR.glob("*.json"))),
        reason="no guided generation has been run in this checkout",
    )
    def test_defender_v3_hash_matches_what_scored_the_run(self) -> None:
        """The frozen model on disk is byte-identical to the one that scored."""
        current = hashlib.sha256((DEFENDER_V3 / "model.json").read_bytes()).hexdigest()
        for path in GUIDED_DIR.glob("*.json"):
            record = GenAIGuidedGeneration.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            if record.provenance.detector_model_version != DEFENDER_V3.name:
                continue
            assert current[:12] in record.notes, (
                f"{record.generation_id} was scored by a different {DEFENDER_V3.name} artifact"
            )


def _reference_snapshot() -> GenerationReferenceSnapshot:
    return GenerationReferenceSnapshot(
        dataset_id="paysim-test",
        base_train_transaction_count=100,
        legitimate_reference_count=98,
        transfer_reference_count=20,
        amount_mean=75.0,
        amount_stddev=25.0,
        transfer_amount_mean=500.0,
        transfer_amount_stddev=150.0,
        transaction_type_distribution={"payment": 0.8, "transfer": 0.2},
        currency="XXX",
        latest_train_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        additional_training_transaction_ids=["bustout-old-row"],
        additional_training_scenario_ids=["bustout-old"],
        defender_model_version="xgboost-hardened-crossfamily-20260301",
        defender_model_sha256="a" * 64,
        source_artifacts=[],
        limitations=["test"],
    )


class TestFastSnapshotFreshness:
    def test_namespace_and_exact_hard_positive_membership_pass_for_fresh_batch(self) -> None:
        blueprint = build_synthetic_identity_blueprint()
        batch = SyntheticIdentityBustOutGenerator().generate(
            blueprint,
            GenerationConfig(
                seed=20261011,
                start_time=datetime(2026, 10, 1, tzinfo=timezone.utc),
                time_horizon=timedelta(days=120),
                split=DataSplit.TEST,
            ),
        )
        skeletons = _snapshot_training_skeletons(_reference_snapshot(), batch)
        assert {row.transaction_id for row in skeletons} >= {"bustout-old-row"}
        assert {row.scenario_id for row in skeletons if row.scenario_id} == {"bustout-old"}

    def test_hard_positive_scenario_collision_is_rejected(self) -> None:
        blueprint = build_synthetic_identity_blueprint()
        batch = SyntheticIdentityBustOutGenerator().generate(
            blueprint,
            GenerationConfig(
                seed=20261011,
                start_time=datetime(2026, 10, 1, tzinfo=timezone.utc),
                time_horizon=timedelta(days=120),
                split=DataSplit.TEST,
            ),
        )
        snapshot = _reference_snapshot().model_copy(
            update={"additional_training_scenario_ids": [batch.scenario_ids[0]]}
        )
        with pytest.raises(GenAIGuidedGenerationError, match="freshness proof failed"):
            _snapshot_training_skeletons(snapshot, batch)

    def test_idempotent_comparison_ignores_nested_creation_times(self) -> None:
        left = {"created_at": "first", "blueprint": {"created_at": "one", "value": 1}}
        right = {"created_at": "second", "blueprint": {"created_at": "two", "value": 1}}
        assert _stable_artifact_payload(left) == _stable_artifact_payload(right)
