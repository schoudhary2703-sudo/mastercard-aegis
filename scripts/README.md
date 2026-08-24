# scripts/

Reproducible entry points. Every script must be runnable from the repository
root with no arguments, or with `--help` explaining what it needs.

| Script | Purpose |
| --- | --- |
| `verify_setup.py` | Smoke-check the install, contracts and interfaces. |
| `prepare_paysim.py` | Prepare a local PaySim CSV into canonical split JSONL artifacts. |

Rules:

* Scripts orchestrate; they do not contain logic. Anything worth testing lives
  in `src/aegis/`.
* No script may download a dataset silently. Print the URL and the expected
  destination, and let a human fetch it.
* Any script that produces data must accept and record a `--seed`.
