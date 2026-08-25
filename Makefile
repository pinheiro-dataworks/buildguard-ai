.PHONY: setup data train evaluate test lint format type-check app api docker-build clean

UV := uv

setup: ## Create the uv-managed environment (core + dev + ml + api + app extras)
	$(UV) sync --python 3.11 --extra dev --extra ml --extra api --extra app

data: ## Generate the deterministic synthetic demo dataset
	$(UV) run python scripts/generate_data.py

train: ## Train and evaluate the core models
	$(UV) run python scripts/train.py

evaluate: ## Re-run evaluation (metrics, slices, error analysis) for the current champion model
	$(UV) run python scripts/evaluate.py

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

docker-build: ## Build the container image
	docker build -t buildguard-ai:local .

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage dist build *.egg-info
