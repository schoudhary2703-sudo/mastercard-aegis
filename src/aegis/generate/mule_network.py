"""Deterministic, benchmark-only mule-network structuring simulation."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
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

_REQUIRED_STEPS = {"network-context", "source-allocation", "layering", "fan-in-cashout"}
_REQUIRED_PARAMETERS: dict[str, ParameterType] = {
    "mule_account_count": ParameterType.INT,
    "fan_out": ParameterType.INT,
    "fan_in": ParameterType.INT,
    "transfer_count": ParameterType.INT,
    "transfer_amount_mean": ParameterType.FLOAT,
    "transfer_amount_stddev": ParameterType.FLOAT,
    "per_transfer_cap": ParameterType.FLOAT,
    "inter_transfer_delay_minutes": ParameterType.FLOAT,
    "layering_depth": ParameterType.INT,
    "destination_diversity": ParameterType.INT,
    "temporal_spread_hours": ParameterType.FLOAT,
    "source_allocation_concentration": ParameterType.FLOAT,
    "cash_out_probability": ParameterType.FLOAT,
    "context_transaction_count_per_account": ParameterType.INT,
    "context_duration_days": ParameterType.INT,
    "context_amount_mean": ParameterType.FLOAT,
    "context_amount_stddev": ParameterType.FLOAT,
    "randomness_seed_offset": ParameterType.INT,
}
_CONTEXT_TYPES = (
    TransactionType.PAYMENT,
    TransactionType.TRANSFER,
    TransactionType.CASH_OUT,
    TransactionType.CASH_IN,
    TransactionType.DEBIT,
)


class MuleNetworkConfigurationError(ValueError):
    """Raised when a mule-network blueprint cannot produce a complete safe scenario."""


@dataclass(frozen=True)
class MuleNetworkReferenceProfile:
    """Bounded-memory moments derived only from legitimate PaySim TRAIN rows."""

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
    def bounded_fallback(cls) -> MuleNetworkReferenceProfile:
        """Return documented assumptions for tests and offline generation."""
        return cls(
            basis="bounded_fallback",
            source="built_in_assumptions",
            sample_count=0,
            transfer_sample_count=0,
            amount_mean=75.0,
            amount_stddev=25.0,
            transfer_amount_mean=500.0,
            transfer_amount_stddev=150.0,
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
    ) -> MuleNetworkReferenceProfile:
        """Accumulate profile moments in constant memory from a TRAIN-only iterator."""
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
                raise MuleNetworkConfigurationError(
                    "mule reference input contains a non-train row: "
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
            raise MuleNetworkConfigurationError(
                "mule reference input contains no legitimate TRAIN rows"
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
        distribution = {
            name: value / count for name, value in sorted(type_counts.items())
        }
        return cls(
            basis="processed_paysim_train",
            source=source,
            sample_count=count,
            transfer_sample_count=transfer_count,
            amount_mean=mean,
            amount_stddev=amount_stddev,
            transfer_amount_mean=transfer_mean,
            transfer_amount_stddev=transfer_stddev,
            transaction_type_distribution=distribution,
            currency=currency_counts.most_common(1)[0][0],
            latest_timestamp=latest,
        )

    @classmethod
    def from_processed_paysim(
        cls, reference_dir: str | Path, *, max_rows: int | None = None
    ) -> MuleNetworkReferenceProfile:
        """Stream only ``train.jsonl``; validation and test paths are never opened."""
        reference_path = Path(reference_dir).expanduser().resolve()
        train_path = reference_path if reference_path.is_file() else reference_path / "train.jsonl"
        if not train_path.is_file():
            raise FileNotFoundError(f"processed PaySim train artifact not found: {train_path}")

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
class MuleNetworkFidelitySummary:
    """Descriptive graph and marginal checks, not a claim of laundering realism."""

    reference_basis: str
    reference_sample_count: int
    reference_transfer_sample_count: int
    context_count: int
    fraud_count: int
    observed_mule_accounts: int
    observed_fan_out: int
    observed_fan_in: int
    observed_destination_diversity: int
    observed_layering_depth: int
    average_fraud_amount: float
    fraud_amount_stddev: float
    reference_transfer_amount_mean: float
    reference_transfer_amount_stddev: float
    amount_distribution_realism: float
    transfer_type_realism: float
    temporal_spacing_reasonableness: float
    fan_out_reasonableness: float
    fan_in_reasonableness: float
    mule_account_reuse_score: float
    destination_diversity_score: float
    structuring_consistency: float
    constraint_violation_rate: float
    overall_fidelity_score: float
    assumptions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _Parameters:
    mule_account_count: int
    fan_out: int
    fan_in: int
    transfer_count: int
    transfer_amount_mean: float
    transfer_amount_stddev: float
    per_transfer_cap: float
    inter_transfer_delay_minutes: float
    layering_depth: int
    destination_diversity: int
    temporal_spread_hours: float
    source_allocation_concentration: float
    cash_out_probability: float
    context_transaction_count_per_account: int
    context_duration_days: int
    context_amount_mean: float
    context_amount_stddev: float
    randomness_seed_offset: int

    @property
    def context_count(self) -> int:
        return (self.mule_account_count + 1) * self.context_transaction_count_per_account

    @property
    def sequence_length(self) -> int:
        return self.context_count + self.transfer_count

    @property
    def duration(self) -> timedelta:
        return timedelta(days=self.context_duration_days, hours=1 + self.temporal_spread_hours)

    @property
    def exit_event_count(self) -> int:
        return max(self.fan_in, self.destination_diversity)


@dataclass(frozen=True)
class _EventSpec:
    timestamp: datetime
    source: str
    destination: str
    amount: float
    transaction_type: TransactionType
    label: FraudLabel
    step_id: str
    phase: str
    source_role: str
    destination_role: str
    layer_index: int | None = None


class MuleNetworkStructuringGenerator(BaseGenerator):
    """Generate bounded synthetic account graphs without reading detector state."""

    name = "mule-network-structuring"
    version = "1.0.0"
    supported_families = (AttackFamily.MULE_NETWORK_STRUCTURING.value,)

    def __init__(self, reference_profile: MuleNetworkReferenceProfile | None = None) -> None:
        self.reference_profile = reference_profile or MuleNetworkReferenceProfile.bounded_fallback()

    def validate_blueprint(self, blueprint: AttackBlueprint) -> None:
        super().validate_blueprint(blueprint)
        missing_steps = sorted(
            _REQUIRED_STEPS.difference(step.step_id for step in blueprint.sequence)
        )
        if missing_steps:
            raise BlueprintNotSupportedError(
                f"mule network blueprint is missing steps: {', '.join(missing_steps)}"
            )
        for name, parameter_type in _REQUIRED_PARAMETERS.items():
            spec = blueprint.parameters.get(name)
            if spec is None:
                raise BlueprintNotSupportedError(f"mule network parameter missing: {name}")
            if spec.param_type is not parameter_type:
                raise BlueprintNotSupportedError(
                    f"mule network parameter {name!r} must use type {parameter_type.value}"
                )
        self._resolve_parameters(blueprint, {})

    def stream(self, blueprint: AttackBlueprint, config: GenerationConfig) -> Iterator[Transaction]:
        self.validate_blueprint(blueprint)
        parameters = self._resolve_parameters(blueprint, config.parameter_overrides)
        self._validate_generation_config(parameters, blueprint, config)
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
        """Materialize one deterministic batch with family-specific fidelity metadata."""
        self.validate_blueprint(blueprint)
        parameters = self._resolve_parameters(blueprint, config.parameter_overrides)
        self._validate_generation_config(parameters, blueprint, config)
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
            batch_id=f"mule-network-{digest}",
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
    ) -> MuleNetworkFidelitySummary:
        """Measure transparent marginals and graph invariants for generated scenarios."""
        resolved = parameters or self._resolve_parameters(blueprint, {})
        context = [transaction for transaction in transactions if not transaction.is_fraud]
        fraud = [transaction for transaction in transactions if transaction.is_fraud]
        amounts = np.asarray([transaction.amount for transaction in fraud], dtype=float)
        amount_mean = float(amounts.mean()) if len(amounts) else 0.0
        amount_stddev = float(amounts.std(ddof=1)) if len(amounts) > 1 else 0.0
        reference_scale = max(
            self.reference_profile.transfer_amount_stddev,
            self.reference_profile.transfer_amount_mean * 0.5,
            1.0,
        )
        mean_similarity = math.exp(
            -abs(amount_mean - self.reference_profile.transfer_amount_mean) / reference_scale
        )
        std_scale = max(self.reference_profile.transfer_amount_stddev, amount_stddev, 1.0)
        std_similarity = math.exp(
            -abs(amount_stddev - self.reference_profile.transfer_amount_stddev) / std_scale
        )
        amount_similarity = (mean_similarity + std_similarity) / 2.0
        type_similarity = _fraud_type_similarity(
            fraud, self.reference_profile.transaction_type_distribution
        )
        spacing_score = _temporal_spacing_score(fraud, resolved)
        allocation = [
            transaction
            for transaction in fraud
            if transaction.metadata.get("synthetic.graph_stage") == "source_allocation"
        ]
        exits = [
            transaction
            for transaction in fraud
            if transaction.metadata.get("synthetic.graph_stage") == "fan_in_cashout"
        ]
        observed_fan_out = len({transaction.destination_account_id for transaction in allocation})
        observed_fan_in = len({transaction.source_account_id for transaction in exits})
        observed_destinations = len({transaction.destination_account_id for transaction in exits})
        observed_layers = len(
            {
                transaction.metadata.get("synthetic.layer_index")
                for transaction in fraud
                if transaction.metadata.get("synthetic.graph_stage") == "layering"
            }
        )
        mule_accounts: set[str] = set()
        for transaction in fraud:
            source_role = transaction.metadata.get("synthetic.source_role")
            destination_role = transaction.metadata.get("synthetic.destination_role")
            if source_role in {"mule", "exit_mule"}:
                mule_accounts.add(transaction.source_account_id)
            if (
                destination_role in {"entry_mule", "mule"}
                and transaction.destination_account_id is not None
            ):
                mule_accounts.add(transaction.destination_account_id)
        mule_event_counts: Counter[str] = Counter()
        for transaction in fraud:
            if transaction.source_account_id in mule_accounts:
                mule_event_counts[transaction.source_account_id] += 1
            if transaction.destination_account_id in mule_accounts:
                mule_event_counts[transaction.destination_account_id] += 1
        reuse_score = (
            sum(count >= 2 for count in mule_event_counts.values()) / resolved.mule_account_count
            if resolved.mule_account_count
            else 0.0
        )
        fan_out_score = min(observed_fan_out, resolved.fan_out) / max(
            observed_fan_out, resolved.fan_out, 1
        )
        fan_in_score = min(observed_fan_in, resolved.fan_in) / max(
            observed_fan_in, resolved.fan_in, 1
        )
        destination_score = min(observed_destinations, resolved.destination_diversity) / max(
            observed_destinations, resolved.destination_diversity, 1
        )
        allocation_total = sum(transaction.amount for transaction in allocation)
        observed_concentration = (
            allocation[0].amount / allocation_total if allocation and allocation_total else 0.0
        )
        concentration_score = math.exp(
            -abs(observed_concentration - resolved.source_allocation_concentration)
            / max(resolved.source_allocation_concentration, 0.05)
        )
        cap_score = (
            sum(transaction.amount <= resolved.per_transfer_cap for transaction in fraud)
            / len(fraud)
            if fraud
            else 0.0
        )
        structuring_score = (concentration_score + cap_score) / 2.0
        violation_rate = _constraint_violation_rate(transactions, blueprint, resolved)
        scores = (
            amount_similarity,
            type_similarity,
            spacing_score,
            fan_out_score,
            fan_in_score,
            min(reuse_score, 1.0),
            destination_score,
            structuring_score,
            1.0 - violation_rate,
        )
        assumptions = (
            [
                "No PaySim TRAIN artifact supplied; bounded fallback moments are assumptions.",
                "Graph fidelity measures declared simulator invariants, not real "
                "laundering prevalence.",
            ]
            if self.reference_profile.basis == "bounded_fallback"
            else [
                "Amount and type moments were derived from legitimate PaySim TRAIN rows only.",
                "Graph fidelity measures declared simulator invariants, not real "
                "laundering prevalence.",
            ]
        )
        return MuleNetworkFidelitySummary(
            reference_basis=self.reference_profile.basis,
            reference_sample_count=self.reference_profile.sample_count,
            reference_transfer_sample_count=self.reference_profile.transfer_sample_count,
            context_count=len(context),
            fraud_count=len(fraud),
            observed_mule_accounts=len(mule_accounts),
            observed_fan_out=observed_fan_out,
            observed_fan_in=observed_fan_in,
            observed_destination_diversity=observed_destinations,
            observed_layering_depth=observed_layers,
            average_fraud_amount=amount_mean,
            fraud_amount_stddev=amount_stddev,
            reference_transfer_amount_mean=self.reference_profile.transfer_amount_mean,
            reference_transfer_amount_stddev=self.reference_profile.transfer_amount_stddev,
            amount_distribution_realism=amount_similarity,
            transfer_type_realism=type_similarity,
            temporal_spacing_reasonableness=spacing_score,
            fan_out_reasonableness=fan_out_score,
            fan_in_reasonableness=fan_in_score,
            mule_account_reuse_score=min(reuse_score, 1.0),
            destination_diversity_score=destination_score,
            structuring_consistency=structuring_score,
            constraint_violation_rate=violation_rate,
            overall_fidelity_score=sum(scores) / len(scores),
            assumptions=assumptions,
        )

    def _resolve_parameters(
        self, blueprint: AttackBlueprint, overrides: Mapping[str, Any]
    ) -> _Parameters:
        unknown = sorted(set(overrides).difference(blueprint.parameters))
        if unknown:
            raise MuleNetworkConfigurationError(
                f"undeclared parameter overrides: {', '.join(unknown)}"
            )
        values: dict[str, int | float] = {}
        for name, parameter_type in _REQUIRED_PARAMETERS.items():
            spec = blueprint.parameters.get(name)
            if spec is None:
                raise MuleNetworkConfigurationError(f"missing parameter: {name}")
            value = overrides.get(name, spec.default)
            if parameter_type is ParameterType.INT:
                if type(value) is not int:
                    raise MuleNetworkConfigurationError(f"parameter {name} must be an int")
                resolved: int | float = int(value)
            else:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise MuleNetworkConfigurationError(f"parameter {name} must be a number")
                resolved = float(value)
            if spec.minimum is not None and resolved < spec.minimum:
                raise MuleNetworkConfigurationError(
                    f"parameter {name}={resolved} is below minimum {spec.minimum}"
                )
            if spec.maximum is not None and resolved > spec.maximum:
                raise MuleNetworkConfigurationError(
                    f"parameter {name}={resolved} exceeds maximum {spec.maximum}"
                )
            values[name] = resolved
        parameters = _Parameters(
            mule_account_count=int(values["mule_account_count"]),
            fan_out=int(values["fan_out"]),
            fan_in=int(values["fan_in"]),
            transfer_count=int(values["transfer_count"]),
            transfer_amount_mean=float(values["transfer_amount_mean"]),
            transfer_amount_stddev=float(values["transfer_amount_stddev"]),
            per_transfer_cap=float(values["per_transfer_cap"]),
            inter_transfer_delay_minutes=float(values["inter_transfer_delay_minutes"]),
            layering_depth=int(values["layering_depth"]),
            destination_diversity=int(values["destination_diversity"]),
            temporal_spread_hours=float(values["temporal_spread_hours"]),
            source_allocation_concentration=float(values["source_allocation_concentration"]),
            cash_out_probability=float(values["cash_out_probability"]),
            context_transaction_count_per_account=int(
                values["context_transaction_count_per_account"]
            ),
            context_duration_days=int(values["context_duration_days"]),
            context_amount_mean=float(values["context_amount_mean"]),
            context_amount_stddev=float(values["context_amount_stddev"]),
            randomness_seed_offset=int(values["randomness_seed_offset"]),
        )
        if parameters.fan_out > parameters.mule_account_count:
            raise MuleNetworkConfigurationError("fan_out cannot exceed mule_account_count")
        if parameters.fan_in > parameters.mule_account_count:
            raise MuleNetworkConfigurationError("fan_in cannot exceed mule_account_count")
        required = parameters.fan_out + parameters.exit_event_count + parameters.layering_depth
        if parameters.transfer_count < required:
            raise MuleNetworkConfigurationError(
                "transfer_count must cover fan-out, every layer, and exit diversity"
            )
        if parameters.transfer_amount_mean > parameters.per_transfer_cap:
            raise MuleNetworkConfigurationError(
                "transfer_amount_mean cannot exceed per_transfer_cap"
            )
        return parameters

    def _validate_generation_config(
        self,
        parameters: _Parameters,
        blueprint: AttackBlueprint,
        config: GenerationConfig,
    ) -> None:
        if parameters.duration > config.time_horizon:
            raise MuleNetworkConfigurationError(
                f"scenario duration {parameters.duration} exceeds configured horizon "
                f"{config.time_horizon}"
            )
        required = parameters.sequence_length * config.n_scenarios
        if config.max_transactions is not None and config.max_transactions < required:
            raise MuleNetworkConfigurationError(
                f"max_transactions={config.max_transactions} would truncate the graph; "
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
            raise MuleNetworkConfigurationError(
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
        scenario_id = f"mule-{digest}-{config.seed}-{scenario_index:04d}"
        coordinator = f"C-MULE-SOURCE-{digest}-{config.seed}-{scenario_index:04d}"
        mules = [
            f"C-MULE-{scenario_id}-{index:02d}"
            for index in range(parameters.mule_account_count)
        ]
        exits = [
            f"C-MULE-EXIT-{scenario_id}-{index:02d}"
            for index in range(parameters.destination_diversity)
        ]
        rng = np.random.default_rng(
            np.random.SeedSequence([config.seed, parameters.randomness_seed_offset, scenario_index])
        )
        start = _scenario_start(config, parameters, scenario_index)
        events = _context_events(
            rng, start, scenario_id, coordinator, mules, parameters, self.reference_profile
        )
        events.extend(
            _fraud_events(rng, start, scenario_id, coordinator, mules, exits, parameters)
        )
        events.sort(key=lambda event: (event.timestamp, event.source, event.destination))
        initial_balance = max(parameters.transfer_amount_mean * 8.0, 5_000.0)
        balances = {coordinator: initial_balance * parameters.fan_out}
        balances.update(dict.fromkeys(mules, initial_balance))
        balances.update(dict.fromkeys(exits, 500.0))
        transactions: list[Transaction] = []
        for sequence_index, event in enumerate(events):
            transactions.append(
                _make_transaction(
                    event=event,
                    blueprint=blueprint,
                    config=config,
                    scenario_id=scenario_id,
                    sequence_index=sequence_index,
                    balances=balances,
                    reference_basis=self.reference_profile.basis,
                    mule_account_count=parameters.mule_account_count,
                )
            )
        return transactions


def _scenario_start(
    config: GenerationConfig, parameters: _Parameters, scenario_index: int
) -> datetime:
    start = _as_utc(config.start_time)
    slack = config.time_horizon - parameters.duration
    if config.n_scenarios == 1:
        return start
    return start + slack * (scenario_index / (config.n_scenarios - 1))


def _context_events(
    rng: np.random.Generator,
    start: datetime,
    scenario_id: str,
    coordinator: str,
    mules: Sequence[str],
    parameters: _Parameters,
    reference: MuleNetworkReferenceProfile,
) -> list[_EventSpec]:
    accounts = [coordinator, *mules]
    count = parameters.context_count
    duration_seconds = timedelta(days=parameters.context_duration_days).total_seconds()
    interval = duration_seconds / (count + 1)
    types = _sample_types(rng, count, reference.transaction_type_distribution)
    events: list[_EventSpec] = []
    for index in range(count):
        account = accounts[index % len(accounts)]
        offset = (index + 1) * interval + float(rng.uniform(-0.1, 0.1)) * interval
        amount = _bounded_normal(
            rng,
            parameters.context_amount_mean,
            parameters.context_amount_stddev,
            1.0,
            min(1_500.0, parameters.per_transfer_cap),
        )
        destination = f"M-MULE-CONTEXT-{scenario_id}-{index % 6:02d}"
        events.append(
            _EventSpec(
                timestamp=start + timedelta(seconds=max(1.0, offset)),
                source=account,
                destination=destination,
                amount=amount,
                transaction_type=types[index],
                label=FraudLabel.LEGITIMATE,
                step_id="network-context",
                phase="context",
                source_role="coordinator" if account == coordinator else "mule",
                destination_role="context_merchant",
            )
        )
    return events


def _fraud_events(
    rng: np.random.Generator,
    start: datetime,
    scenario_id: str,
    coordinator: str,
    mules: Sequence[str],
    exits: Sequence[str],
    parameters: _Parameters,
) -> list[_EventSpec]:
    timestamps = _fraud_timestamps(rng, start, parameters)
    stage_plan = _stage_plan(parameters)
    allocation_amounts = _allocation_amounts(rng, parameters)
    events: list[_EventSpec] = []
    allocation_index = exit_index = 0
    layer_positions: Counter[int] = Counter()
    for timestamp, (stage, layer_index) in zip(timestamps, stage_plan, strict=True):
        if stage == "source_allocation":
            source = coordinator
            destination = mules[allocation_index % parameters.fan_out]
            amount = allocation_amounts[allocation_index]
            transaction_type = TransactionType.TRANSFER
            source_role, destination_role = "coordinator", "entry_mule"
            step_id = "source-allocation"
            allocation_index += 1
        elif stage == "layering":
            assert layer_index is not None
            position = layer_positions[layer_index]
            source_index = (position + layer_index - 1) % len(mules)
            destination_index = (source_index + layer_index + 1) % len(mules)
            if destination_index == source_index:
                destination_index = (destination_index + 1) % len(mules)
            source, destination = mules[source_index], mules[destination_index]
            amount = _bounded_normal(
                rng,
                parameters.transfer_amount_mean,
                parameters.transfer_amount_stddev,
                1.0,
                parameters.per_transfer_cap,
            )
            transaction_type = TransactionType.TRANSFER
            source_role = destination_role = "mule"
            step_id = "layering"
            layer_positions[layer_index] += 1
        else:
            source = mules[exit_index % parameters.fan_in]
            destination = exits[exit_index % parameters.destination_diversity]
            amount = _bounded_normal(
                rng,
                parameters.transfer_amount_mean,
                parameters.transfer_amount_stddev,
                1.0,
                parameters.per_transfer_cap,
            )
            transaction_type = (
                TransactionType.CASH_OUT
                if rng.random() < parameters.cash_out_probability
                else TransactionType.TRANSFER
            )
            source_role, destination_role = "exit_mule", "exit_destination"
            step_id = "fan-in-cashout"
            exit_index += 1
        events.append(
            _EventSpec(
                timestamp=timestamp,
                source=source,
                destination=destination,
                amount=amount,
                transaction_type=transaction_type,
                label=FraudLabel.FRAUD,
                step_id=step_id,
                phase="structuring",
                source_role=source_role,
                destination_role=destination_role,
                layer_index=layer_index,
            )
        )
    return events


def _stage_plan(parameters: _Parameters) -> list[tuple[str, int | None]]:
    layering_count = (
        parameters.transfer_count - parameters.fan_out - parameters.exit_event_count
    )
    layer_counts = [layering_count // parameters.layering_depth] * parameters.layering_depth
    for index in range(layering_count % parameters.layering_depth):
        layer_counts[index] += 1
    plan: list[tuple[str, int | None]] = [
        ("source_allocation", None) for _ in range(parameters.fan_out)
    ]
    for layer_index, count in enumerate(layer_counts, 1):
        plan.extend(("layering", layer_index) for _ in range(count))
    plan.extend(("fan_in_cashout", None) for _ in range(parameters.exit_event_count))
    return plan


def _fraud_timestamps(
    rng: np.random.Generator, start: datetime, parameters: _Parameters
) -> list[datetime]:
    fraud_start = start + timedelta(days=parameters.context_duration_days, hours=1)
    if parameters.transfer_count == 1:
        return [fraud_start]
    target = parameters.inter_transfer_delay_minutes * 60.0
    delays = np.asarray(
        [target * float(rng.uniform(0.75, 1.25)) for _ in range(parameters.transfer_count - 1)]
    )
    maximum_spread = parameters.temporal_spread_hours * 3600.0
    total = float(delays.sum())
    if total > maximum_spread:
        delays *= maximum_spread / total
    offsets = [0.0]
    for delay in delays:
        offsets.append(offsets[-1] + max(float(delay), 1.0))
    return [fraud_start + timedelta(seconds=offset) for offset in offsets]


def _allocation_amounts(
    rng: np.random.Generator, parameters: _Parameters
) -> list[float]:
    total = parameters.transfer_amount_mean * parameters.fan_out
    first = parameters.source_allocation_concentration
    remaining = (1.0 - first) / (parameters.fan_out - 1)
    shares = [first, *([remaining] * (parameters.fan_out - 1))]
    return [
        round(
            min(
                max(total * share * float(rng.uniform(0.95, 1.05)), 1.0),
                parameters.per_transfer_cap,
            ),
            2,
        )
        for share in shares
    ]


def _sample_types(
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
    event: _EventSpec,
    blueprint: AttackBlueprint,
    config: GenerationConfig,
    scenario_id: str,
    sequence_index: int,
    balances: dict[str, float],
    reference_basis: str,
    mule_account_count: int,
) -> Transaction:
    source_before = balances.setdefault(event.source, max(event.amount * 4.0, 1_000.0))
    if event.transaction_type is TransactionType.CASH_IN:
        source_after = source_before + event.amount
    else:
        source_after = max(0.0, source_before - event.amount)
    destination_before = balances.setdefault(event.destination, 500.0)
    destination_after = destination_before + event.amount
    balances[event.source] = round(source_after, 2)
    balances[event.destination] = round(destination_after, 2)
    currency = (
        blueprint.realism_constraints.allowed_currencies[0]
        if blueprint.realism_constraints.allowed_currencies
        else "XXX"
    )
    stage_slug = event.step_id.replace("-", "_")
    transaction_id = f"{scenario_id}-{stage_slug}-{sequence_index:03d}"
    return Transaction(
        transaction_id=transaction_id,
        timestamp=event.timestamp,
        source_account_id=event.source,
        destination_account_id=event.destination,
        amount=event.amount,
        currency=currency,
        transaction_type=event.transaction_type,
        channel=Channel.ONLINE_BANKING,
        merchant_id=(event.destination if event.destination.startswith("M-") else None),
        source_balance_before=round(source_before, 2),
        source_balance_after=round(source_after, 2),
        destination_balance_before=round(destination_before, 2),
        destination_balance_after=round(destination_after, 2),
        label=event.label,
        attack_family=(
            AttackFamily.MULE_NETWORK_STRUCTURING if event.label is FraudLabel.FRAUD else None
        ),
        is_synthetic=True,
        scenario_id=scenario_id,
        blueprint_id=blueprint.attack_id,
        step_id=event.step_id,
        sequence_index=sequence_index,
        generation=config.generation,
        split=config.split,
        metadata={
            "synthetic.phase": event.phase,
            "synthetic.attack_family": AttackFamily.MULE_NETWORK_STRUCTURING.value,
            "synthetic.reference_basis": reference_basis,
            "synthetic.graph_stage": event.step_id.replace("-", "_"),
            "synthetic.layer_index": event.layer_index,
            "synthetic.source_role": event.source_role,
            "synthetic.destination_role": event.destination_role,
            "synthetic.mule_account_count": mule_account_count,
            "synthetic.safety_scope": "synthetic_benchmark_only",
        },
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
    if reference_total == 0.0:
        reference = {TransactionType.TRANSFER.value: 1.0, TransactionType.CASH_OUT.value: 0.0}
    else:
        reference = {
            name: reference_distribution.get(name, 0.0) / reference_total for name in names
        }
    total_variation = 0.5 * sum(abs(observed[name] - reference[name]) for name in names)
    return max(0.0, 1.0 - total_variation)


def _temporal_spacing_score(
    fraud: Sequence[Transaction], parameters: _Parameters
) -> float:
    by_scenario: dict[str, list[datetime]] = {}
    for transaction in fraud:
        if transaction.scenario_id is not None:
            by_scenario.setdefault(transaction.scenario_id, []).append(transaction.timestamp)
    target = parameters.inter_transfer_delay_minutes * 60.0
    spacings = [
        (right - left).total_seconds()
        for timestamps in by_scenario.values()
        for left, right in zip(sorted(timestamps), sorted(timestamps)[1:], strict=False)
    ]
    if not spacings:
        return 0.0
    reasonable = sum(0.25 * target <= spacing <= 1.75 * target for spacing in spacings)
    return reasonable / len(spacings)


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
            or (transaction.is_fraud and transaction.amount > parameters.per_transfer_cap)
        )
        violations += int(violates)
    scenario_counts = Counter(transaction.scenario_id for transaction in transactions)
    scenario_accounts: dict[str | None, set[str]] = {}
    account_days: Counter[tuple[str, date]] = Counter()
    for transaction in transactions:
        accounts = scenario_accounts.setdefault(transaction.scenario_id, set())
        accounts.add(transaction.source_account_id)
        if transaction.destination_account_id is not None:
            accounts.add(transaction.destination_account_id)
        account_days[(transaction.source_account_id, transaction.timestamp.date())] += 1
    sequence_violations = sum(
        (constraints.min_sequence_length is not None and count < constraints.min_sequence_length)
        or (constraints.max_sequence_length is not None and count > constraints.max_sequence_length)
        for count in scenario_counts.values()
    )
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
    fraud = [transaction for transaction in transactions if transaction.is_fraud]
    graph_violations = int(
        any(
            transaction.source_account_id == transaction.destination_account_id
            for transaction in fraud
        )
    )
    diagnostic_units = (
        len(transactions) + len(scenario_counts) + len(scenario_accounts) + len(account_days) + 1
    )
    return (
        violations
        + sequence_violations
        + account_violations
        + velocity_violations
        + graph_violations
    ) / diagnostic_units


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "MuleNetworkConfigurationError",
    "MuleNetworkFidelitySummary",
    "MuleNetworkReferenceProfile",
    "MuleNetworkStructuringGenerator",
]
