from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from aegis.generate import GenerationReferenceSnapshot


def _snapshot() -> GenerationReferenceSnapshot:
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
        additional_training_transaction_ids=["bustout-old-1", "mule-old-1"],
        additional_training_scenario_ids=["bustout-old", "mule-old"],
        defender_model_version="defender-v3-test",
        defender_model_sha256="a" * 64,
        source_artifacts=[],
        limitations=["test fixture"],
    )


def test_snapshot_round_trips_and_counts_all_training_rows(tmp_path: Path) -> None:
    snapshot = _snapshot()
    path = tmp_path / "snapshot.json"
    path.write_text(snapshot.to_json(indent=2), encoding="utf-8")
    loaded = GenerationReferenceSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    assert loaded.total_training_transaction_count == 102
    assert json.loads(loaded.to_json())["dataset_id"] == "paysim-test"


def test_snapshot_builds_all_three_existing_reference_profiles() -> None:
    snapshot = _snapshot()
    bustout = snapshot.to_bustout_profile()
    mule = snapshot.to_mule_profile()
    adaptive = snapshot.to_adaptive_profile()
    assert bustout.sample_count == 98
    assert mule.transfer_sample_count == 20
    assert adaptive.latest_timestamp == snapshot.latest_train_timestamp
    assert {bustout.basis, mule.basis, adaptive.basis} == {
        "precomputed_paysim_train_features"
    }
