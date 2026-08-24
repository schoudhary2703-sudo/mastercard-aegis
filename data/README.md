# data/

Datasets are **never** committed. Only this README and the `.gitkeep` files are
tracked; see `.gitignore`.

| Folder | Contents |
| --- | --- |
| `raw/` | Untouched downloads exactly as obtained (e.g. PaySim CSV). Read-only by convention. |
| `external/` | Third-party reference data that is not a primary dataset. |
| `interim/` | Intermediate artifacts of a pipeline run. PaySim entity profiles are temporary. |
| `processed/` | Canonical PaySim JSONL splits, manifests, and later model-ready matrices. |
| `synthetic/` | Generated attack corpora, one folder per round: `synthetic/round_<n>/`. |

The locked dataset strategy is in [`../docs/DATA_STRATEGY.md`](../docs/DATA_STRATEGY.md).
Read it before adding anything here.

Prepare a human-supplied PaySim CSV with:

```bash
python scripts/prepare_paysim.py path/to/paysim.csv --seed 20260101
```

See [`../docs/PAYSIM_PREPARATION.md`](../docs/PAYSIM_PREPARATION.md) for the
schema, mapping, leakage policy, and output layout. The command never downloads
or modifies raw data.
