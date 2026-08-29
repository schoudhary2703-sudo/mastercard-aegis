"""Frozen train-only statistics for fast, auditable generation runs.

The snapshot is an optimization, not a new source of truth.  It records the
hashes of the train feature artifacts used to derive its moments and the exact
small hard-positive membership used by Defender v3.  Consumers can therefore
avoid rescanning millions of PaySim JSONL rows without replacing provenance
with undocumented constants.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np
from pydantic import Field

from aegis.generate.adaptive_evasion import AdaptiveEvasionReferenceProfile
from aegis.generate.mule_network import MuleNetworkReferenceProfile
from aegis.generate.synthetic_identity import PaySimReferenceProfile
from aegis.shared.base import AegisModel
from aegis.shared.contracts import Transaction


class SnapshotArtifact(AegisModel):
    role: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)
    sha256: str = Field(..., min_length=64, max_length=64)
    byte_size: int = Field(..., ge=0)


class GenerationReferenceSnapshot(AegisModel):
    snapshot_version: str = "generation-reference-v1"
    dataset_id: str = Field(..., min_length=1)
    reference_basis: str = "precomputed_paysim_train_features"
    base_train_transaction_count: int = Field(..., ge=1)
    legitimate_reference_count: int = Field(..., ge=1)
    transfer_reference_count: int = Field(..., ge=0)
    amount_mean: float = Field(..., ge=0.0)
    amount_stddev: float = Field(..., ge=0.0)
    transfer_amount_mean: float = Field(..., ge=0.0)
    transfer_amount_stddev: float = Field(..., ge=0.0)
    transaction_type_distribution: dict[str, float]
    currency: str = Field(..., min_length=3, max_length=3)
    latest_train_timestamp: datetime

    base_transaction_id_prefix: str = "paysim-"
    base_training_has_scenario_ids: bool = False
    additional_training_transaction_ids: list[str]
    additional_training_scenario_ids: list[str]

    defender_model_version: str = Field(..., min_length=1)
    defender_model_sha256: str = Field(..., min_length=64, max_length=64)
    source_artifacts: list[SnapshotArtifact]
    limitations: list[str]

    @property
    def total_training_transaction_count(self) -> int:
        return self.base_train_transaction_count + len(self.additional_training_transaction_ids)

    def to_bustout_profile(self) -> PaySimReferenceProfile:
        return PaySimReferenceProfile(
            basis=self.reference_basis,
            source=f"snapshot:{self.dataset_id}",
            sample_count=self.legitimate_reference_count,
            amount_mean=self.amount_mean,
            amount_stddev=self.amount_stddev,
            transaction_type_distribution=dict(self.transaction_type_distribution),
            currency=self.currency,
        )

    def to_mule_profile(self) -> MuleNetworkReferenceProfile:
        return MuleNetworkReferenceProfile(
            basis=self.reference_basis,
            source=f"snapshot:{self.dataset_id}",
            sample_count=self.legitimate_reference_count,
            transfer_sample_count=self.transfer_reference_count,
            amount_mean=self.amount_mean,
            amount_stddev=self.amount_stddev,
            transfer_amount_mean=self.transfer_amount_mean,
            transfer_amount_stddev=self.transfer_amount_stddev,
            transaction_type_distribution=dict(self.transaction_type_distribution),
            currency=self.currency,
            latest_timestamp=self.latest_train_timestamp,
        )

    def to_adaptive_profile(self) -> AdaptiveEvasionReferenceProfile:
        return AdaptiveEvasionReferenceProfile(
            basis=self.reference_basis,
            source=f"snapshot:{self.dataset_id}",
            sample_count=self.legitimate_reference_count,
            transfer_sample_count=self.transfer_reference_count,
            amount_mean=self.amount_mean,
            amount_stddev=self.amount_stddev,
            transfer_amount_mean=self.transfer_amount_mean,
            transfer_amount_stddev=self.transfer_amount_stddev,
            transaction_type_distribution=dict(self.transaction_type_distribution),
            currency=self.currency,
            latest_timestamp=self.latest_train_timestamp,
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _artifact(role: str, path: Path) -> SnapshotArtifact:
    return SnapshotArtifact(
        role=role,
        path=path.as_posix(),
        sha256=sha256_file(path),
        byte_size=path.stat().st_size,
    )


def _read_hard_positives(path: Path) -> list[Transaction]:
    with path.open("r", encoding="utf-8") as handle:
        return [Transaction.model_validate_json(line) for line in handle if line.strip()]


def build_reference_snapshot(
    *,
    feature_dir: Path,
    processed_summary_path: Path,
    hardening_dir: Path,
    defender_model_dir: Path,
) -> GenerationReferenceSnapshot:
    """Derive the snapshot from frozen train features and small provenance artifacts."""
    feature_dir = Path(feature_dir)
    features_path = feature_dir / "features.npy"
    labels_path = feature_dir / "labels.npy"
    schema_path = feature_dir / "schema.json"
    hard_positives_path = Path(hardening_dir) / "hard_positives.jsonl"
    hardening_provenance_path = Path(hardening_dir) / "provenance.json"
    model_path = Path(defender_model_dir) / "model.json"
    metadata_path = Path(defender_model_dir) / "metadata.json"
    required = (
        features_path,
        labels_path,
        schema_path,
        processed_summary_path,
        hard_positives_path,
        hardening_provenance_path,
        model_path,
        metadata_path,
    )
    missing = [str(path) for path in required if not Path(path).is_file()]
    if missing:
        raise FileNotFoundError(f"snapshot source artifact(s) missing: {missing}")

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    feature_names = [str(name) for name in schema["feature_names"]]
    features = np.load(features_path, mmap_mode="r")
    labels = np.load(labels_path, mmap_mode="r")
    if len(features) != len(labels):
        raise ValueError("train feature and label row counts differ")
    legitimate = labels == 0
    amounts = np.asarray(
        features[:, feature_names.index("temporal.amount")][legitimate], dtype=np.float64
    )
    type_counts: dict[str, int] = {}
    for name in ("payment", "transfer", "cash_in", "cash_out", "debit"):
        column = features[:, feature_names.index(f"temporal.type_{name}")][legitimate]
        type_counts[name] = int(np.asarray(column, dtype=np.int64).sum())
    legitimate_count = int(legitimate.sum())
    transfer_mask = (
        features[:, feature_names.index("temporal.type_transfer")][legitimate] == 1
    )
    transfer_amounts = amounts[transfer_mask]

    processed_summary = json.loads(Path(processed_summary_path).read_text(encoding="utf-8"))
    train_summary = processed_summary["splitting"]["split_statistics"]["train"]
    if int(train_summary["transaction_count"]) != len(labels):
        raise ValueError("processed summary and train feature row counts differ")
    if int(train_summary["legitimate_count"]) != legitimate_count:
        raise ValueError("processed summary and train feature legitimate counts differ")

    hard_positives = _read_hard_positives(hard_positives_path)
    if any(transaction.split.value != "train" for transaction in hard_positives):
        raise ValueError("hard-positive snapshot input contains a non-train row")
    scenario_ids = sorted(
        {transaction.scenario_id for transaction in hard_positives if transaction.scenario_id}
    )
    if len(scenario_ids) == 0 or any(not transaction.scenario_id for transaction in hard_positives):
        raise ValueError("every hard-positive row must carry a scenario id")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return GenerationReferenceSnapshot(
        dataset_id=str(processed_summary["run_id"]),
        base_train_transaction_count=len(labels),
        legitimate_reference_count=legitimate_count,
        transfer_reference_count=len(transfer_amounts),
        amount_mean=float(amounts.mean()),
        amount_stddev=float(amounts.std(ddof=1)),
        transfer_amount_mean=float(transfer_amounts.mean()),
        transfer_amount_stddev=float(transfer_amounts.std(ddof=1)),
        transaction_type_distribution={
            name: count / legitimate_count for name, count in sorted(type_counts.items())
        },
        currency=str(processed_summary["configuration"]["currency"]["value"]),
        latest_train_timestamp=datetime.fromisoformat(
            str(train_summary["timestamp_range_utc"]["maximum"])
        ),
        additional_training_transaction_ids=sorted(
            transaction.transaction_id for transaction in hard_positives
        ),
        additional_training_scenario_ids=scenario_ids,
        defender_model_version=str(metadata["model_version"]),
        defender_model_sha256=sha256_file(model_path),
        source_artifacts=[
            _artifact("train_features", features_path),
            _artifact("train_labels", labels_path),
            _artifact("train_feature_schema", schema_path),
            _artifact("processed_dataset_summary", Path(processed_summary_path)),
            _artifact("defender_v3_hard_positives", hard_positives_path),
            _artifact("defender_v3_hard_positive_provenance", hardening_provenance_path),
            _artifact("defender_v3_metadata", metadata_path),
        ],
        limitations=[
            "Amount moments come from the detector's float32 train feature artifact, so they may "
            "differ from raw JSONL moments at insignificant floating-point precision.",
            "Distributional fidelity is descriptive similarity to legitimate PaySim TRAIN rows, "
            "not evidence of real-world fraud realism.",
            "The base PaySim freshness proof relies on the prepared-data transaction-id namespace "
            "and absence of scenario IDs; hard-positive membership is checked exactly.",
        ],
    )


__all__ = [
    "GenerationReferenceSnapshot",
    "SnapshotArtifact",
    "build_reference_snapshot",
    "sha256_file",
]
