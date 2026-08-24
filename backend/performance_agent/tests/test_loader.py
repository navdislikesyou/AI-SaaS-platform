from pathlib import Path

from backend.performance_agent.data_loader import DataLoader


def main():

    csv_path = (
        Path(__file__).parent.parent
        / "data"
        / "Financials.csv"
    )

    loader = DataLoader(str(csv_path))

    df = loader.load()

    print("=" * 60)
    print("DATASET LOADED SUCCESSFULLY")
    print("=" * 60)

    print(f"\nRows    : {len(df)}")
    print(f"Columns : {len(df.columns)}")

    print("\nColumns:")
    print("-" * 60)

    for column in df.columns:
        print(column)

    print("\nFirst 5 rows:")
    print("-" * 60)

    print(df.head())


if __name__ == "__main__":
    main()
    