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
DEFAULT_EARLY_STOPPING_ROUNDS = 30
"""Rounds without `eval_metric` improvement before boosting stops.

Only applies when `fit` is given an `eval_set`; without one the booster runs
the full `num_boost_round` as before."""


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
        early_stopping_rounds: int = DEFAULT_EARLY_STOPPING_ROUNDS,
    ) -> None:
        super().__init__(action_policy)
        self.seed = seed
        self.num_boost_round = num_boost_round
        self.early_stopping_rounds = early_stopping_rounds
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
        """Train the booster.

        `meta` supports two optional keys, both documented on
        `BaseDetector.fit` as legitimate side-channel (never labels in
        disguise):

        * `sample_weight` - per-row weights aligned with `X_train`. Used to
          give promoted hard positives enough gradient mass to matter; see
          `scripts/harden_defender.py`. Multiplies with `scale_pos_weight`
          rather than replacing it.
        * `eval_set` - an `(X_validation, y_validation)` pair enabling
          early stopping on `eval_metric`. Validation labels steer *when
          boosting stops*, exactly as the threshold is tuned on validation;
          test is never involved.
        """
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

        meta = meta or {}
        sample_weight = meta.get("sample_weight")
        weights = None
        if sample_weight is not None:
            weights = np.asarray(sample_weight, dtype=float)
            if len(weights) != len(y):
                msg = (
                    f"sample_weight length {len(weights)} does not match "
                    f"training row count {len(y)}"
                )
                raise ValueError(msg)

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
                X_train,
                label=y,
                weight=weights,
                feature_names=feature_names,
                nthread=params.get("nthread"),
            )
        else:
            dtrain = xgb.DMatrix(X_train, label=y, weight=weights, feature_names=feature_names)

        # Early stopping turns `num_boost_round` from a hand-picked guess into
        # an upper bound: without an `evals` list the `eval_metric` declared in
        # DEFAULT_HYPERPARAMETERS is never actually computed, and the model
        # trains for exactly 300 rounds whether that under- or over-fits. With
        # a validation set the booster stops when `aucpr` stops improving and
        # `best_iteration` is recorded for use at predict time.
        evals: list[tuple[xgb.DMatrix, str]] = []
        eval_set = meta.get("eval_set")
        if eval_set is not None:
            X_eval, y_eval = eval_set
            deval = xgb.DMatrix(
                X_eval[feature_names],
                label=np.asarray(y_eval, dtype=float),
                feature_names=feature_names,
            )
            evals.append((deval, "validation"))

        self._booster = xgb.train(
            params,
            dtrain,
            num_boost_round=self.num_boost_round,
            evals=evals,
            early_stopping_rounds=self.early_stopping_rounds if evals else None,
            verbose_eval=False,
        )
        self._feature_names = list(X_train.columns)
        self._is_fitted = True
        return self

    @property
    def best_iteration(self) -> int | None:
        """Boosting round early stopping settled on, or `None` if it did not run."""
        if self._booster is None:
            return None
        return getattr(self._booster, "best_iteration", None)

    def _predict_range(self) -> tuple[int, int]:
        """Iteration range to score with - the early-stopped best, or all trees.

        XGBoost keeps every tree it built, including the
        `early_stopping_rounds` worth that failed to improve, so scoring
        without this range silently uses the *overfit* tail rather than the
        model early stopping actually selected.
        """
        best = self.best_iteration
        if best is None:
            return (0, 0)  # (0, 0) means "all trees" to XGBoost.
        return (0, int(best) + 1)

    def score(self, X: pd.DataFrame) -> np.ndarray:
        if not self._is_fitted or self._booster is None:
            msg = f"{type(self).__name__}.score called before fit"
            raise NotFittedError(msg)
        # `inplace_predict` on a plain float64 array, not a DMatrix and not a
        # DataFrame. Both of the latter carry fixed per-call overhead that
        # dominates *single-row* scoring - the exact shape of a live
        # authorization decision, where the measured baseline was ~6.7ms mean
        # against a ~10ms end-to-end budget. Measured on a 21-feature,
        # 300-round booster: DMatrix 4.93ms, DataFrame 3.39ms, float64 array
        # 0.86ms. float64 (not float32) because the in-memory training path
        # feeds float64, and a narrowing cast could land a value on the far
        # side of a split threshold; at this width the scores are bit-identical
        # to the DMatrix path, NaN features included (see
        # tests/test_defend_xgboost.py).
        ordered = X[self._feature_names].to_numpy(dtype=np.float64)
        raw = self._booster.inplace_predict(ordered, iteration_range=self._predict_range())
        clipped: np.ndarray = np.clip(np.asarray(raw, dtype=float), 0.0, 1.0)
        return clipped

    # -- explanation ------------------------------------------------------
    def explain(self, X: pd.DataFrame) -> list[list[SignalContribution]]:
        if not self._is_fitted or self._booster is None:
            msg = f"{type(self).__name__}.explain called before fit"
            raise NotFittedError(msg)
        ordered = X[self._feature_names]
        dmatrix = xgb.DMatrix(ordered, feature_names=self._feature_names)
        # shape (n, n_features + 1); last column is the bias term. Same
        # iteration range as `score`, so an explanation always attributes the
        # score the model actually returned.
        contribs = self._booster.predict(
            dmatrix, pred_contribs=True, iteration_range=self._predict_range()
        )

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
            "early_stopping_rounds": self.early_stopping_rounds,
            # Persisted explicitly: `score`/`explain` restrict scoring to
            # `best_iteration`, so a reloaded model that forgot it would
            # silently score with the overfit tail early stopping rejected.
            "best_iteration": self.best_iteration,
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
            early_stopping_rounds=metadata.get(
                "early_stopping_rounds", DEFAULT_EARLY_STOPPING_ROUNDS
            ),
        )
        booster = xgb.Booster()
        booster.load_model(str(src / "model.json"))
        best_iteration = metadata.get("best_iteration")
        if best_iteration is not None:
            booster.best_iteration = int(best_iteration)
        detector._booster = booster
        detector._feature_names = list(metadata["feature_names"])
        detector._resolved_scale_pos_weight = metadata["scale_pos_weight"]
        detector._is_fitted = True
        return detector


__all__ = [
    "DEFAULT_EARLY_STOPPING_ROUNDS",
    "DEFAULT_HYPERPARAMETERS",
    "DEFAULT_NUM_BOOST_ROUND",
    "XGBoostDetector",
]
