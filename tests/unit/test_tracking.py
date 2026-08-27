"""Unit tests for experiment tracking (Section 25)."""

from __future__ import annotations

from pathlib import Path

import joblib
import mlflow
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression

from buildguard.models.baselines import MeanRegressionBaseline
from buildguard.models.tracking import configure_tracking, get_git_sha, log_model_run

pytestmark = pytest.mark.unit


def _configure(tmp_path: Path, experiment_name: str) -> None:
    """Point MLflow at an isolated tracking DB *and* artifact store under
    `tmp_path`, so running this test suite never writes into the repo's
    real `mlruns/` directory.
    """
    db_path = (tmp_path / "mlflow.db").as_posix()
    artifacts_path = (tmp_path / "artifacts").as_posix()
    configure_tracking(
        f"sqlite:///{db_path}",
        experiment_name=experiment_name,
        artifact_location=f"file:///{artifacts_path}",
    )


class TestGetGitSha:
    def test_returns_a_non_empty_string_inside_this_repo(self) -> None:
        sha = get_git_sha()
        assert isinstance(sha, str)
        assert len(sha) > 0

    def test_short_sha_is_shorter_than_full_sha(self) -> None:
        short = get_git_sha(short=True)
        full = get_git_sha(short=False)
        if short != "unknown" and full != "unknown":
            assert len(short) < len(full)


class TestConfigureAndLogRun:
    def test_log_model_run_records_params_metrics_and_git_sha_tag(self, tmp_path: Path) -> None:
        _configure(tmp_path, "test-experiment-1")
        run_id = log_model_run(
            run_name="unit-test-run",
            params={"n_estimators": 100, "family": "random_forest"},
            metrics={"cv_auc": 0.87},
        )
        run = mlflow.get_run(run_id)
        assert run.data.params["n_estimators"] == "100"
        assert run.data.metrics["cv_auc"] == pytest.approx(0.87)
        assert "git_sha" in run.data.tags

    def test_custom_tags_are_preserved_alongside_git_sha(self, tmp_path: Path) -> None:
        _configure(tmp_path, "test-experiment-2")
        run_id = log_model_run(
            run_name="tagged-run",
            params={},
            metrics={"mae": 100.0},
            tags={"task": "cost_overrun", "model_family": "lightgbm"},
        )
        run = mlflow.get_run(run_id)
        assert run.data.tags["task"] == "cost_overrun"
        assert run.data.tags["model_family"] == "lightgbm"
        assert "git_sha" in run.data.tags

    def test_model_artifact_is_logged_when_provided(self, tmp_path: Path) -> None:
        _configure(tmp_path, "test-experiment-3")
        model = LinearRegression().fit([[1], [2], [3]], [1, 2, 3])
        model_path = tmp_path / "champion.joblib"
        joblib.dump(model, model_path)

        run_id = log_model_run(
            run_name="run-with-model",
            params={},
            metrics={"mae": 0.0},
            model_path=model_path,
        )
        artifacts = mlflow.artifacts.list_artifacts(run_id=run_id)
        assert any(a.path == "champion.joblib" for a in artifacts)

    def test_model_artifact_survives_being_a_custom_baseline_wrapper(self, tmp_path: Path) -> None:
        """Regression guard: `mlflow.sklearn.log_model`'s default skops
        serializer refuses BuildGuard's own baseline wrapper classes
        (`UntrustedTypesFoundException`, hit while building this module).
        `log_model_run` must work uniformly for those too, since a
        baseline can legitimately be the champion.
        """
        _configure(tmp_path, "test-experiment-3b")
        model = MeanRegressionBaseline().fit(
            pd.DataFrame({"x": [1, 2, 3]}), pd.Series([1.0, 2.0, 3.0])
        )
        model_path = tmp_path / "baseline_champion.joblib"
        joblib.dump(model, model_path)

        run_id = log_model_run(
            run_name="run-with-baseline-model",
            params={},
            metrics={"mae": 0.0},
            model_path=model_path,
        )
        artifacts = mlflow.artifacts.list_artifacts(run_id=run_id)
        assert any(a.path == "baseline_champion.joblib" for a in artifacts)

    def test_no_model_logged_when_model_path_argument_omitted(self, tmp_path: Path) -> None:
        _configure(tmp_path, "test-experiment-4")
        run_id = log_model_run(run_name="no-model-run", params={}, metrics={"x": 1.0})
        artifacts = mlflow.artifacts.list_artifacts(run_id=run_id)
        assert len(artifacts) == 0

    def test_two_runs_in_the_same_experiment_get_distinct_ids(self, tmp_path: Path) -> None:
        _configure(tmp_path, "test-experiment-5")
        first = log_model_run(run_name="a", params={}, metrics={"x": 1.0})
        second = log_model_run(run_name="b", params={}, metrics={"x": 2.0})
        assert first != second

    def test_configure_tracking_is_idempotent_for_an_existing_experiment(
        self, tmp_path: Path
    ) -> None:
        _configure(tmp_path, "test-experiment-6")
        _configure(tmp_path, "test-experiment-6")  # must not raise on second call
        run_id = log_model_run(run_name="c", params={}, metrics={"x": 1.0})
        assert mlflow.get_run(run_id) is not None
