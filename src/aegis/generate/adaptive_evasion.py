"""Deterministic synthetic scenarios for bounded adaptive detector evasion."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np

from aegis.generate.base import BaseGenerator, BlueprintNotSupportedError
from aegis.generate.config import GenerationConfig
from aegis.shared.contracts import AttackBlueprint, Transaction, TransactionBatch
from aegis.shared.enums import (
    AttackFamily,
    Channel,
    DataSplit,
    FraudLabel,
    ParameterType,
    TransactionType,
)

_REQUIRED_STEPS = {"behavioral-context", "adaptive-pacing", "adversarial-transfers"}
_REQUIRED_PARAMETERS: dict[str, ParameterType] = {
    "context_transaction_count": ParameterType.INT,
    "context_duration_days": ParameterType.INT,
    "context_amount_mean": ParameterType.FLOAT,
    "context_amount_stddev": ParameterType.FLOAT,
    "fraud_transaction_count": ParameterType.INT,
    "fraud_amount_mean": ParameterType.FLOAT,
    "fraud_amount_stddev": ParameterType.FLOAT,
    "per_transaction_cap": ParameterType.FLOAT,
    "history_blend_ratio": ParameterType.FLOAT,
    "inter_event_delay_hours": ParameterType.FLOAT,
    "destination_diversity": ParameterType.INT,
    "transfer_probability": ParameterType.FLOAT,
    "amount_jitter_ratio": ParameterType.FLOAT,
    "timestamp_jitter_minutes": ParameterType.FLOAT,
    "max_parameter_changes": ParameterType.INT,
    "randomness_seed_offset": ParameterType.INT,
}
_CONTEXT_TYPES = (
    TransactionType.PAYMENT,
    TransactionType.TRANSFER,
    TransactionType.CASH_OUT,
    TransactionType.CASH_IN,
    TransactionType.DEBIT,
)


class AdaptiveEvasionConfigurationError(ValueError):
    """Raised when the declared perturbation envelope cannot be honored."""


@dataclass(frozen=True)
class AdaptiveEvasionReferenceProfile:
    """Constant-memory moments from explicitly legitimate TRAIN rows."""

    basis: str
    source: str
    sample_count: int
    transfer_sample_count: int
    amount_mean: float
    amount_stddev: float
    transfer_amount_mean: float
    transfer_amount_stddev: float
    transaction_type_distribution: dict[str, float]
    currency: str
    latest_timestamp: datetime | None

    @classmethod
    def bounded_fallback(cls) -> AdaptiveEvasionReferenceProfile:
        return cls(
            basis="bounded_fallback",
            source="built_in_assumptions",
            sample_count=0,
            transfer_sample_count=0,
            amount_mean=75.0,
            amount_stddev=25.0,
            transfer_amount_mean=1_000.0,
            transfer_amount_stddev=250.0,
            transaction_type_distribution={
                TransactionType.PAYMENT.value: 0.50,
                TransactionType.TRANSFER.value: 0.22,
                TransactionType.CASH_OUT.value: 0.13,
                TransactionType.CASH_IN.value: 0.10,
                TransactionType.DEBIT.value: 0.05,
            },
            currency="XXX",
            latest_timestamp=None,
        )

    @classmethod
    def from_transactions(
        cls,
        transactions: Iterable[Transaction],
        *,
        source: str = "transaction_iterable",
        max_rows: int | None = None,
    ) -> AdaptiveEvasionReferenceProfile:
        """Accumulate moments without retaining the input population."""
        if max_rows is not None and max_rows < 1:
            raise ValueError("max_rows must be positive when provided")
        count = transfer_count = 0
        mean = second_moment = 0.0
        transfer_mean = transfer_second_moment = 0.0
        type_counts: Counter[str] = Counter()
        currency_counts: Counter[str] = Counter()
        latest: datetime | None = None
        for transaction in transactions:
            if transaction.split is not DataSplit.TRAIN:
                raise AdaptiveEvasionConfigurationError(
                    "adaptive reference input contains a non-train row: "
                    f"{transaction.transaction_id}"
                )
            latest = transaction.timestamp if latest is None else max(latest, transaction.timestamp)
            if transaction.label is not FraudLabel.LEGITIMATE:
                continue
            count += 1
            delta = transaction.amount - mean
            mean += delta / count
            second_moment += delta * (transaction.amount - mean)
            type_counts[transaction.transaction_type.value] += 1
            currency_counts[transaction.currency] += 1
            if transaction.transaction_type is TransactionType.TRANSFER:
                transfer_count += 1
                transfer_delta = transaction.amount - transfer_mean
                transfer_mean += transfer_delta / transfer_count
                transfer_second_moment += transfer_delta * (transaction.amount - transfer_mean)
            if max_rows is not None and count >= max_rows:
                break
        if count == 0:
            raise AdaptiveEvasionConfigurationError(
                "adaptive reference input contains no legitimate TRAIN rows"
            )
        amount_stddev = math.sqrt(second_moment / (count - 1)) if count > 1 else 0.0
        if transfer_count:
            transfer_stddev = (
                math.sqrt(transfer_second_moment / (transfer_count - 1))
                if transfer_count > 1
                else 0.0
            )
        else:
            transfer_mean = mean
            transfer_stddev = amount_stddev
        return cls(
            basis="processed_paysim_train",
            source=source,
            sample_count=count,
            transfer_sample_count=transfer_count,
            amount_mean=mean,
            amount_stddev=amount_stddev,
            transfer_amount_mean=transfer_mean,
            transfer_amount_stddev=transfer_stddev,
            transaction_type_distribution={
                name: value / count for name, value in sorted(type_counts.items())
            },
            currency=currency_counts.most_common(1)[0][0],
            latest_timestamp=latest,
        )

    @classmethod
    def from_processed_paysim(
        cls, reference_dir: str | Path, *, max_rows: int | None = None
    ) -> AdaptiveEvasionReferenceProfile:
        """Open only TRAIN JSONL; validation and test are not consulted."""
        reference_path = Path(reference_dir).expanduser().resolve()
        train_path = reference_path if reference_path.is_file() else reference_path / "train.jsonl"
        if not train_path.is_file():
            raise FileNotFoundError(f"processed PaySim TRAIN artifact not found: {train_path}")

        def records() -> Iterator[Transaction]:
            with train_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        yield Transaction.model_validate_json(line)

        return cls.from_transactions(records(), source=str(train_path), max_rows=max_rows)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["latest_timestamp"] = (
            self.latest_timestamp.isoformat() if self.latest_timestamp is not None else None
        )
        return payload


@dataclass(frozen=True)
class AdaptiveEvasionFidelitySummary:
    """Descriptive realism and perturbation-budget diagnostics."""

    reference_basis: str
    reference_sample_count: int
    reference_transfer_sample_count: int
    context_count: int
    fraud_count: int
    context_amount_similarity: float
    fraud_amount_similarity: float
    transaction_type_similarity: float
    temporal_pacing_reasonableness: float
    history_blend_consistency: float
    destination_diversity_score: float
    perturbation_budget_score: float
    constraint_violation_rate: float
    average_fraud_amount: float
    reference_transfer_amount_mean: float
    overall_fidelity_score: float
    assumptions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _Parameters:
    context_transaction_count: int
    context_duration_days: int
    context_amount_mean: float
    context_amount_stddev: float
    fraud_transaction_count: int
    fraud_amount_mean: float
    fraud_amount_stddev: float
    per_transaction_cap: float
    history_blend_ratio: float
    inter_event_delay_hours: float
    destination_diversity: int
    transfer_probability: float
    amount_jitter_ratio: float
    timestamp_jitter_minutes: float
    max_parameter_changes: int
    randomness_seed_offset: int

    @property
    def sequence_length(self) -> int:
        return self.context_transaction_count + self.fraud_transaction_count

    @property
    def duration(self) -> timedelta:
        fraud_span = self.inter_event_delay_hours * max(self.fraud_transaction_count - 1, 0)
        jitter = self.timestamp_jitter_minutes / 60.0
        return timedelta(days=self.context_duration_days, hours=2 + fraud_span + jitter)

    @property
    def blended_fraud_target(self) -> float:
        return (
            self.history_blend_ratio * self.context_amount_mean
            + (1.0 - self.history_blend_ratio) * self.fraud_amount_mean
        )


class AdaptiveDetectorEvasionGenerator(BaseGenerator):
    """Generate one-account bounded perturbations without detector access."""

    name = "adaptive-detector-evasion"
    version = "1.0.0"
    supported_families = (AttackFamily.ADAPTIVE_DETECTOR_EVASION.value,)

    def __init__(self, reference_profile: AdaptiveEvasionReferenceProfile | None = None) -> None:
        self.reference_profile = (
            reference_profile or AdaptiveEvasionReferenceProfile.bounded_fallback()
        )

    def validate_blueprint(self, blueprint: AttackBlueprint) -> None:
        super().validate_blueprint(blueprint)
        missing_steps = sorted(
            _REQUIRED_STEPS.difference(step.step_id for step in blueprint.sequence)
        )
        if missing_steps:
            raise BlueprintNotSupportedError(
                f"adaptive evasion blueprint is missing steps: {', '.join(missing_steps)}"
            )
        for name, parameter_type in _REQUIRED_PARAMETERS.items():
            spec = blueprint.parameters.get(name)
            if spec is None:
                raise BlueprintNotSupportedError(f"adaptive evasion parameter missing: {name}")
            if spec.param_type is not parameter_type:
                raise BlueprintNotSupportedError(
                    f"adaptive evasion parameter {name!r} must use type {parameter_type.value}"
                )
        self._resolve_parameters(blueprint, {})

    def stream(self, blueprint: AttackBlueprint, config: GenerationConfig) -> Iterator[Transaction]:
        self.validate_blueprint(blueprint)
        parameters = self._resolve_parameters(blueprint, config.parameter_overrides)
        self._validate_generation(parameters, blueprint, config)
        transactions = [
            transaction
            for scenario_index in range(config.n_scenarios)
            for transaction in self._build_scenario(
                blueprint, config, parameters, scenario_index
            )
        ]
        yield from sorted(
            transactions,
            key=lambda transaction: (
                transaction.timestamp,
                transaction.scenario_id or "",
                transaction.sequence_index or 0,
            ),
        )

    def generate(self, blueprint: AttackBlueprint, config: GenerationConfig) -> TransactionBatch:
        self.validate_blueprint(blueprint)
        parameters = self._resolve_parameters(blueprint, config.parameter_overrides)
        self._validate_generation(parameters, blueprint, config)
        transactions = list(self.stream(blueprint, config))
        fidelity = self.assess_fidelity(transactions, blueprint, parameters)
        identity = json.dumps(
            {
                "attack_id": blueprint.attack_id,
                "seed": config.seed,
                "generation": config.generation,
                "n_scenarios": config.n_scenarios,
                "parameters": asdict(parameters),
                "reference": self.reference_profile.to_dict(),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        return TransactionBatch(
            batch_id=f"adaptive-evasion-{digest}",
            transactions=transactions,
            blueprint_id=blueprint.attack_id,
            attack_family=blueprint.attack_family,
            scenario_ids=sorted(
                {transaction.scenario_id for transaction in transactions if transaction.scenario_id}
            ),
            generator_name=self.name,
            generator_version=self.version,
            seed=config.seed,
            generation=config.generation,
            split=config.split,
            created_at=_as_utc(config.start_time),
            metadata={
                "parameters": asdict(parameters),
                "reference_profile": self.reference_profile.to_dict(),
                "fidelity": fidelity.to_dict(),
                "deterministic": config.deterministic,
                "safety_scope": "synthetic_benchmark_only",
            },
        )

    def assess_fidelity(
        self,
        transactions: Sequence[Transaction],
        blueprint: AttackBlueprint,
        parameters: _Parameters | None = None,
    ) -> AdaptiveEvasionFidelitySummary:
        resolved = parameters or self._resolve_parameters(blueprint, {})
        context = [transaction for transaction in transactions if not transaction.is_fraud]
        fraud = [transaction for transaction in transactions if transaction.is_fraud]
        context_amounts = np.asarray([transaction.amount for transaction in context], dtype=float)
        fraud_amounts = np.asarray([transaction.amount for transaction in fraud], dtype=float)
        context_mean = float(context_amounts.mean()) if len(context_amounts) else 0.0
        fraud_mean = float(fraud_amounts.mean()) if len(fraud_amounts) else 0.0
        context_scale = max(
            self.reference_profile.amount_stddev,
            self.reference_profile.amount_mean * 0.25,
            1.0,
        )
        context_similarity = math.exp(
            -abs(context_mean - self.reference_profile.amount_mean) / context_scale
        )
        fraud_scale = max(
            self.reference_profile.transfer_amount_stddev,
            self.reference_profile.transfer_amount_mean * 0.5,
            1.0,
        )
        fraud_similarity = math.exp(
            -abs(fraud_mean - self.reference_profile.transfer_amount_mean) / fraud_scale
        )
        type_similarity = _fraud_type_similarity(
            fraud, self.reference_profile.transaction_type_distribution
        )
        pacing_score = _temporal_pacing_score(fraud, resolved)
        blend_scale = max(resolved.fraud_amount_stddev, resolved.blended_fraud_target * 0.25, 1.0)
        blend_score = math.exp(
            -abs(fraud_mean - resolved.blended_fraud_target) / blend_scale
        )
        observed_destinations = len(
            {transaction.destination_account_id for transaction in fraud}
        )
        expected_destinations = min(
            resolved.destination_diversity, resolved.fraud_transaction_count
        )
        destination_score = min(observed_destinations, expected_destinations) / max(
            observed_destinations, expected_destinations, 1
        )
        cap_score = (
            sum(transaction.amount <= resolved.per_transaction_cap for transaction in fraud)
            / len(fraud)
            if fraud
            else 0.0
        )
        jitter_limit = max(
            resolved.fraud_amount_stddev * 3.0,
            resolved.blended_fraud_target * resolved.amount_jitter_ratio * 3.0,
            1.0,
        )
        jitter_score = (
            sum(
                abs(transaction.amount - resolved.blended_fraud_target) <= jitter_limit
                for transaction in fraud
            )
            / len(fraud)
            if fraud
            else 0.0
        )
        budget_score = (cap_score + jitter_score) / 2.0
        violation_rate = _constraint_violation_rate(transactions, blueprint, resolved)
        scores = (
            context_similarity,
            fraud_similarity,
            type_similarity,
            pacing_score,
            blend_score,
            destination_score,
            budget_score,
            1.0 - violation_rate,
        )
        assumptions = (
            [
                "No PaySim TRAIN artifact supplied; bounded fallback moments are assumptions.",
                "Fidelity measures a declared synthetic perturbation envelope, not real-system "
                "evasion capability.",
            ]
            if self.reference_profile.basis == "bounded_fallback"
            else [
                "Amount and type moments were derived from legitimate PaySim TRAIN rows only.",
                "Fidelity measures a declared synthetic perturbation envelope, not real-system "
                "evasion capability.",
            ]
        )
        return AdaptiveEvasionFidelitySummary(
            reference_basis=self.reference_profile.basis,
            reference_sample_count=self.reference_profile.sample_count,
            reference_transfer_sample_count=self.reference_profile.transfer_sample_count,
            context_count=len(context),
            fraud_count=len(fraud),
            context_amount_similarity=context_similarity,
            fraud_amount_similarity=fraud_similarity,
            transaction_type_similarity=type_similarity,
            temporal_pacing_reasonableness=pacing_score,
            history_blend_consistency=blend_score,
            destination_diversity_score=destination_score,
            perturbation_budget_score=budget_score,
            constraint_violation_rate=violation_rate,
            average_fraud_amount=fraud_mean,
            reference_transfer_amount_mean=self.reference_profile.transfer_amount_mean,
            overall_fidelity_score=sum(scores) / len(scores),
            assumptions=assumptions,
        )

    def _resolve_parameters(
        self, blueprint: AttackBlueprint, overrides: Mapping[str, Any]
    ) -> _Parameters:
        unknown = sorted(set(overrides).difference(blueprint.parameters))
        if unknown:
            raise AdaptiveEvasionConfigurationError(
                f"undeclared parameter overrides: {', '.join(unknown)}"
            )
        values: dict[str, int | float] = {}
        for name, parameter_type in _REQUIRED_PARAMETERS.items():
            spec = blueprint.parameters.get(name)
            if spec is None:
                raise AdaptiveEvasionConfigurationError(f"missing parameter: {name}")
            value = overrides.get(name, spec.default)
            if parameter_type is ParameterType.INT:
                if type(value) is not int:
                    raise AdaptiveEvasionConfigurationError(f"parameter {name} must be an int")
                resolved: int | float = int(value)
            else:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise AdaptiveEvasionConfigurationError(
                        f"parameter {name} must be a number"
                    )
                resolved = float(value)
            if spec.minimum is not None and resolved < spec.minimum:
                raise AdaptiveEvasionConfigurationError(
                    f"parameter {name}={resolved} is below minimum {spec.minimum}"
                )
            if spec.maximum is not None and resolved > spec.maximum:
                raise AdaptiveEvasionConfigurationError(
                    f"parameter {name}={resolved} exceeds maximum {spec.maximum}"
                )
            values[name] = resolved
        parameters = _Parameters(
            context_transaction_count=int(values["context_transaction_count"]),
            context_duration_days=int(values["context_duration_days"]),
            context_amount_mean=float(values["context_amount_mean"]),
            context_amount_stddev=float(values["context_amount_stddev"]),
            fraud_transaction_count=int(values["fraud_transaction_count"]),
            fraud_amount_mean=float(values["fraud_amount_mean"]),
            fraud_amount_stddev=float(values["fraud_amount_stddev"]),
            per_transaction_cap=float(values["per_transaction_cap"]),
            history_blend_ratio=float(values["history_blend_ratio"]),
            inter_event_delay_hours=float(values["inter_event_delay_hours"]),
            destination_diversity=int(values["destination_diversity"]),
            transfer_probability=float(values["transfer_probability"]),
            amount_jitter_ratio=float(values["amount_jitter_ratio"]),
            timestamp_jitter_minutes=float(values["timestamp_jitter_minutes"]),
            max_parameter_changes=int(values["max_parameter_changes"]),
            randomness_seed_offset=int(values["randomness_seed_offset"]),
        )
        if parameters.fraud_amount_mean > parameters.per_transaction_cap:
            raise AdaptiveEvasionConfigurationError(
                "fraud_amount_mean cannot exceed per_transaction_cap"
            )
        return parameters

    def _validate_generation(
        self,
        parameters: _Parameters,
        blueprint: AttackBlueprint,
        config: GenerationConfig,
    ) -> None:
        if parameters.duration > config.time_horizon:
            raise AdaptiveEvasionConfigurationError(
                f"scenario duration {parameters.duration} exceeds configured horizon "
                f"{config.time_horizon}"
            )
        required = parameters.sequence_length * config.n_scenarios
        if config.max_transactions is not None and config.max_transactions < required:
            raise AdaptiveEvasionConfigurationError(
                f"max_transactions={config.max_transactions} would truncate the scenario; "
                f"at least {required} are required"
            )
        constraints = blueprint.realism_constraints
        if (
            constraints.min_sequence_length is not None
            and parameters.sequence_length < constraints.min_sequence_length
        ) or (
            constraints.max_sequence_length is not None
            and parameters.sequence_length > constraints.max_sequence_length
        ):
            raise AdaptiveEvasionConfigurationError(
                "resolved sequence length violates blueprint realism constraints"
            )

    def _build_scenario(
        self,
        blueprint: AttackBlueprint,
        config: GenerationConfig,
        parameters: _Parameters,
        scenario_index: int,
    ) -> list[Transaction]:
        digest = hashlib.sha256(blueprint.attack_id.encode("utf-8")).hexdigest()[:8]
        scenario_id = f"adaptive-{digest}-{config.seed}-{scenario_index:04d}"
        source_id = f"C-ADE-{digest}-{config.seed}-{scenario_index:04d}"
        rng = np.random.default_rng(
            np.random.SeedSequence([config.seed, parameters.randomness_seed_offset, scenario_index])
        )
        start = _scenario_start(config, parameters, scenario_index)
        context_times = _context_timestamps(rng, start, parameters)
        fraud_times = _fraud_timestamps(rng, start, parameters)
        context_types = _sample_context_types(
            rng,
            parameters.context_transaction_count,
            self.reference_profile.transaction_type_distribution,
        )
        context_amounts = [
            _bounded_normal(
                rng,
                parameters.context_amount_mean,
                parameters.context_amount_stddev,
                1.0,
                min(parameters.per_transaction_cap, parameters.context_amount_mean * 3.0),
            )
            for _ in context_times
        ]
        fraud_stddev = max(
            parameters.fraud_amount_stddev,
            parameters.blended_fraud_target * parameters.amount_jitter_ratio,
        )
        fraud_amounts = [
            _bounded_normal(
                rng,
                parameters.blended_fraud_target,
                fraud_stddev,
                1.0,
                parameters.per_transaction_cap,
            )
            for _ in fraud_times
        ]
        fraud_types = [
            TransactionType.TRANSFER
            if rng.random() < parameters.transfer_probability
            else TransactionType.CASH_OUT
            for _ in fraud_times
        ]
        outgoing = sum(
            amount
            for amount, transaction_type in zip(context_amounts, context_types, strict=True)
            if transaction_type is not TransactionType.CASH_IN
        ) + sum(fraud_amounts)
        source_balance = round(max(outgoing * 1.25, 5_000.0), 2)
        destination_balances: dict[str, float] = {}
        transactions: list[Transaction] = []
        sequence_index = 0
        for index, (timestamp, amount, transaction_type) in enumerate(
            zip(context_times, context_amounts, context_types, strict=True)
        ):
            destination = f"M-ADE-CONTEXT-{scenario_id}-{index % 5:02d}"
            transaction, source_balance = _make_transaction(
                blueprint=blueprint,
                config=config,
                transaction_id=f"{scenario_id}-context-{index:03d}",
                timestamp=timestamp,
                source_id=source_id,
                destination_id=destination,
                amount=amount,
                transaction_type=transaction_type,
                label=FraudLabel.LEGITIMATE,
                scenario_id=scenario_id,
                step_id="behavioral-context",
                sequence_index=sequence_index,
                source_balance=source_balance,
                destination_balances=destination_balances,
                reference_basis=self.reference_profile.basis,
                parameters=parameters,
            )
            transactions.append(transaction)
            sequence_index += 1
        for index, (timestamp, amount, transaction_type) in enumerate(
            zip(fraud_times, fraud_amounts, fraud_types, strict=True)
        ):
            destination = (
                f"C-ADE-DEST-{scenario_id}-{index % parameters.destination_diversity:02d}"
            )
            transaction, source_balance = _make_transaction(
                blueprint=blueprint,
                config=config,
                transaction_id=f"{scenario_id}-adversarial-{index:03d}",
                timestamp=timestamp,
                source_id=source_id,
                destination_id=destination,
                amount=amount,
                transaction_type=transaction_type,
                label=FraudLabel.FRAUD,
                scenario_id=scenario_id,
                step_id="adversarial-transfers",
                sequence_index=sequence_index,
                source_balance=source_balance,
                destination_balances=destination_balances,
                reference_basis=self.reference_profile.basis,
                parameters=parameters,
            )
            transactions.append(transaction)
            sequence_index += 1
        return transactions


def _scenario_start(
    config: GenerationConfig, parameters: _Parameters, scenario_index: int
) -> datetime:
    start = _as_utc(config.start_time)
    slack = config.time_horizon - parameters.duration
    if config.n_scenarios == 1:
        return start
    return start + slack * (scenario_index / (config.n_scenarios - 1))


def _context_timestamps(
    rng: np.random.Generator, start: datetime, parameters: _Parameters
) -> list[datetime]:
    duration = timedelta(days=parameters.context_duration_days).total_seconds()
    interval = duration / (parameters.context_transaction_count + 1)
    offsets = [
        max(1.0, (index + 1) * interval + float(rng.uniform(-0.1, 0.1)) * interval)
        for index in range(parameters.context_transaction_count)
    ]
    return [start + timedelta(seconds=offset) for offset in sorted(offsets)]


def _fraud_timestamps(
    rng: np.random.Generator, start: datetime, parameters: _Parameters
) -> list[datetime]:
    fraud_start = start + timedelta(
        days=parameters.context_duration_days,
        hours=parameters.inter_event_delay_hours,
    )
    jitter_seconds = parameters.timestamp_jitter_minutes * 60.0
    timestamps: list[datetime] = []
    for index in range(parameters.fraud_transaction_count):
        base = index * parameters.inter_event_delay_hours * 3600.0
        jitter = float(rng.uniform(-jitter_seconds, jitter_seconds)) if index else 0.0
        timestamps.append(fraud_start + timedelta(seconds=max(base + jitter, 0.0)))
    return sorted(timestamps)


def _sample_context_types(
    rng: np.random.Generator,
    count: int,
    distribution: Mapping[str, float],
) -> list[TransactionType]:
    weights = np.asarray(
        [
            max(distribution.get(transaction_type.value, 0.0), 0.0)
            for transaction_type in _CONTEXT_TYPES
        ],
        dtype=float,
    )
    if float(weights.sum()) == 0.0:
        weights = np.asarray([1.0, 0.0, 0.0, 0.0, 0.0], dtype=float)
    weights /= weights.sum()
    indexes = rng.choice(len(_CONTEXT_TYPES), size=count, p=weights)
    return [_CONTEXT_TYPES[int(index)] for index in indexes]


def _bounded_normal(
    rng: np.random.Generator,
    mean: float,
    stddev: float,
    minimum: float,
    maximum: float,
) -> float:
    return round(min(max(float(rng.normal(mean, stddev)), minimum), maximum), 2)


def _make_transaction(
    *,
    blueprint: AttackBlueprint,
    config: GenerationConfig,
    transaction_id: str,
    timestamp: datetime,
    source_id: str,
    destination_id: str,
    amount: float,
    transaction_type: TransactionType,
    label: FraudLabel,
    scenario_id: str,
    step_id: str,
    sequence_index: int,
    source_balance: float,
    destination_balances: dict[str, float],
    reference_basis: str,
    parameters: _Parameters,
) -> tuple[Transaction, float]:
    source_before = source_balance
    source_after = (
        source_before + amount
        if transaction_type is TransactionType.CASH_IN
        else max(0.0, source_before - amount)
    )
    destination_before = destination_balances.setdefault(destination_id, 500.0)
    destination_after = destination_before + amount
    destination_balances[destination_id] = destination_after
    currency = (
        blueprint.realism_constraints.allowed_currencies[0]
        if blueprint.realism_constraints.allowed_currencies
        else "XXX"
    )
    return (
        Transaction(
            transaction_id=transaction_id,
            timestamp=timestamp,
            source_account_id=source_id,
            destination_account_id=destination_id,
            amount=amount,
            currency=currency,
            transaction_type=transaction_type,
            channel=Channel.MOBILE,
            merchant_id=destination_id if destination_id.startswith("M-") else None,
            source_balance_before=round(source_before, 2),
            source_balance_after=round(source_after, 2),
            destination_balance_before=round(destination_before, 2),
            destination_balance_after=round(destination_after, 2),
            label=label,
            attack_family=(
                AttackFamily.ADAPTIVE_DETECTOR_EVASION
                if label is FraudLabel.FRAUD
                else None
            ),
            is_synthetic=True,
            scenario_id=scenario_id,
            blueprint_id=blueprint.attack_id,
            step_id=step_id,
            sequence_index=sequence_index,
            generation=config.generation,
            split=config.split,
            metadata={
                "synthetic.phase": (
                    "context" if label is not FraudLabel.FRAUD else "adversarial"
                ),
                "synthetic.attack_family": AttackFamily.ADAPTIVE_DETECTOR_EVASION.value,
                "synthetic.reference_basis": reference_basis,
                "synthetic.history_blend_ratio": parameters.history_blend_ratio,
                "synthetic.perturbation_budget": parameters.max_parameter_changes,
                "synthetic.safety_scope": "synthetic_benchmark_only",
            },
        ),
        round(source_after, 2),
    )


def _fraud_type_similarity(
    fraud: Sequence[Transaction], reference_distribution: Mapping[str, float]
) -> float:
    if not fraud:
        return 0.0
    names = (TransactionType.TRANSFER.value, TransactionType.CASH_OUT.value)
    observed_counts = Counter(transaction.transaction_type.value for transaction in fraud)
    observed = {name: observed_counts[name] / len(fraud) for name in names}
    reference_total = sum(reference_distribution.get(name, 0.0) for name in names)
    reference = (
        {name: reference_distribution.get(name, 0.0) / reference_total for name in names}
        if reference_total
        else {TransactionType.TRANSFER.value: 1.0, TransactionType.CASH_OUT.value: 0.0}
    )
    total_variation = 0.5 * sum(abs(observed[name] - reference[name]) for name in names)
    return max(0.0, 1.0 - total_variation)


def _temporal_pacing_score(
    fraud: Sequence[Transaction], parameters: _Parameters
) -> float:
    if len(fraud) < 2:
        return 0.0
    target = parameters.inter_event_delay_hours * 3600.0
    spacings = [
        (right.timestamp - left.timestamp).total_seconds()
        for left, right in pairwise(fraud)
    ]
    jitter = parameters.timestamp_jitter_minutes * 60.0
    tolerance = max(jitter * 2.0, target * 0.25)
    return sum(abs(spacing - target) <= tolerance for spacing in spacings) / len(spacings)


def _constraint_violation_rate(
    transactions: Sequence[Transaction],
    blueprint: AttackBlueprint,
    parameters: _Parameters,
) -> float:
    if not transactions:
        return 1.0
    constraints = blueprint.realism_constraints
    violations = 0
    for transaction in transactions:
        violates = (
            (constraints.min_amount is not None and transaction.amount < constraints.min_amount)
            or (constraints.max_amount is not None and transaction.amount > constraints.max_amount)
            or (
                bool(constraints.allowed_currencies)
                and transaction.currency not in constraints.allowed_currencies
            )
            or (
                bool(constraints.allowed_channels)
                and transaction.channel not in constraints.allowed_channels
            )
            or (transaction.is_fraud and transaction.amount > parameters.per_transaction_cap)
        )
        violations += int(violates)
    scenario_counts = Counter(transaction.scenario_id for transaction in transactions)
    accounts: dict[str | None, set[str]] = {}
    account_days: Counter[tuple[str, date]] = Counter()
    for transaction in transactions:
        scenario_accounts = accounts.setdefault(transaction.scenario_id, set())
        scenario_accounts.add(transaction.source_account_id)
        if transaction.destination_account_id is not None:
            scenario_accounts.add(transaction.destination_account_id)
        account_days[(transaction.source_account_id, transaction.timestamp.date())] += 1
    sequence_violations = sum(
        (constraints.min_sequence_length is not None and count < constraints.min_sequence_length)
        or (constraints.max_sequence_length is not None and count > constraints.max_sequence_length)
        for count in scenario_counts.values()
    )
    account_violations = sum(
        constraints.max_accounts_involved is not None
        and len(scenario_accounts) > constraints.max_accounts_involved
        for scenario_accounts in accounts.values()
    )
    velocity_violations = sum(
        constraints.max_transactions_per_account_per_day is not None
        and count > constraints.max_transactions_per_account_per_day
        for count in account_days.values()
    )
    units = len(transactions) + len(scenario_counts) + len(accounts) + len(account_days)
    return (violations + sequence_violations + account_violations + velocity_violations) / units


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "AdaptiveDetectorEvasionGenerator",
    "AdaptiveEvasionConfigurationError",
    "AdaptiveEvasionFidelitySummary",
    "AdaptiveEvasionReferenceProfile",
]
