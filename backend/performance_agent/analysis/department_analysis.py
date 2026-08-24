import pandas as pd


class DepartmentAnalyzer:

    def __init__(self, dataframe):
        self.df = dataframe.copy()

        numeric_columns = [
            "sales",
            "profit",
            "units_sold",
            "sales_target",
            "profit_target",
        ]

        for column in numeric_columns:
            if column in self.df.columns:
                self.df[column] = pd.to_numeric(
                    self.df[column],
                    errors="coerce"
                ).fillna(0)

    def _build_department_table(self):

        required = [
            "department",
            "sales",
            "profit",
            "units_sold",
            "sales_target",
            "profit_target",
        ]

        missing = [
            column
            for column in required
            if column not in self.df.columns
        ]

        if missing:
            return pd.DataFrame()

        grouped = (
            self.df
            .groupby(
                "department",
                dropna=False
            )
            .agg(
                sales=("sales", "sum"),
                profit=("profit", "sum"),
                units_sold=("units_sold", "sum"),
                sales_target=("sales_target", "sum"),
                profit_target=("profit_target", "sum"),
                transactions=("sales", "count"),
                employees=("employee_id", "nunique")
                if "employee_id" in self.df.columns
                else ("sales", "count"),
            )
            .reset_index()
        )

        grouped["sales_achievement"] = (
            grouped["sales"]
            / grouped["sales_target"]
            * 100
        ).replace(
            [float("inf"), -float("inf")],
            0
        ).fillna(0)

        grouped["profit_achievement"] = (
            grouped["profit"]
            / grouped["profit_target"]
            * 100
        ).replace(
            [float("inf"), -float("inf")],
            0
        ).fillna(0)

        grouped["profit_margin"] = (
            grouped["profit"]
            / grouped["sales"]
            * 100
        ).replace(
            [float("inf"), -float("inf")],
            0
        ).fillna(0)

        total_sales = grouped["sales"].sum()
        total_profit = grouped["profit"].sum()

        grouped["sales_contribution"] = (
            grouped["sales"]
            / total_sales
            * 100
        ).replace(
            [float("inf"), -float("inf")],
            0
        ).fillna(0)

        grouped["profit_contribution"] = (
            grouped["profit"]
            / total_profit
            * 100
        ).replace(
            [float("inf"), -float("inf")],
            0
        ).fillna(0)

        grouped["performance_score"] = (
            grouped["sales_achievement"].clip(
                upper=120
            ) * 0.40
            + grouped["profit_achievement"].clip(
                upper=120
            ) * 0.30
            + (
                grouped["profit_margin"]
                / grouped["profit_margin"].mean()
                * 100
            ).clip(
                upper=120
            ) * 0.20
            + (
                grouped["sales_contribution"]
                / grouped["sales_contribution"].mean()
                * 100
            ).clip(
                upper=120
            ) * 0.10
        ).clip(
            lower=0,
            upper=100
        ).round(2)

        return grouped

    def analyze(self):

        departments = self._build_department_table()

        if departments.empty:
            return {
                "status": "Department data unavailable",
                "departments": {},
            }

        by_sales = departments.sort_values(
            "sales",
            ascending=False
        )

        by_profit = departments.sort_values(
            "profit",
            ascending=False
        )

        by_score = departments.sort_values(
            "performance_score",
            ascending=False
        )

        target_achievers = departments[
            departments["sales_achievement"] >= 100
        ]

        below_target = departments[
            departments["sales_achievement"] < 100
        ]

        records = {}

        for _, row in departments.iterrows():

            records[row["department"]] = {
                "sales": round(
                    float(row["sales"]),
                    2
                ),

                "profit": round(
                    float(row["profit"]),
                    2
                ),

                "units_sold": int(
                    row["units_sold"]
                ),

                "transactions": int(
                    row["transactions"]
                ),

                "employees": int(
                    row["employees"]
                ),

                "sales_target": round(
                    float(row["sales_target"]),
                    2
                ),

                "sales_achievement": round(
                    float(row["sales_achievement"]),
                    2
                ),

                "profit_target": round(
                    float(row["profit_target"]),
                    2
                ),

                "profit_achievement": round(
                    float(row["profit_achievement"]),
                    2
                ),

                "profit_margin": round(
                    float(row["profit_margin"]),
                    2
                ),

                "sales_contribution": round(
                    float(row["sales_contribution"]),
                    2
                ),

                "profit_contribution": round(
                    float(row["profit_contribution"]),
                    2
                ),

                "performance_score": round(
                    float(row["performance_score"]),
                    2
                ),
            }

        return {
            "status": "Success",

            "department_count": len(
                departments
            ),

            "departments": records,

            "best_department_by_sales": (
                by_sales.iloc[0]["department"]
            ),

            "lowest_department_by_sales": (
                by_sales.iloc[-1]["department"]
            ),

            "best_department_by_profit": (
                by_profit.iloc[0]["department"]
            ),

            "best_department_by_score": (
                by_score.iloc[0]["department"]
            ),

            "lowest_department_by_score": (
                by_score.iloc[-1]["department"]
            ),

            "departments_meeting_sales_target": len(
                target_achievers
            ),

            "departments_below_sales_target": len(
                below_target
            ),

            "average_sales_achievement": round(
                departments[
                    "sales_achievement"
                ].mean(),
                2
            ),

            "average_profit_achievement": round(
                departments[
                    "profit_achievement"
                ].mean(),
                2
            ),

            "average_performance_score": round(
                departments[
                    "performance_score"
                ].mean(),
                2
            ),
        }

    def print_report(self):

        result = self.analyze()

        print("\n" + "=" * 70)
        print("DEPARTMENT PERFORMANCE ANALYSIS")
        print("=" * 70)

        if result["status"] != "Success":

            print()
            print(result["status"])

            return result

        print()

        print(
            f"Departments analyzed       : "
            f"{result['department_count']}"
        )

        print(
            f"Average sales achievement  : "
            f"{result['average_sales_achievement']}%"
        )

        print(
            f"Average profit achievement : "
            f"{result['average_profit_achievement']}%"
        )

        print(
            f"Average performance score  : "
            f"{result['average_performance_score']}"
        )

        print()
        print("TOP DEPARTMENTS")
        print("-" * 70)

        print(
            f"Highest sales  : "
            f"{result['best_department_by_sales']}"
        )

        print(
            f"Highest profit : "
            f"{result['best_department_by_profit']}"
        )

        print(
            f"Highest score  : "
            f"{result['best_department_by_score']}"
        )

        print()
        print("DEPARTMENTS NEEDING ATTENTION")
        print("-" * 70)

        print(
            f"Lowest sales : "
            f"{result['lowest_department_by_sales']}"
        )

        print(
            f"Lowest score : "
            f"{result['lowest_department_by_score']}"
        )

        print()
        print("TARGET STATUS")
        print("-" * 70)

        print(
            f"Meeting sales target: "
            f"{result['departments_meeting_sales_target']}"
        )

        print(
            f"Below sales target  : "
            f"{result['departments_below_sales_target']}"
        )

        print()
        print("DEPARTMENT DETAILS")
        print("-" * 70)

        ranked = sorted(
            result["departments"].items(),
            key=lambda item:
                item[1]["performance_score"],
            reverse=True
        )

        for index, (department, data) in enumerate(
            ranked,
            start=1
        ):

            print()
            print(
                f"{index}. {department}"
            )

            print(
                f"   Sales                : "
                f"{data['sales']}"
            )

            print(
                f"   Profit               : "
                f"{data['profit']}"
            )

            print(
                f"   Employees            : "
                f"{data['employees']}"
            )

            print(
                f"   Units sold           : "
                f"{data['units_sold']}"
            )

            print(
                f"   Transactions         : "
                f"{data['transactions']}"
            )

            print(
                f"   Sales achievement    : "
                f"{data['sales_achievement']}%"
            )

            print(
                f"   Profit achievement   : "
                f"{data['profit_achievement']}%"
            )

            print(
                f"   Profit margin        : "
                f"{data['profit_margin']}%"
            )

            print(
                f"   Sales contribution   : "
                f"{data['sales_contribution']}%"
            )

            print(
                f"   Profit contribution  : "
                f"{data['profit_contribution']}%"
            )

            print(
                f"   Performance score    : "
                f"{data['performance_score']}"
            )

        print("\n" + "=" * 70)

        return result