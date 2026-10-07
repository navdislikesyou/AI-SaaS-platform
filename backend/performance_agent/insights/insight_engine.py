from pathlib import Path
import json
import pandas as pd


class InsightEngine:
    """Generate prioritized business insights from a dataset."""

    def __init__(self, df):
        self.df = df.copy()
        self._prepare_data()

    def _prepare_data(self):
        numeric_columns = [
            "sales",
            "profit",
            "units_sold",
            "sales_target",
            "profit_target",
            "gross_sales",
            "discount",
            "cogs",
        ]

        for column in numeric_columns:
            if column in self.df.columns:
                self.df[column] = pd.to_numeric(
                    self.df[column],
                    errors="coerce"
                )

    @staticmethod
    def _divide(a, b):
        if b == 0 or pd.isna(b):
            return 0.0
        return a / b

    @staticmethod
    def _priority_value(priority):
        return {
            "critical": 4,
            "warning": 3,
            "opportunity": 2,
            "positive": 1,
            "info": 0,
        }.get(priority, 0)

    def _insight(
        self,
        category,
        priority,
        title,
        message,
        entity=None,
        metric=None,
        impact=50,
        recommendation=None,
    ):
        return {
            "category": category,
            "priority": priority,
            "title": title,
            "entity": entity,
            "metric": metric,
            "impact": round(float(impact), 2),
            "message": message,
            "recommendation": recommendation,
        }

    def summary(self):
        result = {}

        if "sales" in self.df.columns:
            result["total_sales"] = round(
                self.df["sales"].sum(), 2
            )

        if "profit" in self.df.columns:
            result["total_profit"] = round(
                self.df["profit"].sum(), 2
            )

        if "sales" in self.df.columns and "profit" in self.df.columns:
            result["profit_margin"] = round(
                self._divide(
                    self.df["profit"].sum(),
                    self.df["sales"].sum()
                ) * 100,
                2
            )

        if "units_sold" in self.df.columns:
            result["total_units_sold"] = round(
                self.df["units_sold"].sum(), 2
            )

        if "sales" in self.df.columns and "sales_target" in self.df.columns:
            result["sales_target_achievement"] = round(
                self._divide(
                    self.df["sales"].sum(),
                    self.df["sales_target"].sum()
                ) * 100,
                2
            )

        if "profit" in self.df.columns and "profit_target" in self.df.columns:
            result["profit_target_achievement"] = round(
                self._divide(
                    self.df["profit"].sum(),
                    self.df["profit_target"].sum()
                ) * 100,
                2
            )

        return result

    def target_insights(self):
        insights = []

        if "sales" in self.df.columns and "sales_target" in self.df.columns:
            actual = self.df["sales"].sum()
            target = self.df["sales_target"].sum()

            achievement = self._divide(actual, target) * 100
            gap = target - actual

            if achievement < 90:
                priority = "critical"
                recommendation = (
                    "Review the sales pipeline, "
                    "underperforming segments and channels."
                )
            elif achievement < 100:
                priority = "warning"
                recommendation = (
                    "Identify the largest contributors "
                    "to the sales target gap."
                )
            else:
                priority = "positive"
                recommendation = (
                    "Maintain current performance "
                    "and investigate successful drivers."
                )

            insights.append(
                self._insight(
                    "target",
                    priority,
                    "Sales target performance",
                    (
                        f"Sales achievement is {achievement:.2f}%. "
                        f"The business is {abs(gap):,.2f} "
                        f"{'below' if gap > 0 else 'above'} "
                        f"the sales target."
                    ),
                    metric=round(achievement, 2),
                    impact=min(
                        100,
                        abs(100 - achievement) + 40
                    ),
                    recommendation=recommendation,
                )
            )

        if "profit" in self.df.columns and "profit_target" in self.df.columns:
            actual = self.df["profit"].sum()
            target = self.df["profit_target"].sum()

            achievement = self._divide(actual, target) * 100
            gap = target - actual

            if achievement < 90:
                priority = "critical"
                recommendation = (
                    "Investigate margin erosion, discounting "
                    "and high-cost products."
                )
            elif achievement < 100:
                priority = "warning"
                recommendation = (
                    "Identify products, customers and channels "
                    "causing the profit gap."
                )
            else:
                priority = "positive"
                recommendation = (
                    "Maintain profitability and monitor "
                    "margin drivers."
                )

            insights.append(
                self._insight(
                    "target",
                    priority,
                    "Profit target performance",
                    (
                        f"Profit achievement is {achievement:.2f}%. "
                        f"The business is {abs(gap):,.2f} "
                        f"{'below' if gap > 0 else 'above'} "
                        f"the profit target."
                    ),
                    metric=round(achievement, 2),
                    impact=min(
                        100,
                        abs(100 - achievement) + 45
                    ),
                    recommendation=recommendation,
                )
            )

        return insights

    def overall_insight(self):
        if "sales" not in self.df.columns or "profit" not in self.df.columns:
            return []

        sales = self.df["sales"].sum()
        profit = self.df["profit"].sum()
        margin = self._divide(profit, sales) * 100

        return [
            self._insight(
                "overall",
                "info",
                "Overall business performance",
                (
                    f"Total sales are {sales:,.2f} with total profit "
                    f"of {profit:,.2f} and an overall profit margin "
                    f"of {margin:.2f}%."
                ),
                metric=round(margin, 2),
                impact=20,
            )
        ]

    def dimension_insights(self, dimension, label):
        insights = []

        required = {
            dimension,
            "sales",
            "profit",
        }

        if not required.issubset(self.df.columns):
            return insights

        grouped = (
            self.df
            .groupby(dimension)
            .agg(
                sales=("sales", "sum"),
                profit=("profit", "sum"),
            )
            .reset_index()
        )

        if grouped.empty:
            return insights

        top = grouped.loc[grouped["sales"].idxmax()]

        insights.append(
            self._insight(
                dimension,
                "positive",
                f"Top {label}",
                (
                    f"{top[dimension]} has the highest "
                    f"{label.lower()} sales at "
                    f"{top['sales']:,.2f}."
                ),
                entity=str(top[dimension]),
                metric=round(top["sales"], 2),
                impact=35,
            )
        )

        if len(grouped) > 1:
            low = grouped.loc[grouped["sales"].idxmin()]

            average_sales = grouped["sales"].mean()

            sales_gap = (
                self._divide(
                    average_sales - low["sales"],
                    average_sales
                ) * 100
            )

            total_sales = grouped["sales"].sum()

            contribution = (
                self._divide(
                    low["sales"],
                    total_sales
                ) * 100
            )

            if sales_gap >= 25 and contribution >= 5:
                insights.append(
                    self._insight(
                        dimension,
                        "warning",
                        f"Underperforming {label}",
                        (
                            f"{low[dimension]} generates "
                            f"{low['sales']:,.2f} in sales, "
                            f"{sales_gap:.2f}% below the average "
                            f"among {label.lower()}s."
                        ),
                        entity=str(low[dimension]),
                        metric=round(sales_gap, 2),
                        impact=min(
                            90,
                            50 + sales_gap
                        ),
                        recommendation=(
                            f"Investigate the factors affecting "
                            f"{low[dimension]}'s sales performance."
                        ),
                    )
                )

        return insights

    def margin_opportunities(self, dimension, label):
        insights = []

        required = {
            dimension,
            "sales",
            "profit",
        }

        if not required.issubset(self.df.columns):
            return insights

        grouped = (
            self.df
            .groupby(dimension)
            .agg(
                sales=("sales", "sum"),
                profit=("profit", "sum"),
            )
            .reset_index()
        )

        if len(grouped) < 2:
            return insights

        grouped["margin"] = (
            grouped["profit"]
            / grouped["sales"]
            * 100
        )

        total_sales = grouped["sales"].sum()

        overall_margin = (
            self._divide(
                grouped["profit"].sum(),
                total_sales
            ) * 100
        )

        sales_median = grouped["sales"].median()

        high_sales_low_margin = grouped[
            (grouped["sales"] >= sales_median)
            & (
                grouped["margin"]
                < overall_margin - 1.5
            )
        ]

        for _, row in high_sales_low_margin.iterrows():
            margin_gap = overall_margin - row["margin"]

            priority = (
                "critical"
                if margin_gap >= 3
                else "warning"
            )

            impact = min(
                100,
                55
                + margin_gap * 8
                + (
                    row["sales"]
                    / total_sales
                    * 30
                )
            )

            insights.append(
                self._insight(
                    "margin",
                    priority,
                    "High sales / low margin",
                    (
                        f"{row[dimension]} generates "
                        f"{row['sales']:,.2f} in sales but "
                        f"has a profit margin of "
                        f"{row['margin']:.2f}%, which is "
                        f"{margin_gap:.2f} percentage points "
                        f"below the overall margin."
                    ),
                    entity=str(row[dimension]),
                    metric=round(
                        row["margin"],
                        2
                    ),
                    impact=impact,
                    recommendation=(
                        "Review pricing, discounts, COGS "
                        "and product mix."
                    ),
                )
            )

        low_sales_high_margin = grouped[
            (grouped["sales"] < sales_median)
            & (
                grouped["margin"]
                > overall_margin + 1
            )
        ]

        for _, row in low_sales_high_margin.iterrows():
            margin_advantage = (
                row["margin"]
                - overall_margin
            )

            insights.append(
                self._insight(
                    "opportunity",
                    "opportunity",
                    "Low sales / high margin",
                    (
                        f"{row[dimension]} has a profit margin "
                        f"of {row['margin']:.2f}% but relatively "
                        f"low sales of {row['sales']:,.2f}. "
                        f"This may represent a growth opportunity."
                    ),
                    entity=str(row[dimension]),
                    metric=round(
                        row["margin"],
                        2
                    ),
                    impact=min(
                        90,
                        45 + margin_advantage * 8
                    ),
                    recommendation=(
                        "Evaluate whether sales can be expanded "
                        "without reducing the current margin."
                    ),
                )
            )

        return insights

    def employee_target_insights(self):
        insights = []

        required = {
            "employee_name",
            "sales",
            "sales_target",
        }

        if not required.issubset(self.df.columns):
            return insights

        grouped = (
            self.df
            .groupby("employee_name")
            .agg(
                sales=("sales", "sum"),
                target=("sales_target", "sum"),
            )
            .reset_index()
        )

        grouped["achievement"] = (
            grouped["sales"]
            / grouped["target"]
            * 100
        )

        below = (
            grouped[
                grouped["achievement"] < 90
            ]
            .sort_values("achievement")
            .head(3)
        )

        for _, row in below.iterrows():
            achievement = row["achievement"]

            insights.append(
                self._insight(
                    "employee",
                    "warning",
                    "Employee below target",
                    (
                        f"{row['employee_name']} is achieving "
                        f"{achievement:.2f}% of the sales target."
                    ),
                    entity=str(
                        row["employee_name"]
                    ),
                    metric=round(
                        achievement,
                        2
                    ),
                    impact=min(
                        90,
                        55 + (90 - achievement)
                    ),
                    recommendation=(
                        "Review sales pipeline, workload, "
                        "territory and conversion performance."
                    ),
                )
            )

        return insights

    def trend_insights(self):
        insights = []

        if "date" not in self.df.columns or "sales" not in self.df.columns:
            return insights

        data = self.df.copy()

        data["date"] = pd.to_datetime(
            data["date"],
            errors="coerce"
        )

        data = data.dropna(
            subset=["date"]
        )

        if data.empty:
            return insights

        monthly = (
            data
            .set_index("date")
            .resample("MS")["sales"]
            .sum()
        )

        if len(monthly) < 2:
            return insights

        growth = monthly.pct_change() * 100
        growth = growth.dropna()

        if growth.empty:
            return insights

        strongest_date = growth.idxmax()
        weakest_date = growth.idxmin()

        strongest = growth.loc[
            strongest_date
        ]

        weakest = growth.loc[
            weakest_date
        ]

        if strongest >= 20:
            insights.append(
                self._insight(
                    "trend",
                    "positive",
                    "Strong sales growth",
                    (
                        f"Sales increased by "
                        f"{strongest:.2f}% in "
                        f"{strongest_date.strftime('%Y-%m')}."
                    ),
                    entity=strongest_date.strftime(
                        "%Y-%m"
                    ),
                    metric=round(
                        strongest,
                        2
                    ),
                    impact=min(
                        90,
                        45 + strongest / 2
                    ),
                    recommendation=(
                        "Identify the products, customers "
                        "and channels responsible for the growth."
                    ),
                )
            )

        if weakest <= -20:
            severity = abs(weakest)

            insights.append(
                self._insight(
                    "trend",
                    (
                        "critical"
                        if severity >= 40
                        else "warning"
                    ),
                    "Significant sales decline",
                    (
                        f"Sales changed by "
                        f"{weakest:.2f}% in "
                        f"{weakest_date.strftime('%Y-%m')}."
                    ),
                    entity=weakest_date.strftime(
                        "%Y-%m"
                    ),
                    metric=round(
                        weakest,
                        2
                    ),
                    impact=min(
                        100,
                        50 + severity
                    ),
                    recommendation=(
                        "Investigate the causes of the decline "
                        "and compare product, region and channel "
                        "performance for this period."
                    ),
                )
            )

        return insights

    def deduplicate(self, insights):
        seen = set()
        result = []

        for insight in insights:
            key = (
                insight["category"],
                insight["title"],
                insight.get("entity"),
            )

            if key not in seen:
                seen.add(key)
                result.append(insight)

        return result

    def prioritize(self, insights):
        insights = self.deduplicate(insights)

        insights.sort(
            key=lambda item: (
                self._priority_value(
                    item["priority"]
                ),
                item.get("impact", 0),
            ),
            reverse=True,
        )

        return insights

    def generate(self):
        insights = []

        insights.extend(
            self.overall_insight()
        )

        insights.extend(
            self.target_insights()
        )

        dimensions = [
            ("employee_name", "Employee"),
            ("department", "Department"),
            ("product", "Product"),
            ("region", "Region"),
            ("customer_name", "Customer"),
            ("sales_channel", "Sales Channel"),
        ]

        for dimension, label in dimensions:
            insights.extend(
                self.dimension_insights(
                    dimension,
                    label
                )
            )

        margin_dimensions = [
            ("product", "Product"),
            ("customer_name", "Customer"),
            ("sales_channel", "Sales Channel"),
        ]

        for dimension, label in margin_dimensions:
            insights.extend(
                self.margin_opportunities(
                    dimension,
                    label
                )
            )

        insights.extend(
            self.employee_target_insights()
        )

        insights.extend(
            self.trend_insights()
        )

        insights = self.prioritize(
            insights
        )

        critical = [
            item for item in insights
            if item["priority"] == "critical"
        ][:5]

        warnings = [
            item for item in insights
            if item["priority"] == "warning"
        ][:7]

        opportunities = [
            item for item in insights
            if item["priority"] == "opportunity"
        ][:5]

        positive = [
            item for item in insights
            if item["priority"] == "positive"
        ][:5]

        info = [
            item for item in insights
            if item["priority"] == "info"
        ][:2]

        selected = (
            critical
            + warnings
            + opportunities
            + positive
            + info
        )

        return {
            "summary": self.summary(),
            "total_insights": len(selected),
            "critical": critical,
            "warnings": warnings,
            "opportunities": opportunities,
            "positive": positive,
            "info": info,
            "all_insights": selected,
        }

    def print_report(self):
        result = self.generate()

        print()
        print("=" * 70)
        print("BUSINESS INSIGHT ENGINE")
        print("=" * 70)

        print(
            f"\nTotal actionable insights: "
            f"{result['total_insights']}"
        )

        print("\nBUSINESS SUMMARY")
        print("-" * 70)

        for key, value in result["summary"].items():
            print(
                f"{key:<35}: {value}"
            )

        sections = [
            ("CRITICAL INSIGHTS", result["critical"]),
            ("WARNINGS", result["warnings"]),
            ("OPPORTUNITIES", result["opportunities"]),
            ("POSITIVE FINDINGS", result["positive"]),
            ("GENERAL", result["info"]),
        ]

        number = 1

        for title, items in sections:

            if not items:
                continue

            print()
            print(title)
            print("-" * 70)

            for insight in items:

                print(
                    f"\n{number}. "
                    f"[{insight['priority'].upper()}] "
                    f"{insight['title']}"
                )

                if insight.get("entity"):
                    print(
                        f"   Entity         : "
                        f"{insight['entity']}"
                    )

                if insight.get("metric") is not None:
                    print(
                        f"   Metric         : "
                        f"{insight['metric']}"
                    )

                print(
                    f"   Impact         : "
                    f"{insight['impact']}"
                )

                print(
                    f"   Insight        : "
                    f"{insight['message']}"
                )

                if insight.get("recommendation"):
                    print(
                        f"   Recommendation : "
                        f"{insight['recommendation']}"
                    )

                number += 1

        print()
        print("=" * 70)

        return result

    def save_json(self, output_path):
        result = self.generate()

        output_path = Path(output_path)

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with open(
            output_path,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                result,
                file,
                indent=4,
                ensure_ascii=False
            )

        return output_path


if __name__ == "__main__":
    from performance_agent.data_loader import DataLoader

    project_root = (
        Path(__file__).resolve().parent.parent
    )

    csv_path = (
        project_root
        / "data"
        / "Financials_standardized.csv"
    )

    output_path = (
        project_root
        / "results"
        / "insights.json"
    )

    loader = DataLoader(
        str(csv_path)
    )

    dataframe = loader.load()

    engine = InsightEngine(
        dataframe
    )

    engine.print_report()

    saved = engine.save_json(
        output_path
    )

    print()
    print(
        f"Saved insights to: {saved}"
    )