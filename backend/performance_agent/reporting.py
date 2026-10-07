"""Serialization and console reporting.

Holds everything about *writing results out*: where they go, how they are
encoded, and what the CLI prints. This module was extracted from
``performance_agent.performance_agent`` so that the pipeline itself becomes free
of console output and can be called from a request handler without polluting
stdout.

Nothing here interprets the results. The console report is intentionally a
faithful relocation of the original banners so existing CLI output is
unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: Package directory, used to resolve relative result paths.
BASE_DIR = Path(__file__).resolve().parent


def resolve_results_dir(results_dir: str | Path | None = None) -> Path:
    """Resolve the directory analysis output is written to.

    Returns an absolute path so output does not depend on the process working
    directory.

    Args:
        results_dir: Optional override. Relative paths resolve against the
            performance_agent package directory.

    Returns:
        The results directory path.
    """
    if results_dir is None:
        return BASE_DIR / "results"

    path = Path(results_dir)

    return path if path.is_absolute() else BASE_DIR / path


RESULTS_DIR = resolve_results_dir()
VISUALIZATION_DIR = RESULTS_DIR / "visualizations"


def ensure_results_dirs() -> None:
    """Create the results and visualization output directories.

    Called explicitly rather than at import time so that importing this module
    has no filesystem side effects.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    VISUALIZATION_DIR.mkdir(parents=True, exist_ok=True)


def make_json_safe(obj: Any) -> Any:
    """Recursively convert pandas and datetime values into JSON-safe types.

    NumPy scalars become Python scalars via ``.item()`` and timestamps become
    ISO strings via ``.isoformat()``. Anything unconvertible is returned as-is,
    matching the original behavior of passing unknown objects through.

    Args:
        obj: The value to convert.

    Returns:
        A JSON-serializable equivalent.
    """
    if isinstance(obj, dict):
        return {
            str(key): make_json_safe(value)
            for key, value in obj.items()
        }

    if isinstance(obj, (list, tuple)):
        return [
            make_json_safe(value)
            for value in obj
        ]

    if hasattr(obj, "item"):
        try:
            return make_json_safe(obj.item())
        except Exception:
            pass

    if hasattr(obj, "isoformat"):
        try:
            return obj.isoformat()
        except Exception:
            pass

    return obj


def save_json(data: Any, path: str | Path) -> Path:
    """Write JSON-safe data to a file.

    Args:
        data: The value to serialize.
        path: Destination file path.

    Returns:
        The path written to.
    """
    target = Path(path)

    with open(target, "w", encoding="utf-8") as file:
        json.dump(
            make_json_safe(data),
            file,
            indent=2,
            ensure_ascii=False
        )

    return target


def save_run_summary(
    input_file: str | Path,
    df: Any,
    successful_modules: list[str],
    failed_modules: list[dict[str, str]],
    visualization_count: int,
    insight_count: int,
) -> Path:
    """Write a machine-readable summary of one completed run.

    Args:
        input_file: The dataset that was analyzed.
        df: The prepared DataFrame, used for row and column counts.
        successful_modules: Analyzer modules that completed.
        failed_modules: Analyzer modules that failed, with error text.
        visualization_count: Number of charts written.
        insight_count: Number of insights generated.

    Returns:
        The path the summary was written to.
    """
    summary = {
        "input_file": str(input_file),
        "input_type": Path(input_file).suffix.lower(),
        "rows_processed": int(len(df)),
        "columns_processed": int(len(df.columns)),
        "analysis_modules_completed": len(successful_modules),
        "analysis_modules": successful_modules,
        "failed_modules": failed_modules,
        "visualizations_generated": visualization_count,
        "actionable_insights": insight_count,
        "results_directory": str(RESULTS_DIR),
    }

    return save_json(summary, RESULTS_DIR / "run_summary.json")


def print_dataset_header(input_file: Path, df: Any) -> None:
    """Print the input file banner.

    Args:
        input_file: The dataset being analyzed.
        df: The prepared DataFrame.
    """
    print("\n" + "=" * 70)
    print("PERFORMANCE AGENT")
    print("=" * 70)

    print("\nINPUT")
    print("-" * 70)
    print(f"File : {input_file.name}")
    print(f"Type : {input_file.suffix.lower()}")
    print(f"Rows : {len(df)}")
    print(f"Columns : {len(df.columns)}")


def print_standardization_header(df: Any, standardized_path: Path) -> None:
    """Print the standardization banner.

    Args:
        df: The standardized DataFrame.
        standardized_path: Where the standardized CSV was written.
    """
    print("\nDATA STANDARDIZATION")
    print("-" * 70)
    print(f"Standardized columns : {len(df.columns)}")
    print(f"Saved standardized data: {standardized_path}")


def print_analysis_header() -> None:
    """Print the banner shown before analyzers run."""
    print("\n" + "=" * 70)
    print("RUNNING ANALYSIS MODULES")
    print("=" * 70)


def print_analysis_footer(successful_modules: list[str]) -> None:
    """Print the banner shown after analyzers run.

    Args:
        successful_modules: Modules that completed.
    """
    print(f"\nCompleted {len(successful_modules)} analysis modules.")


def print_analysis_saved(analysis_results_path: Path) -> None:
    """Print where the analysis results were written.

    Args:
        analysis_results_path: The destination file.
    """
    print(f"\nSaved analysis results: {analysis_results_path}")


def print_module_result(module_name: str, error: str | None = None) -> None:
    """Print the per-module status line.

    Args:
        module_name: The module that was attempted.
        error: Failure text when the module was skipped, else None.
    """
    if error is None:
        print(f"[OK] {module_name} analysis completed")
    else:
        print(f"[WARN] {module_name} analysis skipped: {error}")


def print_visualization_header() -> None:
    """Print the banner shown before charts are generated."""
    print("\n" + "=" * 70)
    print("GENERATING VISUALIZATIONS")
    print("=" * 70)


def print_visualization_footer(count: int) -> None:
    """Print the chart count.

    Args:
        count: Number of charts written.
    """
    print(f"\n[OK] Generated {count} visualizations.")


def print_visualization_failure(error: str) -> None:
    """Print a visualization failure notice.

    Args:
        error: The failure text.
    """
    print(f"\n[WARN] Visualization generation failed: {error}")


def print_insight_header() -> None:
    """Print the banner shown before insights are generated."""
    print("\n" + "=" * 70)
    print("GENERATING BUSINESS INSIGHTS")
    print("=" * 70)


def print_insight_footer(count: int, insights_path: Path) -> None:
    """Print the insight count and destination.

    Args:
        count: Number of insights generated.
        insights_path: Where the insights JSON was written.
    """
    print(f"\n[OK] Generated {count} actionable insights.")
    print(f"Saved insights: {insights_path}")


def print_insight_failure(error: str) -> None:
    """Print an insight generation failure notice.

    Args:
        error: The failure text.
    """
    print(f"\n[WARN] Insight generation failed: {error}")


def print_run_report(
    input_file: Path,
    df: Any,
    analysis_results_path: Path,
    successful_modules: list[str],
    failed_modules: list[dict[str, str]],
    visualization_count: int,
    insight_count: int,
    summary_path: Path,
) -> None:
    """Print the closing summary shown at the end of a CLI run.

    Args:
        input_file: The dataset that was analyzed.
        df: The prepared DataFrame.
        analysis_results_path: Where analysis JSON was written.
        successful_modules: Modules that completed.
        failed_modules: Modules that failed, with error text.
        visualization_count: Number of charts written.
        insight_count: Number of insights generated.
        summary_path: Where the run summary was written.
    """
    print("\n" + "=" * 70)
    print("PERFORMANCE AGENT COMPLETE")
    print("=" * 70)

    print(f"\nInput file              : {input_file.name}")
    print(f"Rows processed          : {len(df)}")
    print(f"Analysis modules        : {len(successful_modules)}")
    print(f"Visualizations          : {visualization_count}")
    print(f"Actionable insights     : {insight_count}")

    if failed_modules:
        print("\nModules with warnings:")
        for module in failed_modules:
            print(f"  - {module['module']}: {module['error']}")

    print("\nResults directory:")
    print(RESULTS_DIR)

    print("\nAnalysis results:")
    print(analysis_results_path)

    print("\nRun summary:")
    print(summary_path)

    print("\n" + "=" * 70)