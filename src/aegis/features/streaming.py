"""Disk-materializing feature computation for splits too large to hold in RAM.

`TemporalBaselineFeatureExtractor.transform()` requires the whole split as a
list of `Transaction` objects plus a pandas `DataFrame` of `float64` feature
values - fine for a fixture, unworkable for a multi-million-row PaySim split
on an 8GB machine (observed: peak RSS of 4-4.6GB and repeated near-zero free
memory before the process was killed; see `docs/BASELINE_DETECTOR.md`
"Memory-safe materialization" for the full diagnosis).

This module computes the *identical* per-row features - via the same
`_CausalHistoryState.compute()` / `.observe()` calls, in the same order, on
the same causally-sorted input - but streams the source JSONL in bounded
chunks and writes results directly into a pre-sized `float32` memmap array on
disk. Only two things are ever resident at once: the current chunk of raw
`Transaction` objects (released after folding into the array) and the running
per-account state (bounded by distinct-account count, not row count - a few
hundred bytes per account, not per row).

Because the source files are chronologically sorted (verified for every split
of the real PaySim run used here: 0 out-of-order rows across 6,362,620 total
transactions), a single forward pass with one shared `_CausalHistoryState`
reproduces exactly the same causal ordering `TemporalBaselineFeatureExtractor`
achieves by sorting the whole split in memory. `materialize_split_features`
still checks this invariant while streaming and raises loudly if it is ever
violated, rather than silently computing wrong history.
"""

from __future__ import annotations

import itertools
import json
import shutil
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from aegis.features.io import count_labelled_jsonl_lines, iter_transactions_jsonl_chunks
from aegis.features.temporal import _CausalHistoryState, feature_columns
from aegis.shared.contracts import Transaction
from aegis.shared.enums import FraudLabel

SCHEMA_VERSION = "1.0.0"
FEATURES_FILENAME = "features.npy"
LABELS_FILENAME = "labels.npy"
TRANSACTION_IDS_FILENAME = "transaction_ids.txt"
SCHEMA_FILENAME = "schema.json"
DEFAULT_CHUNK_SIZE = 200_000


@dataclass(frozen=True)
class FeatureArtifact:
    """Paths and metadata for one split's materialized feature artifact."""

    directory: Path
    row_count: int
    feature_names: list[str]
    namespace: str
    chunk_size: int
    source_path: Path

    @property
    def features_path(self) -> Path:
        return self.directory / FEATURES_FILENAME

    @property
    def labels_path(self) -> Path:
        return self.directory / LABELS_FILENAME

    @property
    def transaction_ids_path(self) -> Path:
        return self.directory / TRANSACTION_IDS_FILENAME

    def load_features(self, *, mmap: bool = True) -> np.ndarray:
        """Load the feature matrix. Memory-mapped (read-only) by default."""
        array: np.ndarray = np.load(self.features_path, mmap_mode="r" if mmap else None)
        return array

    def load_labels(self) -> np.ndarray:
        array: np.ndarray = np.load(self.labels_path)
        return array

    def load_transaction_ids(self) -> list[str]:
        with self.transaction_ids_path.open("r", encoding="utf-8") as handle:
            return [line.rstrip("\n") for line in handle]

    @classmethod
    def load_schema(cls, directory: Path | str) -> dict[str, object]:
        path = Path(directory) / SCHEMA_FILENAME
        result: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
        return result


def materialize_split_features(
    jsonl_path: Path | str,
    output_dir: Path | str,
    *,
    namespace: str = "temporal",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> FeatureArtifact:
    """Stream `jsonl_path`, write compact feature/label/id artifacts under `output_dir`.

    `FraudLabel.UNKNOWN` rows are dropped, matching `_labelled_only` elsewhere
    in the baseline pipeline - unknown is not usable as a training or
    evaluation target. Written atomically: everything is built under a
    sibling temp directory and `rename`d into place only once complete, so a
    killed process never leaves a partial directory that looks valid.
    """
    source = Path(jsonl_path)
    row_count = count_labelled_jsonl_lines(source)
    return _materialize_features(
        chunks=iter_transactions_jsonl_chunks(source, chunk_size),
        row_count=row_count,
        output_dir=output_dir,
        namespace=namespace,
        chunk_size=chunk_size,
        source_descriptor=str(source),
    )


def materialize_split_features_with_extra(
    base_jsonl_path: Path | str,
    extra_jsonl_paths: Sequence[Path | str],
    output_dir: Path | str,
    *,
    namespace: str = "temporal",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> FeatureArtifact:
    """Materialize `base_jsonl_path` followed by each of `extra_jsonl_paths`, as one stream.

    Built for training-only hard-positive augmentation (see
    `aegis.defend.hard_positives`): validation and test are never
    materialized through this path. The concatenation is still required to
    be chronologically non-decreasing end-to-end - the same monotonicity
    check `materialize_split_features` applies runs across the boundary
    between `base_jsonl_path` and each extra file, and between consecutive
    extra files, so an extra source dated *before* the base split's last row
    fails loudly rather than silently computing wrong causal history.
    """
    base = Path(base_jsonl_path)
    extras = [Path(p) for p in extra_jsonl_paths]
    row_count = count_labelled_jsonl_lines(base) + sum(
        count_labelled_jsonl_lines(p) for p in extras
    )
    chunk_iterables: list[Iterable[list[Transaction]]] = [
        iter_transactions_jsonl_chunks(base, chunk_size)
    ]
    chunk_iterables.extend(iter_transactions_jsonl_chunks(p, chunk_size) for p in extras)
    source_descriptor = " + ".join(str(p) for p in (base, *extras))
    return _materialize_features(
        chunks=itertools.chain.from_iterable(chunk_iterables),
        row_count=row_count,
        output_dir=output_dir,
        namespace=namespace,
        chunk_size=chunk_size,
        source_descriptor=source_descriptor,
    )


def _materialize_features(
    *,
    chunks: Iterable[list[Transaction]],
    row_count: int,
    output_dir: Path | str,
    namespace: str,
    chunk_size: int,
    source_descriptor: str,
) -> FeatureArtifact:
    """Shared write path for both the single-source and multi-source entry points.

    Identical atomic-write, monotonicity-check, and schema logic either way -
    the two public functions above only differ in how they build `chunks` and
    `row_count`.
    """
    if chunk_size <= 0:
        msg = f"chunk_size must be positive, got {chunk_size}"
        raise ValueError(msg)

    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing feature artifact: {destination}")

    feature_names = feature_columns(namespace)
    n_features = len(feature_names)

    temp_dir = destination.parent / f".{destination.name}.tmp-{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True)
    features_map = None
    labels_map = None
    try:
        try:
            features_map = np.lib.format.open_memmap(
                temp_dir / FEATURES_FILENAME,
                mode="w+",
                dtype=np.float32,
                shape=(row_count, n_features),
            )
            labels_map = np.lib.format.open_memmap(
                temp_dir / LABELS_FILENAME, mode="w+", dtype=np.int8, shape=(row_count,)
            )

            state = _CausalHistoryState()
            write_index = 0
            previous_timestamp = None
            ids_path = temp_dir / TRANSACTION_IDS_FILENAME
            with ids_path.open("w", encoding="utf-8") as ids_handle:
                for chunk in chunks:
                    for txn in chunk:
                        if previous_timestamp is not None and txn.timestamp < previous_timestamp:
                            msg = (
                                f"{source_descriptor} is not chronologically ordered at or "
                                f"before row {write_index}: {txn.timestamp} follows "
                                f"{previous_timestamp}. Streaming materialization requires a "
                                "pre-sorted, concatenation-ordered input - see the module "
                                "docstring."
                            )
                            raise ValueError(msg)
                        previous_timestamp = txn.timestamp

                        if txn.label is FraudLabel.UNKNOWN:
                            # Matches the approved pipeline exactly:
                            # `_labelled_only` drops UNKNOWN rows *before*
                            # they ever reach the extractor (see
                            # scripts/train_baseline_detector.py), so they
                            # never enter causal history either. This is not
                            # an optimization - it reproduces the same
                            # feature values the approved in-memory path
                            # produces.
                            continue

                        features_map[write_index] = state.compute(txn)
                        labels_map[write_index] = 1 if txn.label is FraudLabel.FRAUD else 0
                        ids_handle.write(txn.transaction_id)
                        ids_handle.write("\n")
                        state.observe(txn)
                        write_index += 1
                    # `chunk` goes out of scope here and is eligible for GC
                    # before the next chunk is read - only `state` persists.

            features_map.flush()
            labels_map.flush()
        finally:
            # Release the memmap file handles before any rename/rmtree -
            # Windows refuses to remove or rename a directory containing an
            # open memory-mapped file.
            del features_map, labels_map

        if write_index != row_count:  # pragma: no cover - defensive only
            msg = (
                f"pre-counted {row_count} labelled rows but wrote {write_index}; "
                f"{source_descriptor} changed during materialization"
            )
            raise RuntimeError(msg)

        schema = {
            "schema_version": SCHEMA_VERSION,
            "namespace": namespace,
            "feature_names": feature_names,
            "row_count": row_count,
            "dtype": "float32",
            "label_dtype": "int8",
            "chunk_size": chunk_size,
            "source_path": source_descriptor,
        }
        (temp_dir / SCHEMA_FILENAME).write_text(
            json.dumps(schema, indent=2, sort_keys=True), encoding="utf-8"
        )
    except BaseException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_dir.rename(destination)  # atomic within the same filesystem
    return FeatureArtifact(
        directory=destination,
        row_count=row_count,
        feature_names=feature_names,
        namespace=namespace,
        chunk_size=chunk_size,
        source_path=Path(source_descriptor.split(" + ", 1)[0]),
    )


__all__ = [
    "DEFAULT_CHUNK_SIZE",
    "FeatureArtifact",
    "materialize_split_features",
    "materialize_split_features_with_extra",
]
