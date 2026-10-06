import pandas as pd


class EmployeeAnalyzer:

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

    def _build_employee_table(self):

        required = [
            "employee_id",
            "employee_name",
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
                [
                    "employee_id",
                    "employee_name",
                ],
                dropna=False
            )
            .agg(
                sales=("sales", "sum"),
                profit=("profit", "sum"),
                units_sold=("units_sold", "sum"),
                sales_target=("sales_target", "sum"),
                profit_target=("profit_target", "sum"),
                transactions=("sales", "count"),
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

        average_margin = grouped[
            "profit_margin"
        ].mean()

        average_sales_contribution = grouped[
            "sales_contribution"
        ].mean()

        grouped["margin_score"] = (
            grouped["profit_margin"]
            / average_margin
            * 100
        ).clip(
            upper=120
        ).fillna(0)

        grouped["contribution_score"] = (
            grouped["sales_contribution"]
            / average_sales_contribution
            * 100
        ).clip(
            upper=120
        ).fillna(0)

        grouped["sales_achievement_score"] = (
            grouped["sales_achievement"]
            .clip(
                upper=120
            )
        )

        grouped["profit_achievement_score"] = (
            grouped["profit_achievement"]
            .clip(
                upper=120
            )
        )

        grouped["performance_score"] = (
            grouped["sales_achievement_score"] * 0.40
            + grouped["profit_achievement_score"] * 0.30
            + grouped["margin_score"] * 0.20
            + grouped["contribution_score"] * 0.10
        ).clip(
            lower=0,
            upper=100
        ).round(2)

        return grouped

    def analyze(self):

        employees = self._build_employee_table()

        if employees.empty:
            return {
                "status": "Employee data unavailable",
                "employees": {},
            }

        by_sales = employees.sort_values(
            "sales",
            ascending=False
        )

        by_score = employees.sort_values(
            "performance_score",
            ascending=False
        )

        target_achievers = employees[
            employees["sales_achievement"] >= 100
        ]

        below_target = employees[
            employees["sales_achievement"] < 100
        ]

        employee_records = {}

        for _, row in employees.iterrows():

            employee_records[
                row["employee_id"]
            ] = {
                "employee_name": row["employee_name"],

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

            "employee_count": len(
                employees
            ),

            "employees": employee_records,

            "top_employee_by_sales": (
                by_sales.iloc[0]["employee_name"]
            ),

            "lowest_employee_by_sales": (
                by_sales.iloc[-1]["employee_name"]
            ),

            "top_employee_by_score": (
                by_score.iloc[0]["employee_name"]
            ),

            "lowest_employee_by_score": (
                by_score.iloc[-1]["employee_name"]
            ),

            "employees_meeting_sales_target": len(
                target_achievers
            ),

            "employees_below_sales_target": len(
                below_target
            ),

            "average_sales_achievement": round(
                employees[
                    "sales_achievement"
                ].mean(),
                2
            ),

            "average_profit_achievement": round(
                employees[
                    "profit_achievement"
                ].mean(),
                2
            ),

            "average_performance_score": round(
                employees[
                    "performance_score"
                ].mean(),
                2
            ),
        }

    def print_report(self):

        result = self.analyze()

        print("\n" + "=" * 70)
        print("EMPLOYEE PERFORMANCE ANALYSIS")
        print("=" * 70)

        if result["status"] != "Success":

            print()
            print(result["status"])

            return result

        print()

        print(
            f"Employees analyzed        : "
            f"{result['employee_count']}"
        )

        print(
            f"Average sales achievement : "
            f"{result['average_sales_achievement']}%"
        )

        print(
            f"Average profit achievement: "
            f"{result['average_profit_achievement']}%"
        )

        print(
            f"Average performance score : "
            f"{result['average_performance_score']}"
        )

        print()
        print("TOP PERFORMERS")
        print("-" * 70)

        print(
            f"Highest sales : "
            f"{result['top_employee_by_sales']}"
        )

        print(
            f"Highest score : "
            f"{result['top_employee_by_score']}"
        )

        print()
        print("EMPLOYEES NEEDING ATTENTION")
        print("-" * 70)

        print(
            f"Lowest sales  : "
            f"{result['lowest_employee_by_sales']}"
        )

        print(
            f"Lowest score  : "
            f"{result['lowest_employee_by_score']}"
        )

        print()
        print("TARGET STATUS")
        print("-" * 70)

        print(
            f"Meeting sales target: "
            f"{result['employees_meeting_sales_target']}"
        )

        print(
            f"Below sales target  : "
            f"{result['employees_below_sales_target']}"
        )

        print()
        print("EMPLOYEE DETAILS")
        print("-" * 70)

        ranked = sorted(
            result["employees"].values(),
            key=lambda employee:
                employee["performance_score"],
            reverse=True
        )

        for index, employee in enumerate(
            ranked,
            start=1
        ):

            print()
            print(
                f"{index}. "
                f"{employee['employee_name']}"
            )

            print(
                f"   Sales                : "
                f"{employee['sales']}"
            )

            print(
                f"   Profit               : "
                f"{employee['profit']}"
            )

            print(
                f"   Units sold           : "
                f"{employee['units_sold']}"
            )

            print(
                f"   Transactions         : "
                f"{employee['transactions']}"
            )

            print(
                f"   Sales achievement    : "
                f"{employee['sales_achievement']}%"
            )

            print(
                f"   Profit achievement   : "
                f"{employee['profit_achievement']}%"
            )

            print(
                f"   Profit margin        : "
                f"{employee['profit_margin']}%"
            )

            print(
                f"   Sales contribution   : "
                f"{employee['sales_contribution']}%"
            )

            print(
                f"   Profit contribution  : "
                f"{employee['profit_contribution']}%"
            )

            print(
                f"   Performance score    : "
                f"{employee['performance_score']}"
            )

        print("\n" + "=" * 70)

        return result