"""Run the first non-adaptive Red-versus-Blue bust-out confrontation.

Memory-safe by default
-----------------------
The first real run against the full PaySim processed artifacts crashed with
a `MemoryError` loading `validation.jsonl` - right after a full, successful
load of `train.jsonl` (4,463,587 rows). The script was eagerly loading
train, validation, *and* test as full `Transaction` object lists simply to
compute two small things: the maximum timestamp across all three splits, and
the set of training transaction IDs for the leakage-freshness check. Neither
needs the full data:

* The max timestamp is read from the *last line* of each already
  chronologically-sorted split file (`_last_jsonl_timestamp`), not by
  scanning and holding every row.
* The training-ID check (`aegis.evaluate.confrontation._assert_fresh_batch`,
  frozen, not modified here) only ever reads `.transaction_id` and
  `.scenario_id` off each training record. `_training_id_skeletons` builds
  one lightweight `Transaction` per training row carrying only those two
  fields (plus whatever the contract already defaults, e.g.
  `scenario_id=None`) via `model_copy` from a single template - not full
  JSON validation - cutting both the per-row cost and the retained memory
  (skeletons share the template's empty `features`/`metadata` dicts instead
  of each allocating their own).
* `--reuse-model-dir` skips the internal `run_baseline_pipeline` retraining
  step entirely and loads an already-persisted detector directly - this is
  what a real run against the already-trained `models/xgboost-baseline-*`
  artifact should use, so nothing is retrained and no validation/test split
  is rescored.
* `--low-memory` (used only when no `--reuse-model-dir` is given, i.e. the
  internal baseline must actually be trained) forwards to
  `scripts/train_baseline_detector.py`'s streaming path.

Feature and detection semantics are unchanged throughout: same 19
decision-time-safe features, same detector, same explain=False bulk-scoring
behaviour. See `tests/test_bustout_confrontation_low_memory.py` for the
equivalence proof.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aegis.defend import XGBoostDetector
from aegis.evaluate import BustOutConfrontationReport, build_bustout_confrontation_report
from aegis.features import TemporalBaselineFeatureExtractor
from aegis.generate import (
    GenerationConfig,
    PaySimReferenceProfile,
    SyntheticIdentityBustOutGenerator,
)
from aegis.identify import build_synthetic_identity_blueprint
from aegis.shared.contracts import AttackBlueprint, DetectorOutput, Transaction, TransactionBatch
from aegis.shared.enums import DataSplit

# Direct ``python scripts/run_bustout_confrontation.py`` execution places
# scripts/, not the repository root, on sys.path. Importing by the appropriate
# runtime name keeps both that command and normal module imports working.
_training_module = importlib.import_module(
    "scripts.train_baseline_detector" if __package__ else "train_baseline_detector"
)
BaselinePipelineConfig = _training_module.BaselinePipelineConfig
run_baseline_pipeline = _training_module.run_baseline_pipeline
_DEFAULT_CHUNK_SIZE = _training_module.DEFAULT_CHUNK_SIZE
_LOW_MEMORY_DEFAULT_NTHREAD = _training_module.LOW_MEMORY_DEFAULT_NTHREAD

_TRANSACTION_ID_PATTERN = re.compile(r'"transaction_id":"([^"]+)"')
_SCENARIO_ID_PATTERN = re.compile(r'"scenario_id":(?:null|"([^"]*)")')


@dataclass(frozen=True)
class ConfrontationPipelineConfig:
    """Inputs needed to reproduce training and one fresh confrontation."""

    processed_dir: Path
    output_dir: Path = Path("data/synthetic/confrontations")
    model_output_dir: Path = Path("models/confrontations")
    seed: int = 20260101
    num_boost_round: int = 300
    latency_sample_size: int = 50
    reference_max_rows: int | None = None
    integration_only: bool = False
    data_basis: str = "processed_paysim"
    low_memory: bool = False
    chunk_size: int = _DEFAULT_CHUNK_SIZE
    nthread: int | None = None
    reuse_model_dir: Path | None = None
    """Load an already-persisted `XGBoostDetector` from here instead of
    retraining. When set, `run_baseline_pipeline` is never called - no
    validation/test split is touched at all for this confrontation run."""


@dataclass(frozen=True)
class ConfrontationPipelineResult:
    """In-memory result and paths written by one confrontation run."""

    report: BustOutConfrontationReport
    batch: TransactionBatch
    outputs: list[DetectorOutput]
    output_dir: Path
    model_dir: Path
    artifacts: dict[str, Path]


def _last_jsonl_line(path: Path, chunk_size: int = 65536) -> str:
    """Read the last non-blank line of a text file without scanning from the start."""
    with path.open("rb") as handle:
        handle.seek(0, 2)
        file_size = handle.tell()
        if file_size == 0:
            msg = f"{path} is empty"
            raise ValueError(msg)
        buffer = b""
        position = file_size
        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            handle.seek(position)
            buffer = handle.read(read_size) + buffer
            trimmed = buffer.rstrip(b"\n")
            newline_index = trimmed.rfind(b"\n")
            if newline_index != -1:
                last_line = trimmed[newline_index + 1 :]
                if last_line.strip():
                    return last_line.decode("utf-8")
                buffer = trimmed[:newline_index]
            elif position == 0 and trimmed.strip():
                return trimmed.decode("utf-8")
    msg = f"{path} contains no non-blank lines"
    raise ValueError(msg)


def _last_jsonl_timestamp(path: Path) -> datetime:
    """Timestamp of a chronologically-sorted split's final row, without loading the rest."""
    return Transaction.model_validate_json(_last_jsonl_line(path)).timestamp


def _training_id_skeletons(path: Path) -> list[Transaction]:
    """One lightweight `Transaction` per training row, carrying only the two
    fields `aegis.evaluate.confrontation._assert_fresh_batch` actually reads:
    `transaction_id` (regex-extracted per row) and `scenario_id` (also
    regex-extracted, since a promoted hard-positive could carry one even
    though ordinary PaySim rows never do - see docs/EVALUATION_RULES.md
    SS2). Built via `model_copy` from a single template so every skeleton
    shares the template's other defaulted fields (empty `features`/
    `metadata`, etc.) instead of each allocating and validating its own ~20
    fields. Full JSON validation of 4.46M rows is what caused the original
    `MemoryError`; this never constructs more than one fully-validated
    `Transaction` (the template).
    """
    # Required fields need *some* correctly-typed value to satisfy the
    # pydantic mypy plugin's view of `model_construct`; their content is
    # irrelevant since nothing downstream reads them (see docstring above).
    template = Transaction.model_construct(
        transaction_id="placeholder",
        timestamp=datetime(1970, 1, 1, tzinfo=timezone.utc),
        source_account_id="placeholder",
        amount=0.0,
    )
    skeletons: list[Transaction] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            id_match = _TRANSACTION_ID_PATTERN.search(stripped)
            if id_match is None:
                msg = f"{path}: could not find transaction_id in line: {stripped[:120]!r}"
                raise ValueError(msg)
            scenario_match = _SCENARIO_ID_PATTERN.search(stripped)
            if scenario_match is None:
                msg = f"{path}: could not find scenario_id in line: {stripped[:120]!r}"
                raise ValueError(msg)
            skeletons.append(
                template.model_copy(
                    update={
                        "transaction_id": id_match.group(1),
                        "scenario_id": scenario_match.group(1),
                    }
                )
            )
    return skeletons


def _is_valid_model_artifact(directory: Path) -> bool:
    """Whether `directory` holds a saved `XGBoostDetector` (`model.json` + `metadata.json`)."""
    return (directory / "model.json").is_file() and (directory / "metadata.json").is_file()


def run_bustout_confrontation(
    config: ConfrontationPipelineConfig,
) -> ConfrontationPipelineResult:
    """Load (or, if not reusing, train/tune) the approved baseline, then score
    one unseen bust-out batch."""
    processed_dir = Path(config.processed_dir)
    train_path = processed_dir / "train.jsonl"
    validation_path = processed_dir / "validation.jsonl"
    test_path = processed_dir / "test.jsonl"
    for path in (train_path, validation_path, test_path):
        if not path.is_file():
            raise ValueError(f"prepared PaySim artifact not found: {path}")

    if config.reuse_model_dir is not None and _is_valid_model_artifact(config.reuse_model_dir):
        detector = XGBoostDetector.load(str(config.reuse_model_dir))
        model_dir = config.reuse_model_dir
    else:
        baseline = run_baseline_pipeline(
            BaselinePipelineConfig(
                processed_dir=processed_dir,
                output_dir=Path(config.model_output_dir),
                seed=config.seed,
                num_boost_round=config.num_boost_round,
                latency_sample_size=config.latency_sample_size,
                low_memory=config.low_memory,
                chunk_size=config.chunk_size,
                nthread=config.nthread,
            )
        )
        detector = XGBoostDetector.load(str(baseline.artifact_dir))
        model_dir = baseline.artifact_dir

    # The extractor's vocabulary is fixed/schema-known, not learned from
    # data (see aegis.features.temporal), so fitting it needs no rows at all.
    extractor = TemporalBaselineFeatureExtractor().fit([])
    reference = PaySimReferenceProfile.from_processed_paysim(
        processed_dir, max_rows=config.reference_max_rows
    )
    blueprint = build_synthetic_identity_blueprint(
        warmup_amount_mean=reference.amount_mean,
        warmup_amount_stddev=max(reference.amount_stddev, 1.0),
        currency=reference.currency,
        reference_basis=reference.basis,
    )
    start_time = (
        max(
            _last_jsonl_timestamp(train_path),
            _last_jsonl_timestamp(validation_path),
            _last_jsonl_timestamp(test_path),
        )
        + timedelta(days=1)
    )
    generation_config = GenerationConfig(
        seed=config.seed,
        n_scenarios=1,
        start_time=start_time,
        time_horizon=timedelta(days=120),
        split=DataSplit.TEST,
        generation=0,
        deterministic=True,
    )
    batch = SyntheticIdentityBustOutGenerator(reference).generate(blueprint, generation_config)
    X_synthetic = extractor.transform(batch.transactions)
    outputs = detector.predict(
        X_synthetic,
        [txn.transaction_id for txn in batch.transactions],
        explain=False,
    )
    training_transactions = _training_id_skeletons(train_path)
    report = build_bustout_confrontation_report(
        batch=batch,
        outputs=outputs,
        training_transactions=training_transactions,
        training_dataset_id=processed_dir.name,
        data_basis=config.data_basis,
        integration_only=config.integration_only,
    )
    output_dir = Path(config.output_dir) / report.report_id
    artifacts = write_confrontation_artifacts(output_dir, report, batch, outputs, blueprint)
    return ConfrontationPipelineResult(
        report=report,
        batch=batch,
        outputs=outputs,
        output_dir=output_dir,
        model_dir=model_dir,
        artifacts=artifacts,
    )


def write_confrontation_artifacts(
    output_dir: Path,
    report: BustOutConfrontationReport,
    batch: TransactionBatch,
    outputs: Sequence[DetectorOutput],
    blueprint: AttackBlueprint,
) -> dict[str, Path]:
    """Write canonical inputs, verdicts, report, and ranked evasions once."""
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite confrontation run: {destination}")
    destination.mkdir(parents=True)
    artifacts = {
        "transactions": destination / "transactions.jsonl",
        "detector_outputs": destination / "detector_outputs.jsonl",
        "report": destination / "confrontation.json",
        "evasions": destination / "evasions.jsonl",
        "hardest_evasions": destination / "hardest_evasions.json",
        "blueprint": destination / "blueprint.json",
    }
    _write_jsonl(artifacts["transactions"], batch.transactions)
    _write_jsonl(artifacts["detector_outputs"], outputs)
    _write_jsonl(artifacts["evasions"], report.successful_evasions)
    artifacts["report"].write_text(report.to_json(indent=2) + "\n", encoding="utf-8")
    artifacts["hardest_evasions"].write_text(
        json.dumps(
            [record.model_dump(mode="json") for record in report.hardest_evasions],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    artifacts["blueprint"].write_text(blueprint.to_json(indent=2) + "\n", encoding="utf-8")
    return artifacts


def _write_jsonl(path: Path, records: Sequence[object]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            if not hasattr(record, "to_json"):
                raise TypeError(f"record does not support canonical serialization: {type(record)}")
            handle.write(record.to_json())  # type: ignore[attr-defined]
            handle.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Train/tune the approved PaySim baseline (or reuse an already-persisted one), "
            "generate one fresh synthetic-identity bust-out scenario, score it, and write a "
            "non-adaptive confrontation report."
        )
    )
    parser.add_argument(
        "processed_dir",
        type=Path,
        help="prepared PaySim run containing train/validation/test.jsonl",
    )
    parser.add_argument("--seed", type=int, default=20260101)
    parser.add_argument("--num-boost-round", type=int, default=300)
    parser.add_argument("--latency-sample-size", type=int, default=50)
    parser.add_argument("--reference-max-rows", type=int)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/synthetic/confrontations"),
    )
    parser.add_argument(
        "--model-output-dir",
        type=Path,
        default=Path("models/confrontations"),
        help="where a freshly-trained baseline is written (ignored with --reuse-model-dir)",
    )
    parser.add_argument(
        "--reuse-model-dir",
        type=Path,
        default=None,
        help=(
            "load an already-persisted XGBoostDetector from this directory instead of "
            "retraining, e.g. models/xgboost-baseline-20260101. No validation/test split "
            "is touched when this is used."
        ),
    )
    parser.add_argument(
        "--low-memory",
        action="store_true",
        help=(
            "when retraining (i.e. --reuse-model-dir is not given), train the internal "
            "baseline via the streaming, bounded-memory path (see "
            "scripts/train_baseline_detector.py --low-memory)."
        ),
    )
    parser.add_argument("--chunk-size", type=int, default=_DEFAULT_CHUNK_SIZE)
    parser.add_argument(
        "--nthread",
        type=int,
        default=None,
        help=(
            "XGBoost thread count for an internal retraining run; defaults to "
            f"{_LOW_MEMORY_DEFAULT_NTHREAD} when --low-memory is set and this is omitted"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    nthread = args.nthread
    if args.low_memory and nthread is None:
        nthread = _LOW_MEMORY_DEFAULT_NTHREAD
    result = run_bustout_confrontation(
        ConfrontationPipelineConfig(
            processed_dir=args.processed_dir,
            output_dir=args.output_dir,
            model_output_dir=args.model_output_dir,
            seed=args.seed,
            num_boost_round=args.num_boost_round,
            latency_sample_size=args.latency_sample_size,
            reference_max_rows=args.reference_max_rows,
            low_memory=args.low_memory,
            chunk_size=args.chunk_size,
            nthread=nthread,
            reuse_model_dir=args.reuse_model_dir,
        )
    )
    scenario = result.report.scenario_reports[0]
    print(f"Confrontation: {result.report.report_id}")
    print(f"  model={result.report.model_version} scenario={scenario.scenario_id}")
    print(f"  model_dir={result.model_dir}")
    print(
        f"  fraud={scenario.fraudulent_bustout_count} caught={scenario.caught_fraud_count} "
        f"evaded={scenario.evaded_fraud_count} recall={scenario.fraud_recall:.4f}"
    )
    print(f"  report: {result.artifacts['report']}")
    print(f"  hardest evasions: {result.artifacts['hardest_evasions']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
