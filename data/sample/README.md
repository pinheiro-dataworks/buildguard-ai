# Sample Data

A small, deterministic subset (the first 20 projects) of the synthetic
BuildGuard AI portfolio, written by `make data`
(`scripts/generate_data.py` → `src/buildguard/data/synthetic.py`). It is
committed so the data can be inspected without a generation step, and the
integration tests (`tests/integration/`) run the full pipeline against it.

The full 400-project portfolio used for training and evaluation is
regenerated on demand into `data/processed/` (gitignored).
