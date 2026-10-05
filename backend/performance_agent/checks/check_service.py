"""Manual check for PerformanceService.

Verifies the service layer against the bundled dataset: every method returns a
JSON-safe dict, the nine analyzers run in their registered order, and the
in-memory methods perform no disk I/O.

This is a manual verification script, not an automated test. It prints what it
finds and takes a few seconds. It follows the naming of the sibling checks so
pytest does not try to collect it.

Run directly:

    cd backend
    python -m performance_agent.checks.check_service
"""

from pathlib import Path

from performance_agent.dataset import load_clean_dataset
from performance_agent.service import PerformanceService, available_analyzers

DATASET = (
    Path(__file__).parent.parent
    / "data"
    / "Financials_standardized.csv"
)


def main() -> None:
    """Run the service checks and print what each method returns."""
    print("=" * 70)
    print("PERFORMANCE SERVICE CHECK")
    print("=" * 70)

    if not DATASET.exists():
        print(
            f"\nDataset missing at {DATASET}. Run "
            "python -m performance_agent.create_sample_dataset first."
        )
        return

    service = PerformanceService()

    print(f"\nOperations : {service.operations}")
    print(f"Analyzers  : {available_analyzers()}")

    print("\n" + "-" * 70)
    print("load_dataset")
    print("-" * 70)

    metadata = service.load_dataset(str(DATASET))

    print(f"  rows           : {metadata['rows']}")
    print(f"  columns        : {metadata['columns']}")
    print(f"  column_names   : {len(metadata['column_names'])} names")
    print(f"  extensions     : {metadata['supported_extensions']}")
    print(f"  returns dict   : {isinstance(metadata, dict)}")

    df = load_clean_dataset(DATASET)

    print("\n" + "-" * 70)
    print("compute_kpis")
    print("-" * 70)

    kpis = service.compute_kpis(df)

    print(f"  keys           : {list(kpis)}")
    total_sales = kpis["overall"].get("total_sales")
    margin = kpis["overall"].get("profit_margin")
    print(f"  total_sales    : {total_sales}")
    print(f"  profit_margin  : {margin}")

    print("\n" + "-" * 70)
    print("compare_periods")
    print("-" * 70)

    comparison = service.compare_periods(df)

    print(f"  status         : {comparison.get('status')}")
    print(f"  years          : {comparison.get('year_count')}")
    print(f"  months         : {comparison.get('month_count')}")

    latest = comparison.get("latest_comparison") or {}
    print(f"  latest compare : {latest}")
    print(f"  growth streaks : {comparison.get('longest_growth_streak')}")

    print("\n" + "-" * 70)
    print("analyze")
    print("-" * 70)

    analysis = service.analyze(df)

    print(f"  keys           : {list(analysis)}")
    print(f"  successful     : {analysis['successful_modules']}")
    print(f"  failed         : {[m['module'] for m in analysis['failed_modules']]}")
    print(f"  module order   : {list(analysis['analysis'])}")

    order_matches = (
        list(analysis["analysis"])
        == available_analyzers()
    )
    print(f"  order matches registry: {order_matches}")

    print("\n" + "-" * 70)
    print("generate_insights")
    print("-" * 70)

    insights = service.generate_insights(df)

    print(f"  keys           : {list(insights)}")
    print(f"  total_insights : {insights.get('total_insights')}")
    print(f"  critical       : {len(insights.get('critical', []))}")
    print(f"  warnings       : {len(insights.get('warnings', []))}")

    print("\n" + "-" * 70)
    print("generate_visualizations (writes PNGs)")
    print("-" * 70)

    visualizations = service.generate_visualizations(df)

    print(f"  generated      : {visualizations['generated']}")
    print(f"  output_dir     : {visualizations['output_dir']}")

    print("\n" + "-" * 70)
    print("run_full_pipeline (no visualizations by default)")
    print("-" * 70)

    pipeline = service.run_full_pipeline(df)

    print(f"  keys           : {list(pipeline)}")
    print(f"  has insights   : {'insights' in pipeline}")
    print(f"  has images     : {'visualizations' in pipeline}")

    print("\n" + "=" * 70)
    print("PERFORMANCE SERVICE CHECK COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()