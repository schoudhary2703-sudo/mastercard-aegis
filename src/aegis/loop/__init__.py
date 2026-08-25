"""Closed-loop orchestration.

IDENTIFY -> GENERATE -> DEFEND -> EVALUATE -> EVOLVE -> RETRAIN.

Adaptive evolution v1 mutates only the approved synthetic-identity blueprint
and scores fresh variants against one frozen detector. Defender retraining is
still deliberately absent.

What is already fixed is the data flow, and it is entirely contract-based:

    identify.BaseAttackIdentifier -> AttackBlueprint
    generate.BaseGenerator        -> TransactionBatch
    features.BaseFeatureExtractor -> feature matrix
    defend.BaseDetector           -> DetectorOutput
    evaluate.BaseEvaluator        -> EvaluationResult
    (defend + evaluate)           -> EvasionFeedback
    loop                          -> mutated AttackBlueprint (generation + 1)

`loop/` is the only package permitted to import from both Red Team and Blue
Team packages. Nothing may import from `loop/`.
"""

from __future__ import annotations

from aegis.loop.adaptive import (
    AdaptiveCandidateResult,
    AdaptiveEvolutionError,
    AdaptiveRoundExecution,
    AdaptiveRoundReport,
    BlindSpotAnalysis,
    MutationCandidate,
    ParameterRegionEvidence,
    RoundAttackMetrics,
    RoundComparison,
    analyze_blind_spots,
    build_evasion_feedback,
    calculate_attack_fitness,
    compare_rounds,
    evolve_bustout_round,
    generate_mutation_candidates,
)
from aegis.loop.adaptive_evasion import (
    AdaptiveEvasionLoopError,
    GuidedAdaptation,
    adapt_blueprint_from_evasions,
    build_adaptive_evasion_feedback,
)

__all__ = [
    "AdaptiveCandidateResult",
    "AdaptiveEvasionLoopError",
    "AdaptiveEvolutionError",
    "AdaptiveRoundExecution",
    "AdaptiveRoundReport",
    "BlindSpotAnalysis",
    "GuidedAdaptation",
    "MutationCandidate",
    "ParameterRegionEvidence",
    "RoundAttackMetrics",
    "RoundComparison",
    "adapt_blueprint_from_evasions",
    "analyze_blind_spots",
    "build_adaptive_evasion_feedback",
    "build_evasion_feedback",
    "calculate_attack_fitness",
    "compare_rounds",
    "evolve_bustout_round",
    "generate_mutation_candidates",
]
