from pathlib import Path

from performance_agent.data_loader import DataLoader
from performance_agent.analysis.schema_detector import SchemaDetector


def main():

    project_root = Path(__file__).resolve().parent.parent

    csv_path = (
        project_root
        / "data"
        / "Financials_standardized.csv"
    )

    print("=" * 70)
    print("LOADING STANDARDIZED DATASET")
    print("=" * 70)
    print()
    print(f"File: {csv_path}")
    print()

    loader = DataLoader(str(csv_path))
    df = loader.load()

    print(f"Rows    : {len(df)}")
    print(f"Columns : {len(df.columns)}")
    print()

    detector = SchemaDetector(df)

    detector.print_schema()


if __name__ == "__main__":
    main()