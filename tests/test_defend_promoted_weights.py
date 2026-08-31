"""Weighting that gives promoted hard positives enough gradient mass to matter.

Promotion added 6-22 fraud rows, unweighted, to a split holding thousands of
positives -- below the noise floor of retraining, which is why two hardening
rounds moved metrics by variance rather than learning.
`promoted_sample_weights` solves for the weight that gives those rows a target
*share* of positive gradient mass, so the fix holds as the loop scales from 22
promoted rows to 2,200.

The function is positionally coupled to the feature materializer: it trusts
that promoted rows are the last `promoted_row_count` entries. These tests pin
both the arithmetic and the guard that turns a violated coupling into a loud
failure instead of a silent return to unweighted training.
"""

from __future__ import annotations

import numpy as np
import pytest

from aegis.defend.hard_positives import (
    HardPositiveValidationError,
    promoted_sample_weights,
)

SHARE = 0.05


def _labels(base_positives: int, base_negatives: int, promoted: list[int]) -> np.ndarray:
    """Base split (positives then negatives) with `promoted` appended last."""
    base = [1] * base_positives + [0] * base_negatives
    return np.array(base + promoted, dtype=float)


# -- the solved weight ------------------------------------------------------
def test_promoted_positives_reach_the_target_share_of_positive_mass():
    """w * H / (P + w * H) == share, which is the whole point of the formula."""
    y = _labels(base_positives=1000, base_negatives=5000, promoted=[1] * 20)
    weights = promoted_sample_weights(y, 20, positive_mass_share=SHARE)

    promoted_mass = float(weights[-20:].sum())
    base_mass = float(weights[:-20][y[:-20] == 1].sum())
    assert promoted_mass / (base_mass + promoted_mass) == pytest.approx(SHARE)


def test_solved_weight_matches_the_closed_form():
    y = _labels(base_positives=1000, base_negatives=5000, promoted=[1] * 20)
    weights = promoted_sample_weights(y, 20, positive_mass_share=SHARE)
    expected = (SHARE * 1000) / (20 * (1 - SHARE))
    assert weights[-1] == pytest.approx(expected)


@pytest.mark.parametrize("promoted_count", [22, 100, 200])
def test_share_holds_as_the_promotion_scales(promoted_count: int):
    """A share, not a fixed multiplier -- it holds while the solved weight is > 1.

    With 4,000 base positives at a 5% target the crossover sits at
    200 / 0.95 ~= 211 promoted rows; below it the solved weight does the work.
    """
    y = _labels(base_positives=4000, base_negatives=20000, promoted=[1] * promoted_count)
    weights = promoted_sample_weights(y, promoted_count, positive_mass_share=SHARE)
    promoted_mass = float(weights[-promoted_count:].sum())
    base_mass = float(weights[:-promoted_count][y[:-promoted_count] == 1].sum())
    assert promoted_mass / (base_mass + promoted_mass) == pytest.approx(SHARE)


@pytest.mark.parametrize("promoted_count", [220, 2200])
def test_past_the_crossover_the_clamp_floors_the_share_above_target(promoted_count: int):
    """Once a promotion is big enough to exceed the target on its own, the
    solved weight drops below 1 and the clamp holds every row at 1.0. The
    realized share then *exceeds* the target -- correct, because the share is
    documented as a floor on influence, not a cap.
    """
    y = _labels(base_positives=4000, base_negatives=20000, promoted=[1] * promoted_count)
    weights = promoted_sample_weights(y, promoted_count, positive_mass_share=SHARE)
    assert np.all(weights[-promoted_count:] == 1.0)

    promoted_mass = float(weights[-promoted_count:].sum())
    base_mass = float(weights[:-promoted_count][y[:-promoted_count] == 1].sum())
    assert promoted_mass / (base_mass + promoted_mass) > SHARE


def test_base_negatives_and_untouched_rows_stay_at_one():
    y = _labels(base_positives=100, base_negatives=500, promoted=[1] * 10)
    weights = promoted_sample_weights(y, 10, positive_mass_share=SHARE)
    assert np.all(weights[:600] == 1.0)


# -- only fraud rows in the tail are up-weighted ----------------------------
def test_promoted_legitimate_warmup_rows_are_not_up_weighted():
    """A promoted scenario carries legit warm-up rows for realistic history.

    They are ordinary negatives -- up-weighting them would tell the model that
    normal behaviour is unusually important.
    """
    # tail: 3 fraud, 5 legitimate warm-up
    y = _labels(base_positives=500, base_negatives=2000, promoted=[1, 1, 1, 0, 0, 0, 0, 0])
    weights = promoted_sample_weights(y, 8, positive_mass_share=SHARE)

    tail = weights[-8:]
    assert np.all(tail[:3] > 1.0)
    assert np.all(tail[3:] == 1.0)


def test_share_is_computed_from_fraud_rows_only_not_the_whole_tail():
    """Warm-up rows must not dilute the solved weight."""
    y = _labels(base_positives=500, base_negatives=2000, promoted=[1, 1, 0, 0, 0, 0])
    weights = promoted_sample_weights(y, 6, positive_mass_share=SHARE)
    expected = (SHARE * 500) / (2 * (1 - SHARE))  # H = 2 fraud rows, not 6
    assert weights[-6] == pytest.approx(expected)


# -- the clamp --------------------------------------------------------------
def test_weight_is_clamped_at_one_so_promotion_never_demotes():
    """A promotion already past the target share must not be scaled *down*.

    The share is a floor on influence, not a cap: with 500 promoted rows
    against 100 base positives the solved weight is ~0.026, which would make
    each promoted row 40x less important than an ordinary one.
    """
    y = _labels(base_positives=100, base_negatives=1000, promoted=[1] * 500)
    weights = promoted_sample_weights(y, 500, positive_mass_share=SHARE)
    assert np.all(weights[-500:] == 1.0)
    assert np.all(weights >= 1.0)


# -- the positional coupling, and its guard ---------------------------------
def test_raises_when_the_tail_holds_no_fraud_rows():
    """The silent-failure guard.

    `promote_hard_positives` rejects a scenario with no fraud, so an all-negative
    tail means the rows are not where this function was told they are. Returning
    all-ones there would quietly restore the unweighted behaviour that made two
    hardening rounds no-ops -- so it raises instead.
    """
    y = _labels(base_positives=500, base_negatives=2000, promoted=[0] * 10)
    with pytest.raises(HardPositiveValidationError, match="promoted rows must be appended last"):
        promoted_sample_weights(y, 10, positive_mass_share=SHARE)


def test_raises_when_promoted_rows_were_prepended_instead_of_appended():
    """Concretely: the materializer changes to prepend, nothing else changes."""
    y = np.array([1.0] * 5 + [1.0] * 200 + [0.0] * 1000)  # promoted at the FRONT
    with pytest.raises(HardPositiveValidationError):
        promoted_sample_weights(y, 5, positive_mass_share=SHARE)


def test_raises_when_promoted_row_count_exceeds_the_split():
    y = _labels(base_positives=10, base_negatives=10, promoted=[1] * 5)
    with pytest.raises(HardPositiveValidationError, match="exceeds training row count"):
        promoted_sample_weights(y, 999, positive_mass_share=SHARE)


@pytest.mark.parametrize("share", [-0.1, 1.0, 1.5])
def test_rejects_a_share_outside_the_unit_interval(share: float):
    y = _labels(base_positives=100, base_negatives=500, promoted=[1] * 5)
    with pytest.raises(HardPositiveValidationError, match="positive_mass_share"):
        promoted_sample_weights(y, 5, positive_mass_share=share)


# -- legitimately unweightable, not wrong -----------------------------------
def test_nothing_promoted_returns_all_ones():
    """Callers need no special-casing for a plain baseline run."""
    y = _labels(base_positives=100, base_negatives=500, promoted=[])
    assert np.all(promoted_sample_weights(y, 0, positive_mass_share=SHARE) == 1.0)


def test_zero_share_opts_out_without_raising():
    y = _labels(base_positives=100, base_negatives=500, promoted=[1] * 5)
    assert np.all(promoted_sample_weights(y, 5, positive_mass_share=0.0) == 1.0)


def test_no_base_positives_is_unweightable_rather_than_an_error():
    """No positive mass to take a share of -- degenerate, but not a coupling bug."""
    y = _labels(base_positives=0, base_negatives=500, promoted=[1] * 5)
    assert np.all(promoted_sample_weights(y, 5, positive_mass_share=SHARE) == 1.0)


def test_empty_training_split_returns_empty_weights():
    weights = promoted_sample_weights(np.array([], dtype=float), 0, positive_mass_share=SHARE)
    assert weights.shape == (0,)


def test_returns_one_weight_per_training_row():
    y = _labels(base_positives=100, base_negatives=500, promoted=[1] * 5)
    assert promoted_sample_weights(y, 5, positive_mass_share=SHARE).shape == y.shape
