import os
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


class VisualizationEngine:

    def __init__(self, dataframe, output_dir="visualizations"):

        self.df = dataframe.copy()

        self.output_dir = Path(output_dir)

        self._prepare_data()

    def ensure_output_dir(self):
        """Create the visualization output directory.

        Separate from construction so that instantiating the engine has no
        filesystem side effect. Callers that intend to write charts must
        call this first.

        Returns:
            The output directory path.
        """
        self.output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        return self.output_dir

    # ==============================================================
    # DATA PREPARATION
    # ==============================================================

    def _prepare_data(self):

        numeric_columns = [
            "sales",
            "profit",
            "units_sold",
            "unit_price",
            "gross_sales",
            "discount",
            "cogs",
            "sales_target",
            "profit_target",
        ]

        for column in numeric_columns:

            if column in self.df.columns:

                self.df[column] = pd.to_numeric(
                    self.df[column],
                    errors="coerce"
                )

        if "date" in self.df.columns:

            self.df["date"] = pd.to_datetime(
                self.df["date"],
                errors="coerce"
            )

        if "year" in self.df.columns:

            self.df["year"] = pd.to_numeric(
                self.df["year"],
                errors="coerce"
            )

        if "month_number" in self.df.columns:

            self.df["month_number"] = pd.to_numeric(
                self.df["month_number"],
                errors="coerce"
            )

        if (
            "date" in self.df.columns
            and self.df["date"].notna().any()
        ):

            self.df["period"] = (
                self.df["date"]
                .dt.to_period("M")
                .astype(str)
            )

    # ==============================================================
    # HELPER
    # ==============================================================

    def _save(self, filename):

        path = self.output_dir / filename

        plt.tight_layout()

        plt.savefig(
            path,
            dpi=150,
            bbox_inches="tight"
        )

        plt.close()

        print(
            f"Created visualization: {path}"
        )

        return str(path)

    def _check_columns(self, columns):

        return all(
            column in self.df.columns
            for column in columns
        )

    # ==============================================================
    # 1. MONTHLY SALES TREND
    # ==============================================================

    def monthly_sales_trend(self):

        if not self._check_columns(
            ["period", "sales"]
        ):
            return None

        data = (
            self.df
            .groupby("period")["sales"]
            .sum()
            .reset_index()
        )

        plt.figure(figsize=(12, 6))

        plt.plot(
            data["period"],
            data["sales"],
            marker="o"
        )

        plt.title(
            "Monthly Sales Trend"
        )

        plt.xlabel("Month")
        plt.ylabel("Sales")

        plt.xticks(
            rotation=45
        )

        return self._save(
            "monthly_sales_trend.png"
        )

    # ==============================================================
    # 2. MONTHLY PROFIT TREND
    # ==============================================================

    def monthly_profit_trend(self):

        if not self._check_columns(
            ["period", "profit"]
        ):
            return None

        data = (
            self.df
            .groupby("period")["profit"]
            .sum()
            .reset_index()
        )

        plt.figure(figsize=(12, 6))

        plt.plot(
            data["period"],
            data["profit"],
            marker="o"
        )

        plt.title(
            "Monthly Profit Trend"
        )

        plt.xlabel("Month")
        plt.ylabel("Profit")

        plt.xticks(
            rotation=45
        )

        return self._save(
            "monthly_profit_trend.png"
        )

    # ==============================================================
    # 3. SALES VS PROFIT BY MONTH
    # ==============================================================

    def monthly_sales_profit(self):

        if not self._check_columns(
            ["period", "sales", "profit"]
        ):
            return None

        data = (
            self.df
            .groupby("period")[
                ["sales", "profit"]
            ]
            .sum()
            .reset_index()
        )

        plt.figure(figsize=(12, 6))

        plt.plot(
            data["period"],
            data["sales"],
            marker="o",
            label="Sales"
        )

        plt.plot(
            data["period"],
            data["profit"],
            marker="o",
            label="Profit"
        )

        plt.title(
            "Monthly Sales vs Profit"
        )

        plt.xlabel("Month")
        plt.ylabel("Amount")

        plt.xticks(
            rotation=45
        )

        plt.legend()

        return self._save(
            "monthly_sales_vs_profit.png"
        )

    # ==============================================================
    # 4. YEARLY SALES
    # ==============================================================

    def yearly_sales(self):

        if not self._check_columns(
            ["year", "sales"]
        ):
            return None

        data = (
            self.df
            .groupby("year")["sales"]
            .sum()
            .reset_index()
        )

        plt.figure(figsize=(8, 6))

        plt.bar(
            data["year"].astype(str),
            data["sales"]
        )

        plt.title(
            "Yearly Sales"
        )

        plt.xlabel("Year")
        plt.ylabel("Sales")

        return self._save(
            "yearly_sales.png"
        )

    # ==============================================================
    # 5. PRODUCT SALES
    # ==============================================================

    def product_sales(self):

        if not self._check_columns(
            ["product", "sales"]
        ):
            return None

        data = (
            self.df
            .groupby("product")["sales"]
            .sum()
            .sort_values(
                ascending=False
            )
        )

        plt.figure(figsize=(10, 6))

        plt.bar(
            data.index.astype(str),
            data.values
        )

        plt.title(
            "Sales by Product"
        )

        plt.xlabel("Product")
        plt.ylabel("Sales")

        plt.xticks(
            rotation=30
        )

        return self._save(
            "product_sales.png"
        )

    # ==============================================================
    # 6. PRODUCT PROFIT
    # ==============================================================

    def product_profit(self):

        if not self._check_columns(
            ["product", "profit"]
        ):
            return None

        data = (
            self.df
            .groupby("product")["profit"]
            .sum()
            .sort_values(
                ascending=False
            )
        )

        plt.figure(figsize=(10, 6))

        plt.bar(
            data.index.astype(str),
            data.values
        )

        plt.title(
            "Profit by Product"
        )

        plt.xlabel("Product")
        plt.ylabel("Profit")

        plt.xticks(
            rotation=30
        )

        return self._save(
            "product_profit.png"
        )

    # ==============================================================
    # 7. EMPLOYEE SALES
    # ==============================================================

    def employee_sales(self):

        if not self._check_columns(
            ["employee_name", "sales"]
        ):
            return None

        data = (
            self.df
            .groupby("employee_name")["sales"]
            .sum()
            .sort_values(
                ascending=True
            )
        )

        plt.figure(figsize=(10, 7))

        plt.barh(
            data.index.astype(str),
            data.values
        )

        plt.title(
            "Sales by Employee"
        )

        plt.xlabel("Sales")
        plt.ylabel("Employee")

        return self._save(
            "employee_sales.png"
        )

    # ==============================================================
    # 8. EMPLOYEE PROFIT
    # ==============================================================

    def employee_profit(self):

        if not self._check_columns(
            ["employee_name", "profit"]
        ):
            return None

        data = (
            self.df
            .groupby("employee_name")["profit"]
            .sum()
            .sort_values(
                ascending=True
            )
        )

        plt.figure(figsize=(10, 7))

        plt.barh(
            data.index.astype(str),
            data.values
        )

        plt.title(
            "Profit by Employee"
        )

        plt.xlabel("Profit")
        plt.ylabel("Employee")

        return self._save(
            "employee_profit.png"
        )

    # ==============================================================
    # 9. DEPARTMENT SALES
    # ==============================================================

    def department_sales(self):

        if not self._check_columns(
            ["department", "sales"]
        ):
            return None

        data = (
            self.df
            .groupby("department")["sales"]
            .sum()
            .sort_values(
                ascending=False
            )
        )

        plt.figure(figsize=(10, 6))

        plt.bar(
            data.index.astype(str),
            data.values
        )

        plt.title(
            "Sales by Department"
        )

        plt.xlabel("Department")
        plt.ylabel("Sales")

        plt.xticks(
            rotation=30
        )

        return self._save(
            "department_sales.png"
        )

    # ==============================================================
    # 10. DEPARTMENT PROFIT
    # ==============================================================

    def department_profit(self):

        if not self._check_columns(
            ["department", "profit"]
        ):
            return None

        data = (
            self.df
            .groupby("department")["profit"]
            .sum()
            .sort_values(
                ascending=False
            )
        )

        plt.figure(figsize=(10, 6))

        plt.bar(
            data.index.astype(str),
            data.values
        )

        plt.title(
            "Profit by Department"
        )

        plt.xlabel("Department")
        plt.ylabel("Profit")

        plt.xticks(
            rotation=30
        )

        return self._save(
            "department_profit.png"
        )

    # ==============================================================
    # 11. REGIONAL SALES
    # ==============================================================

    def regional_sales(self):

        if not self._check_columns(
            ["region", "sales"]
        ):
            return None

        data = (
            self.df
            .groupby("region")["sales"]
            .sum()
            .sort_values(
                ascending=False
            )
        )

        plt.figure(figsize=(9, 6))

        plt.bar(
            data.index.astype(str),
            data.values
        )

        plt.title(
            "Sales by Region"
        )

        plt.xlabel("Region")
        plt.ylabel("Sales")

        return self._save(
            "regional_sales.png"
        )

    # ==============================================================
    # 12. REGIONAL PROFIT
    # ==============================================================

    def regional_profit(self):

        if not self._check_columns(
            ["region", "profit"]
        ):
            return None

        data = (
            self.df
            .groupby("region")["profit"]
            .sum()
            .sort_values(
                ascending=False
            )
        )

        plt.figure(figsize=(9, 6))

        plt.bar(
            data.index.astype(str),
            data.values
        )

        plt.title(
            "Profit by Region"
        )

        plt.xlabel("Region")
        plt.ylabel("Profit")

        return self._save(
            "regional_profit.png"
        )

    # ==============================================================
    # 13. CUSTOMER SALES
    # ==============================================================

    def customer_sales(self):

        if not self._check_columns(
            ["customer_name", "sales"]
        ):
            return None

        data = (
            self.df
            .groupby("customer_name")["sales"]
            .sum()
            .sort_values(
                ascending=True
            )
        )

        plt.figure(figsize=(10, 7))

        plt.barh(
            data.index.astype(str),
            data.values
        )

        plt.title(
            "Sales by Customer"
        )

        plt.xlabel("Sales")
        plt.ylabel("Customer")

        return self._save(
            "customer_sales.png"
        )

    # ==============================================================
    # 14. CUSTOMER PROFIT
    # ==============================================================

    def customer_profit(self):

        if not self._check_columns(
            ["customer_name", "profit"]
        ):
            return None

        data = (
            self.df
            .groupby("customer_name")["profit"]
            .sum()
            .sort_values(
                ascending=True
            )
        )

        plt.figure(figsize=(10, 7))

        plt.barh(
            data.index.astype(str),
            data.values
        )

        plt.title(
            "Profit by Customer"
        )

        plt.xlabel("Profit")
        plt.ylabel("Customer")

        return self._save(
            "customer_profit.png"
        )

    # ==============================================================
    # 15. CHANNEL SALES
    # ==============================================================

    def channel_sales(self):

        if not self._check_columns(
            ["sales_channel", "sales"]
        ):
            return None

        data = (
            self.df
            .groupby("sales_channel")["sales"]
            .sum()
            .sort_values(
                ascending=False
            )
        )

        plt.figure(figsize=(9, 6))

        plt.bar(
            data.index.astype(str),
            data.values
        )

        plt.title(
            "Sales by Sales Channel"
        )

        plt.xlabel("Sales Channel")
        plt.ylabel("Sales")

        return self._save(
            "channel_sales.png"
        )

    # ==============================================================
    # 16. CHANNEL PROFIT
    # ==============================================================

    def channel_profit(self):

        if not self._check_columns(
            ["sales_channel", "profit"]
        ):
            return None

        data = (
            self.df
            .groupby("sales_channel")["profit"]
            .sum()
            .sort_values(
                ascending=False
            )
        )

        plt.figure(figsize=(9, 6))

        plt.bar(
            data.index.astype(str),
            data.values
        )

        plt.title(
            "Profit by Sales Channel"
        )

        plt.xlabel("Sales Channel")
        plt.ylabel("Profit")

        return self._save(
            "channel_profit.png"
        )

    # ==============================================================
    # 17. CUSTOMER SEGMENT SALES
    # ==============================================================

    def segment_sales(self):

        if not self._check_columns(
            ["customer_segment", "sales"]
        ):
            return None

        data = (
            self.df
            .groupby(
                "customer_segment"
            )["sales"]
            .sum()
            .sort_values(
                ascending=False
            )
        )

        plt.figure(figsize=(9, 6))

        plt.bar(
            data.index.astype(str),
            data.values
        )

        plt.title(
            "Sales by Customer Segment"
        )

        plt.xlabel("Customer Segment")
        plt.ylabel("Sales")

        plt.xticks(
            rotation=20
        )

        return self._save(
            "segment_sales.png"
        )

    # ==============================================================
    # 18. SALES VS PROFIT SCATTER
    # ==============================================================

    def sales_profit_scatter(
        self,
        dimension="product"
    ):

        if not self._check_columns(
            [
                dimension,
                "sales",
                "profit"
            ]
        ):
            return None

        data = (
            self.df
            .groupby(dimension)[
                ["sales", "profit"]
            ]
            .sum()
            .reset_index()
        )

        plt.figure(figsize=(9, 7))

        plt.scatter(
            data["sales"],
            data["profit"],
            s=80
        )

        for _, row in data.iterrows():

            plt.annotate(
                str(row[dimension]),
                (
                    row["sales"],
                    row["profit"]
                ),
                xytext=(5, 5),
                textcoords="offset points"
            )

        plt.title(
            f"Sales vs Profit - "
            f"{dimension.replace('_', ' ').title()}"
        )

        plt.xlabel("Sales")
        plt.ylabel("Profit")

        return self._save(
            f"{dimension}_sales_profit_scatter.png"
        )

    # ==============================================================
    # 19. SALES VS TARGET
    # ==============================================================

    def sales_vs_target(
        self,
        dimension="product"
    ):

        if not self._check_columns(
            [
                dimension,
                "sales",
                "sales_target"
            ]
        ):
            return None

        data = (
            self.df
            .groupby(dimension)[
                ["sales", "sales_target"]
            ]
            .sum()
        )

        ax = data.plot(
            kind="bar",
            figsize=(11, 6)
        )

        ax.set_title(
            f"Actual Sales vs Target - "
            f"{dimension.replace('_', ' ').title()}"
        )

        ax.set_xlabel(
            dimension.replace(
                "_",
                " "
            ).title()
        )

        ax.set_ylabel(
            "Sales"
        )

        plt.xticks(
            rotation=30
        )

        return self._save(
            f"{dimension}_sales_vs_target.png"
        )

    # ==============================================================
    # 20. PROFIT VS TARGET
    # ==============================================================

    def profit_vs_target(
        self,
        dimension="product"
    ):

        if not self._check_columns(
            [
                dimension,
                "profit",
                "profit_target"
            ]
        ):
            return None

        data = (
            self.df
            .groupby(dimension)[
                ["profit", "profit_target"]
            ]
            .sum()
        )

        ax = data.plot(
            kind="bar",
            figsize=(11, 6)
        )

        ax.set_title(
            f"Actual Profit vs Target - "
            f"{dimension.replace('_', ' ').title()}"
        )

        ax.set_xlabel(
            dimension.replace(
                "_",
                " "
            ).title()
        )

        ax.set_ylabel(
            "Profit"
        )

        plt.xticks(
            rotation=30
        )

        return self._save(
            f"{dimension}_profit_vs_target.png"
        )

    # ==============================================================
    # 21. PROFIT MARGIN SCATTER
    # ==============================================================

    def sales_margin_scatter(
        self,
        dimension="product"
    ):

        if not self._check_columns(
            [
                dimension,
                "sales",
                "profit"
            ]
        ):
            return None

        data = (
            self.df
            .groupby(dimension)[
                ["sales", "profit"]
            ]
            .sum()
            .reset_index()
        )

        data["profit_margin"] = (
            data["profit"]
            / data["sales"]
            * 100
        )

        plt.figure(figsize=(9, 7))

        plt.scatter(
            data["sales"],
            data["profit_margin"],
            s=100
        )

        for _, row in data.iterrows():

            plt.annotate(
                str(row[dimension]),
                (
                    row["sales"],
                    row["profit_margin"]
                ),
                xytext=(5, 5),
                textcoords="offset points"
            )

        plt.title(
            f"Sales vs Profit Margin - "
            f"{dimension.replace('_', ' ').title()}"
        )

        plt.xlabel("Sales")
        plt.ylabel("Profit Margin (%)")

        return self._save(
            f"{dimension}_sales_margin_scatter.png"
        )

    # ==============================================================
    # 22. DISCOUNT VS PROFIT
    # ==============================================================

    def discount_profit_scatter(self):

        if not self._check_columns(
            [
                "discount",
                "profit"
            ]
        ):
            return None

        plt.figure(figsize=(9, 7))

        plt.scatter(
            self.df["discount"],
            self.df["profit"],
            alpha=0.6
        )

        plt.title(
            "Discount vs Profit"
        )

        plt.xlabel("Discount")
        plt.ylabel("Profit")

        return self._save(
            "discount_vs_profit.png"
        )

    # ==============================================================
    # 23. UNITS VS SALES
    # ==============================================================

    def units_sales_scatter(self):

        if not self._check_columns(
            [
                "units_sold",
                "sales"
            ]
        ):
            return None

        plt.figure(figsize=(9, 7))

        plt.scatter(
            self.df["units_sold"],
            self.df["sales"],
            alpha=0.6
        )

        plt.title(
            "Units Sold vs Sales"
        )

        plt.xlabel("Units Sold")
        plt.ylabel("Sales")

        return self._save(
            "units_sold_vs_sales.png"
        )

    # ==============================================================
    # RUN ALL
    # ==============================================================

    def generate_all(self):

        self.ensure_output_dir()

        generated = []

        visualizations = [

            self.monthly_sales_trend,

            self.monthly_profit_trend,

            self.monthly_sales_profit,

            self.yearly_sales,

            self.product_sales,

            self.product_profit,

            self.employee_sales,

            self.employee_profit,

            self.department_sales,

            self.department_profit,

            self.regional_sales,

            self.regional_profit,

            self.customer_sales,

            self.customer_profit,

            self.channel_sales,

            self.channel_profit,

            self.segment_sales,

            lambda:
                self.sales_profit_scatter(
                    "product"
                ),

            lambda:
                self.sales_profit_scatter(
                    "employee_name"
                ),

            lambda:
                self.sales_profit_scatter(
                    "department"
                ),

            lambda:
                self.sales_profit_scatter(
                    "region"
                ),

            lambda:
                self.sales_profit_scatter(
                    "customer_name"
                ),

            lambda:
                self.sales_profit_scatter(
                    "sales_channel"
                ),

            lambda:
                self.sales_vs_target(
                    "employee_name"
                ),

            lambda:
                self.sales_vs_target(
                    "department"
                ),

            lambda:
                self.sales_vs_target(
                    "product"
                ),

            lambda:
                self.sales_vs_target(
                    "region"
                ),

            lambda:
                self.sales_vs_target(
                    "sales_channel"
                ),

            lambda:
                self.sales_vs_target(
                    "customer_segment"
                ),

            lambda:
                self.profit_vs_target(
                    "employee_name"
                ),

            lambda:
                self.profit_vs_target(
                    "department"
                ),

            lambda:
                self.profit_vs_target(
                    "product"
                ),

            lambda:
                self.profit_vs_target(
                    "region"
                ),

            lambda:
                self.profit_vs_target(
                    "sales_channel"
                ),

            lambda:
                self.profit_vs_target(
                    "customer_segment"
                ),

            lambda:
                self.sales_margin_scatter(
                    "product"
                ),

            lambda:
                self.sales_margin_scatter(
                    "employee_name"
                ),

            self.discount_profit_scatter,

            self.units_sales_scatter,
        ]

        for visualization in visualizations:

            try:

                result = visualization()

                if result:
                    generated.append(result)

            except Exception as error:

                print(
                    "Visualization skipped:"
                )

                print(error)

        print()
        print("=" * 70)
        print(
            f"VISUALIZATIONS GENERATED: "
            f"{len(generated)}"
        )
        print("=" * 70)

        return generated


# ==============================================================
# DIRECT EXECUTION
# ==============================================================

if __name__ == "__main__":

    from performance_agent.data_loader import (
        DataLoader
    )

    project_root = (
        Path(__file__)
        .resolve()
        .parent.parent
    )

    csv_path = (
        project_root
        / "data"
        / "Financials_standardized.csv"
    )

    loader = DataLoader(
        str(csv_path)
    )

    dataframe = loader.load()

    engine = VisualizationEngine(
        dataframe
    )

    engine.generate_all()