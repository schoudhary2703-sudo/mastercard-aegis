# web/

Placeholder. The demo UI is **not** part of the foundation and must not be
started before Red Team and Blue Team produce real artifacts.

When it is built:

* It reads `EvaluationResult`, `DetectorOutput` and `EvasionFeedback` JSON
  through `api/`. It must not import `aegis.defend` or `aegis.generate`
  directly, and it must not compute metrics of its own.
* Any number shown on screen must be traceable to an `evaluation_id`.

Framework choice is deferred. Nothing here is installed by default.
