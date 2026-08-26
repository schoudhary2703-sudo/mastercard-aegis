"""GenAI reasoning layer: attack ideation and detector blind-spot analysis.

AEGIS uses a language model for *reasoning*, at exactly two points in the
closed loop, and for nothing else:

1. **Attack Analyst** -- turns researched fraud-taxonomy material into a
   structured, executable attack hypothesis with recommended simulator
   parameters.
2. **Blind-Spot Analyst** -- reads a real detector's real failures and
   proposes bounded next-generation mutations.

Everything numeric between and after those two stages stays deterministic:
seeded simulators (`aegis.generate`) produce the transactions, XGBoost
(`aegis.defend`) scores them, and `aegis.evaluate` computes the metrics. A
language model never emits a transaction row, never fits a model, and never
produces a reported number -- which is what keeps every corpus reproducible
from its seed and every benchmark figure traceable to an artifact.

See `docs/GENAI_LAYER.md`.
"""

from __future__ import annotations

from aegis.genai.analysts import (
    ATTACK_ANALYST_STAGE,
    BLIND_SPOT_ANALYST_STAGE,
    GenAIRunOutcome,
    enforce_mutation_bounds,
    run_attack_analyst,
    run_blind_spot_analyst,
)
from aegis.genai.artifacts import (
    GENAI_ARTIFACTS_DIR,
    build_run_id,
    read_run_artifact,
    write_run_artifact,
)
from aegis.genai.contracts import (
    MAX_MUTATION_MAGNITUDE,
    MAX_MUTATION_PROPOSALS,
    AttackAnalystRequest,
    AttackAnalystResponse,
    BlindSpotAnalystRequest,
    BlindSpotAnalystResponse,
    BoundedMutationProposal,
    GenAIProvenance,
    GenAIRunArtifact,
    SimulatorParameterProposal,
)
from aegis.genai.errors import (
    GenAIConfigurationError,
    GenAIError,
    GenAIProviderError,
    GenAISchemaError,
    MutationBoundsError,
)
from aegis.genai.prompts import PROMPT_VERSION
from aegis.genai.provider import (
    DEFAULT_MODEL,
    AnthropicProvider,
    GenAIProvider,
    ProviderResult,
    RecordedProvider,
    build_provider,
)

__all__ = [
    "ATTACK_ANALYST_STAGE",
    "BLIND_SPOT_ANALYST_STAGE",
    "DEFAULT_MODEL",
    "GENAI_ARTIFACTS_DIR",
    "MAX_MUTATION_MAGNITUDE",
    "MAX_MUTATION_PROPOSALS",
    "PROMPT_VERSION",
    "AnthropicProvider",
    "AttackAnalystRequest",
    "AttackAnalystResponse",
    "BlindSpotAnalystRequest",
    "BlindSpotAnalystResponse",
    "BoundedMutationProposal",
    "GenAIConfigurationError",
    "GenAIError",
    "GenAIProvenance",
    "GenAIProvider",
    "GenAIProviderError",
    "GenAIRunArtifact",
    "GenAIRunOutcome",
    "GenAISchemaError",
    "MutationBoundsError",
    "ProviderResult",
    "RecordedProvider",
    "SimulatorParameterProposal",
    "build_provider",
    "build_run_id",
    "enforce_mutation_bounds",
    "read_run_artifact",
    "run_attack_analyst",
    "run_blind_spot_analyst",
    "write_run_artifact",
]
