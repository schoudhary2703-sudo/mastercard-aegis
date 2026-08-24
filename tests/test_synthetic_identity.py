"""Synthetic identity tests cover one real behavioral attack family only."""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aegis.generate import (
    BaseGenerator,
    BlueprintNotSupportedError,
    GenerationConfig,
    PaySimReferenceProfile,
    SyntheticIdentityBustOutGenerator,
    SyntheticIdentityConfigurationError,
    write_synthetic_identity_artifacts,
)
from aegis.identify import (
    SYNTHETIC_IDENTITY_BLUEPRINT_PROMPT,
    IdentificationContext,
    SyntheticIdentityBlueprintIdentifier,
    build_synthetic_identity_blueprint,
)
from aegis.shared.contracts import Transaction, TransactionBatch
from aegis.shared.enums import AttackFamily, DataSplit, FraudLabel, TransactionType


@pytest.fixture
def red_tmp_path() -> Iterator[Path]:
    path = (Path("data/interim") / f"bustout-test-{uuid.uuid4().hex}").resolve()
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path)


@pytest.fixture
def bustout_blueprint():
    return build_synthetic_identity_blueprint()


@pytest.fixture
def bustout_config():
    return GenerationConfig(
        seed=77,
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        split=DataSplit.TEST,
    )


def test_blueprint_declares_bounded_sequence_and_parameters(bustout_blueprint):
    assert bustout_blueprint.attack_family is AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT
    assert [step.step_id for step in bustout_blueprint.ordered_sequence()] == [
        "identity-onboarding",
        "warmup-history",
        "trust-transition",
        "bust-out",
    ]
    required = {
        "warmup_transaction_count",
        "warmup_amount_mean",
        "warmup_amount_stddev",
        "warmup_duration_days",
        "account_age_days",
        "bustout_amount_multiplier",
        "bustout_transaction_count",
        "bustout_window_hours",
        "destination_diversity",
        "transition_delay_hours",
        "warmup_transfer_probability",
        "randomness_seed_offset",
    }
    assert set(bustout_blueprint.parameters) == required
    for spec in bustout_blueprint.parameters.values():
        assert spec.minimum is not None
        assert spec.maximum is not None
        assert spec.minimum <= spec.default <= spec.maximum


def test_identifier_and_prompt_are_structured_for_future_genai():
    identifier = SyntheticIdentityBlueprintIdentifier()
    proposals = identifier.propose(
        IdentificationContext(
            target_families=[AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT],
            observed_feature_names=["temporal.velocity_24h"],
            seed=42,
        )
    )

    assert len(proposals) == 1
    assert proposals[0].attack_id == "synthetic-identity-bustout-42"
    assert proposals[0].target_features == ["temporal.velocity_24h"]
    assert "AttackBlueprint" in SYNTHETIC_IDENTITY_BLUEPRINT_PROMPT
    assert "detector internals" in SYNTHETIC_IDENTITY_BLUEPRINT_PROMPT
    assert (
        identifier.propose(
            IdentificationContext(target_families=[AttackFamily.MULE_NETWORK_STRUCTURING])
        )
        == []
    )


def test_generator_rejects_invalid_blueprint_and_out_of_bounds_override(
    bustout_blueprint, bustout_config
):
    missing_step = bustout_blueprint.model_copy(
        update={
            "sequence": [step for step in bustout_blueprint.sequence if step.step_id != "bust-out"]
        }
    )
    generator = SyntheticIdentityBustOutGenerator()
    wrong_family = bustout_blueprint.model_copy(
        update={"attack_family": AttackFamily.MULE_NETWORK_STRUCTURING}
    )
    with pytest.raises(BlueprintNotSupportedError, match="does not support"):
        generator.generate(wrong_family, bustout_config)
    with pytest.raises(BlueprintNotSupportedError, match="missing steps"):
        generator.generate(missing_step, bustout_config)
    with pytest.raises(SyntheticIdentityConfigurationError, match="exceeds maximum"):
        generator.generate(
            bustout_blueprint,
            bustout_config.model_copy(
                update={"parameter_overrides": {"warmup_transaction_count": 41}}
            ),
        )


def test_generation_is_fully_deterministic_and_interface_compliant(
    bustout_blueprint, bustout_config
):
    generator = SyntheticIdentityBustOutGenerator()
    first = generator.generate(bustout_blueprint, bustout_config)
    second = generator.generate(bustout_blueprint, bustout_config)

    assert isinstance(generator, BaseGenerator)
    assert first.to_json() == second.to_json()
    assert first.batch_id == second.batch_id
    assert first.seed == 77
    assert first.generator_name == "synthetic-identity-bustout"
    assert len(first.scenario_ids) == 1


def test_sequence_is_chronological_with_warmup_then_bustout(bustout_blueprint, bustout_config):
    batch = SyntheticIdentityBustOutGenerator().generate(bustout_blueprint, bustout_config)
    warmup = [
        transaction
        for transaction in batch.transactions
        if transaction.metadata["synthetic.phase"] == "warmup"
    ]
    bustout = [
        transaction
        for transaction in batch.transactions
        if transaction.metadata["synthetic.phase"] == "bustout"
    ]

    assert len(warmup) == 12
    assert len(bustout) == 3
    assert batch.transactions == sorted(
        batch.transactions, key=lambda transaction: transaction.timestamp
    )
    assert max(transaction.timestamp for transaction in warmup) < min(
        transaction.timestamp for transaction in bustout
    )
    assert all(transaction.label is FraudLabel.LEGITIMATE for transaction in warmup)
    assert all(transaction.attack_family is None for transaction in warmup)
    assert all(transaction.label is FraudLabel.FRAUD for transaction in bustout)
    assert all(
        transaction.attack_family is AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT
        for transaction in bustout
    )
    assert sum(transaction.amount for transaction in bustout) / len(bustout) > (
        sum(transaction.amount for transaction in warmup) / len(warmup)
    )


def test_transactions_have_canonical_synthetic_provenance_and_balances(
    bustout_blueprint, bustout_config
):
    batch = SyntheticIdentityBustOutGenerator().generate(bustout_blueprint, bustout_config)
    scenario_id = batch.scenario_ids[0]

    assert all(transaction.is_synthetic for transaction in batch.transactions)
    assert all(transaction.scenario_id == scenario_id for transaction in batch.transactions)
    assert all(
        transaction.blueprint_id == bustout_blueprint.attack_id
        for transaction in batch.transactions
    )
    assert all(transaction.split is DataSplit.TEST for transaction in batch.transactions)
    assert all(
        transaction.sequence_index == index for index, transaction in enumerate(batch.transactions)
    )
    assert all(
        transaction.metadata["synthetic.attack_family"]
        == AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT.value
        for transaction in batch.transactions
    )
    assert all(transaction.source_balance_before is not None for transaction in batch.transactions)
    assert all(transaction.source_balance_after is not None for transaction in batch.transactions)


def test_fidelity_summary_reports_measurable_sequence_checks(bustout_blueprint, bustout_config):
    batch = SyntheticIdentityBustOutGenerator().generate(bustout_blueprint, bustout_config)
    fidelity = batch.metadata["fidelity"]

    assert fidelity["reference_basis"] == "bounded_fallback"
    assert fidelity["warmup_count"] == 12
    assert fidelity["fraud_count"] == 3
    assert fidelity["fraud_proportion"] == pytest.approx(0.2)
    assert 0.0 <= fidelity["warmup_amount_similarity"] <= 1.0
    assert 0.0 <= fidelity["transaction_type_similarity"] <= 1.0
    assert 0.0 <= fidelity["temporal_spacing_reasonableness"] <= 1.0
    assert fidelity["transition_sharpness"] > 2.0
    assert fidelity["constraint_violation_rate"] == 0.0
    assert 0.0 <= fidelity["overall_fidelity_score"] <= 1.0
    assert "not measured statistical fidelity" in fidelity["assumptions"][0]


def test_reference_profile_reads_legitimate_train_rows_only(red_tmp_path):
    reference_dir = red_tmp_path / "processed-run"
    reference_dir.mkdir()
    train_rows = [
        Transaction(
            transaction_id="train-legit-1",
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            source_account_id="C1",
            destination_account_id="C2",
            amount=20.0,
            currency="INR",
            transaction_type=TransactionType.PAYMENT,
            label=FraudLabel.LEGITIMATE,
            split=DataSplit.TRAIN,
        ),
        Transaction(
            transaction_id="train-legit-2",
            timestamp=datetime(2025, 1, 2, tzinfo=timezone.utc),
            source_account_id="C3",
            destination_account_id="C4",
            amount=40.0,
            currency="INR",
            transaction_type=TransactionType.TRANSFER,
            label=FraudLabel.LEGITIMATE,
            split=DataSplit.TRAIN,
        ),
        Transaction(
            transaction_id="train-fraud",
            timestamp=datetime(2025, 1, 3, tzinfo=timezone.utc),
            source_account_id="C5",
            destination_account_id="C6",
            amount=9_000.0,
            currency="INR",
            transaction_type=TransactionType.CASH_OUT,
            label=FraudLabel.FRAUD,
            attack_family=AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT,
            split=DataSplit.TRAIN,
        ),
    ]
    with (reference_dir / "train.jsonl").open("w", encoding="utf-8") as handle:
        for transaction in train_rows:
            handle.write(transaction.model_dump_json() + "\n")
    with (reference_dir / "test.jsonl").open("w", encoding="utf-8") as handle:
        handle.write(
            train_rows[0].model_copy(update={"amount": 999_999.0}).model_dump_json() + "\n"
        )

    profile = PaySimReferenceProfile.from_processed_paysim(reference_dir)

    assert profile.basis == "processed_paysim_train"
    assert profile.sample_count == 2
    assert profile.amount_mean == pytest.approx(30.0)
    assert profile.amount_stddev == pytest.approx(14.1421356)
    assert profile.transaction_type_distribution == {"payment": 0.5, "transfer": 0.5}
    assert profile.currency == "INR"


def test_output_serialization_round_trips(bustout_blueprint, bustout_config, red_tmp_path):
    batch = SyntheticIdentityBustOutGenerator().generate(bustout_blueprint, bustout_config)
    artifacts = write_synthetic_identity_artifacts(
        red_tmp_path / "synthetic" / "round_0" / "scenario", batch, bustout_blueprint
    )

    restored_transactions = [
        Transaction.model_validate_json(line)
        for line in artifacts["transactions"].read_text(encoding="utf-8").splitlines()
    ]
    report = json.loads(artifacts["scenario"].read_text(encoding="utf-8"))

    assert restored_transactions == batch.transactions
    assert TransactionBatch.model_validate(
        report["batch"] | {"transactions": restored_transactions}
    )
    assert report["transaction_count"] == 15
    assert report["fraud_count"] == 3
    assert report["fidelity"] == batch.metadata["fidelity"]


def test_sequence_integrity_rejects_truncation_and_short_horizon(bustout_blueprint, bustout_config):
    generator = SyntheticIdentityBustOutGenerator()
    with pytest.raises(SyntheticIdentityConfigurationError, match="would truncate"):
        generator.generate(
            bustout_blueprint,
            bustout_config.model_copy(update={"max_transactions": 14}),
        )
    with pytest.raises(SyntheticIdentityConfigurationError, match="exceeds configured horizon"):
        generator.generate(
            bustout_blueprint,
            bustout_config.model_copy(update={"time_horizon": timedelta(days=10)}),
        )
