import json
import sys
from pathlib import Path

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


BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"
VISUALIZATION_DIR = RESULTS_DIR / "visualizations"


def ensure_results_dirs():
    """Create the results and visualization output directories.

    Called from run_performance_agent() rather than at import time so that
    importing this module has no filesystem side effects.

    Returns:
        None
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    VISUALIZATION_DIR.mkdir(parents=True, exist_ok=True)


def make_json_safe(obj):
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


def save_json(data, path):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(
            make_json_safe(data),
            file,
            indent=2,
            ensure_ascii=False
        )


def load_input_file(file_path):
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Input file not found: {file_path}"
        )

    extension = file_path.suffix.lower()

    if extension == ".csv":
        return pd.read_csv(file_path)

    if extension in [".xlsx", ".xls"]:
        return pd.read_excel(file_path)

    raise ValueError(
        "Unsupported file type. Use CSV or Excel."
    )


def standardize_dataframe(df):
    df = df.copy()

    df = df.dropna(how="all")

    df.columns = [
        str(column).strip()
        for column in df.columns
    ]

    df = df.dropna(axis=1, how="all")

    return df


ANALYZERS = [
    ("company", CompanyAnalyzer),
    ("employee", EmployeeAnalyzer),
    ("department", DepartmentAnalyzer),
    ("product", ProductAnalyzer),
    ("regional", RegionalAnalyzer),
    ("customer", CustomerAnalyzer),
    ("channel", ChannelAnalyzer),
    ("time", TimeAnalyzer),
    ("target", TargetAnalyzer),
]


def run_analysis_modules(df):

    results = {}
    successful_modules = []
    failed_modules = []

    print("\n" + "=" * 70)
    print("RUNNING ANALYSIS MODULES")
    print("=" * 70)

    for module_name, analyzer_class in ANALYZERS:

        print(f"\nRunning {module_name} analysis...")

        try:
            analyzer = analyzer_class(df)
            result = analyzer.analyze()

            results[module_name] = make_json_safe(result)
            successful_modules.append(module_name)

            print(
                f"[OK] {module_name} analysis completed"
            )

        except Exception as error:

            failed_modules.append({
                "module": module_name,
                "error": str(error)
            })

            print(
                f"[WARN] {module_name} analysis skipped: "
                f"{error}"
            )

    print(
        f"\nCompleted {len(successful_modules)} "
        f"analysis modules."
    )

    return (
        results,
        successful_modules,
        failed_modules
    )


def generate_visualizations(df):

    print("\n" + "=" * 70)
    print("GENERATING VISUALIZATIONS")
    print("=" * 70)

    try:

        from performance_agent.visualization.visualization_engine import (
            VisualizationEngine
        )

        engine = VisualizationEngine(
            df,
            VISUALIZATION_DIR
        )

        engine.generate_all()

        files = list(
            VISUALIZATION_DIR.glob("*.png")
        )

        count = len(files)

        print(
            f"\n[OK] Generated {count} visualizations."
        )

        return count

    except Exception as error:

        print(
            f"\n[WARN] Visualization generation failed: "
            f"{error}"
        )

        return 0


def generate_insights(df):

    print("\n" + "=" * 70)
    print("GENERATING BUSINESS INSIGHTS")
    print("=" * 70)

    try:

        from performance_agent.insights.insight_engine import (
            InsightEngine
        )

        engine = InsightEngine(df)

        result = engine.generate()

        result = make_json_safe(result)

        insights_path = (
            RESULTS_DIR /
            "insights.json"
        )

        save_json(
            result,
            insights_path
        )

        if isinstance(result, dict):

            if "all_insights" in result:
                count = len(
                    result["all_insights"]
                )

            elif "insights" in result:
                count = len(
                    result["insights"]
                )

            elif "total_insights" in result:
                count = int(
                    result["total_insights"]
                )

            else:
                count = 0

        elif isinstance(result, list):

            count = len(result)

        else:

            count = 0

        print(
            f"\n[OK] Generated "
            f"{count} actionable insights."
        )

        print(
            f"Saved insights: "
            f"{insights_path}"
        )

        return result, count

    except Exception as error:

        print(
            f"\n[WARN] Insight generation failed: "
            f"{error}"
        )

        return {}, 0


def save_run_summary(
    input_file,
    df,
    successful_modules,
    failed_modules,
    visualization_count,
    insight_count
):

    summary = {
        "input_file": str(input_file),
        "input_type": Path(
            input_file
        ).suffix.lower(),
        "rows_processed": int(
            len(df)
        ),
        "columns_processed": int(
            len(df.columns)
        ),
        "analysis_modules_completed": len(
            successful_modules
        ),
        "analysis_modules": successful_modules,
        "failed_modules": failed_modules,
        "visualizations_generated": (
            visualization_count
        ),
        "actionable_insights": (
            insight_count
        ),
        "results_directory": str(
            RESULTS_DIR
        )
    }

    summary_path = (
        RESULTS_DIR /
        "run_summary.json"
    )

    save_json(
        summary,
        summary_path
    )

    return summary_path


def run_performance_agent(input_file):

    input_file = Path(input_file)

    ensure_results_dirs()

    print("\n" + "=" * 70)
    print("PERFORMANCE AGENT")
    print("=" * 70)

    print("\nINPUT")
    print("-" * 70)

    print(
        f"File : {input_file.name}"
    )

    print(
        f"Type : {input_file.suffix.lower()}"
    )

    df = load_input_file(
        input_file
    )

    print(
        f"Rows : {len(df)}"
    )

    print(
        f"Columns : {len(df.columns)}"
    )

    print("\nDATA STANDARDIZATION")
    print("-" * 70)

    df = standardize_dataframe(df)

    standardized_path = (
        RESULTS_DIR /
        "standardized_data.csv"
    )

    df.to_csv(
        standardized_path,
        index=False
    )

    print(
        f"Standardized columns : "
        f"{len(df.columns)}"
    )

    print(
        f"Saved standardized data: "
        f"{standardized_path}"
    )

    (
        analysis_results,
        successful_modules,
        failed_modules
    ) = run_analysis_modules(df)

    analysis_results_path = (
        RESULTS_DIR /
        "analysis_results.json"
    )

    save_json(
        analysis_results,
        analysis_results_path
    )

    print(
        f"\nSaved analysis results: "
        f"{analysis_results_path}"
    )

    visualization_count = (
        generate_visualizations(df)
    )

    (
        insights,
        insight_count
    ) = generate_insights(df)

    summary_path = save_run_summary(
        input_file,
        df,
        successful_modules,
        failed_modules,
        visualization_count,
        insight_count
    )

    print("\n" + "=" * 70)
    print("PERFORMANCE AGENT COMPLETE")
    print("=" * 70)

    print(
        f"\nInput file              : "
        f"{input_file.name}"
    )

    print(
        f"Rows processed          : "
        f"{len(df)}"
    )

    print(
        f"Analysis modules        : "
        f"{len(successful_modules)}"
    )

    print(
        f"Visualizations          : "
        f"{visualization_count}"
    )

    print(
        f"Actionable insights     : "
        f"{insight_count}"
    )

    if failed_modules:

        print(
            "\nModules with warnings:"
        )

        for module in failed_modules:

            print(
                f"  - {module['module']}: "
                f"{module['error']}"
            )

    print(
        "\nResults directory:"
    )

    print(
        RESULTS_DIR
    )

    print(
        "\nAnalysis results:"
    )

    print(
        analysis_results_path
    )

    print(
        "\nRun summary:"
    )

    print(
        summary_path
    )

    print("\n" + "=" * 70)

    return {
        "analysis": analysis_results,
        "insights": insights,
        "successful_modules": successful_modules,
        "failed_modules": failed_modules,
        "visualization_count": visualization_count,
        "insight_count": insight_count
    }


if __name__ == "__main__":

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

        sys.exit(1)

    try:

        run_performance_agent(
            sys.argv[1]
        )

    except Exception as error:

        print("\n" + "=" * 70)
        print("PERFORMANCE AGENT FAILED")
        print("=" * 70)

        print(
            f"\nError: {error}"
        )

        sys.exit(1)