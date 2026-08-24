"""First Red/Blue confrontation tests; all detector data here is fixture-only."""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from scripts.run_bustout_confrontation import (
    ConfrontationPipelineConfig,
    run_bustout_confrontation,
)

from aegis.evaluate import (
    BustOutConfrontationReport,
    ConfrontationValidationError,
    build_bustout_confrontation_report,
)
from aegis.generate import GenerationConfig, SyntheticIdentityBustOutGenerator
from aegis.identify import build_synthetic_identity_blueprint
from aegis.shared.contracts import DetectorOutput, Transaction, TransactionBatch
from aegis.shared.enums import (
    DataSplit,
    FraudLabel,
    RecommendedAction,
    TransactionType,
)

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def integration_tmp_path() -> Iterator[Path]:
    path = Path("data/interim") / f"confrontation-test-{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def bustout_batch() -> TransactionBatch:
    blueprint = build_synthetic_identity_blueprint()
    return SyntheticIdentityBustOutGenerator().generate(
        blueprint,
        GenerationConfig(
            seed=31415,
            n_scenarios=1,
            start_time=T0,
            time_horizon=timedelta(days=120),
            split=DataSplit.TEST,
        ),
    )


def _outputs_for_batch(batch: TransactionBatch) -> list[DetectorOutput]:
    fraud_seen = 0
    outputs: list[DetectorOutput] = []
    for txn in batch.transactions:
        if txn.is_fraud:
            fraud_seen += 1
            caught = fraud_seen == 1
            risk = 0.9 if caught else 0.1 * fraud_seen
        else:
            caught = False
            risk = 0.05
        outputs.append(
            DetectorOutput(
                transaction_id=txn.transaction_id,
                risk_score=risk,
                predicted_label=FraudLabel.FRAUD if caught else FraudLabel.LEGITIMATE,
                recommended_action=(
                    RecommendedAction.DECLINE if caught else RecommendedAction.APPROVE
                ),
                model_version="fixture-model-v1",
                threshold=0.5,
                policy_version="fixture-policy-v1",
            )
        )
    return outputs


def _training_transaction(
    index: int = 0,
    *,
    transaction_id: str | None = None,
    scenario_id: str | None = None,
) -> Transaction:
    return Transaction(
        transaction_id=transaction_id or f"train-{index}",
        timestamp=T0 - timedelta(days=2, minutes=-index),
        source_account_id=f"train-source-{index % 4}",
        destination_account_id=f"train-destination-{index % 3}",
        amount=50.0 + index,
        transaction_type=TransactionType.PAYMENT,
        label=FraudLabel.LEGITIMATE,
        scenario_id=scenario_id,
        split=DataSplit.TRAIN,
    )


def _build_report(batch: TransactionBatch, outputs: list[DetectorOutput]):
    return build_bustout_confrontation_report(
        batch=batch,
        outputs=outputs,
        training_transactions=[_training_transaction()],
        training_dataset_id="fixture-paysim",
        data_basis="synthetic_fixture",
        integration_only=True,
    )


def test_warmup_and_bustout_labels_feed_accounting_without_contract_hacks(bustout_batch):
    report = _build_report(bustout_batch, _outputs_for_batch(bustout_batch))
    scenario = report.scenario_reports[0]

    warmup = [txn for txn in bustout_batch.transactions if not txn.is_fraud]
    bustout = [txn for txn in bustout_batch.transactions if txn.is_fraud]
    assert all(txn.label is FraudLabel.LEGITIMATE for txn in warmup)
    assert all(txn.label is FraudLabel.FRAUD for txn in bustout)
    assert scenario.total_transactions == 15
    assert scenario.legitimate_warmup_transaction_count == 12
    assert scenario.fraudulent_bustout_count == 3
    assert scenario.caught_fraud_count == 1
    assert scenario.evaded_fraud_count == 2
    assert scenario.fraud_recall == pytest.approx(1 / 3)
    assert scenario.evaluation_result.overall.counts.true_positives == 1
    assert scenario.evaluation_result.overall.counts.false_negatives == 2


def test_evasions_preserve_fraud_ground_truth_and_event_details(bustout_batch):
    report = _build_report(bustout_batch, _outputs_for_batch(bustout_batch))
    fraud_by_id = {txn.transaction_id: txn for txn in bustout_batch.transactions if txn.is_fraud}

    assert len(report.successful_evasions) == 2
    for evasion in report.successful_evasions:
        assert evasion.ground_truth_label is FraudLabel.FRAUD
        assert fraud_by_id[evasion.transaction_id].label is FraudLabel.FRAUD
        assert evasion.detector_risk_score < 0.5
        assert evasion.action is RecommendedAction.APPROVE
    for event in report.scenario_reports[0].fraudulent_events:
        assert 0.0 <= event.risk_score <= 1.0
        assert event.ground_truth_label is FraudLabel.FRAUD
        assert event.model_version == "fixture-model-v1"


def test_generated_scenario_must_not_overlap_detector_training(bustout_batch):
    outputs = _outputs_for_batch(bustout_batch)
    with pytest.raises(ConfrontationValidationError, match="transactions overlap"):
        build_bustout_confrontation_report(
            batch=bustout_batch,
            outputs=outputs,
            training_transactions=[bustout_batch.transactions[0]],
            training_dataset_id="bad-fixture",
            data_basis="synthetic_fixture",
            integration_only=True,
        )

    overlapping_scenario = _training_transaction(
        scenario_id=bustout_batch.scenario_ids[0], transaction_id="different-training-id"
    )
    with pytest.raises(ConfrontationValidationError, match="scenarios overlap"):
        build_bustout_confrontation_report(
            batch=bustout_batch,
            outputs=outputs,
            training_transactions=[overlapping_scenario],
            training_dataset_id="bad-fixture",
            data_basis="synthetic_fixture",
            integration_only=True,
        )


def test_scenario_is_indivisible_and_output_ids_are_joined_not_positioned(bustout_batch):
    outputs = list(reversed(_outputs_for_batch(bustout_batch)))
    report = _build_report(bustout_batch, outputs)
    assert report.scenario_reports[0].caught_fraud_count == 1

    split_transactions = list(bustout_batch.transactions)
    split_transactions[-1] = split_transactions[-1].model_copy(
        update={"split": DataSplit.HOLDOUT}
    )
    invalid_batch = bustout_batch.model_copy(update={"transactions": split_transactions})
    with pytest.raises(ConfrontationValidationError, match="multiple data splits"):
        _build_report(invalid_batch, outputs)


def test_hardest_evasion_ranking_is_deterministic(bustout_batch):
    outputs = _outputs_for_batch(bustout_batch)
    first = _build_report(bustout_batch, outputs)
    second = _build_report(bustout_batch, list(reversed(outputs)))

    first_ranking = [
        (record.rank, record.transaction_id, record.hardness_score)
        for record in first.hardest_evasions
    ]
    second_ranking = [
        (record.rank, record.transaction_id, record.hardness_score)
        for record in second.hardest_evasions
    ]
    assert first_ranking == second_ranking
    assert first_ranking[0][2] >= first_ranking[1][2]
    assert all(record.rank is None for record in first.successful_evasions)


def test_confrontation_result_serializes_and_round_trips(bustout_batch):
    report = _build_report(bustout_batch, _outputs_for_batch(bustout_batch))
    restored = BustOutConfrontationReport.from_json(report.to_json())
    assert restored == report
    assert restored.metadata["adaptive"] is False
    assert restored.integration_only is True


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


def test_real_modules_run_end_to_end_on_integration_fixtures(integration_tmp_path):
    processed = integration_tmp_path / "fixture-paysim-run"
    processed.mkdir()
    train = _make_split(100, 0, DataSplit.TRAIN)
    _write_transactions(processed / "train.jsonl", train)
    _write_transactions(processed / "validation.jsonl", _make_split(30, 10, DataSplit.VALIDATION))
    _write_transactions(processed / "test.jsonl", _make_split(30, 20, DataSplit.TEST))

    result = run_bustout_confrontation(
        ConfrontationPipelineConfig(
            processed_dir=processed,
            output_dir=integration_tmp_path / "confrontations",
            model_output_dir=integration_tmp_path / "models",
            seed=77,
            num_boost_round=8,
            latency_sample_size=3,
            integration_only=True,
            data_basis="synthetic_fixture",
        )
    )

    training_ids = {txn.transaction_id for txn in train}
    generated_ids = {txn.transaction_id for txn in result.batch.transactions}
    assert training_ids.isdisjoint(generated_ids)
    assert result.report.training_transaction_count == len(train)
    assert result.report.integration_only is True
    assert result.report.data_basis == "synthetic_fixture"
    assert len(result.outputs) == len(result.batch.transactions)
    assert all(txn.split is DataSplit.TEST for txn in result.batch.transactions)
    assert all(path.exists() for path in result.artifacts.values())
    scenario = result.report.scenario_reports[0]
    assert scenario.caught_fraud_count + scenario.evaded_fraud_count == (
        scenario.fraudulent_bustout_count
    )
    assert len(scenario.fraudulent_events) == scenario.fraudulent_bustout_count
    assert scenario.evaluation_result.overall.recall == scenario.fraud_recall
    assert BustOutConfrontationReport.from_json(
        result.artifacts["report"].read_text(encoding="utf-8")
    ) == result.report
    assert scenario.model_version == "xgboost-baseline-77"
