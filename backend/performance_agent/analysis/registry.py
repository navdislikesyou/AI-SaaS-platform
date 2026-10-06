"""Analyzer registry and execution.

Holds the table of available analyzers and the loop that runs them. Both were
previously inlined in ``performance_agent.performance_agent``, which mixed
orchestration with file writing and console output.

The per-module error handling here is preserved exactly as it was: any analyzer
that raises is recorded in ``failed`` with the raw ``str(error)`` and the run
continues. Callers must sanitize that text before returning it to a client.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from performance_agent.analysis.channel_analysis import ChannelAnalyzer
from performance_agent.analysis.company_analysis import CompanyAnalyzer
from performance_agent.analysis.customer_analysis import CustomerAnalyzer
from performance_agent.analysis.department_analysis import DepartmentAnalyzer
from performance_agent.analysis.employee_analysis import EmployeeAnalyzer
from performance_agent.analysis.product_analysis import ProductAnalyzer
from performance_agent.analysis.regional_analysis import RegionalAnalyzer
from performance_agent.analysis.target_analysis import TargetAnalyzer
from performance_agent.analysis.time_analysis import TimeAnalyzer
from performance_agent.reporting import make_json_safe

logger = logging.getLogger(__name__)

#: Operations the agent advertises. Mirrored by the service layer so the two
#: can be compared, but declared here to keep the operation list beside the
#: analyzer table it describes.
OPERATIONS = (
    "load_dataset",
    "compute_kpis",
    "compare_periods",
    "analyze",
    "visualize",
)

#: Analyzers run for every dataset, in execution order. Import order is
#: preserved from the original module so behavior is unchanged.
ANALYZERS: tuple[tuple[str, type], ...] = (
    ("company", CompanyAnalyzer),
    ("employee", EmployeeAnalyzer),
    ("department", DepartmentAnalyzer),
    ("product", ProductAnalyzer),
    ("regional", RegionalAnalyzer),
    ("customer", CustomerAnalyzer),
    ("channel", ChannelAnalyzer),
    ("time", TimeAnalyzer),
    ("target", TargetAnalyzer),
)


@dataclass
class AnalyzerRun:
    """Outcome of running every analyzer against one dataset.

    Attributes:
        results: Per-module results keyed by module name. Absent for modules
            that failed.
        successful: Names of modules that completed, in execution order.
        failed: Modules that raised, each with the raw error text.
    """

    results: dict[str, Any] = field(default_factory=dict)
    successful: list[str] = field(default_factory=list)
    failed: list[dict[str, str]] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        """Report whether every analyzer completed.

        Returns:
            True when no module failed.
        """
        return not self.failed


def analyzer_names() -> list[str]:
    """Return the analyzer module names in execution order.

    Returns:
        The registered module names.
    """
    return [name for name, _ in ANALYZERS]


def run_analyzers(
    df: pd.DataFrame,
    on_start: Callable[[str], None] | None = None,
    on_complete: Callable[[str, str | None], None] | None = None,
) -> AnalyzerRun:
    """Run every registered analyzer against a dataset.

    Each analyzer is constructed with the frame and its ``analyze()`` result is
    JSON-safe converted. A failing analyzer never stops the others: the failure
    is recorded and the run continues, which is how the original pipeline
    behaved.

    The callbacks exist so the CLI can report progress in the original order.
    Analyzer execution is synchronous, so ``on_start`` fires immediately before
    each module runs and ``on_complete`` immediately after it finishes.

    Args:
        df: The prepared dataset.
        on_start: Called with each module name before it runs.
        on_complete: Called with each module name and its error text, or None
            when the module succeeded.

    Returns:
        The combined outcome of every analyzer.
    """
    run = AnalyzerRun()

    for module_name, analyzer_class in ANALYZERS:

        if on_start is not None:
            on_start(module_name)

        try:
            analyzer = analyzer_class(df)

            run.results[module_name] = make_json_safe(
                analyzer.analyze()
            )

            run.successful.append(module_name)

            logger.info(
                "analyzer_ok module=%s",
                module_name,
            )

            error = None

        except Exception as exc:
            error = str(exc)

            run.failed.append(
                {
                    "module": module_name,
                    "error": error,
                }
            )

            logger.warning(
                "analyzer_skipped module=%s",
                module_name,
            )

        if on_complete is not None:
            on_complete(module_name, error)

    return run