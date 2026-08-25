"""Focused coverage for the benchmark-only mule-network attack family."""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aegis.evaluate import (
    ConfrontationValidationError,
    TrainingOverlapScan,
    build_mule_network_confrontation_report,
    scan_training_overlap,
)
from aegis.features import TemporalBaselineFeatureExtractor
from aegis.generate import (
    GenerationConfig,
    MuleNetworkConfigurationError,
    MuleNetworkReferenceProfile,
    MuleNetworkStructuringGenerator,
)
from aegis.identify import (
    MULE_NETWORK_BLUEPRINT_PROMPT,
    IdentificationContext,
    MuleNetworkBlueprintIdentifier,
    build_mule_network_blueprint,
)
from aegis.loop import (
    BlindSpotAnalysis,
    calculate_attack_fitness,
    generate_mutation_candidates,
)
from aegis.shared.contracts import DetectorOutput, Transaction
from aegis.shared.enums import (
    AttackFamily,
    DataSplit,
    EvaluationProtocol,
    FraudLabel,
    RecommendedAction,
    TransactionType,
)

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def mule_tmp_path() -> Iterator[Path]:
    path = (Path("data/interim") / f"mule-test-{uuid.uuid4().hex}").resolve()
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def mule_blueprint():
    return build_mule_network_blueprint()


@pytest.fixture
def mule_config():
    return GenerationConfig(
        seed=4242,
        n_scenarios=1,
        start_time=T0,
        time_horizon=timedelta(days=60),
        split=DataSplit.TEST,
        deterministic=True,
    )


def _reference_transaction(
    index: int,
    *,
    split: DataSplit = DataSplit.TRAIN,
    label: FraudLabel = FraudLabel.LEGITIMATE,
    transaction_type: TransactionType = TransactionType.TRANSFER,
    transaction_id: str | None = None,
    scenario_id: str | None = None,
) -> Transaction:
    return Transaction(
        transaction_id=transaction_id or f"reference-{index}",
        timestamp=T0 + timedelta(minutes=index),
        source_account_id=f"source-{index % 3}",
        destination_account_id=f"destination-{index % 4}",
        amount=100.0 + index * 25.0,
        currency="XXX",
        transaction_type=transaction_type,
        label=label,
        scenario_id=scenario_id,
        split=split,
    )


def _write_jsonl(path: Path, transactions: list[Transaction]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for transaction in transactions:
            handle.write(transaction.to_json())
            handle.write("\n")


def _fixture_outputs(transactions: list[Transaction]) -> list[DetectorOutput]:
    outputs: list[DetectorOutput] = []
    fraud_index = 0
    for transaction in transactions:
        if transaction.is_fraud:
            caught = fraud_index % 2 == 0
            risk = 0.8 if caught else 0.2
            fraud_index += 1
        else:
            caught = False
            risk = 0.05
        outputs.append(
            DetectorOutput(
                transaction_id=transaction.transaction_id,
                risk_score=risk,
                predicted_label=FraudLabel.FRAUD if caught else FraudLabel.LEGITIMATE,
                recommended_action=(
                    RecommendedAction.DECLINE if caught else RecommendedAction.APPROVE
                ),
                model_version="fixture-detector-v2",
                threshold=0.5,
                policy_version="fixture-policy-v1",
            )
        )
    return outputs


def test_blueprint_declares_bounded_graph_and_safe_scope(mule_blueprint):
    assert mule_blueprint.attack_family is AttackFamily.MULE_NETWORK_STRUCTURING
    assert [step.step_id for step in mule_blueprint.ordered_sequence()] == [
        "network-context",
        "source-allocation",
        "layering",
        "fan-in-cashout",
    ]
    expected = {
        "mule_account_count",
        "fan_out",
        "fan_in",
        "transfer_count",
        "transfer_amount_mean",
        "transfer_amount_stddev",
        "per_transfer_cap",
        "inter_transfer_delay_minutes",
        "layering_depth",
        "destination_diversity",
        "temporal_spread_hours",
        "source_allocation_concentration",
        "cash_out_probability",
        "context_transaction_count_per_account",
        "context_duration_days",
        "context_amount_mean",
        "context_amount_stddev",
        "randomness_seed_offset",
    }
    assert set(mule_blueprint.parameters) == expected
    for name, spec in mule_blueprint.parameters.items():
        assert spec.minimum is not None and spec.maximum is not None
        assert spec.minimum <= spec.default <= spec.maximum
        assert spec.mutable is (name != "randomness_seed_offset")
    assert mule_blueprint.realism_constraints.custom["benchmark_only"] is True
    assert "jurisdiction-specific" in MULE_NETWORK_BLUEPRINT_PROMPT


def test_identifier_selects_only_the_mule_family():
    identifier = MuleNetworkBlueprintIdentifier()
    context = IdentificationContext(
        target_families=[AttackFamily.MULE_NETWORK_STRUCTURING], seed=91
    )
    proposal = identifier.propose(context)[0]
    assert proposal.attack_id == "mule-network-structuring-91"
    excluded = identifier.propose(
        IdentificationContext(target_families=[AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT])
    )
    assert excluded == []


def test_generation_is_deterministic_and_seed_variation_is_fresh(
    mule_blueprint, mule_config
):
    generator = MuleNetworkStructuringGenerator()
    first = generator.generate(mule_blueprint, mule_config)
    second = generator.generate(mule_blueprint, mule_config)
    different = generator.generate(
        mule_blueprint, mule_config.model_copy(update={"seed": mule_config.seed + 1})
    )
    assert first.to_json() == second.to_json()
    assert first.batch_id == second.batch_id
    assert first.batch_id != different.batch_id
    assert set(first.scenario_ids).isdisjoint(different.scenario_ids)
    assert {item.transaction_id for item in first.transactions}.isdisjoint(
        item.transaction_id for item in different.transactions
    )


def test_generation_preserves_labels_ids_lineage_and_order(mule_blueprint, mule_config):
    batch = MuleNetworkStructuringGenerator().generate(mule_blueprint, mule_config)
    assert len(batch.transactions) == 26
    assert batch.fraud_count == 12
    assert len({transaction.transaction_id for transaction in batch.transactions}) == 26
    assert [transaction.sequence_index for transaction in batch.transactions] == list(range(26))
    assert [transaction.timestamp for transaction in batch.transactions] == sorted(
        transaction.timestamp for transaction in batch.transactions
    )
    context = [transaction for transaction in batch.transactions if not transaction.is_fraud]
    fraud = [transaction for transaction in batch.transactions if transaction.is_fraud]
    assert len(context) == 14
    assert all(transaction.label is FraudLabel.LEGITIMATE for transaction in context)
    assert all(transaction.attack_family is None for transaction in context)
    assert all(transaction.label is FraudLabel.FRAUD for transaction in fraud)
    assert all(
        transaction.attack_family is AttackFamily.MULE_NETWORK_STRUCTURING
        for transaction in fraud
    )
    assert all(transaction.blueprint_id == mule_blueprint.attack_id for transaction in fraud)
    assert all(transaction.generation == 0 for transaction in batch.transactions)


def test_graph_stages_and_constraints_are_enforced(mule_blueprint, mule_config):
    generator = MuleNetworkStructuringGenerator()
    batch = generator.generate(mule_blueprint, mule_config)
    fraud = [transaction for transaction in batch.transactions if transaction.is_fraud]
    stages = [transaction.metadata["synthetic.graph_stage"] for transaction in fraud]
    assert stages[:3] == ["source_allocation"] * 3
    assert stages[-4:] == ["fan_in_cashout"] * 4
    assert {transaction.metadata["synthetic.layer_index"] for transaction in fraud} >= {
        1,
        2,
    }
    assert all(transaction.amount <= 9_500.0 for transaction in fraud)
    assert all(
        transaction.source_account_id != transaction.destination_account_id
        for transaction in fraud
    )
    assert batch.metadata["fidelity"]["constraint_violation_rate"] == 0.0

    with pytest.raises(MuleNetworkConfigurationError, match="fan_out"):
        generator.generate(
            mule_blueprint,
            mule_config.model_copy(
                update={"parameter_overrides": {"mule_account_count": 3, "fan_out": 6}}
            ),
        )
    with pytest.raises(MuleNetworkConfigurationError, match="transfer_count"):
        generator.generate(
            mule_blueprint,
            mule_config.model_copy(
                update={
                    "parameter_overrides": {
                        "transfer_count": 6,
                        "fan_out": 3,
                        "destination_diversity": 4,
                        "layering_depth": 2,
                    }
                }
            ),
        )
    with pytest.raises(MuleNetworkConfigurationError, match="below minimum"):
        generator.generate(
            mule_blueprint,
            mule_config.model_copy(update={"parameter_overrides": {"fan_in": 0}}),
        )


def test_multiple_scenarios_have_no_id_collisions(mule_blueprint, mule_config):
    batch = MuleNetworkStructuringGenerator().generate(
        mule_blueprint, mule_config.model_copy(update={"n_scenarios": 3})
    )
    ids = [transaction.transaction_id for transaction in batch.transactions]
    assert len(batch.scenario_ids) == 3
    assert len(ids) == len(set(ids))


def test_reference_profile_is_streaming_equivalent_and_train_only(mule_tmp_path):
    train = [
        _reference_transaction(0, transaction_type=TransactionType.PAYMENT),
        _reference_transaction(1, transaction_type=TransactionType.TRANSFER),
        _reference_transaction(2, transaction_type=TransactionType.CASH_OUT),
        _reference_transaction(3, label=FraudLabel.FRAUD),
    ]
    _write_jsonl(mule_tmp_path / "train.jsonl", train)
    # Poisoned evaluation files prove the profile method never opens them.
    (mule_tmp_path / "validation.jsonl").write_text("not-json\n", encoding="utf-8")
    (mule_tmp_path / "test.jsonl").write_text("not-json\n", encoding="utf-8")
    path_profile = MuleNetworkReferenceProfile.from_processed_paysim(mule_tmp_path)
    iterator_profile = MuleNetworkReferenceProfile.from_transactions(
        iter(train), source=str((mule_tmp_path / "train.jsonl").resolve())
    )
    assert path_profile == iterator_profile
    assert path_profile.sample_count == 3
    assert path_profile.transfer_sample_count == 1
    assert path_profile.latest_timestamp == train[-1].timestamp

    with pytest.raises(MuleNetworkConfigurationError, match="non-train"):
        MuleNetworkReferenceProfile.from_transactions(
            [_reference_transaction(9, split=DataSplit.VALIDATION)]
        )


def test_fidelity_is_deterministic_and_descriptive(mule_blueprint, mule_config):
    generator = MuleNetworkStructuringGenerator()
    first = generator.generate(mule_blueprint, mule_config).metadata["fidelity"]
    second = generator.generate(mule_blueprint, mule_config).metadata["fidelity"]
    assert first == second
    assert first["observed_mule_accounts"] == 6
    assert first["observed_fan_out"] == 3
    assert first["observed_fan_in"] == 2
    assert first["observed_destination_diversity"] == 4
    assert first["observed_layering_depth"] == 2
    assert 0.5 <= first["overall_fidelity_score"] <= 1.0
    assert "not real laundering prevalence" in first["assumptions"][1]


def test_training_overlap_scan_is_bounded_and_rejects_non_train(
    mule_blueprint, mule_config, mule_tmp_path
):
    batch = MuleNetworkStructuringGenerator().generate(mule_blueprint, mule_config)
    clean = [_reference_transaction(index) for index in range(4)]
    train_path = mule_tmp_path / "train.jsonl"
    _write_jsonl(train_path, clean)
    scan = scan_training_overlap(train_path, batch.transactions)
    assert scan.training_transaction_count == 4
    assert scan.is_fresh

    overlap = [
        *clean,
        _reference_transaction(
            10,
            transaction_id=batch.transactions[0].transaction_id,
            scenario_id=batch.scenario_ids[0],
        )
    ]
    _write_jsonl(train_path, overlap)
    overlapping_scan = scan_training_overlap(train_path, batch.transactions)
    assert not overlapping_scan.is_fresh
    assert overlapping_scan.transaction_id_overlaps == [batch.transactions[0].transaction_id]
    assert overlapping_scan.scenario_id_overlaps == [batch.scenario_ids[0]]

    _write_jsonl(train_path, [_reference_transaction(11, split=DataSplit.TEST)])
    with pytest.raises(ConfrontationValidationError, match="non-train"):
        scan_training_overlap(train_path, batch.transactions)


def test_detector_feature_and_evaluator_compatibility(mule_blueprint, mule_config):
    batch = MuleNetworkStructuringGenerator().generate(mule_blueprint, mule_config)
    frame = TemporalBaselineFeatureExtractor().fit([]).transform(batch.transactions)
    assert len(frame) == len(batch.transactions)
    outputs = _fixture_outputs(batch.transactions)
    scan = TrainingOverlapScan(
        source="fixture-train.jsonl",
        training_transaction_count=100,
        generated_transaction_count=len(batch.transactions),
        train_only_verified=True,
    )
    report = build_mule_network_confrontation_report(
        batch=batch,
        outputs=list(reversed(outputs)),
        training_overlap_scan=scan,
        training_dataset_id="fixture-paysim",
        data_basis="synthetic_fixture",
        integration_only=True,
    )
    scenario = report.scenario_reports[0]
    assert scenario.evaluation_result.protocol is EvaluationProtocol.STATIC_HOLDOUT
    assert scenario.evaluation_result.split is DataSplit.TEST
    assert AttackFamily.MULE_NETWORK_STRUCTURING in (
        scenario.evaluation_result.per_attack_family
    )
    assert scenario.fraudulent_structuring_count == 12
    assert scenario.caught_fraud_count == 6
    assert scenario.evaded_fraud_count == 6
    assert all(
        evasion.ground_truth_label is FraudLabel.FRAUD
        for evasion in report.successful_evasions
    )
    assert report == type(report).from_json(report.to_json())


def test_evaluator_rejects_unverified_or_overlapping_training_scan(
    mule_blueprint, mule_config
):
    batch = MuleNetworkStructuringGenerator().generate(mule_blueprint, mule_config)
    outputs = _fixture_outputs(batch.transactions)
    scan = TrainingOverlapScan(
        source="fixture-train.jsonl",
        training_transaction_count=1,
        generated_transaction_count=len(batch.transactions),
        transaction_id_overlaps=[batch.transactions[0].transaction_id],
        train_only_verified=True,
    )
    with pytest.raises(ConfrontationValidationError, match="overlaps detector training"):
        build_mule_network_confrontation_report(
            batch=batch,
            outputs=outputs,
            training_overlap_scan=scan,
            training_dataset_id="fixture-paysim",
            data_basis="synthetic_fixture",
            integration_only=True,
        )


def test_adaptive_fitness_contract_and_mutable_parameters(mule_blueprint):
    mutable = mule_blueprint.mutable_parameters()
    assert "randomness_seed_offset" not in mutable
    assert mutable
    assert all(spec.minimum is not None and spec.maximum is not None for spec in mutable.values())
    assert calculate_attack_fitness(0.25, 0.8) == pytest.approx(0.6)

    analysis = BlindSpotAnalysis(
        analysis_id="mule-fixture-analysis",
        parent_blueprint_id=mule_blueprint.attack_id,
        detector_model_version="fixture-detector-v2",
        original_parameters=mule_blueprint.default_parameters(),
        evasion_count=1,
        credible_evasion_count=1,
        average_evasion_risk_score=0.2,
        lowest_evasion_risk_score=0.2,
        average_fidelity_score=0.8,
        hardest_evasion_ids=["fixture-evasion"],
        feedback=[],
        parameter_evidence=[],
        directional_evidence_available=False,
        notes=["Fixture proves family-generic bounded mutation only."],
    )
    candidates = generate_mutation_candidates(
        mule_blueprint, analysis, seed=99, candidate_count=3
    )
    assert len(candidates) == 3
    assert all(
        candidate.blueprint.attack_family is AttackFamily.MULE_NETWORK_STRUCTURING
        for candidate in candidates
    )
    assert all(
        candidate.blueprint.parent_blueprint_id == mule_blueprint.attack_id
        and candidate.blueprint.generation == mule_blueprint.generation + 1
        for candidate in candidates
    )
    assert all(
        candidate.blueprint.parameters["randomness_seed_offset"]
        == mule_blueprint.parameters["randomness_seed_offset"]
        for candidate in candidates
    )
