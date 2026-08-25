"""Memory-safe confrontation execution must be semantically identical to the
original eager-load path it replaced.

Diagnosed incident: `run_bustout_confrontation` loaded train, validation, and
test as full `Transaction` lists simultaneously just to compute a max
timestamp and a training-ID set, and crashed with `MemoryError` loading
validation right after a successful full load of train (4,463,587 rows). See
the module docstring in `scripts/run_bustout_confrontation.py` for the fix.
"""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from scripts.run_bustout_confrontation import (
    ConfrontationPipelineConfig,
    _is_valid_model_artifact,
    _last_jsonl_timestamp,
    _training_id_skeletons,
    run_bustout_confrontation,
)
from scripts.train_baseline_detector import BaselinePipelineConfig, run_baseline_pipeline

from aegis.evaluate import build_bustout_confrontation_report
from aegis.features import load_transactions_jsonl
from aegis.generate import GenerationConfig, SyntheticIdentityBustOutGenerator
from aegis.identify import build_synthetic_identity_blueprint
from aegis.shared.contracts import DetectorOutput, Transaction
from aegis.shared.enums import DataSplit, FraudLabel, RecommendedAction, TransactionType

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def work_dir() -> Iterator[Path]:
    path = Path("data/interim") / f"confrontation-lowmem-test-{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _make_split(
    n: int, day: int, split: DataSplit, *, scenario_every: int | None = None
) -> list[Transaction]:
    out = []
    for i in range(n):
        fraud = i % 10 == 0
        out.append(
            Transaction(
                transaction_id=f"{split.value}-{i}",
                timestamp=T0 + timedelta(days=day, minutes=i * 5),
                source_account_id=f"src-{i % 7}",
                destination_account_id=f"dst-{i % 5}",
                amount=(700.0 + i) if fraud else (30.0 + i % 25),
                transaction_type=TransactionType.CASH_OUT if fraud else TransactionType.PAYMENT,
                label=FraudLabel.FRAUD if fraud else FraudLabel.LEGITIMATE,
                split=split,
                scenario_id=f"scn-{i}" if scenario_every and i % scenario_every == 0 else None,
            )
        )
    return out


def _write_jsonl(path: Path, transactions: list[Transaction]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for txn in transactions:
            fh.write(txn.to_json())
            fh.write("\n")


# --- _last_jsonl_timestamp --------------------------------------------------
def test_last_jsonl_timestamp_matches_true_max(work_dir):
    txns = _make_split(37, 0, DataSplit.TRAIN)
    path = work_dir / "split.jsonl"
    _write_jsonl(path, txns)
    assert _last_jsonl_timestamp(path) == max(t.timestamp for t in txns)


def test_last_jsonl_timestamp_single_row(work_dir):
    txns = _make_split(1, 0, DataSplit.TRAIN)
    path = work_dir / "split.jsonl"
    _write_jsonl(path, txns)
    assert _last_jsonl_timestamp(path) == txns[0].timestamp


def test_last_jsonl_timestamp_works_with_tiny_read_chunks(work_dir):
    """Forces the backward-seek loop through many small reads instead of one."""
    from scripts.run_bustout_confrontation import _last_jsonl_line

    txns = _make_split(20, 0, DataSplit.TRAIN)
    path = work_dir / "split.jsonl"
    _write_jsonl(path, txns)
    last_line_small_chunks = _last_jsonl_line(path, chunk_size=8)
    last_line_default = _last_jsonl_line(path)
    assert last_line_small_chunks == last_line_default
    parsed_id = Transaction.model_validate_json(last_line_small_chunks).transaction_id
    assert parsed_id == txns[-1].transaction_id


# --- _training_id_skeletons --------------------------------------------------
def test_training_id_skeletons_match_full_load_ids_and_order(work_dir):
    txns = _make_split(50, 0, DataSplit.TRAIN, scenario_every=None)
    path = work_dir / "train.jsonl"
    _write_jsonl(path, txns)

    skeletons = _training_id_skeletons(path)
    full = load_transactions_jsonl(path)

    assert [s.transaction_id for s in skeletons] == [t.transaction_id for t in full]
    assert all(s.scenario_id is None for s in skeletons)  # none of these fixture rows have one


def test_training_id_skeletons_preserve_scenario_id_when_present(work_dir):
    # PaySim-derived rows never carry a scenario_id, but the skeleton builder
    # must not silently drop one if a row somehow has it.
    txns = _make_split(20, 0, DataSplit.TRAIN, scenario_every=4)
    path = work_dir / "train.jsonl"
    _write_jsonl(path, txns)

    skeletons = _training_id_skeletons(path)
    full = load_transactions_jsonl(path)
    assert [s.scenario_id for s in skeletons] == [t.scenario_id for t in full]
    assert any(s.scenario_id is not None for s in skeletons)  # fixture actually exercises this


def test_training_id_skeletons_are_lighter_than_full_transactions_conceptually():
    """Skeletons must not carry the required-but-irrelevant fields as real data -
    accessing them should behave like an unset field, not a fabricated value."""
    txns = [
        Transaction(
            transaction_id="only-one",
            timestamp=T0,
            source_account_id="src",
            amount=42.0,
            label=FraudLabel.LEGITIMATE,
        )
    ]
    import tempfile

    with tempfile.TemporaryDirectory(dir="data/interim") as tmp:
        path = Path(tmp) / "train.jsonl"
        _write_jsonl(path, txns)
        from scripts.run_bustout_confrontation import _training_id_skeletons as build

        skeletons = build(path)
    assert skeletons[0].transaction_id == "only-one"
    # Template placeholder, not the real 42.0 - amount is never read downstream.
    assert skeletons[0].amount == 0.0


# --- end-to-end semantic equivalence: skeleton vs. full training list -------
def test_confrontation_report_identical_with_skeleton_vs_full_training_list(work_dir):
    blueprint = build_synthetic_identity_blueprint()
    batch = SyntheticIdentityBustOutGenerator().generate(
        blueprint,
        GenerationConfig(
            seed=99,
            n_scenarios=1,
            start_time=T0,
            time_horizon=timedelta(days=120),
            split=DataSplit.TEST,
        ),
    )
    outputs: list[DetectorOutput] = []
    for i, txn in enumerate(batch.transactions):
        caught = txn.is_fraud and i % 2 == 0
        outputs.append(
            DetectorOutput(
                transaction_id=txn.transaction_id,
                risk_score=0.9 if caught else 0.1,
                predicted_label=FraudLabel.FRAUD if caught else FraudLabel.LEGITIMATE,
                recommended_action=(
                    RecommendedAction.DECLINE if caught else RecommendedAction.APPROVE
                ),
                model_version="fixture-v1",
                threshold=0.5,
            )
        )

    train = _make_split(60, -5, DataSplit.TRAIN)
    path = work_dir / "train.jsonl"
    _write_jsonl(path, train)

    full_report = build_bustout_confrontation_report(
        batch=batch,
        outputs=outputs,
        training_transactions=train,
        training_dataset_id="fixture",
        data_basis="synthetic_fixture",
        integration_only=True,
    )
    skeleton_report = build_bustout_confrontation_report(
        batch=batch,
        outputs=outputs,
        training_transactions=_training_id_skeletons(path),
        training_dataset_id="fixture",
        data_basis="synthetic_fixture",
        integration_only=True,
    )

    # Everything except per-call identity/creation timestamps must match -
    # `evaluation_result.created_at` is freshly stamped on every call, even
    # with byte-identical inputs (confirmed by diffing two full-list calls
    # against each other before trusting this as a skeleton-vs-full check).
    exclude: dict[str, Any] = {
        "created_at": True,
        "report_id": True,
        "scenario_reports": {"__all__": {"evaluation_result": {"created_at"}}},
    }
    full_dump = full_report.model_dump(mode="json", exclude=exclude)
    skeleton_dump = skeleton_report.model_dump(mode="json", exclude=exclude)
    assert full_dump == skeleton_dump

    # Explicit checks on the specific things this task called out.
    assert full_report.scenario_reports[0].caught_fraud_count == (
        skeleton_report.scenario_reports[0].caught_fraud_count
    )
    assert full_report.scenario_reports[0].evaded_fraud_count == (
        skeleton_report.scenario_reports[0].evaded_fraud_count
    )
    full_ranking = [(r.rank, r.transaction_id) for r in full_report.hardest_evasions]
    skeleton_ranking = [(r.rank, r.transaction_id) for r in skeleton_report.hardest_evasions]
    assert full_ranking == skeleton_ranking
    assert full_report.training_transaction_count == skeleton_report.training_transaction_count


# --- --reuse-model-dir: no retraining ---------------------------------------
def test_reuse_model_dir_skips_retraining_and_leaves_default_output_untouched(work_dir):
    processed = work_dir / "run"
    processed.mkdir()
    _write_jsonl(processed / "train.jsonl", _make_split(80, 0, DataSplit.TRAIN))
    _write_jsonl(processed / "validation.jsonl", _make_split(25, 10, DataSplit.VALIDATION))
    _write_jsonl(processed / "test.jsonl", _make_split(25, 20, DataSplit.TEST))

    pretrained_dir = work_dir / "pretrained"
    trained = run_baseline_pipeline(
        BaselinePipelineConfig(
            processed_dir=processed, output_dir=pretrained_dir, seed=55, num_boost_round=8
        )
    )
    assert _is_valid_model_artifact(trained.artifact_dir)

    unused_model_output = work_dir / "should-not-be-written"
    result = run_bustout_confrontation(
        ConfrontationPipelineConfig(
            processed_dir=processed,
            output_dir=work_dir / "confrontations",
            model_output_dir=unused_model_output,
            seed=55,
            integration_only=True,
            data_basis="synthetic_fixture",
            reuse_model_dir=trained.artifact_dir,
        )
    )

    assert result.model_dir == trained.artifact_dir
    assert not unused_model_output.exists()  # confirms run_baseline_pipeline was never called


def test_invalid_reuse_model_dir_falls_back_to_training(work_dir):
    processed = work_dir / "run"
    processed.mkdir()
    _write_jsonl(processed / "train.jsonl", _make_split(40, 0, DataSplit.TRAIN))
    _write_jsonl(processed / "validation.jsonl", _make_split(15, 10, DataSplit.VALIDATION))
    _write_jsonl(processed / "test.jsonl", _make_split(15, 20, DataSplit.TEST))

    bogus_dir = work_dir / "not-a-real-model"
    bogus_dir.mkdir()  # exists, but has no model.json/metadata.json

    model_output = work_dir / "models"
    result = run_bustout_confrontation(
        ConfrontationPipelineConfig(
            processed_dir=processed,
            output_dir=work_dir / "confrontations",
            model_output_dir=model_output,
            seed=12,
            num_boost_round=6,
            integration_only=True,
            data_basis="synthetic_fixture",
            reuse_model_dir=bogus_dir,
        )
    )
    assert result.model_dir != bogus_dir
    assert model_output.exists()  # training did happen, as the safe fallback


# --- generator reference reads only train -----------------------------------
def test_generator_reference_unaffected_by_validation_and_test_content(work_dir):
    """Same train, different validation/test -> identical reference-derived
    blueprint parameters, proving the reference never reads those splits."""
    train = _make_split(70, 0, DataSplit.TRAIN)

    def _run(tag: str, validation_n: int, test_n: int) -> Path:
        processed = work_dir / tag
        processed.mkdir()
        _write_jsonl(processed / "train.jsonl", train)
        _write_jsonl(
            processed / "validation.jsonl",
            _make_split(validation_n, 10, DataSplit.VALIDATION),
        )
        _write_jsonl(processed / "test.jsonl", _make_split(test_n, 20, DataSplit.TEST))
        result = run_bustout_confrontation(
            ConfrontationPipelineConfig(
                processed_dir=processed,
                output_dir=work_dir / f"confrontations-{tag}",
                model_output_dir=work_dir / f"models-{tag}",
                seed=33,
                num_boost_round=6,
                integration_only=True,
                data_basis="synthetic_fixture",
            )
        )
        return result.artifacts["blueprint"]

    blueprint_a = _run("a", validation_n=15, test_n=15).read_text(encoding="utf-8")
    # Deliberately very different validation/test sizes from run "a".
    blueprint_b = _run("b", validation_n=90, test_n=3).read_text(encoding="utf-8")
    assert blueprint_a == blueprint_b
