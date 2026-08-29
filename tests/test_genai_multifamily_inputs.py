from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.run_genai_analysis import _build_blind_spot_request, main

from aegis.shared.enums import AttackFamily


def _write_family_confrontation(root: Path, family: AttackFamily) -> Path:
    root.mkdir(parents=True)
    (root / "confrontation.json").write_text(
        json.dumps(
            {
                "model_version": "xgboost-hardened-crossfamily-20260301",
                "scenario_reports": [
                    {"evaded_fraud_count": 2, "caught_fraud_count": 1}
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "blueprint.json").write_text(
        json.dumps(
            {
                "attack_id": f"{family.value}-v1",
                "attack_family": family.value,
                "target_features": ["temporal.amount"],
                "parameters": {
                    "amount": {"mutable": True},
                    "structural": {"mutable": False},
                },
            }
        ),
        encoding="utf-8",
    )
    (root / "hardest_evasions.json").write_text(
        json.dumps([{"detector_risk_score": 0.4, "fidelity_score": 0.8}]),
        encoding="utf-8",
    )
    return root


@pytest.mark.parametrize(
    "family",
    [AttackFamily.MULE_NETWORK_STRUCTURING, AttackFamily.ADAPTIVE_DETECTOR_EVASION],
)
def test_blind_spot_input_path_accepts_other_implemented_families(
    tmp_path: Path, family: AttackFamily
) -> None:
    directory = _write_family_confrontation(tmp_path / family.value, family)
    request, sources = _build_blind_spot_request(directory)
    assert request.attack_family is family
    assert request.mutable_parameters == ["amount"]
    assert request.missed_transaction_count == 2
    assert len(sources) == 2


def test_request_only_prepares_input_without_building_a_provider(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = _write_family_confrontation(
        tmp_path / "mule", AttackFamily.MULE_NETWORK_STRUCTURING
    )
    assert main(["blind-spot", "--confrontation-dir", str(directory), "--request-only"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["attack_family"] == AttackFamily.MULE_NETWORK_STRUCTURING.value
