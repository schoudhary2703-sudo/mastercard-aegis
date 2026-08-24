"""Closed-loop orchestration.

IDENTIFY -> GENERATE -> DEFEND -> EVALUATE -> EVOLVE -> RETRAIN.

Intentionally empty of logic at foundation stage. The orchestration algorithm,
the mutation strategy and the retraining schedule are Phase 2 work and must not
be written before both workstreams have working implementations.

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

__all__: list[str] = []
