"""Adaptive bust-out evolution tests; all efficacy observations are fixtures."""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from scripts.run_adaptive_bustout_round import (
    AdaptiveBustOutConfig,
    run_adaptive_bustout_round,
)
from scripts.run_bustout_confrontation import (
    ConfrontationPipelineConfig,
    run_bustout_confrontation,
)

from aegis.evaluate import build_bustout_confrontation_report
from aegis.generate import GenerationConfig, SyntheticIdentityBustOutGenerator
from aegis.identify import build_synthetic_identity_blueprint
from aegis.loop import (
    AdaptiveRoundReport,
    analyze_blind_spots,
    calculate_attack_fitness,
    compare_rounds,
    generate_mutation_candidates,
)
from aegis.shared.contracts import DetectorOutput, SignalContribution, Transaction
from aegis.shared.enums import (
    DataSplit,
    FraudLabel,
    RecommendedAction,
    SignalDirection,
    TransactionType,
)

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def adaptive_tmp_path() -> Iterator[Path]:
    path = Path("data/interim") / f"adaptive-test-{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def parent_blueprint():
    return build_synthetic_identity_blueprint()


@pytest.fixture
def parent_batch(parent_blueprint):
    return SyntheticIdentityBustOutGenerator().generate(
        parent_blueprint,
        GenerationConfig(
            seed=100,
            start_time=T0,
            time_horizon=timedelta(days=120),
            split=DataSplit.TEST,
        ),
    )


def _training_transaction() -> Transaction:
    return Transaction(
        transaction_id="training-0",
        timestamp=T0 - timedelta(days=10),
        source_account_id="training-source",
        destination_account_id="training-destination",
        amount=50.0,
        transaction_type=TransactionType.PAYMENT,
        label=FraudLabel.LEGITIMATE,
        split=DataSplit.TRAIN,
    )


def _evasion_outputs(parent_batch) -> list[DetectorOutput]:
    outputs: list[DetectorOutput] = []
    for transaction in parent_batch.transactions:
        fraud = transaction.is_fraud
        outputs.append(
            DetectorOutput(
                transaction_id=transaction.transaction_id,
                risk_score=0.20 if fraud else 0.05,
                predicted_label=FraudLabel.LEGITIMATE,
                recommended_action=RecommendedAction.APPROVE,
                important_signals=(
                    [
                        SignalContribution(
                            name="temporal.amount",
                            contribution=0.40,
                            value=transaction.amount,
                            direction=SignalDirection.INCREASES_RISK,
                            rank=0,
                        )
                    ]
                    if fraud
                    else []
                ),
                model_version="fixture-frozen-v1",
                threshold=0.5,
                policy_version="fixture-policy-v1",
            )
        )
    return outputs


def _parent_report(parent_batch, outputs):
    return build_bustout_confrontation_report(
        batch=parent_batch,
        outputs=outputs,
        training_transactions=[_training_transaction()],
        training_dataset_id="fixture-paysim",
        data_basis="synthetic_fixture",
        integration_only=True,
    )


def test_mutations_are_bounded_deterministic_and_not_clones(parent_blueprint, parent_batch):
    outputs = _evasion_outputs(parent_batch)
    analysis = analyze_blind_spots(
        _parent_report(parent_batch, outputs), parent_blueprint, outputs
    )
    first = generate_mutation_candidates(parent_blueprint, analysis, seed=222, candidate_count=4)
    second = generate_mutation_candidates(parent_blueprint, analysis, seed=222, candidate_count=4)

    assert [item.model_dump() for item in first] == [item.model_dump() for item in second]
    assert len({item.candidate_id for item in first}) == 4
    parent_values = parent_blueprint.default_parameters()
    for candidate in first:
        child = candidate.blueprint
        assert child.parent_blueprint_id == parent_blueprint.attack_id
        assert child.generation == 1
        assert child.default_parameters() != parent_values
        for _name, spec in child.parameters.items():
            value = spec.default
            if spec.minimum is not None:
                assert value >= spec.minimum
            if spec.maximum is not None:
                assert value <= spec.maximum


def test_immutable_parameters_and_attack_structure_stay_unchanged(
    parent_blueprint, parent_batch
):
    outputs = _evasion_outputs(parent_batch)
    analysis = analyze_blind_spots(
        _parent_report(parent_batch, outputs), parent_blueprint, outputs
    )
    candidates = generate_mutation_candidates(parent_blueprint, analysis, seed=7)

    immutable = {
        name: spec
        for name, spec in parent_blueprint.parameters.items()
        if not spec.mutable
    }
    assert immutable
    for candidate in candidates:
        child = candidate.blueprint
        assert {name: child.parameters[name] for name in immutable} == immutable
        assert child.attack_family is parent_blueprint.attack_family
        assert child.sequence == parent_blueprint.sequence
        assert child.realism_constraints == parent_blueprint.realism_constraints


def test_mutated_blueprint_preserves_warmup_bustout_semantics(parent_blueprint, parent_batch):
    outputs = _evasion_outputs(parent_batch)
    analysis = analyze_blind_spots(
        _parent_report(parent_batch, outputs), parent_blueprint, outputs
    )
    candidate = generate_mutation_candidates(
        parent_blueprint, analysis, seed=333, candidate_count=2
    )[0]
    batch = SyntheticIdentityBustOutGenerator().generate(
        candidate.blueprint,
        GenerationConfig(
            seed=334,
            start_time=T0 + timedelta(days=150),
            time_horizon=timedelta(days=120),
            split=DataSplit.TEST,
            generation=1,
        ),
    )

    assert batch.transactions == sorted(batch.transactions, key=lambda txn: txn.timestamp)
    labels = [txn.label for txn in batch.transactions]
    first_fraud = labels.index(FraudLabel.FRAUD)
    assert first_fraud > 0
    assert all(label is FraudLabel.LEGITIMATE for label in labels[:first_fraud])
    assert all(label is FraudLabel.FRAUD for label in labels[first_fraud:])
    assert all(txn.generation == 1 for txn in batch.transactions)


def test_blind_spot_direction_requires_observed_signal_evidence(
    parent_blueprint, parent_batch
):
    outputs = _evasion_outputs(parent_batch)
    analysis = analyze_blind_spots(
        _parent_report(parent_batch, outputs), parent_blueprint, outputs
    )
    multiplier = next(
        item
        for item in analysis.parameter_evidence
        if item.parameter == "bustout_amount_multiplier"
    )
    assert analysis.directional_evidence_available is True
    assert multiplier.suggested_direction is not None
    assert multiplier.suggested_direction.value == "decrease"
    assert multiplier.risk_increasing_contribution > 0.0
    assert "not a cross-region" in analysis.notes[0]


def test_fidelity_participates_in_fitness():
    low_fidelity = calculate_attack_fitness(average_fraud_risk=0.2, fidelity_score=0.4)
    high_fidelity = calculate_attack_fitness(average_fraud_risk=0.2, fidelity_score=0.9)
    assert high_fidelity > low_fidelity
    assert high_fidelity == pytest.approx(0.72)


def test_round_comparison_uses_signed_round1_minus_round0(parent_blueprint, parent_batch):
    outputs = _evasion_outputs(parent_batch)
    scenario = _parent_report(parent_batch, outputs).scenario_reports[0]
    from aegis.loop import RoundAttackMetrics

    round0 = RoundAttackMetrics(
        generated_scenario_count=1,
        transaction_count=15,
        fraud_count=3,
        caught_count=2,
        evaded_count=1,
        fraud_recall=2 / 3,
        average_fraud_risk_score=0.6,
        fidelity_score=0.9,
        fitness=calculate_attack_fitness(0.6, 0.9),
        evaluation_result=scenario.evaluation_result,
    )
    round1 = round0.model_copy(
        update={
            "caught_count": 1,
            "evaded_count": 2,
            "fraud_recall": 1 / 3,
            "average_fraud_risk_score": 0.3,
            "fidelity_score": 0.8,
            "fitness": calculate_attack_fitness(0.3, 0.8),
        }
    )
    comparison = compare_rounds(round0, round1)
    assert comparison.fraud_recall_delta == pytest.approx(-1 / 3)
    assert comparison.average_fraud_risk_delta == pytest.approx(-0.3)
    assert comparison.fidelity_delta == pytest.approx(-0.1)
    assert comparison.evaded_count_delta == 1


def _make_split(n: int, day: int, split: DataSplit) -> list[Transaction]:
    transactions: list[Transaction] = []
    for index in range(n):
        fraud = index % 10 == 0
        transactions.append(
            Transaction(
                transaction_id=f"{split.value}-{index}",
                timestamp=T0 + timedelta(days=day, minutes=index * 4),
                source_account_id=f"source-{index % 9}",
                destination_account_id=f"destination-{index % 6}",
                amount=(800.0 + index * 3.0) if fraud else (40.0 + index % 20),
                currency="XXX",
                transaction_type=(
                    TransactionType.CASH_OUT if fraud else TransactionType.PAYMENT
                ),
                source_balance_before=2000.0,
                source_balance_after=1200.0 if fraud else 1950.0,
                destination_balance_before=300.0,
                destination_balance_after=1100.0 if fraud else 350.0,
                label=FraudLabel.FRAUD if fraud else FraudLabel.LEGITIMATE,
                split=split,
            )
        )
    return transactions


def _write_transactions(path: Path, transactions: list[Transaction]) -> None:
    path.write_text(
        "".join(f"{transaction.to_json()}\n" for transaction in transactions),
        encoding="utf-8",
    )


def _first_json_difference(left, right, path="$"):
    if type(left) is not type(right):
        return f"{path}: types {type(left).__name__} != {type(right).__name__}"
    if isinstance(left, dict):
        if left.keys() != right.keys():
            return f"{path}: keys {left.keys()} != {right.keys()}"
        for key in left:
            difference = _first_json_difference(left[key], right[key], f"{path}.{key}")
            if difference is not None:
                return difference
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: lengths {len(left)} != {len(right)}"
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
            difference = _first_json_difference(
                left_item, right_item, f"{path}[{index}]"
            )
            if difference is not None:
                return difference
        return None
    return None if left == right else f"{path}: {left!r} != {right!r}"


def test_round1_runs_fresh_variants_against_unchanged_fixture_model(adaptive_tmp_path):
    processed = adaptive_tmp_path / "fixture-paysim-run"
    processed.mkdir()
    _write_transactions(processed / "train.jsonl", _make_split(100, 0, DataSplit.TRAIN))
    _write_transactions(processed / "validation.jsonl", _make_split(30, 10, DataSplit.VALIDATION))
    _write_transactions(processed / "test.jsonl", _make_split(30, 20, DataSplit.TEST))

    round0 = run_bustout_confrontation(
        ConfrontationPipelineConfig(
            processed_dir=processed,
            output_dir=adaptive_tmp_path / "round0",
            model_output_dir=adaptive_tmp_path / "models",
            seed=77,
            num_boost_round=8,
            latency_sample_size=3,
            integration_only=True,
            data_basis="synthetic_fixture",
        )
    )
    model_before = (round0.model_dir / "model.json").read_bytes()
    metadata_before = (round0.model_dir / "metadata.json").read_bytes()

    first = run_adaptive_bustout_round(
        AdaptiveBustOutConfig(
            processed_dir=processed,
            confrontation_dir=round0.output_dir,
            model_dir=round0.model_dir,
            output_dir=adaptive_tmp_path / "adaptive-first",
            seed=78,
            candidate_count=3,
        )
    )
    second = run_adaptive_bustout_round(
        AdaptiveBustOutConfig(
            processed_dir=processed,
            confrontation_dir=round0.output_dir,
            model_dir=round0.model_dir,
            output_dir=adaptive_tmp_path / "adaptive-second",
            seed=78,
            candidate_count=3,
        )
    )

    assert (round0.model_dir / "model.json").read_bytes() == model_before
    assert (round0.model_dir / "metadata.json").read_bytes() == metadata_before
    report = first.execution.report
    assert report.detector_retrained is False
    assert report.threshold_changed is False
    assert report.model_version == round0.report.model_version
    assert len(report.candidate_results) == 3
    assert [result.fitness_rank for result in report.candidate_results] == [1, 2, 3]
    assert [result.metrics.fitness for result in report.candidate_results] == sorted(
        (result.metrics.fitness for result in report.candidate_results), reverse=True
    )
    assert report.selected_candidate_id == second.execution.report.selected_candidate_id
    assert [
        result.candidate.changed_parameters for result in report.candidate_results
    ] == [
        result.candidate.changed_parameters
        for result in second.execution.report.candidate_results
    ]
    assert [
        result.metrics.fitness for result in report.candidate_results
    ] == [
        result.metrics.fitness for result in second.execution.report.candidate_results
    ]

    round0_ids = {txn.transaction_id for txn in round0.batch.transactions}
    for result in report.candidate_results:
        batch = first.execution.batches[result.candidate.candidate_id]
        assert batch.seed != round0.batch.seed
        assert batch.generation == 1
        assert round0_ids.isdisjoint(txn.transaction_id for txn in batch.transactions)
        assert all(txn.label is FraudLabel.FRAUD for txn in batch.transactions if txn.is_fraud)
        assert (
            result.metrics.caught_count + result.metrics.evaded_count
            == result.metrics.fraud_count
        )
        assert result.metrics.evaluation_result.metadata["detector_retrained"] is False

    assert [record.rank for record in report.hardest_surviving_evasions] == list(
        range(1, len(report.hardest_surviving_evasions) + 1)
    )
    assert all(
        record.ground_truth_label is FraudLabel.FRAUD
        for record in report.hardest_surviving_evasions
    )
    restored = AdaptiveRoundReport.model_validate_json(
        first.artifacts["report"].read_text(encoding="utf-8")
    )
    difference = _first_json_difference(
        restored.model_dump(mode="json"), report.model_dump(mode="json")
    )
    assert difference is None, difference
