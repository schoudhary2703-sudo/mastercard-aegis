"""Shared feature engineering.

Consumed primarily by the Blue Team; `feature_names` is readable by the Red
Team so attacks can target detector-visible signals. Temporal and graph
extractors are added here in Phase 1.

This package must not import from `defend/`, `generate/` or `loop/`.
"""

from __future__ import annotations

from aegis.features.base import BaseFeatureExtractor
from aegis.features.io import load_transactions_jsonl
from aegis.features.temporal import TemporalBaselineFeatureExtractor

__all__ = ["BaseFeatureExtractor", "TemporalBaselineFeatureExtractor", "load_transactions_jsonl"]
