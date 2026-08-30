.PHONY: setup data train calibrate evaluate monitor test lint format type-check app api package docker-build docker-run clean

UV := uv

setup: ## Create the uv-managed environment (core deps + dev extra)
	$(UV) sync --python 3.11 --extra dev

data: ## Generate the deterministic synthetic demo dataset
	$(UV) run python scripts/generate_data.py

train: ## Train and select the three core champion models
	$(UV) run python scripts/train.py

calibrate: ## Calibrate probabilities, optimize thresholds, quantify uncertainty (requires make train first)
	$(UV) run python scripts/calibrate.py

evaluate: ## Re-run evaluation (metrics, slices, error analysis) for the current champion model
	$(UV) run python scripts/evaluate.py

monitor: ## Run data quality, drift, and performance monitoring (requires make evaluate first)
	$(UV) run python scripts/monitor.py

test: ## Run the full test suite with coverage
	$(UV) run pytest --cov

lint: ## Ruff lint
	$(UV) run ruff check .

format: ## Ruff format check
	$(UV) run ruff format --check .

type-check: ## Mypy static type checking
	$(UV) run mypy src

app: ## Run the Streamlit app locally
	$(UV) run streamlit run app/Home.py

api: ## Run the FastAPI inference service locally
	$(UV) run uvicorn buildguard.api.app:app --reload

package: ## Package trained/calibrated models + manifest for distribution (requires make calibrate first)
	$(UV) run python scripts/package_model.py

docker-build: ## Build the container image (trains + calibrates fresh inside the image)
	docker build -t buildguard-ai:local .

docker-run: ## Run the built container locally on http://localhost:8501
	docker run --rm -p 8501:8501 buildguard-ai:local

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage dist build *.egg-info
