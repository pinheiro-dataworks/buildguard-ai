# syntax=docker/dockerfile:1
#
# Section 32: slim base image, non-root runtime, deterministic install,
# no secrets, reasonable size. Not part of the mandatory zero-cost public
# path (Streamlit Community Cloud deploys straight from the repo, no
# Docker involved -- ADR-0013) -- this image is for local/portable use
# and as engineering evidence that the system is genuinely containerizable.
#
# Champion models are trained and calibrated *inside* the build
# (deterministic, fixed seed in configs/base.yaml -- Section 26), so the
# image is fully self-contained and reproducible from source alone,
# never dependent on whatever happens to be in the host's models/
# directory when `docker build` runs.

FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

# Dependencies first, for layer caching -- changes to application code
# below never invalidate this layer.
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
RUN uv sync --frozen --no-dev

# Application code and the config/asset files it reads at runtime.
COPY configs/ configs/
COPY scripts/ scripts/
COPY app/ app/
COPY assets/ assets/
COPY docs/design/ docs/design/
COPY data/sample/ data/sample/
# Already-committed evaluation/monitoring reports (Model Performance and
# Model Health pages read these; they are not regenerated at build time
# -- refreshed by whoever last ran `make evaluate`/`make monitor`).
COPY reports/ reports/

# Train + calibrate the three champions against this exact image's code
# (Section 26 reproducibility) -- not copied in from the host, and never
# stale relative to the code that will serve them.
RUN uv run python scripts/train.py && uv run python scripts/calibrate.py

# Non-root runtime (Section 32) -- ownership fixed after training, which
# necessarily runs as root during the build.
RUN useradd --create-home --shell /usr/sbin/nologin buildguard \
    && chown -R buildguard:buildguard /app
USER buildguard

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD uv run python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

ENTRYPOINT ["uv", "run", "streamlit", "run", "app/Home.py", "--server.address=0.0.0.0", "--server.port=8501"]
