"""Service layer.

Intentionally empty at foundation stage. No framework is imported and no server
is started; `fastapi` sits behind the optional `api` extra and is not installed
by default.

When it is built, this layer may only expose contracts from
`aegis.shared.contracts`. It must not re-shape them into bespoke response
models, or the UI and the pipeline will drift apart.
"""

from __future__ import annotations

__all__: list[str] = []
