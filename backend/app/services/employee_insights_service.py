"""Service provider for the Employee Insights agent.

Creates and caches a single :class:`EmployeeInsightsService` instance per
process. The RoBERTa model is loaded lazily by the service on first use, so
creating the provider is cheap and never blocks startup.
"""

from __future__ import annotations

from employee_insights.service import EmployeeInsightsService

_service: EmployeeInsightsService | None = None


def get_employee_insights_service() -> EmployeeInsightsService:
    """Return the process-wide Employee Insights service, creating it on first use."""
    global _service
    if _service is None:
        _service = EmployeeInsightsService()
    return _service


def reset_employee_insights_service() -> None:
    """Clear the cached service. Intended for test isolation."""
    global _service
    _service = None
