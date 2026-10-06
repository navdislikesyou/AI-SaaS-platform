from pathlib import Path

from performance_agent.data_loader import DataLoader
from performance_agent.analysis.channel_analysis import (
    ChannelAnalyzer
)


def main():

    project_root = Path(__file__).resolve().parent.parent

    csv_path = (
        project_root
        / "data"
        / "Financials_standardized.csv"
    )

    loader = DataLoader(str(csv_path))

    df = loader.load()

    analyzer = ChannelAnalyzer(df)

    analyzer.print_report()


if __name__ == "__main__":
    main()