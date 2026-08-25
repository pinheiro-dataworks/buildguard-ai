# Models

Packaged, versioned model artifacts produced by `scripts/train.py` /
`scripts/package_model.py` land here. Artifacts themselves are gitignored
(see `.gitignore`) — this folder is tracked for its structure and this
README, not for binary contents, keeping the repository small and avoiding
committing anything that isn't reproducible from `make train`.

Each artifact is expected to carry the version metadata described in
Section 25 of `BUILDGUARD_AI_PROJECT_SCOPE.md`: `model_name`,
`semantic_version`, `training_date`, `data_version`, `git_sha`, `metrics`,
`threshold`, `calibration_method`.

Nothing has been trained yet — this folder is currently empty by design.
