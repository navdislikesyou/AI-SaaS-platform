import pandas as pd


class CompanyAnalyzer:

    def __init__(self, dataframe):
        self.df = dataframe.copy()

        if "date" in self.df.columns:
            self.df["date"] = pd.to_datetime(
                self.df["date"],
                errors="coerce"
            )

    def _sum(self, column):
        if column not in self.df.columns:
            return None

        values = pd.to_numeric(
            self.df[column],
            errors="coerce"
        ).fillna(0)

        return float(values.sum())

    def _mean(self, column):
        if column not in self.df.columns:
            return None

        values = pd.to_numeric(
            self.df[column],
            errors="coerce"
        ).dropna()

        if values.empty:
            return None

        return float(values.mean())

    def _percentage(self, numerator, denominator):
        if numerator is None or denominator in (None, 0):
            return None

        return round(
            (numerator / denominator) * 100,
            2
        )

    def _growth(self, current, previous):
        if previous in (None, 0):
            return None

        return round(
            ((current - previous) / previous) * 100,
            2
        )

    def overall_performance(self):

        sales = self._sum("sales")
        profit = self._sum("profit")

        return {
            "total_sales": sales,
            "total_profit": profit,
            "profit_margin": self._percentage(
                profit,
                sales
            ),
            "total_units_sold": self._sum(
                "units_sold"
            ),
            "average_sale": self._mean(
                "sales"
            ),
            "average_profit": self._mean(
                "profit"
            ),
            "gross_sales": self._sum(
                "gross_sales"
            ),
            "total_discount": self._sum(
                "discount"
            ),
            "total_cogs": self._sum(
                "cogs"
            ),
        }

    def target_performance(self):

        actual_sales = self._sum("sales")
        sales_target = self._sum("sales_target")

        actual_profit = self._sum("profit")
        profit_target = self._sum("profit_target")

        return {
            "sales_target": sales_target,
            "actual_sales": actual_sales,
            "sales_target_achievement": self._percentage(
                actual_sales,
                sales_target
            ),
            "profit_target": profit_target,
            "actual_profit": actual_profit,
            "profit_target_achievement": self._percentage(
                actual_profit,
                profit_target
            ),
        }

    def product_performance(self):

        if "product" not in self.df.columns:
            return {}

        grouped = (
            self.df
            .groupby("product")
            .agg(
                sales=("sales", "sum"),
                profit=("profit", "sum"),
                units_sold=("units_sold", "sum")
            )
            .sort_values(
                "sales",
                ascending=False
            )
        )

        result = {
            "products": grouped.to_dict(
                orient="index"
            )
        }

        if not grouped.empty:

            result["top_product_by_sales"] = (
                grouped["sales"].idxmax()
            )

            result["top_product_by_profit"] = (
                grouped["profit"].idxmax()
            )

            result["lowest_product_by_profit"] = (
                grouped["profit"].idxmin()
            )

        return result

    def employee_performance(self):

        if "employee_name" not in self.df.columns:
            return {}

        grouped = (
            self.df
            .groupby(
                [
                    "employee_id",
                    "employee_name"
                ],
                dropna=False
            )
            .agg(
                sales=("sales", "sum"),
                profit=("profit", "sum"),
                units_sold=("units_sold", "sum"),
                sales_target=("sales_target", "sum"),
                profit_target=("profit_target", "sum")
            )
        )

        grouped["sales_target_achievement"] = (
            grouped["sales"]
            / grouped["sales_target"]
            * 100
        ).replace(
            [float("inf"), -float("inf")],
            0
        )

        grouped["profit_target_achievement"] = (
            grouped["profit"]
            / grouped["profit_target"]
            * 100
        ).replace(
            [float("inf"), -float("inf")],
            0
        )

        grouped = grouped.sort_values(
            "sales",
            ascending=False
        )

        result = {
            "employees": grouped.to_dict(
                orient="index"
            )
        }

        if not grouped.empty:

            result["top_employee"] = (
                grouped["sales"].idxmax()[1]
            )

            result["lowest_employee"] = (
                grouped["sales"].idxmin()[1]
            )

        return result

    def department_performance(self):

        if "department" not in self.df.columns:
            return {}

        grouped = (
            self.df
            .groupby("department")
            .agg(
                sales=("sales", "sum"),
                profit=("profit", "sum"),
                units_sold=("units_sold", "sum")
            )
            .sort_values(
                "sales",
                ascending=False
            )
        )

        result = {
            "departments": grouped.to_dict(
                orient="index"
            )
        }

        if not grouped.empty:

            result["best_department"] = (
                grouped["sales"].idxmax()
            )

            result["lowest_department"] = (
                grouped["sales"].idxmin()
            )

        return result

    def regional_performance(self):

        if "region" not in self.df.columns:
            return {}

        grouped = (
            self.df
            .groupby("region")
            .agg(
                sales=("sales", "sum"),
                profit=("profit", "sum"),
                units_sold=("units_sold", "sum")
            )
            .sort_values(
                "sales",
                ascending=False
            )
        )

        result = {
            "regions": grouped.to_dict(
                orient="index"
            )
        }

        if not grouped.empty:

            result["best_region"] = (
                grouped["sales"].idxmax()
            )

            result["lowest_region"] = (
                grouped["sales"].idxmin()
            )

        return result

    def customer_segment_performance(self):

        if "customer_segment" not in self.df.columns:
            return {}

        grouped = (
            self.df
            .groupby("customer_segment")
            .agg(
                sales=("sales", "sum"),
                profit=("profit", "sum"),
                units_sold=("units_sold", "sum")
            )
            .sort_values(
                "sales",
                ascending=False
            )
        )

        result = {
            "segments": grouped.to_dict(
                orient="index"
            )
        }

        if not grouped.empty:

            result["best_segment"] = (
                grouped["sales"].idxmax()
            )

            result["lowest_segment"] = (
                grouped["sales"].idxmin()
            )

        return result

    def channel_performance(self):

        if "sales_channel" not in self.df.columns:
            return {}

        grouped = (
            self.df
            .groupby("sales_channel")
            .agg(
                sales=("sales", "sum"),
                profit=("profit", "sum"),
                units_sold=("units_sold", "sum")
            )
            .sort_values(
                "sales",
                ascending=False
            )
        )

        result = {
            "channels": grouped.to_dict(
                orient="index"
            )
        }

        if not grouped.empty:

            result["best_channel"] = (
                grouped["sales"].idxmax()
            )

            result["lowest_channel"] = (
                grouped["sales"].idxmin()
            )

        return result

    def monthly_performance(self):

        if "date" not in self.df.columns:
            return {}

        data = self.df.dropna(
            subset=["date"]
        ).copy()

        if data.empty:
            return {}

        data["period"] = (
            data["date"]
            .dt.to_period("M")
            .astype(str)
        )

        grouped = (
            data
            .groupby("period")
            .agg(
                sales=("sales", "sum"),
                profit=("profit", "sum"),
                units_sold=("units_sold", "sum")
            )
            .sort_index()
        )

        grouped["sales_growth"] = (
            grouped["sales"]
            .pct_change()
            .mul(100)
            .round(2)
        )

        grouped["profit_growth"] = (
            grouped["profit"]
            .pct_change()
            .mul(100)
            .round(2)
        )

        result = {
            "months": grouped.to_dict(
                orient="index"
            )
        }

        if not grouped.empty:

            result["best_month"] = (
                grouped["sales"].idxmax()
            )

            result["worst_month"] = (
                grouped["sales"].idxmin()
            )

            result["best_month_sales"] = float(
                grouped["sales"].max()
            )

            result["worst_month_sales"] = float(
                grouped["sales"].min()
            )

        return result

    def yearly_performance(self):

        if "date" not in self.df.columns:
            return {}

        data = self.df.dropna(
            subset=["date"]
        ).copy()

        if data.empty:
            return {}

        data["year_value"] = (
            data["date"].dt.year
        )

        yearly = (
            data
            .groupby("year_value")
            .agg(
                sales=("sales", "sum"),
                profit=("profit", "sum"),
                units_sold=("units_sold", "sum")
            )
            .sort_index()
        )

        result = {
            "years": yearly.to_dict(
                orient="index"
            )
        }

        if not yearly.empty:

            result["best_year"] = (
                yearly["sales"].idxmax()
            )

            result["worst_year"] = (
                yearly["sales"].idxmin()
            )

        # --------------------------------------------------------
        # Comparable year-over-year analysis
        # --------------------------------------------------------

        available_years = sorted(
            yearly.index.tolist()
        )

        if len(available_years) < 2:

            result["comparison_status"] = (
                "Not available: only one year of data"
            )

            result["year_over_year_sales_growth"] = None
            result["year_over_year_profit_growth"] = None

            return result

        current_year = available_years[-1]
        previous_year = current_year - 1

        if previous_year not in available_years:

            result["comparison_status"] = (
                "Not available: no consecutive previous year"
            )

            result["year_over_year_sales_growth"] = None
            result["year_over_year_profit_growth"] = None

            return result

        current_data = data[
            data["year_value"] == current_year
        ].copy()

        previous_data = data[
            data["year_value"] == previous_year
        ].copy()

        current_data["month_number"] = (
            current_data["date"].dt.month
        )

        previous_data["month_number"] = (
            previous_data["date"].dt.month
        )

        current_months = set(
            current_data["month_number"].unique()
        )

        previous_months = set(
            previous_data["month_number"].unique()
        )

        comparable_months = sorted(
            current_months.intersection(
                previous_months
            )
        )

        if not comparable_months:

            result["comparison_status"] = (
                "Not available: no overlapping months"
            )

            result["year_over_year_sales_growth"] = None
            result["year_over_year_profit_growth"] = None

            return result

        current_comparable = current_data[
            current_data["month_number"].isin(
                comparable_months
            )
        ]

        previous_comparable = previous_data[
            previous_data["month_number"].isin(
                comparable_months
            )
        ]

        current_sales = float(
            current_comparable["sales"].sum()
        )

        previous_sales = float(
            previous_comparable["sales"].sum()
        )

        current_profit = float(
            current_comparable["profit"].sum()
        )

        previous_profit = float(
            previous_comparable["profit"].sum()
        )

        result["comparison_status"] = "Valid"

        result["comparison_year"] = current_year
        result["comparison_previous_year"] = previous_year

        result["comparable_months"] = [
            pd.Timestamp(
                year=2000,
                month=month,
                day=1
            ).strftime("%B")
            for month in comparable_months
        ]

        result["comparable_month_count"] = len(
            comparable_months
        )

        result["current_comparable_sales"] = (
            current_sales
        )

        result["previous_comparable_sales"] = (
            previous_sales
        )

        result["current_comparable_profit"] = (
            current_profit
        )

        result["previous_comparable_profit"] = (
            previous_profit
        )

        result["year_over_year_sales_growth"] = (
            self._growth(
                current_sales,
                previous_sales
            )
        )

        result["year_over_year_profit_growth"] = (
            self._growth(
                current_profit,
                previous_profit
            )
        )

        return result

    def analyze(self):

        return {
            "overall": self.overall_performance(),
            "targets": self.target_performance(),
            "products": self.product_performance(),
            "employees": self.employee_performance(),
            "departments": self.department_performance(),
            "regions": self.regional_performance(),
            "customer_segments": (
                self.customer_segment_performance()
            ),
            "channels": self.channel_performance(),
            "monthly": self.monthly_performance(),
            "yearly": self.yearly_performance(),
        }

    def print_report(self):

        report = self.analyze()

        print("\n" + "=" * 70)
        print("COMPANY PERFORMANCE ANALYSIS")
        print("=" * 70)

        overall = report["overall"]

        print("\nOVERALL PERFORMANCE")
        print("-" * 70)

        for key, value in overall.items():
            print(f"{key:<35}: {value}")

        targets = report["targets"]

        print("\nTARGET PERFORMANCE")
        print("-" * 70)

        for key, value in targets.items():
            print(f"{key:<35}: {value}")

        products = report["products"]

        print("\nPRODUCT PERFORMANCE")
        print("-" * 70)

        if products:
            print(
                f"Top product by sales   : "
                f"{products.get('top_product_by_sales')}"
            )

            print(
                f"Top product by profit  : "
                f"{products.get('top_product_by_profit')}"
            )

            print(
                f"Lowest product profit  : "
                f"{products.get('lowest_product_by_profit')}"
            )

        employees = report["employees"]

        print("\nEMPLOYEE PERFORMANCE")
        print("-" * 70)

        if employees:
            print(
                f"Top employee     : "
                f"{employees.get('top_employee')}"
            )

            print(
                f"Lowest employee  : "
                f"{employees.get('lowest_employee')}"
            )

        departments = report["departments"]

        print("\nDEPARTMENT PERFORMANCE")
        print("-" * 70)

        if departments:
            print(
                f"Best department    : "
                f"{departments.get('best_department')}"
            )

            print(
                f"Lowest department  : "
                f"{departments.get('lowest_department')}"
            )

        regions = report["regions"]

        print("\nREGIONAL PERFORMANCE")
        print("-" * 70)

        if regions:
            print(
                f"Best region    : "
                f"{regions.get('best_region')}"
            )

            print(
                f"Lowest region  : "
                f"{regions.get('lowest_region')}"
            )

        segments = report["customer_segments"]

        print("\nCUSTOMER SEGMENT PERFORMANCE")
        print("-" * 70)

        if segments:
            print(
                f"Best segment    : "
                f"{segments.get('best_segment')}"
            )

            print(
                f"Lowest segment  : "
                f"{segments.get('lowest_segment')}"
            )

        channels = report["channels"]

        print("\nSALES CHANNEL PERFORMANCE")
        print("-" * 70)

        if channels:
            print(
                f"Best channel    : "
                f"{channels.get('best_channel')}"
            )

            print(
                f"Lowest channel  : "
                f"{channels.get('lowest_channel')}"
            )

        monthly = report["monthly"]

        print("\nMONTHLY PERFORMANCE")
        print("-" * 70)

        if monthly:

            print(
                f"Best month          : "
                f"{monthly.get('best_month')}"
            )

            print(
                f"Best month sales    : "
                f"{monthly.get('best_month_sales')}"
            )

            print(
                f"Worst month         : "
                f"{monthly.get('worst_month')}"
            )

            print(
                f"Worst month sales   : "
                f"{monthly.get('worst_month_sales')}"
            )

        yearly = report["yearly"]

        print("\nYEARLY PERFORMANCE")
        print("-" * 70)

        if yearly:

            print(
                f"Best year           : "
                f"{yearly.get('best_year')}"
            )

            print(
                f"Worst year          : "
                f"{yearly.get('worst_year')}"
            )

            print(
                f"Comparison status   : "
                f"{yearly.get('comparison_status')}"
            )

            if yearly.get("comparable_months"):

                print(
                    f"Comparable period   : "
                    f"{', '.join(yearly['comparable_months'])}"
                )

                print(
                    f"YoY sales growth    : "
                    f"{yearly.get('year_over_year_sales_growth')}%"
                )

                print(
                    f"YoY profit growth   : "
                    f"{yearly.get('year_over_year_profit_growth')}%"
                )

            else:

                print(
                    "YoY sales growth    : Not available"
                )

                print(
                    "YoY profit growth   : Not available"
                )

        print("\n" + "=" * 70)

        return report