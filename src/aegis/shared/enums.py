"""Closed vocabularies shared by Red Team and Blue Team.

These enums are contracts. Adding a member is a MINOR contract change; removing
or renaming one is MAJOR. Do not add attack families beyond the three below
without an explicit architecture decision - the project is deliberately scoped.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """String-valued enum that serializes as its value on every Python 3.10+."""

    def __str__(self) -> str:
        return str(self.value)


class AttackFamily(StrEnum):
    """The three in-scope attack families. Do not extend at this stage."""

    SYNTHETIC_IDENTITY_BUSTOUT = "synthetic_identity_bustout"
    """Fabricated or blended identities nurtured into good standing, then
    drained in a coordinated bust-out."""

    MULE_NETWORK_STRUCTURING = "mule_network_structuring"
    """Layered transfers across mule accounts, often structured under reporting
    thresholds, to obscure the origin of funds."""

    ADAPTIVE_DETECTOR_EVASION = "adaptive_detector_evasion"
    """Attacks whose parameters are mutated in response to detector feedback in
    order to stay below the decision threshold."""


class TransactionType(StrEnum):
    """Payment operation type. Values align with the PaySim vocabulary."""

    PAYMENT = "payment"
    TRANSFER = "transfer"
    CASH_IN = "cash_in"
    CASH_OUT = "cash_out"
    DEBIT = "debit"
    REFUND = "refund"


class Channel(StrEnum):
    """Acquisition / initiation channel."""

    CARD_PRESENT = "card_present"
    CARD_NOT_PRESENT = "card_not_present"
    ECOMMERCE = "ecommerce"
    ATM = "atm"
    POS = "pos"
    MOBILE = "mobile"
    ONLINE_BANKING = "online_banking"
    P2P = "p2p"
    WIRE = "wire"
    ACH = "ach"
    UNKNOWN = "unknown"


class FraudLabel(int, Enum):
    """Ground-truth label. `UNKNOWN` means unlabelled, never 'legitimate'."""

    LEGITIMATE = 0
    FRAUD = 1
    UNKNOWN = -1

    def __str__(self) -> str:
        return self.name.lower()


class RecommendedAction(StrEnum):
    """Action the decision policy recommends, ordered by increasing friction."""

    APPROVE = "approve"
    STEP_UP = "step_up"
    REVIEW = "review"
    DECLINE = "decline"


class DataSplit(StrEnum):
    """Which partition a record belongs to. Enforced by the evaluation rules."""

    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"
    HOLDOUT = "holdout"
    UNASSIGNED = "unassigned"


class EvaluationProtocol(StrEnum):
    """How an `EvaluationResult` was produced. Required for interpretation."""

    STATIC_HOLDOUT = "static_holdout"
    """Fixed train/validation/test partition of a single corpus."""

    CLOSED_LOOP_ROUND = "closed_loop_round"
    """Post-retraining evaluation on attacks generated after the retrain."""

    LEAVE_ONE_ATTACK_FAMILY_OUT = "leave_one_attack_family_out"
    """One attack family withheld from training entirely, to measure
    generalization to unseen attacks."""

    STRESS_IMBALANCE = "stress_imbalance"
    """Sanity check under extreme class imbalance."""


class MutationDirection(StrEnum):
    """How the Red Team is advised to move a parameter after feedback."""

    INCREASE = "increase"
    DECREASE = "decrease"
    SET = "set"
    JITTER = "jitter"
    RESAMPLE = "resample"


class ParameterType(StrEnum):
    """Declared type of a tunable blueprint parameter."""

    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    STRING = "string"
    CATEGORICAL = "categorical"
    DURATION_SECONDS = "duration_seconds"


class SignalDirection(StrEnum):
    """Whether a signal pushed the risk score up or down."""

    INCREASES_RISK = "increases_risk"
    DECREASES_RISK = "decreases_risk"
    NEUTRAL = "neutral"


__all__ = [
    "AttackFamily",
    "Channel",
    "DataSplit",
    "EvaluationProtocol",
    "FraudLabel",
    "MutationDirection",
    "ParameterType",
    "RecommendedAction",
    "SignalDirection",
    "StrEnum",
    "TransactionType",
]
