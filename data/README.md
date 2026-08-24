# data/

Datasets are **never** committed. Only this README and the `.gitkeep` files are
tracked; see `.gitignore`.

| Folder | Contents |
| --- | --- |
| `raw/` | Untouched downloads exactly as obtained (e.g. PaySim CSV). Read-only by convention. |
| `external/` | Third-party reference data that is not a primary dataset. |
| `interim/` | Intermediate artifacts of a pipeline run. Disposable. |
| `processed/` | Model-ready feature matrices and split assignments. |
| `synthetic/` | Generated attack corpora, one folder per round: `synthetic/round_<n>/`. |

The locked dataset strategy is in [`../docs/DATA_STRATEGY.md`](../docs/DATA_STRATEGY.md).
Read it before adding anything here.
