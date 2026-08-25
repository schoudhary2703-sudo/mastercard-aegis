"""`XGBoostDetector` - the first real Blue Team baseline detector.

Uses XGBoost's low-level `Booster` API directly (not the sklearn-compatible
wrapper), which keeps the dependency footprint to `xgboost` alone - no
`scikit-learn` needed for training, scoring, or explanation. Class imbalance
is handled via `scale_pos_weight`; explanation uses the booster's native
Shapley-value contributions (`pred_contribs=True`), which are exact, not an
approximation, and require no extra library.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import xgboost as xgb

from aegis.defend.base import BaseDetector, NotFittedError
from aegis.defend.policy import ActionPolicy
from aegis.shared.contracts import SignalContribution
from aegis.shared.enums import SignalDirection
from aegis.shared.version import CONTRACT_VERSION

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

DEFAULT_HYPERPARAMETERS: dict[str, Any] = {
    "max_depth": 5,
    "eta": 0.05,
    "objective": "binary:logistic",
    "eval_metric": "aucpr",
    "tree_method": "hist",
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 2,
}
DEFAULT_NUM_BOOST_ROUND = 300


class XGBoostDetector(BaseDetector):
    """Gradient-boosted-tree fraud detector, trained via `xgb.train`."""

    name = "xgboost-baseline"

    def __init__(
        self,
        action_policy: ActionPolicy | None = None,
        *,
        seed: int = 20260101,
        num_boost_round: int = DEFAULT_NUM_BOOST_ROUND,
        hyperparameters: dict[str, Any] | None = None,
        scale_pos_weight: float | None = None,
        model_version: str | None = None,
    ) -> None:
        super().__init__(action_policy)
        self.seed = seed
        self.num_boost_round = num_boost_round
        self.hyperparameters = (
            dict(hyperparameters) if hyperparameters else dict(DEFAULT_HYPERPARAMETERS)
        )
        self._configured_scale_pos_weight = scale_pos_weight
        self.model_version = model_version or f"xgboost-baseline-{seed}"
        self._booster: xgb.Booster | None = None
        self._resolved_scale_pos_weight: float | None = None

    @property
    def scale_pos_weight(self) -> float | None:
        """The `scale_pos_weight` actually used in the last `fit` call."""
        return self._resolved_scale_pos_weight

    # -- required -------------------------------------------------------
    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series | np.ndarray,
        meta: dict[str, Any] | None = None,
    ) -> XGBoostDetector:
        y = np.asarray(y_train, dtype=float)
        spw = self._configured_scale_pos_weight
        if spw is None:
            n_pos = float(y.sum())
            n_neg = float(len(y) - n_pos)
            spw = n_neg / n_pos if n_pos > 0 else 1.0
        self._resolved_scale_pos_weight = spw

        params = dict(self.hyperparameters)
        params["scale_pos_weight"] = spw
        params["seed"] = self.seed

        feature_names = list(X_train.columns)
        # QuantileDMatrix builds the hist tree method's quantile sketch
        # directly from the input, skipping the intermediate CSR/dense copy a
        # plain DMatrix makes for that method - materially lower peak memory
        # for large splits, mathematically equivalent for `tree_method`
        # `hist`/`gpu_hist` (see tests/test_defend_xgboost.py). Falls back to
        # a plain DMatrix for any other tree method, where QuantileDMatrix
        # is not applicable.
        if params.get("tree_method") in ("hist", "gpu_hist"):
            dtrain: xgb.DMatrix = xgb.QuantileDMatrix(
                X_train, label=y, feature_names=feature_names, nthread=params.get("nthread")
            )
        else:
            dtrain = xgb.DMatrix(X_train, label=y, feature_names=feature_names)
        self._booster = xgb.train(params, dtrain, num_boost_round=self.num_boost_round)
        self._feature_names = list(X_train.columns)
        self._is_fitted = True
        return self

    def score(self, X: pd.DataFrame) -> np.ndarray:
        if not self._is_fitted or self._booster is None:
            msg = f"{type(self).__name__}.score called before fit"
            raise NotFittedError(msg)
        ordered = X[self._feature_names]
        dmatrix = xgb.DMatrix(ordered, feature_names=self._feature_names)
        raw = self._booster.predict(dmatrix)
        clipped: np.ndarray = np.clip(np.asarray(raw, dtype=float), 0.0, 1.0)
        return clipped

    # -- explanation ------------------------------------------------------
    def explain(self, X: pd.DataFrame) -> list[list[SignalContribution]]:
        if not self._is_fitted or self._booster is None:
            msg = f"{type(self).__name__}.explain called before fit"
            raise NotFittedError(msg)
        ordered = X[self._feature_names]
        dmatrix = xgb.DMatrix(ordered, feature_names=self._feature_names)
        # shape (n, n_features + 1); last column is the bias term.
        contribs = self._booster.predict(dmatrix, pred_contribs=True)

        results: list[list[SignalContribution]] = []
        values = ordered.to_numpy()
        for row_idx in range(contribs.shape[0]):
            per_feature = contribs[row_idx, :-1]
            order = np.argsort(-np.abs(per_feature))
            row_signals: list[SignalContribution] = []
            for rank, feature_idx in enumerate(order):
                contribution = float(per_feature[feature_idx])
                if contribution > 0:
                    direction = SignalDirection.INCREASES_RISK
                elif contribution < 0:
                    direction = SignalDirection.DECREASES_RISK
                else:
                    direction = SignalDirection.NEUTRAL
                row_signals.append(
                    SignalContribution(
                        name=self._feature_names[feature_idx],
                        contribution=contribution,
                        value=float(values[row_idx, feature_idx]),
                        direction=direction,
                        rank=rank,
                    )
                )
            results.append(row_signals)
        return results

    # -- persistence ------------------------------------------------------
    def save(self, path: str) -> None:
        if not self._is_fitted or self._booster is None:
            msg = f"{type(self).__name__}.save called before fit"
            raise NotFittedError(msg)
        out = Path(path)
        out.mkdir(parents=True, exist_ok=True)
        self._booster.save_model(str(out / "model.json"))
        metadata = {
            "contract_version": CONTRACT_VERSION,
            "detector_name": self.name,
            "model_version": self.model_version,
            "seed": self.seed,
            "num_boost_round": self.num_boost_round,
            "hyperparameters": self.hyperparameters,
            "scale_pos_weight": self._resolved_scale_pos_weight,
            "feature_names": self._feature_names,
            "action_policy": self.action_policy.model_dump(mode="json"),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        (out / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: str) -> XGBoostDetector:
        src = Path(path)
        metadata = json.loads((src / "metadata.json").read_text(encoding="utf-8"))
        policy = ActionPolicy.model_validate(metadata["action_policy"])
        detector = cls(
            action_policy=policy,
            seed=metadata["seed"],
            num_boost_round=metadata["num_boost_round"],
            hyperparameters=metadata["hyperparameters"],
            scale_pos_weight=metadata["scale_pos_weight"],
            model_version=metadata["model_version"],
        )
        booster = xgb.Booster()
        booster.load_model(str(src / "model.json"))
        detector._booster = booster
        detector._feature_names = list(metadata["feature_names"])
        detector._resolved_scale_pos_weight = metadata["scale_pos_weight"]
        detector._is_fitted = True
        return detector


__all__ = ["DEFAULT_HYPERPARAMETERS", "DEFAULT_NUM_BOOST_ROUND", "XGBoostDetector"]
