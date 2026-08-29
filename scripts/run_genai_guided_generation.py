"""Turn one *live* Blind-Spot Analyst artifact into one scored next generation.

This is the closing edge of the loop: the only place a language model's
reasoning is allowed to influence what gets generated, and it is deliberately
narrow.

    live GenAI blind-spot artifact  (data/genai/blind_spot_analyst/<run>.json)
      -> bounds check per proposal  (aegis.loop.genai_handoff)
      -> deterministic child blueprint
      -> deterministic seeded simulator  (aegis.generate)
      -> frozen detector, scored not fitted  (aegis.defend)
      -> persisted GenAIGuidedGeneration  (data/genai/guided_generations/)

What this script does *not* do:

* It never rewrites the model's output. Proposals are taken exactly as the
  artifact recorded them; the adapter accepts or rejects each one, and both
  sets are persisted with the rule that decided.
* It never lets GenAI supply a value. Only *direction* and *magnitude* cross
  the boundary; the new parameter value is recomputed by the same
  deterministic step function the built-in optimizer uses.
* It never trains. The detector is loaded from a frozen artifact directory,
  and `model.json` / `metadata.json` are hashed before and after the run --
  a change in either is a hard failure.

Usage::

    python scripts/run_genai_guided_generation.py \\
        --genai-artifact data/genai/blind_spot_analyst/<run_id>.json \\
        --confrontation-dir data/synthetic/confrontations/<id> \\
        --processed-dir data/processed/paysim/<dataset-id> \\
        --model-dir models/xgboost-hardened-crossfamily-20260301
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aegis.defend import XGBoostDetector
from aegis.evaluate import BustOutConfrontationReport, build_bustout_confrontation_report
from aegis.features import TemporalBaselineFeatureExtractor, load_transactions_jsonl
from aegis.genai.contracts import BlindSpotAnalystResponse, GenAIRunArtifact
from aegis.genai.handoff_contracts import (
    GenAIGuidedGeneration,
    GenAIHandoffProvenance,
)
from aegis.generate import (
    GenerationConfig,
    GenerationReferenceSnapshot,
    PaySimReferenceProfile,
    SyntheticIdentityBustOutGenerator,
    sha256_file,
)
from aegis.loop.genai_handoff import HandoffResult, apply_blind_spot_proposals
from aegis.shared.base import AegisModel
from aegis.shared.contracts import AttackBlueprint, DetectorOutput, Transaction, TransactionBatch
from aegis.shared.enums import DataSplit

# Direct `python scripts/...` execution puts scripts/, not the repo root, on
# sys.path -- same import dance the other confrontation scripts use. The
# training-ID skeleton reader is reused rather than reimplemented so the
# freshness check here is byte-for-byte the one Round 0 ran.
_confrontation_module = importlib.import_module(
    "scripts.run_bustout_confrontation" if __package__ else "run_bustout_confrontation"
)
_training_id_skeletons = _confrontation_module._training_id_skeletons

DEFAULT_MODEL_DIR = Path("models/xgboost-hardened-crossfamily-20260301")
DEFAULT_SEED = 20260901
GUIDED_ARTIFACT_DIR = Path("data/genai/guided_generations")
GUIDED_EVIDENCE_DIR = Path("data/synthetic/genai_guided")


class GenAIGuidedGenerationError(RuntimeError):
    """The guided generation cannot proceed, or produced nothing admissible."""


@dataclass(frozen=True)
class GenAIGuidedConfig:
    """Inputs for one reproducible GenAI-guided generation."""

    genai_artifact: Path
    confrontation_dir: Path
    processed_dir: Path
    model_dir: Path = DEFAULT_MODEL_DIR
    artifact_dir: Path = GUIDED_ARTIFACT_DIR
    evidence_dir: Path = GUIDED_EVIDENCE_DIR
    seed: int = DEFAULT_SEED
    reference_max_rows: int | None = None
    reference_snapshot: Path | None = None
    reuse_identical: bool = False
    require_live: bool = True
    """Refuse a recorded/replayed artifact. A recorded run may still be applied
    with `--allow-recorded`, but it is persisted with `live=False` and can
    never be badged as live downstream."""


@dataclass(frozen=True)
class GenAIGuidedResult:
    """What one run produced, in memory and on disk."""

    record: GenAIGuidedGeneration
    handoff: HandoffResult
    report: BustOutConfrontationReport
    batch: TransactionBatch
    outputs: list[DetectorOutput]
    artifact_path: Path
    evidence_dir: Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_training_skeletons(
    snapshot: GenerationReferenceSnapshot,
    batch: TransactionBatch,
) -> list[Transaction]:
    """Prove freshness without scanning base PaySim row membership.

    Prepared PaySim IDs are generated under the ``paysim-`` namespace and
    carry no scenario ID. The snapshot records that invariant plus every ID
    and scenario in Defender v3's small appended hard-positive set. This is an
    exact membership check for the additions and a namespace proof for base
    PaySim, not a skipped freshness check.
    """
    if snapshot.base_training_has_scenario_ids:
        raise GenAIGuidedGenerationError(
            "fast freshness requires a base training corpus with no scenario IDs"
        )
    generated_ids = {transaction.transaction_id for transaction in batch.transactions}
    bad_namespace = sorted(
        transaction_id
        for transaction_id in generated_ids
        if transaction_id.startswith(snapshot.base_transaction_id_prefix)
    )
    hard_id_overlap = sorted(
        generated_ids & set(snapshot.additional_training_transaction_ids)
    )
    hard_scenario_overlap = sorted(
        set(batch.scenario_ids) & set(snapshot.additional_training_scenario_ids)
    )
    if bad_namespace or hard_id_overlap or hard_scenario_overlap:
        raise GenAIGuidedGenerationError(
            "fast freshness proof failed: "
            f"base_namespace={bad_namespace[:3]}, hard_ids={hard_id_overlap[:3]}, "
            f"hard_scenarios={hard_scenario_overlap[:3]}"
        )

    template = Transaction.model_construct(
        transaction_id="placeholder",
        timestamp=datetime(1970, 1, 1, tzinfo=timezone.utc),
        source_account_id="placeholder",
        amount=0.0,
    )
    skeletons = [
        template.model_copy(update={"transaction_id": transaction_id})
        for transaction_id in snapshot.additional_training_transaction_ids
    ]
    skeletons.extend(
        template.model_copy(
            update={"transaction_id": f"snapshot-scenario-{index}", "scenario_id": scenario_id}
        )
        for index, scenario_id in enumerate(snapshot.additional_training_scenario_ids)
    )
    return skeletons


def _load_reference_snapshot(
    path: Path,
    *,
    detector_model_version: str,
    model_sha256: str,
) -> GenerationReferenceSnapshot:
    snapshot = GenerationReferenceSnapshot.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )
    if snapshot.defender_model_version != detector_model_version:
        raise GenAIGuidedGenerationError(
            "reference snapshot targets "
            f"{snapshot.defender_model_version}, not {detector_model_version}"
        )
    if snapshot.defender_model_sha256 != model_sha256:
        raise GenAIGuidedGenerationError(
            "reference snapshot model hash does not match the frozen detector"
        )
    # The large feature artifacts are intentionally not re-hashed in the demo.
    # The small Defender v3 additions are cheap and must still match exactly.
    for artifact in snapshot.source_artifacts:
        if artifact.role not in {
            "defender_v3_hard_positives",
            "defender_v3_hard_positive_provenance",
            "defender_v3_metadata",
        }:
            continue
        source = Path(artifact.path)
        if not source.is_file() or sha256_file(source) != artifact.sha256:
            raise GenAIGuidedGenerationError(
                f"reference snapshot source no longer matches: {artifact.role} ({source})"
            )
    return snapshot


def _load_genai_artifact(path: Path) -> GenAIRunArtifact:
    artifact = GenAIRunArtifact.model_validate_json(Path(path).read_text(encoding="utf-8"))
    if artifact.stage != "blind_spot_analyst":
        msg = f"{path} is a {artifact.stage!r} run, not a blind_spot_analyst run"
        raise GenAIGuidedGenerationError(msg)
    if not artifact.schema_valid or artifact.response is None:
        msg = f"{path} is a failed run (schema_valid={artifact.schema_valid}); nothing to apply"
        raise GenAIGuidedGenerationError(msg)
    return artifact


def _build_provenance(
    artifact: GenAIRunArtifact,
    *,
    artifact_path: Path,
    confrontation_id: str,
    source_artifact: str,
    detector_model_version: str,
) -> GenAIHandoffProvenance:
    """Copy provenance off the artifact. Nothing here is inferred or defaulted:
    `live` in particular is whatever the run recorded, so a replay stays a
    replay all the way to the UI."""
    return GenAIHandoffProvenance(
        genai_run_id=artifact.run_id,
        provider=artifact.provenance.provider,
        model=artifact.provenance.model,
        prompt_version=artifact.provenance.prompt_version,
        live=artifact.provenance.live,
        genai_artifact=artifact_path.as_posix(),
        source_confrontation_id=confrontation_id,
        source_artifact=source_artifact,
        detector_model_version=detector_model_version,
    )


def _known_scenario_ids(roots: Sequence[Path]) -> set[str]:
    """Scenario ids any previously persisted confrontation already used."""
    known: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for report_path in root.rglob("confrontation.json"):
            try:
                payload = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for scenario in payload.get("scenario_reports") or []:
                if isinstance(scenario, dict) and isinstance(scenario.get("scenario_id"), str):
                    known.add(scenario["scenario_id"])
    return known


def _generation_id(*, genai_run_id: str, blueprint_id: str, seed: int) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {"genai_run_id": genai_run_id, "blueprint": blueprint_id, "seed": seed},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:12]
    return f"genai-guided-{digest}"


def _hardest_survivor(report: BustOutConfrontationReport) -> dict[str, object] | None:
    ranked = report.hardest_evasions or report.successful_evasions
    return ranked[0].model_dump(mode="json") if ranked else None


def run_genai_guided_generation(config: GenAIGuidedConfig) -> GenAIGuidedResult:
    """Apply one live blind-spot artifact and score exactly one fresh scenario."""
    artifact_path = Path(config.genai_artifact)
    artifact = _load_genai_artifact(artifact_path)
    if config.require_live and not artifact.provenance.live:
        msg = (
            f"{artifact_path} is a recorded replay (live=False). Pass --allow-recorded to apply "
            "it anyway; it will be persisted as live=False and can never be badged live."
        )
        raise GenAIGuidedGenerationError(msg)
    response = BlindSpotAnalystResponse.model_validate(artifact.response)

    confrontation_dir = Path(config.confrontation_dir)
    parent_blueprint = AttackBlueprint.model_validate_json(
        (confrontation_dir / "blueprint.json").read_text(encoding="utf-8")
    )
    parent_report = BustOutConfrontationReport.model_validate_json(
        (confrontation_dir / "confrontation.json").read_text(encoding="utf-8")
    )

    model_dir = Path(config.model_dir)
    model_path = model_dir / "model.json"
    metadata_path = model_dir / "metadata.json"
    if not model_path.is_file() or not metadata_path.is_file():
        msg = f"frozen detector artifact not found: {model_dir}"
        raise GenAIGuidedGenerationError(msg)
    model_hash_before = _sha256(model_path)
    metadata_hash_before = _sha256(metadata_path)
    detector = XGBoostDetector.load(str(model_dir))

    # ---- Task A: apply the model's proposals under the bounds --------------
    provenance = _build_provenance(
        artifact,
        artifact_path=artifact_path,
        confrontation_id=parent_report.report_id,
        source_artifact=(confrontation_dir / "confrontation.json").as_posix(),
        detector_model_version=detector.model_version,
    )
    handoff = apply_blind_spot_proposals(
        response,
        parent_blueprint,
        seed=config.seed,
        provenance=provenance,
        dry_run=False,
    )
    if handoff.blueprint is None or not handoff.applied:
        msg = (
            "no proposal survived the bounds check; nothing was generated. "
            f"rejections: {[r.reason for r in handoff.rejected]}"
        )
        raise GenAIGuidedGenerationError(msg)
    child = handoff.blueprint

    # ---- Task B: one fresh scenario from the deterministic simulator -------
    processed_dir = Path(config.processed_dir)
    train_path = processed_dir / "train.jsonl"
    if config.reference_snapshot is None and not train_path.is_file():
        msg = f"prepared PaySim TRAIN artifact not found: {train_path}"
        raise GenAIGuidedGenerationError(msg)
    parent_transactions = load_transactions_jsonl(confrontation_dir / "transactions.jsonl")
    start_time = max(txn.timestamp for txn in parent_transactions) + timedelta(days=1)

    snapshot: GenerationReferenceSnapshot | None = None
    if config.reference_snapshot is not None:
        snapshot = _load_reference_snapshot(
            config.reference_snapshot,
            detector_model_version=detector.model_version,
            model_sha256=model_hash_before,
        )
        reference = snapshot.to_bustout_profile()
    else:
        reference = PaySimReferenceProfile.from_processed_paysim(
            processed_dir, max_rows=config.reference_max_rows
        )
    generation_config = GenerationConfig(
        seed=config.seed,
        n_scenarios=1,
        start_time=start_time,
        time_horizon=timedelta(days=120),
        split=DataSplit.TEST,
        generation=child.generation,
        deterministic=True,
    )
    batch = SyntheticIdentityBustOutGenerator(reference).generate(child, generation_config)
    if len(batch.scenario_ids) != 1:
        msg = f"expected exactly one fresh scenario, got {len(batch.scenario_ids)}"
        raise GenAIGuidedGenerationError(msg)
    scenario_id = batch.scenario_ids[0]
    collisions = _known_scenario_ids(
        [Path("data/synthetic"), Path("submission/artifacts/data/synthetic")]
    ) & set(batch.scenario_ids)
    if collisions:
        msg = f"generated scenario id(s) {sorted(collisions)} collide with a prior confrontation"
        raise GenAIGuidedGenerationError(msg)

    # ---- Task C: score against the frozen detector, never fit it -----------
    # The extractor's vocabulary is schema-known, not learned (see
    # aegis.features.temporal), so fitting it needs no rows.
    extractor = TemporalBaselineFeatureExtractor().fit([])
    outputs = detector.predict(
        extractor.transform(batch.transactions),
        [txn.transaction_id for txn in batch.transactions],
        explain=False,
    )
    training_transactions = (
        _snapshot_training_skeletons(snapshot, batch)
        if snapshot is not None
        else _training_id_skeletons(train_path)
    )
    report = build_bustout_confrontation_report(
        batch=batch,
        outputs=outputs,
        training_transactions=training_transactions,
        training_dataset_id=snapshot.dataset_id if snapshot is not None else processed_dir.name,
        data_basis=(
            "precomputed_paysim_train_reference"
            if snapshot is not None
            else "processed_paysim"
        ),
        integration_only=False,
    )
    if snapshot is not None:
        assert config.reference_snapshot is not None
        report_metadata = dict(report.metadata)
        report_metadata["fast_freshness_attestation"] = {
            "method": "base_id_namespace_plus_exact_hard_positive_membership",
            "reference_snapshot": Path(config.reference_snapshot).as_posix(),
            "base_transaction_id_prefix": snapshot.base_transaction_id_prefix,
            "base_training_has_scenario_ids": snapshot.base_training_has_scenario_ids,
            "base_train_transaction_count": snapshot.base_train_transaction_count,
            "additional_training_transaction_count": len(
                snapshot.additional_training_transaction_ids
            ),
            "generated_transaction_id_overlap_count": 0,
            "generated_scenario_id_overlap_count": 0,
        }
        report = report.model_copy(
            update={
                "training_transaction_count": snapshot.total_training_transaction_count,
                "metadata": report_metadata,
            }
        )
    if _sha256(model_path) != model_hash_before or _sha256(metadata_path) != metadata_hash_before:
        msg = f"frozen detector artifact changed during the run: {model_dir}"
        raise GenAIGuidedGenerationError(msg)

    scenario = report.scenario_reports[0]
    fidelity = scenario.fidelity_summary.get("overall_fidelity_score")
    record = GenAIGuidedGeneration(
        generation_id=_generation_id(
            genai_run_id=artifact.run_id, blueprint_id=child.attack_id, seed=config.seed
        ),
        attack_family=child.attack_family,
        provenance=handoff.provenance,
        blind_spot_hypothesis=response.blind_spot_hypothesis,
        proposed_mutation_count=len(response.mutation_proposals),
        applied_mutations=handoff.applied,
        rejected_mutations=handoff.rejected,
        parent_blueprint_id=parent_blueprint.attack_id,
        resulting_blueprint_id=child.attack_id,
        resulting_blueprint=child.model_dump(mode="json"),
        scenario_id=scenario_id,
        fraud_count=scenario.fraudulent_bustout_count,
        caught_count=scenario.caught_fraud_count,
        escaped_count=scenario.evaded_fraud_count,
        recall=scenario.fraud_recall,
        fidelity_score=float(fidelity) if isinstance(fidelity, (int, float)) else None,
        hardest_survivor=_hardest_survivor(report),
        dry_run=False,
        notes=(
            f"Scored against frozen {detector.model_version}; no training occurred "
            f"(model.json sha256 {model_hash_before[:12]} unchanged)."
            + (
                f" Fast path used hash-bound reference snapshot "
                f"{Path(config.reference_snapshot).as_posix()}."
                if config.reference_snapshot is not None
                else ""
            )
        ),
    )

    artifact_out = _write_artifacts(
        config, record=record, report=report, batch=batch, outputs=outputs, child=child,
        parent=parent_blueprint,
    )
    return GenAIGuidedResult(
        record=record,
        handoff=handoff,
        report=report,
        batch=batch,
        outputs=list(outputs),
        artifact_path=artifact_out[0],
        evidence_dir=artifact_out[1],
    )


def _write_model(path: Path, model: AegisModel) -> None:
    path.write_text(model.to_json(indent=2), encoding="utf-8")


def _write_jsonl(path: Path, models: Sequence[AegisModel]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for model in models:
            handle.write(model.to_json())
            handle.write("\n")


def _stable_artifact_payload(value: object) -> object:
    """Remove wall-clock creation fields before an idempotent reuse comparison."""
    if isinstance(value, dict):
        return {
            key: _stable_artifact_payload(child)
            for key, child in value.items()
            if key != "created_at"
        }
    if isinstance(value, list):
        return [_stable_artifact_payload(child) for child in value]
    return value


def _write_artifacts(
    config: GenAIGuidedConfig,
    *,
    record: GenAIGuidedGeneration,
    report: BustOutConfrontationReport,
    batch: TransactionBatch,
    outputs: Sequence[DetectorOutput],
    child: AttackBlueprint,
    parent: AttackBlueprint,
) -> tuple[Path, Path]:
    """Persist the summary record and its full evidence, never overwriting."""
    artifact_dir = Path(config.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{record.generation_id}.json"
    evidence_dir = Path(config.evidence_dir) / record.generation_id
    if artifact_path.exists() or evidence_dir.exists():
        if config.reuse_identical and artifact_path.is_file() and evidence_dir.is_dir():
            existing = GenAIGuidedGeneration.model_validate_json(
                artifact_path.read_text(encoding="utf-8")
            )
            stable_existing = _stable_artifact_payload(existing.model_dump(mode="json"))
            stable_new = _stable_artifact_payload(record.model_dump(mode="json"))
            required = {
                "genai_guided_generation.json",
                "confrontation.json",
                "blueprint.json",
                "parent_blueprint.json",
                "transactions.jsonl",
                "detector_outputs.jsonl",
                "hardest_evasions.json",
            }
            present = {path.name for path in evidence_dir.iterdir() if path.is_file()}
            if stable_existing == stable_new and required <= present:
                return artifact_path, evidence_dir
            msg = f"existing guided generation differs or is incomplete: {record.generation_id}"
            raise FileExistsError(msg)
        msg = f"refusing to overwrite an existing guided generation: {record.generation_id}"
        raise FileExistsError(msg)
    evidence_dir.mkdir(parents=True)

    _write_model(artifact_path, record)
    _write_model(evidence_dir / "genai_guided_generation.json", record)
    _write_model(evidence_dir / "confrontation.json", report)
    _write_model(evidence_dir / "blueprint.json", child)
    _write_model(evidence_dir / "parent_blueprint.json", parent)
    _write_jsonl(evidence_dir / "transactions.jsonl", batch.transactions)
    _write_jsonl(evidence_dir / "detector_outputs.jsonl", list(outputs))
    (evidence_dir / "hardest_evasions.json").write_text(
        json.dumps([e.model_dump(mode="json") for e in report.hardest_evasions], indent=2),
        encoding="utf-8",
    )
    return artifact_path, evidence_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply one live Blind-Spot artifact and score one fresh scenario."
    )
    parser.add_argument("--genai-artifact", type=Path, required=True)
    parser.add_argument("--confrontation-dir", type=Path, required=True)
    parser.add_argument("--processed-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--artifact-dir", type=Path, default=GUIDED_ARTIFACT_DIR)
    parser.add_argument("--evidence-dir", type=Path, default=GUIDED_EVIDENCE_DIR)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--reference-max-rows", type=int, default=None)
    parser.add_argument(
        "--reference-snapshot",
        type=Path,
        default=None,
        help="hash-bound train-only snapshot; avoids full PaySim reference/freshness scans",
    )
    parser.add_argument(
        "--reuse-identical",
        action="store_true",
        help="reuse an existing byte-equivalent generation instead of overwriting it",
    )
    parser.add_argument(
        "--allow-recorded",
        action="store_true",
        help="apply a recorded/replayed artifact (persisted as live=False)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = GenAIGuidedConfig(
        genai_artifact=args.genai_artifact,
        confrontation_dir=args.confrontation_dir,
        processed_dir=args.processed_dir,
        model_dir=args.model_dir,
        artifact_dir=args.artifact_dir,
        evidence_dir=args.evidence_dir,
        seed=args.seed,
        reference_max_rows=args.reference_max_rows,
        reference_snapshot=args.reference_snapshot,
        reuse_identical=args.reuse_identical,
        require_live=not args.allow_recorded,
    )
    try:
        result = run_genai_guided_generation(config)
    except (GenAIGuidedGenerationError, FileExistsError) as exc:
        print(f"error: {exc}")
        return 1

    record = result.record
    print(f"generation      {record.generation_id}")
    print(f"genai run       {record.provenance.genai_run_id} "
          f"({record.provenance.provider}/{record.provenance.model}, "
          f"live={record.provenance.live}, {record.provenance.prompt_version})")
    print(f"parent          {record.parent_blueprint_id}")
    print(f"child           {record.resulting_blueprint_id}  seed={record.provenance.seed}")
    print(f"scenario        {record.scenario_id}")
    for applied in record.applied_mutations:
        print(f"  applied       {applied.parameter}: {applied.from_value} -> {applied.to_value} "
              f"({applied.direction}, magnitude {applied.magnitude})")
    for rejected in record.rejected_mutations:
        print(f"  rejected      {rejected.parameter}: {rejected.reason}")
    print(f"detector        {record.provenance.detector_model_version}")
    print(f"fraud/caught/escaped  {record.fraud_count}/{record.caught_count}/"
          f"{record.escaped_count}")
    print(f"recall          {record.recall}")
    print(f"fidelity        {record.fidelity_score}")
    print(f"artifact        {result.artifact_path}")
    print(f"evidence        {result.evidence_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
