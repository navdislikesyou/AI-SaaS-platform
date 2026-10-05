"""Performance Agent entry point.

This module is the command-line interface and the full-run pipeline. It
delegates every step to the focused modules:

    dataset loading   performance_agent.dataset
    analyzer execution performance_agent.analysis.registry
    serialization      performance_agent.reporting
    disk and console   performance_agent.reporting
    in-memory analytics performance_agent.service

``run_performance_agent`` keeps its original signature and six-key return
value. Console output is unchanged from the pre-refactor implementation.

Run directly:

    python performance_agent/performance_agent.py data/Financials.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from performance_agent.analysis.registry import run_analyzers
from performance_agent.dataset import (
    load_clean_dataset,
    load_dataset,
    standardize_dataframe,
)
from performance_agent.reporting import (
    RESULTS_DIR,
    VISUALIZATION_DIR,
    ensure_results_dirs,
    make_json_safe,
    print_analysis_footer,
    print_analysis_header,
    print_analysis_saved,
    print_dataset_header,
    print_insight_failure,
    print_insight_footer,
    print_insight_header,
    print_module_result,
    print_run_report,
    print_standardization_header,
    print_visualization_failure,
    print_visualization_footer,
    print_visualization_header,
    resolve_results_dir,
    save_json,
    save_run_summary,
)

__all__ = [
    "ANALYZERS",
    "RESULTS_DIR",
    "VISUALIZATION_DIR",
    "ensure_results_dirs",
    "generate_insights",
    "generate_visualizations",
    "load_dataset",
    "make_json_safe",
    "resolve_results_dir",
    "run_analysis_modules",
    "run_performance_agent",
    "save_json",
    "save_run_summary",
    "standardize_dataframe",
]

#: Analyzer table, re-exported for backwards compatibility. The definition now
#: lives in performance_agent.analysis.registry.
from performance_agent.analysis.registry import ANALYZERS  # noqa: E402


def run_analysis_modules(df: pd.DataFrame) -> tuple[dict, list[str], list[dict]]:
    """Run every analyzer against a dataset, printing progress.

    Retained for backwards compatibility with existing callers and check
    scripts. Prefer :func:`performance_agent.analysis.registry.run_analyzers`,
    which does not print.

    Error handling is unchanged: a failing analyzer is recorded with its raw
    ``str(error)`` and the run continues.

    Args:
        df: The prepared dataset.

    Returns:
        A ``(results, successful_modules, failed_modules)`` tuple.
    """
    print_analysis_header()

    def announce(module_name: str) -> None:
        print(f"\nRunning {module_name} analysis...")

    run = run_analyzers(
        df,
        on_start=announce,
        on_complete=print_module_result,
    )

    print_analysis_footer(run.successful)

    return (
        run.results,
        list(run.successful),
        list(run.failed),
    )


def _save_analysis_results(
    analysis_results: dict,
) -> Path:
    """Write the analysis results JSON and report where it went.

    Args:
        analysis_results: The combined analyzer output.

    Returns:
        The path the results were written to.
    """
    analysis_results_path = RESULTS_DIR / "analysis_results.json"

    save_json(analysis_results, analysis_results_path)

    print_analysis_saved(analysis_results_path)

    return analysis_results_path


def generate_visualizations(df: pd.DataFrame) -> int:
    """Render charts to disk and report how many were written.

    Args:
        df: The prepared dataset.

    Returns:
        The number of PNG files written, or 0 when generation failed.
    """
    print_visualization_header()

    try:
        from performance_agent.visualization.visualization_engine import (
            VisualizationEngine
        )

        engine = VisualizationEngine(df, VISUALIZATION_DIR)

        engine.generate_all()

        count = len(
            list(VISUALIZATION_DIR.glob("*.png"))
        )

        print_visualization_footer(count)

        return count

    except Exception as error:
        print_visualization_failure(str(error))

        return 0


def generate_insights(df: pd.DataFrame) -> tuple[dict, int]:
    """Generate business insights, write them to disk, and count them.

    Args:
        df: The prepared dataset.

    Returns:
        An ``(insights, count)`` tuple. On failure the insights are empty and
        the count is zero.
    """
    print_insight_header()

    try:
        from performance_agent.insights.insight_engine import InsightEngine

        engine = InsightEngine(df)

        result = make_json_safe(engine.generate())

        insights_path = RESULTS_DIR / "insights.json"

        save_json(result, insights_path)

        if isinstance(result, dict):
            if "all_insights" in result:
                count = len(result["all_insights"])
            elif "insights" in result:
                count = len(result["insights"])
            elif "total_insights" in result:
                count = int(result["total_insights"])
            else:
                count = 0
        elif isinstance(result, list):
            count = len(result)
        else:
            count = 0

        print_insight_footer(count, insights_path)

        return result, count

    except Exception as error:
        print_insight_failure(str(error))

        return {}, 0


def run_performance_agent(input_file: str | Path) -> dict:
    """Run the complete pipeline over a dataset file.

    Loads the file, standardizes it, runs every analyzer, writes the analysis
    results, renders charts, generates insights, and writes a run summary.

    Disk output is written to ``performance_agent/results/``. Callers that
    need analysis without side effects should use
    :meth:`performance_agent.service.PerformanceService.analyze` instead.

    A module that fails is recorded in ``failed_modules`` with its raw error
    text; the run continues.

    Args:
        input_file: Path to a ``.csv``, ``.xlsx``, or ``.xls`` file.

    Returns:
        A dictionary with ``analysis``, ``insights``, ``successful_modules``,
        ``failed_modules``, ``visualization_count``, and ``insight_count``.
    """
    path = Path(input_file)

    ensure_results_dirs()

    df = load_clean_dataset(path)

    print_dataset_header(path, df)

    standardized_path = RESULTS_DIR / "standardized_data.csv"

    df.to_csv(standardized_path, index=False)

    print_standardization_header(df, standardized_path)

    (
        analysis_results,
        successful_modules,
        failed_modules,
    ) = run_analysis_modules(df)

    analysis_results_path = _save_analysis_results(
        analysis_results
    )

    visualization_count = generate_visualizations(df)

    insights, insight_count = generate_insights(df)

    summary_path = save_run_summary(
        path,
        df,
        successful_modules,
        failed_modules,
        visualization_count,
        insight_count,
    )

    print_run_report(
        path,
        df,
        analysis_results_path,
        successful_modules,
        failed_modules,
        visualization_count,
        insight_count,
        summary_path,
    )

    return {
        "analysis": analysis_results,
        "insights": insights,
        "successful_modules": successful_modules,
        "failed_modules": failed_modules,
        "visualization_count": visualization_count,
        "insight_count": insight_count,
    }


def main() -> int:
    """Run the pipeline from the command line.

    Returns:
        The process exit code: 0 on success, 1 on a usage error or a failure.
    """
    if len(sys.argv) < 2:
        print("\nUsage:")
        print(
            "python performance_agent.py "
            "<csv_or_excel_file>"
        )

        print("\nExample:")
        print(
            "python performance_agent.py "
            "data\\Financials_standardized.csv"
        )

        print("\nExcel example:")
        print(
            "python performance_agent.py "
            "data\\Financials.xlsx"
        )

        return 1

    try:
        run_performance_agent(sys.argv[1])

    except Exception as error:
        print("\n" + "=" * 70)
        print("PERFORMANCE AGENT FAILED")
        print("=" * 70)

        print(f"\nError: {error}")

        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())