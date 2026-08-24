"""`BaseGenerator` - the interface every attack generator implements.

    generate(blueprint, config) -> TransactionBatch
    stream(blueprint, config)   -> Iterator[Transaction]

`generate` is the contract the rest of the system uses; `stream` exists so that
large corpora do not have to be materialised in memory. The default `generate`
is built on `stream`, so an implementation only needs to write one of them.

Deliberately absent: CTGAN, SDV, diffusion, GANs, LLM prompting, and any actual
fraud logic. Those arrive in Phase 1, as subclasses.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Iterator

from aegis.generate.config import GenerationConfig
from aegis.shared.contracts import AttackBlueprint, Transaction, TransactionBatch


class BlueprintNotSupportedError(ValueError):
    """Raised when a generator is handed a blueprint it cannot realise."""


class BaseGenerator(ABC):
    """Abstract transaction generator.

    Contract for implementers:

    * Given the same `blueprint` and `config` (same seed), output must be
      byte-identical when `config.deterministic` is True.
    * Every emitted `Transaction` must carry `is_synthetic=True`, the
      originating `blueprint_id`, a `scenario_id`, and `config.split`.
    * Emitted traffic must respect `blueprint.realism_constraints`. Breaking a
      constraint to achieve evasion invalidates the result.
    * Never read detector internals. The only permitted feedback channel is
      `EvasionFeedback` applied to the blueprint by `loop/`.
    """

    #: Implementation name, recorded on every batch.
    name: str = "base"

    #: Implementation version, recorded on every batch.
    version: str = "0.1.0"

    #: Attack families this generator can realise. Empty means "any".
    supported_families: tuple[str, ...] = ()

    @abstractmethod
    def stream(self, blueprint: AttackBlueprint, config: GenerationConfig) -> Iterator[Transaction]:
        """Yield transactions one at a time for the given blueprint and config."""

    def generate(self, blueprint: AttackBlueprint, config: GenerationConfig) -> TransactionBatch:
        """Realise a blueprint into a fully-provenanced `TransactionBatch`.

        Implementations may override this when they can build a batch more
        efficiently than by streaming, but must keep the provenance fields.
        """
        self.validate_blueprint(blueprint)
        transactions = list(self.stream(blueprint, config))
        if config.max_transactions is not None:
            transactions = transactions[: config.max_transactions]

        scenario_ids = sorted(
            {txn.scenario_id for txn in transactions if txn.scenario_id is not None}
        )
        return TransactionBatch(
            batch_id=f"{blueprint.attack_id}-{config.seed}-{uuid.uuid4().hex[:8]}",
            transactions=transactions,
            blueprint_id=blueprint.attack_id,
            attack_family=blueprint.attack_family,
            scenario_ids=scenario_ids,
            generator_name=self.name,
            generator_version=self.version,
            seed=config.seed,
            generation=config.generation,
            split=config.split,
        )

    def validate_blueprint(self, blueprint: AttackBlueprint) -> None:
        """Reject blueprints this generator cannot realise.

        Override to add implementation-specific checks; call `super()` first.
        """
        if self.supported_families and blueprint.attack_family.value not in (
            self.supported_families
        ):
            msg = (
                f"{type(self).__name__} does not support attack family "
                f"{blueprint.attack_family.value!r}"
            )
            raise BlueprintNotSupportedError(msg)


__all__ = ["BaseGenerator", "BlueprintNotSupportedError"]
