"""Deterministic synthetic-identity warm-up and bust-out simulation."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import uuid
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
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

_REQUIRED_STEPS = {"identity-onboarding", "warmup-history", "trust-transition", "bust-out"}
_REQUIRED_PARAMETERS: dict[str, ParameterType] = {
    "warmup_transaction_count": ParameterType.INT,
    "warmup_amount_mean": ParameterType.FLOAT,
    "warmup_amount_stddev": ParameterType.FLOAT,
    "warmup_duration_days": ParameterType.INT,
    "account_age_days": ParameterType.INT,
    "bustout_amount_multiplier": ParameterType.FLOAT,
    "bustout_transaction_count": ParameterType.INT,
    "bustout_window_hours": ParameterType.FLOAT,
    "destination_diversity": ParameterType.INT,
    "transition_delay_hours": ParameterType.FLOAT,
    "warmup_transfer_probability": ParameterType.FLOAT,
    "randomness_seed_offset": ParameterType.INT,
}
_WARMUP_TYPES = (
    TransactionType.PAYMENT,
    TransactionType.TRANSFER,
    TransactionType.CASH_OUT,
    TransactionType.CASH_IN,
    TransactionType.DEBIT,
)


class SyntheticIdentityConfigurationError(ValueError):
    """Raised when a blueprint or generation override would break the scenario."""


@dataclass(frozen=True)
class PaySimReferenceProfile:
    """Train-only PaySim moments used as a transparent simulation reference."""

    basis: str
    source: str
    sample_count: int
    amount_mean: float
    amount_stddev: float
    transaction_type_distribution: dict[str, float]
    currency: str

    @classmethod
    def bounded_fallback(cls) -> PaySimReferenceProfile:
        """Return explicit assumptions when no prepared PaySim train data is available."""
        return cls(
            basis="bounded_fallback",
            source="built_in_assumptions",
            sample_count=0,
            amount_mean=75.0,
            amount_stddev=25.0,
            transaction_type_distribution={
                TransactionType.PAYMENT.value: 0.50,
                TransactionType.TRANSFER.value: 0.25,
                TransactionType.CASH_OUT.value: 0.12,
                TransactionType.CASH_IN.value: 0.08,
                TransactionType.DEBIT.value: 0.05,
            },
            currency="XXX",
        )

    @classmethod
    def from_processed_paysim(
        cls, reference_dir: str | Path, *, max_rows: int | None = None
    ) -> PaySimReferenceProfile:
        """Stream legitimate rows from a prepared train artifact; never read evaluation splits."""
        reference_path = Path(reference_dir).expanduser().resolve()
        train_path = reference_path if reference_path.is_file() else reference_path / "train.jsonl"
        if not train_path.is_file():
            msg = f"processed PaySim train artifact not found: {train_path}"
            raise FileNotFoundError(msg)
        if max_rows is not None and max_rows < 1:
            raise ValueError("max_rows must be positive when provided")

        count = 0
        mean = 0.0
        second_moment = 0.0
        type_counts: Counter[str] = Counter()
        currency_counts: Counter[str] = Counter()
        with train_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                transaction = Transaction.model_validate_json(line)
                if transaction.split is not DataSplit.TRAIN:
                    raise SyntheticIdentityConfigurationError(
                        f"reference train artifact contains a non-train row: "
                        f"{transaction.transaction_id}"
                    )
                if transaction.label is not FraudLabel.LEGITIMATE:
                    continue
                count += 1
                delta = transaction.amount - mean
                mean += delta / count
                second_moment += delta * (transaction.amount - mean)
                type_counts[transaction.transaction_type.value] += 1
                currency_counts[transaction.currency] += 1
                if max_rows is not None and count >= max_rows:
                    break
        if count == 0:
            raise SyntheticIdentityConfigurationError(
                "processed PaySim train artifact contains no legitimate reference rows"
            )
        stddev = math.sqrt(second_moment / (count - 1)) if count > 1 else 0.0
        total_types = sum(type_counts.values())
        distribution = {name: value / total_types for name, value in sorted(type_counts.items())}
        currency = currency_counts.most_common(1)[0][0]
        return cls(
            basis="processed_paysim_train",
            source=str(train_path),
            sample_count=count,
            amount_mean=mean,
            amount_stddev=stddev,
            transaction_type_distribution=distribution,
            currency=currency,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BustOutFidelitySummary:
    """Descriptive simulator diagnostics; not a detector evaluation result."""

    reference_basis: str
    reference_sample_count: int
    warmup_count: int
    fraud_count: int
    fraud_proportion: float
    warmup_amount_mean: float
    reference_amount_mean: float
    warmup_amount_stddev: float
    reference_amount_stddev: float
    warmup_amount_similarity: float
    transaction_type_similarity: float
    temporal_spacing_reasonableness: float
    transition_sharpness: float
    transition_multiplier_similarity: float
    constraint_violation_rate: float
    overall_fidelity_score: float
    assumptions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _Parameters:
    warmup_transaction_count: int
    warmup_amount_mean: float
    warmup_amount_stddev: float
    warmup_duration_days: int
    account_age_days: int
    bustout_amount_multiplier: float
    bustout_transaction_count: int
    bustout_window_hours: float
    destination_diversity: int
    transition_delay_hours: float
    warmup_transfer_probability: float
    randomness_seed_offset: int

    @property
    def sequence_length(self) -> int:
        return self.warmup_transaction_count + self.bustout_transaction_count

    @property
    def duration(self) -> timedelta:
        return timedelta(
            days=self.warmup_duration_days,
            hours=self.transition_delay_hours + self.bustout_window_hours,
        )


class SyntheticIdentityBustOutGenerator(BaseGenerator):
    """Generate bounded behavioral sequences for one attack family only."""

    name = "synthetic-identity-bustout"
    version = "1.0.0"
    supported_families = (AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT.value,)

    def __init__(self, reference_profile: PaySimReferenceProfile | None = None) -> None:
        self.reference_profile = reference_profile or PaySimReferenceProfile.bounded_fallback()

    def validate_blueprint(self, blueprint: AttackBlueprint) -> None:
        super().validate_blueprint(blueprint)
        step_ids = {step.step_id for step in blueprint.sequence}
        missing_steps = sorted(_REQUIRED_STEPS.difference(step_ids))
        if missing_steps:
            msg = f"synthetic identity blueprint is missing steps: {', '.join(missing_steps)}"
            raise BlueprintNotSupportedError(msg)
        for name, parameter_type in _REQUIRED_PARAMETERS.items():
            spec = blueprint.parameters.get(name)
            if spec is None:
                raise BlueprintNotSupportedError(f"synthetic identity parameter missing: {name}")
            if spec.param_type is not parameter_type:
                msg = f"synthetic identity parameter {name!r} must use type {parameter_type.value}"
                raise BlueprintNotSupportedError(msg)
        self._resolve_parameters(blueprint, {})

    def stream(self, blueprint: AttackBlueprint, config: GenerationConfig) -> Iterator[Transaction]:
        self.validate_blueprint(blueprint)
        parameters = self._resolve_parameters(blueprint, config.parameter_overrides)
        self._validate_generation_config(parameters, config)
        transactions: list[Transaction] = []
        for scenario_index in range(config.n_scenarios):
            transactions.extend(self._build_scenario(blueprint, config, parameters, scenario_index))
        yield from sorted(
            transactions,
            key=lambda transaction: (
                transaction.timestamp,
                transaction.scenario_id or "",
                transaction.sequence_index or 0,
            ),
        )

    def generate(self, blueprint: AttackBlueprint, config: GenerationConfig) -> TransactionBatch:
        """Return a deterministic batch and attach transparent fidelity diagnostics."""
        self.validate_blueprint(blueprint)
        parameters = self._resolve_parameters(blueprint, config.parameter_overrides)
        self._validate_generation_config(parameters, config)
        transactions = list(self.stream(blueprint, config))
        fidelity = self.assess_fidelity(transactions, blueprint, parameters)
        scenario_ids = sorted(
            {transaction.scenario_id for transaction in transactions if transaction.scenario_id}
        )
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
        batch_digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        return TransactionBatch(
            batch_id=f"bustout-{batch_digest}",
            transactions=transactions,
            blueprint_id=blueprint.attack_id,
            attack_family=blueprint.attack_family,
            scenario_ids=scenario_ids,
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
            },
        )

    def assess_fidelity(
        self,
        transactions: Sequence[Transaction],
        blueprint: AttackBlueprint,
        parameters: _Parameters | None = None,
    ) -> BustOutFidelitySummary:
        """Measure sequence realism against the declared reference and constraints."""
        resolved = parameters or self._resolve_parameters(blueprint, {})
        warmup = [
            transaction
            for transaction in transactions
            if transaction.metadata.get("synthetic.phase") == "warmup"
        ]
        bustout = [
            transaction
            for transaction in transactions
            if transaction.metadata.get("synthetic.phase") == "bustout"
        ]
        warmup_amounts = np.asarray([transaction.amount for transaction in warmup], dtype=float)
        bustout_amounts = np.asarray([transaction.amount for transaction in bustout], dtype=float)
        warmup_mean = float(warmup_amounts.mean()) if len(warmup_amounts) else 0.0
        warmup_stddev = float(warmup_amounts.std(ddof=1)) if len(warmup_amounts) > 1 else 0.0
        reference_scale = max(
            self.reference_profile.amount_stddev,
            self.reference_profile.amount_mean * 0.25,
            1.0,
        )
        amount_similarity = math.exp(
            -abs(warmup_mean - self.reference_profile.amount_mean) / reference_scale
        )
        type_similarity = _type_distribution_similarity(
            warmup, self.reference_profile.transaction_type_distribution
        )
        spacing_score = _temporal_spacing_score(warmup, resolved)
        bustout_mean = float(bustout_amounts.mean()) if len(bustout_amounts) else 0.0
        transition_sharpness = bustout_mean / max(warmup_mean, 0.01)
        multiplier_similarity = math.exp(
            -abs(math.log(max(transition_sharpness, 0.01) / resolved.bustout_amount_multiplier))
        )
        violation_rate = _constraint_violation_rate(transactions, blueprint)
        scores = (
            amount_similarity,
            type_similarity,
            spacing_score,
            multiplier_similarity,
            1.0 - violation_rate,
        )
        total = len(warmup) + len(bustout)
        assumptions = (
            [
                "No processed PaySim train artifact supplied; bounded defaults are assumptions, "
                "not measured statistical fidelity."
            ]
            if self.reference_profile.basis == "bounded_fallback"
            else ["Reference moments were derived from legitimate prepared PaySim train rows only."]
        )
        return BustOutFidelitySummary(
            reference_basis=self.reference_profile.basis,
            reference_sample_count=self.reference_profile.sample_count,
            warmup_count=len(warmup),
            fraud_count=len(bustout),
            fraud_proportion=len(bustout) / total if total else 0.0,
            warmup_amount_mean=warmup_mean,
            reference_amount_mean=self.reference_profile.amount_mean,
            warmup_amount_stddev=warmup_stddev,
            reference_amount_stddev=self.reference_profile.amount_stddev,
            warmup_amount_similarity=amount_similarity,
            transaction_type_similarity=type_similarity,
            temporal_spacing_reasonableness=spacing_score,
            transition_sharpness=transition_sharpness,
            transition_multiplier_similarity=multiplier_similarity,
            constraint_violation_rate=violation_rate,
            overall_fidelity_score=sum(scores) / len(scores),
            assumptions=assumptions,
        )

    def _validate_generation_config(
        self, parameters: _Parameters, config: GenerationConfig
    ) -> None:
        if parameters.duration > config.time_horizon:
            msg = (
                f"scenario duration {parameters.duration} exceeds configured horizon "
                f"{config.time_horizon}"
            )
            raise SyntheticIdentityConfigurationError(msg)
        required = parameters.sequence_length * config.n_scenarios
        if config.max_transactions is not None and config.max_transactions < required:
            msg = (
                f"max_transactions={config.max_transactions} would truncate the behavioral "
                f"sequence; at least {required} are required"
            )
            raise SyntheticIdentityConfigurationError(msg)

    def _resolve_parameters(
        self, blueprint: AttackBlueprint, overrides: Mapping[str, Any]
    ) -> _Parameters:
        unknown = sorted(set(overrides).difference(blueprint.parameters))
        if unknown:
            raise SyntheticIdentityConfigurationError(
                f"undeclared parameter overrides: {', '.join(unknown)}"
            )
        values: dict[str, int | float] = {}
        for name, parameter_type in _REQUIRED_PARAMETERS.items():
            spec = blueprint.parameters.get(name)
            if spec is None:
                raise SyntheticIdentityConfigurationError(f"missing parameter: {name}")
            value = overrides.get(name, spec.default)
            if parameter_type is ParameterType.INT:
                if type(value) is not int:
                    raise SyntheticIdentityConfigurationError(f"parameter {name} must be an int")
                resolved: int | float = int(value)
            else:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise SyntheticIdentityConfigurationError(f"parameter {name} must be a number")
                resolved = float(value)
            if spec.minimum is not None and resolved < spec.minimum:
                raise SyntheticIdentityConfigurationError(
                    f"parameter {name}={resolved} is below minimum {spec.minimum}"
                )
            if spec.maximum is not None and resolved > spec.maximum:
                raise SyntheticIdentityConfigurationError(
                    f"parameter {name}={resolved} exceeds maximum {spec.maximum}"
                )
            values[name] = resolved
        return _Parameters(
            warmup_transaction_count=int(values["warmup_transaction_count"]),
            warmup_amount_mean=float(values["warmup_amount_mean"]),
            warmup_amount_stddev=float(values["warmup_amount_stddev"]),
            warmup_duration_days=int(values["warmup_duration_days"]),
            account_age_days=int(values["account_age_days"]),
            bustout_amount_multiplier=float(values["bustout_amount_multiplier"]),
            bustout_transaction_count=int(values["bustout_transaction_count"]),
            bustout_window_hours=float(values["bustout_window_hours"]),
            destination_diversity=int(values["destination_diversity"]),
            transition_delay_hours=float(values["transition_delay_hours"]),
            warmup_transfer_probability=float(values["warmup_transfer_probability"]),
            randomness_seed_offset=int(values["randomness_seed_offset"]),
        )

    def _build_scenario(
        self,
        blueprint: AttackBlueprint,
        config: GenerationConfig,
        parameters: _Parameters,
        scenario_index: int,
    ) -> Iterator[Transaction]:
        blueprint_digest = hashlib.sha256(blueprint.attack_id.encode("utf-8")).hexdigest()[:8]
        scenario_id = f"bustout-{blueprint_digest}-{config.seed}-{scenario_index:04d}"
        persona_id = f"C-SYN-{blueprint_digest}-{config.seed}-{scenario_index:04d}"
        rng = np.random.default_rng(
            np.random.SeedSequence([config.seed, parameters.randomness_seed_offset, scenario_index])
        )
        start = _scenario_start(config, parameters, scenario_index)
        warmup_times, bustout_times = _scenario_timestamps(rng, start, parameters)
        warmup_types = _sample_warmup_types(
            rng,
            parameters.warmup_transaction_count,
            self.reference_profile.transaction_type_distribution,
            parameters.warmup_transfer_probability,
        )
        minimum, maximum = _amount_bounds(blueprint)
        warmup_amounts = [
            _bounded_amount(
                rng,
                parameters.warmup_amount_mean,
                parameters.warmup_amount_stddev,
                minimum,
                min(maximum, parameters.warmup_amount_mean * 3.0),
            )
            for _ in warmup_times
        ]
        bustout_target = parameters.warmup_amount_mean * parameters.bustout_amount_multiplier
        bustout_amounts = [
            _bounded_amount(
                rng,
                bustout_target,
                max(bustout_target * 0.12, 1.0),
                max(minimum, parameters.warmup_amount_mean * 2.0),
                maximum,
            )
            for _ in bustout_times
        ]
        bustout_types = [
            TransactionType.CASH_OUT if rng.random() < 0.45 else TransactionType.TRANSFER
            for _ in bustout_times
        ]
        outgoing = sum(
            amount
            for amount, transaction_type in zip(warmup_amounts, warmup_types, strict=True)
            if transaction_type is not TransactionType.CASH_IN
        ) + sum(bustout_amounts)
        source_balance = round(max(outgoing * 1.20, 1_000.0), 2)
        destination_balances: dict[str, float] = {}
        identity_created_at = start - timedelta(days=parameters.account_age_days)

        sequence_index = 0
        for event_index, (timestamp, amount, transaction_type) in enumerate(
            zip(warmup_times, warmup_amounts, warmup_types, strict=True)
        ):
            destination_id = _warmup_destination(
                rng, scenario_id, event_index, transaction_type, parameters.destination_diversity
            )
            transaction, source_balance = _make_transaction(
                blueprint=blueprint,
                config=config,
                transaction_id=f"{scenario_id}-warmup-{event_index:03d}",
                timestamp=timestamp,
                persona_id=persona_id,
                destination_id=destination_id,
                amount=amount,
                transaction_type=transaction_type,
                label=FraudLabel.LEGITIMATE,
                attack_family=None,
                scenario_id=scenario_id,
                step_id="warmup-history",
                sequence_index=sequence_index,
                source_balance=source_balance,
                destination_balances=destination_balances,
                identity_created_at=identity_created_at,
                account_age_days=parameters.account_age_days,
                phase="warmup",
                reference_basis=self.reference_profile.basis,
            )
            yield transaction
            sequence_index += 1

        for event_index, (timestamp, amount, transaction_type) in enumerate(
            zip(bustout_times, bustout_amounts, bustout_types, strict=True)
        ):
            destination_id = (
                f"C-BUST-{scenario_id}-{event_index % parameters.destination_diversity:02d}"
            )
            transaction, source_balance = _make_transaction(
                blueprint=blueprint,
                config=config,
                transaction_id=f"{scenario_id}-bustout-{event_index:03d}",
                timestamp=timestamp,
                persona_id=persona_id,
                destination_id=destination_id,
                amount=amount,
                transaction_type=transaction_type,
                label=FraudLabel.FRAUD,
                attack_family=AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT,
                scenario_id=scenario_id,
                step_id="bust-out",
                sequence_index=sequence_index,
                source_balance=source_balance,
                destination_balances=destination_balances,
                identity_created_at=identity_created_at,
                account_age_days=parameters.account_age_days,
                phase="bustout",
                reference_basis=self.reference_profile.basis,
            )
            yield transaction
            sequence_index += 1


def _scenario_start(
    config: GenerationConfig, parameters: _Parameters, scenario_index: int
) -> datetime:
    start = _as_utc(config.start_time)
    slack = config.time_horizon - parameters.duration
    if config.n_scenarios == 1:
        return start
    return start + slack * (scenario_index / (config.n_scenarios - 1))


def _scenario_timestamps(
    rng: np.random.Generator, start: datetime, parameters: _Parameters
) -> tuple[list[datetime], list[datetime]]:
    warmup_seconds = timedelta(days=parameters.warmup_duration_days).total_seconds()
    interval = warmup_seconds / (parameters.warmup_transaction_count + 1)
    warmup_offsets = [
        min(
            warmup_seconds,
            max(1.0, (index + 1) * interval + rng.uniform(-0.15, 0.15) * interval),
        )
        for index in range(parameters.warmup_transaction_count)
    ]
    warmup_times = [start + timedelta(seconds=float(offset)) for offset in sorted(warmup_offsets)]
    bustout_start = start + timedelta(
        days=parameters.warmup_duration_days, hours=parameters.transition_delay_hours
    )
    window_seconds = timedelta(hours=parameters.bustout_window_hours).total_seconds()
    if parameters.bustout_transaction_count == 1:
        bustout_offsets = [window_seconds / 2.0]
    else:
        bustout_offsets = [
            index * window_seconds / (parameters.bustout_transaction_count - 1)
            for index in range(parameters.bustout_transaction_count)
        ]
    bustout_times = [bustout_start + timedelta(seconds=offset) for offset in bustout_offsets]
    return warmup_times, bustout_times


def _sample_warmup_types(
    rng: np.random.Generator,
    count: int,
    reference_distribution: Mapping[str, float],
    transfer_probability: float,
) -> list[TransactionType]:
    non_transfer = {
        transaction_type: max(reference_distribution.get(transaction_type.value, 0.0), 0.0)
        for transaction_type in _WARMUP_TYPES
        if transaction_type is not TransactionType.TRANSFER
    }
    non_transfer_total = sum(non_transfer.values())
    if non_transfer_total == 0.0:
        non_transfer = {TransactionType.PAYMENT: 1.0}
        non_transfer_total = 1.0
    weights = [
        transfer_probability
        if transaction_type is TransactionType.TRANSFER
        else (1.0 - transfer_probability)
        * non_transfer.get(transaction_type, 0.0)
        / non_transfer_total
        for transaction_type in _WARMUP_TYPES
    ]
    indexes = rng.choice(len(_WARMUP_TYPES), size=count, p=np.asarray(weights, dtype=float))
    return [_WARMUP_TYPES[int(index)] for index in indexes]


def _amount_bounds(blueprint: AttackBlueprint) -> tuple[float, float]:
    minimum = blueprint.realism_constraints.min_amount
    maximum = blueprint.realism_constraints.max_amount
    return (1.0 if minimum is None else minimum, 10_000.0 if maximum is None else maximum)


def _bounded_amount(
    rng: np.random.Generator, mean: float, stddev: float, minimum: float, maximum: float
) -> float:
    if minimum > maximum:
        raise SyntheticIdentityConfigurationError(
            f"amount bounds are incompatible: minimum {minimum} exceeds maximum {maximum}"
        )
    value = float(rng.normal(mean, stddev))
    return round(min(max(value, minimum), maximum), 2)


def _warmup_destination(
    rng: np.random.Generator,
    scenario_id: str,
    event_index: int,
    transaction_type: TransactionType,
    diversity: int,
) -> str:
    pool_index = int(rng.integers(0, diversity))
    if transaction_type is TransactionType.PAYMENT:
        return f"M-WARM-{scenario_id}-{pool_index:02d}"
    return f"C-WARM-{scenario_id}-{(pool_index + event_index) % diversity:02d}"


def _make_transaction(
    *,
    blueprint: AttackBlueprint,
    config: GenerationConfig,
    transaction_id: str,
    timestamp: datetime,
    persona_id: str,
    destination_id: str,
    amount: float,
    transaction_type: TransactionType,
    label: FraudLabel,
    attack_family: AttackFamily | None,
    scenario_id: str,
    step_id: str,
    sequence_index: int,
    source_balance: float,
    destination_balances: dict[str, float],
    identity_created_at: datetime,
    account_age_days: int,
    phase: str,
    reference_basis: str,
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
    transaction = Transaction(
        transaction_id=transaction_id,
        timestamp=timestamp,
        source_account_id=persona_id,
        destination_account_id=destination_id,
        amount=amount,
        currency=currency,
        transaction_type=transaction_type,
        channel=Channel.MOBILE,
        merchant_id=destination_id if destination_id.startswith("M") else None,
        source_balance_before=round(source_before, 2),
        source_balance_after=round(source_after, 2),
        destination_balance_before=round(destination_before, 2),
        destination_balance_after=round(destination_after, 2),
        label=label,
        attack_family=attack_family,
        is_synthetic=True,
        scenario_id=scenario_id,
        blueprint_id=blueprint.attack_id,
        step_id=step_id,
        sequence_index=sequence_index,
        generation=config.generation,
        split=config.split,
        metadata={
            "synthetic.phase": phase,
            "synthetic.persona_id": persona_id,
            "synthetic.identity_created_at": identity_created_at.isoformat(),
            "synthetic.account_age_days_at_start": account_age_days,
            "synthetic.attack_family": AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT.value,
            "synthetic.reference_basis": reference_basis,
        },
    )
    return transaction, round(source_after, 2)


def _type_distribution_similarity(
    warmup: Sequence[Transaction], reference_distribution: Mapping[str, float]
) -> float:
    if not warmup:
        return 0.0
    observed_counts = Counter(transaction.transaction_type.value for transaction in warmup)
    observed = {name: count / len(warmup) for name, count in observed_counts.items()}
    names = set(observed).union(reference_distribution)
    total_variation = 0.5 * sum(
        abs(observed.get(name, 0.0) - reference_distribution.get(name, 0.0)) for name in names
    )
    return max(0.0, 1.0 - total_variation)


def _temporal_spacing_score(warmup: Sequence[Transaction], parameters: _Parameters) -> float:
    by_scenario: dict[str, list[datetime]] = {}
    for transaction in warmup:
        if transaction.scenario_id is not None:
            by_scenario.setdefault(transaction.scenario_id, []).append(transaction.timestamp)
    expected = timedelta(days=parameters.warmup_duration_days).total_seconds() / (
        parameters.warmup_transaction_count + 1
    )
    spacings = [
        (right - left).total_seconds()
        for timestamps in by_scenario.values()
        for left, right in zip(sorted(timestamps), sorted(timestamps)[1:], strict=False)
    ]
    if not spacings:
        return 1.0 if parameters.warmup_transaction_count == 1 else 0.0
    reasonable = sum(0.25 * expected <= spacing <= 1.75 * expected for spacing in spacings)
    return reasonable / len(spacings)


def _constraint_violation_rate(
    transactions: Sequence[Transaction], blueprint: AttackBlueprint
) -> float:
    if not transactions:
        return 1.0
    constraints = blueprint.realism_constraints
    violations = 0
    for transaction in transactions:
        violates = False
        if constraints.min_amount is not None and transaction.amount < constraints.min_amount:
            violates = True
        if constraints.max_amount is not None and transaction.amount > constraints.max_amount:
            violates = True
        if constraints.allowed_currencies and transaction.currency not in (
            constraints.allowed_currencies
        ):
            violates = True
        if constraints.allowed_channels and transaction.channel not in constraints.allowed_channels:
            violates = True
        violations += int(violates)
    scenario_counts = Counter(transaction.scenario_id for transaction in transactions)
    sequence_violations = sum(
        (constraints.min_sequence_length is not None and count < constraints.min_sequence_length)
        or (constraints.max_sequence_length is not None and count > constraints.max_sequence_length)
        for count in scenario_counts.values()
    )
    scenario_accounts: dict[str | None, set[str]] = {}
    account_days: Counter[tuple[str, date]] = Counter()
    for transaction in transactions:
        accounts = scenario_accounts.setdefault(transaction.scenario_id, set())
        accounts.add(transaction.source_account_id)
        if transaction.destination_account_id is not None:
            accounts.add(transaction.destination_account_id)
        account_days[(transaction.source_account_id, transaction.timestamp.date())] += 1
    account_violations = sum(
        constraints.max_accounts_involved is not None
        and len(accounts) > constraints.max_accounts_involved
        for accounts in scenario_accounts.values()
    )
    velocity_violations = sum(
        constraints.max_transactions_per_account_per_day is not None
        and count > constraints.max_transactions_per_account_per_day
        for count in account_days.values()
    )
    diagnostic_units = (
        len(transactions) + len(scenario_counts) + len(scenario_accounts) + len(account_days)
    )
    return (
        violations + sequence_violations + account_violations + velocity_violations
    ) / diagnostic_units


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def write_synthetic_identity_artifacts(
    output_dir: str | Path,
    batch: TransactionBatch,
    blueprint: AttackBlueprint,
) -> dict[str, Path]:
    """Atomically serialize one generated corpus and its self-describing scenario report."""
    if batch.attack_family is not AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT:
        raise SyntheticIdentityConfigurationError(
            "artifact writer accepts synthetic-identity bust-out batches only"
        )
    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"synthetic output already exists; refusing overwrite: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".{destination.name}-{uuid.uuid4().hex}"
    temporary.mkdir()
    try:
        transactions_path = temporary / "transactions.jsonl"
        digest = hashlib.sha256()
        with transactions_path.open("w", encoding="utf-8", newline="\n") as handle:
            for transaction in batch.transactions:
                line = transaction.model_dump_json()
                handle.write(line)
                handle.write("\n")
                digest.update(line.encode("utf-8"))
                digest.update(b"\n")
        report = {
            "blueprint": blueprint.model_dump(mode="json"),
            "batch": batch.model_dump(mode="json", exclude={"transactions"}),
            "transaction_count": len(batch),
            "fraud_count": batch.fraud_count,
            "transactions_sha256": digest.hexdigest(),
            "fidelity": batch.metadata.get("fidelity", {}),
        }
        report_path = temporary / "scenario.json"
        with report_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "transactions": destination / "transactions.jsonl",
        "scenario": destination / "scenario.json",
    }


__all__ = [
    "BustOutFidelitySummary",
    "PaySimReferenceProfile",
    "SyntheticIdentityBustOutGenerator",
    "SyntheticIdentityConfigurationError",
    "write_synthetic_identity_artifacts",
]
