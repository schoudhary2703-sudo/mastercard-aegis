"""Read-only API layer over persisted AEGIS artifacts.

`fastapi`/`uvicorn` sit behind the optional `api` extra
(`pip install -e ".[api]"`) and are only imported by `app.py`; the rest of
this package (`index.py`, `reader.py`, `paths.py`, `service.py`) has no
framework dependency and can be exercised directly in tests.

Layout:

* `paths.py`, `reader.py` -- safe, fault-tolerant filesystem access. Every
  path is validated against `settings.artifacts_root`; missing or malformed
  files degrade to `None` / empty instead of raising.
* `index.py` -- discovers what artifacts currently exist on disk (models,
  confrontations, adaptive rounds, hardening runs) and resolves the lineage
  between them (which confrontation followed which model, etc.) from real
  fields already on those artifacts.
* `dto.py` -- the API's response types. Where an artifact embeds a real
  `aegis.shared.contracts` model (`EvaluationResult`, `AttackBlueprint`,
  `DetectorOutput`) the DTOs mirror that contract's fields exactly. Where the
  artifact is a script-level report with no shared-contract equivalent
  (`confrontation.json`, `adaptive_round.json`, hardening provenance), a
  bespoke DTO is unavoidable -- this is the adapter layer the integration
  brief calls for, kept out of `shared/` so the frozen contracts are
  untouched.
* `service.py` -- assembles DTOs from the index. Computes only plain
  aggregates of numbers already present on an artifact (sums, ratios); it
  never trains, scores, or simulates anything.
* `app.py` -- the FastAPI routes.

This package and `web/` are read-only consumers of what the pipeline has
already produced.
"""

from __future__ import annotations

__all__: list[str] = []
