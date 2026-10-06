"""Service layer for the Performance Agent.

Dict-in, dict-out facade over the analyzers, the visualization engine, and the
insight engine. Where the CLI entry point orchestrates a full run and writes
four files plus 39 PNGs to disk, this service exposes each capability
separately and keeps analysis entirely in memory.

Nothing here prints. The console reporting lives in
:mod:`performance_agent.reporting`, so this module is safe to call from a
request handler.

Served by the API through background jobs rather than the generic agent
endpoint, because analysis over a real dataset is CPU-bound and long running.
:class:`app.services.job_manager.JobManager` calls this service; the Performance
adapter is a catalog entry only.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from performance_agent.analysis.registry import (
    ANALYZERS,
    OPERATIONS,
    analyzer_names,
    run_analyzers,
)
from performance_agent.analysis.time_analysis import TimeAnalyzer
from performance_agent.dataset import (
    SUPPORTED_EXTENSIONS,
    load_clean_dataset,
)
from performance_agent.reporting import make_json_safe

logger = logging.getLogger(__name__)

#: Operations the service implements, matching the agent's advertised
#: capabilities. Trimming this list is a deliberate API decision, not a
#: side effect of refactoring.
SERVICE_OPERATIONS = OPERATIONS


class PerformanceService:
    """In-memory analytics over a tabular dataset.

    No state is held between calls: each method receives a DataFrame and
    returns a plain dict. Datasets are loaded on demand by
    :meth:`load_dataset` rather than cached, so a caller must not assume two
    calls see the same data if the underlying file changed.
    """

    def __init__(self, settings: Any | None = None) -> None:
        """Initialize the service.

        Args:
            settings: Optional application settings. Accepted for parity with
                the other agent services and reserved for future use; nothing
                in the Performance Agent reads configuration today.
        """
        self._settings = settings

    @property
    def operations(self) -> list[str]:
        """Return the operations this service implements.

        Returns:
            A copy of the operation list.
        """
        return list(SERVICE_OPERATIONS)

    @property
    def analyzers(self) -> list[str]:
        """Return the analyzer module names available to this service.

        Returns:
            The registered module names, in execution order.
        """
        return analyzer_names()

    def load_dataset(self, file_path: str) -> dict[str, Any]:
        """Read a dataset and describe its shape.

        Returns metadata only. Callers pass the returned frame to the other
        methods, which keeps loading explicit and avoids holding a large
        DataFrame in service state.

        Args:
            file_path: Path to a ``.csv``, ``.xlsx``, or ``.xls`` file.

        Returns:
            A dictionary with ``file_path``, ``rows``, ``columns``,
            ``column_names``, and ``supported_extensions``.

        Raises:
            FileNotFoundError: If the path does not exist.
            ValueError: If the extension is not supported.
        """
        df = load_clean_dataset(file_path)

        logger.info(
            "performance_dataset_loaded rows=%d columns=%d",
            len(df),
            len(df.columns),
        )

        return {
            "file_path": str(file_path),
            "rows": int(len(df)),
            "columns": int(len(df.columns)),
            "column_names": [str(column) for column in df.columns],
            "supported_extensions": list(SUPPORTED_EXTENSIONS),
        }

    def compute_kpis(self, df: pd.DataFrame) -> dict[str, Any]:
        """Compute headline KPIs for a dataset.

        Delegates to :class:`CompanyAnalyzer`, which is the only analyzer that
        aggregates the whole frame rather than one dimension.

        Args:
            df: A prepared dataset.

        Returns:
            The ``overall`` and ``targets`` blocks from the company analysis.

        Raises:
            ValueError: If the dataset has no usable sales columns.
        """
        from performance_agent.analysis.company_analysis import CompanyAnalyzer

        result = make_json_safe(
            CompanyAnalyzer(df).analyze()
        )

        return {
            "overall": result.get("overall", {}),
            "targets": result.get("targets", {}),
        }

    def compare_periods(self, df: pd.DataFrame) -> dict[str, Any]:
        """Compare sales and profit across periods.

        Delegates to :class:`TimeAnalyzer`, whose comparable-period logic
        intersects months across consecutive years so partial years stay
        honest. The full time analysis is returned because the comparison is
        expressed through several of its fields rather than one nested block.

        Args:
            df: A prepared dataset containing a ``date`` column.

        Returns:
            The time analysis, whose ``status`` is ``"Success"`` or a reason the
            data was unusable.

        Raises:
            KeyError: If the dataset has no ``date`` column.
        """
        return make_json_safe(
            TimeAnalyzer(df).analyze()
        )

    def analyze(self, df: pd.DataFrame) -> dict[str, Any]:
        """Run every analyzer against a dataset, entirely in memory.

        Performs no disk I/O: no PNGs, no JSON, no summary file. A module that
        raises is recorded in ``failed_modules`` with its raw error text, which
        callers must sanitize before exposing it.

        Args:
            df: A prepared dataset.

        Returns:
            A dictionary with ``analysis`` keyed by module name,
            ``successful_modules``, and ``failed_modules``.
        """
        run = run_analyzers(df)

        logger.info(
            "performance_analysis_complete successful=%d failed=%d",
            len(run.successful),
            len(run.failed),
        )

        return {
            "analysis": run.results,
            "successful_modules": list(run.successful),
            "failed_modules": list(run.failed),
        }

    def generate_visualizations(
        self,
        df: pd.DataFrame,
        output_dir: str | None = None,
    ) -> dict[str, Any]:
        """Render charts to disk.

        This is the one method that writes files, because charts are inherently
        files. The output directory defaults to
        ``performance_agent/results/visualizations``.

        Args:
            df: A prepared dataset.
            output_dir: Optional override for the chart directory.

        Returns:
            A dictionary with ``generated``, ``output_dir``, and
            ``visualizations`` listing the chart filenames.
        """
        from performance_agent.reporting import (
            VISUALIZATION_DIR,
            resolve_results_dir,
        )
        from performance_agent.visualization.visualization_engine import (
            VisualizationEngine,
        )

        if output_dir is None:
            target = VISUALIZATION_DIR
        else:
            target = resolve_results_dir(output_dir) / "visualizations"

        engine = VisualizationEngine(df, target)

        engine.generate_all()

        generated = sorted(
            path.name
            for path in target.glob("*.png")
        )

        logger.info(
            "performance_visualizations_generated count=%d",
            len(generated),
        )

        return {
            "generated": len(generated),
            "output_dir": str(target),
            "visualizations": generated,
        }

    def generate_insights(self, df: pd.DataFrame) -> dict[str, Any]:
        """Generate prioritized business insights, in memory.

        Pure pandas, no LLM and no disk I/O.

        Args:
            df: A prepared dataset.

        Returns:
            The insight payload with ``summary``, ``total_insights``, the five
            priority buckets, and ``all_insights``.
        """
        from performance_agent.insights.insight_engine import InsightEngine

        result = make_json_safe(
            InsightEngine(df).generate()
        )

        logger.info(
            "performance_insights_generated total=%s",
            result.get("total_insights"),
        )

        return result

    def run_full_pipeline(
        self,
        df: pd.DataFrame,
        include_visualizations: bool = False,
        include_insights: bool = True,
    ) -> dict[str, Any]:
        """Run analysis and insights over a dataset in one call.

        A convenience for callers that want most of a full run without the
        disk side effects. Visualizations are off by default because writing
        39 PNGs inside a request handler is not appropriate.

        Args:
            df: A prepared dataset.
            include_visualizations: Whether to also render charts.
            include_insights: Whether to also generate insights.

        Returns:
            A dictionary combining the analysis and insight results.
        """
        payload = self.analyze(df)

        if include_insights:
            payload["insights"] = self.generate_insights(df)

        if include_visualizations:
            payload["visualizations"] = (
                self.generate_visualizations(df)
            )

        return payload


def available_analyzers() -> list[str]:
    """Return the analyzer module names registered with this service.

    Returns:
        The registered module names.
    """
    return [name for name, _ in ANALYZERS]