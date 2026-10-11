# Contributing to BuildGuard AI

BuildGuard AI is maintained by a single developer and developed in the
open. External contributions are welcome under the same rules the
maintainer follows.

## Workflow

1. **Open an issue first** for anything beyond a trivial fix — describe the
   problem, not just the solution.
2. **Branch naming:** `feat/<name>`, `fix/<name>`, `docs/<name>`, `test/<name>`,
   `ci/<name>`, `chore/<name>`, `refactor/<name>`.
3. **Commits:** English only, [Conventional Commits](https://www.conventionalcommits.org/)
   style (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `ci:`, `perf:`,
   `security:`, `chore:`). Avoid vague messages (`update`, `fix`, `final`).
4. **Pull requests:** describe Problem / Solution / Tests / Risks /
   Evidence. Squash-merge is preferred for cohesive features. Never merge on
   failing CI.
5. **Tests:** new behavior needs tests; run `make test` and `make lint`
   locally before opening a PR.

## Engineering standards

- Python 3.11+, full type hints, docstrings on public APIs.
- No feature logic duplicated between training and inference — shared code
  lives in `src/buildguard/features/`.
- No confidential, proprietary, or personally identifiable data may ever be
  committed. See [`docs/DATA_PRIVACY.md`](docs/DATA_PRIVACY.md).
- Any model predicting risk at time `t` may only use information available
  at or before `t`. See [`docs/LEAKAGE_POLICY.md`](docs/LEAKAGE_POLICY.md).
- Architectural decisions are recorded as ADRs in `docs/adr/`.

## Local setup

```bash
make setup
make test
```

See [How to Run](README.md#13-how-to-run) in the README for the full
reproduction path.
