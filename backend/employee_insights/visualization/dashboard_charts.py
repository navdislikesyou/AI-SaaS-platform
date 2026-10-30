from pathlib import Path

import plotly.express as px
import pandas as pd

from backend.employee_insights.analysis.frequency_analyzer import FrequencyAnalyzer


class DashboardCharts:

    def __init__(self):
        self.analyzer = FrequencyAnalyzer()

        self.output_directory = (
            Path(__file__).resolve().parents[1] / "data" / "charts"
        )

        self.output_directory.mkdir(parents=True, exist_ok=True)

    def generate_employee_chart(self):

        results = self.analyzer.analyze()

        df = pd.DataFrame(results)

        df = df.melt(
            id_vars=["employee_name"],
            value_vars=["positive", "negative", "neutral"],
            var_name="sentiment",
            value_name="count"
        )

        fig = px.bar(
            df,
            x="employee_name",
            y="count",
            color="sentiment",
            barmode="group",
            title="Employee-wise Feedback Analysis",
            labels={
                "employee_name": "Employee",
                "count": "Feedback Count",
                "sentiment": "Sentiment"
            }
        )

        fig.write_html(
            self.output_directory / "employee_feedback.html"
        )

        return fig

    def generate_monthly_chart(self):

        results = self.analyzer.monthly_analysis()

        if not results:
            print("No monthly feedback data available.")
            return None

        df = pd.DataFrame.from_dict(results, orient="index")
        df.index.name = "month"
        df = df.reset_index()

        df = df.melt(
            id_vars=["month"],
            value_vars=["positive", "negative", "neutral"],
            var_name="sentiment",
            value_name="count"
        )

        fig = px.bar(
            df,
            x="month",
            y="count",
            color="sentiment",
            barmode="stack",
            title="Monthly Feedback Sentiment Trends",
            labels={
                "month": "Month",
                "count": "Feedback Count",
                "sentiment": "Sentiment"
            }
        )

        fig.write_html(
            self.output_directory / "monthly_feedback.html"
        )

        return fig

    def generate_all(self):

        self.generate_employee_chart()
        self.generate_monthly_chart()

        print("\nCharts generated successfully.")
        print(f"Location: {self.output_directory}")


if __name__ == "__main__":

    dashboard = DashboardCharts()
    dashboard.generate_all()