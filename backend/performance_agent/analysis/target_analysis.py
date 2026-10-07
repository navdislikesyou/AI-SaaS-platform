import pandas as pd


class TargetAnalyzer:

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

    def _achievement(self, actual, target):

        if target == 0:
            return None

        return round(
            (actual / target) * 100,
            2
        )

    def _gap(self, actual, target):

        return round(
            actual - target,
            2
        )

    def _status(self, achievement):

        if achievement is None:
            return "No Target"

        if achievement >= 100:
            return "Meeting Target"

        return "Below Target"

    def _performance_score(
        self,
        sales_achievement,
        profit_achievement
    ):

        values = [
            value
            for value in [
                sales_achievement,
                profit_achievement
            ]
            if value is not None
        ]

        if not values:
            return None

        return round(
            sum(values) / len(values),
            2
        )

    def _dimension_analysis(self, dimension):

        required = [
            dimension,
            "sales",
            "profit",
            "sales_target",
            "profit_target",
            "units_sold",
        ]

        missing = [
            column
            for column in required
            if column not in self.df.columns
        ]

        if missing:
            return None

        grouped = (
            self.df
            .groupby(
                dimension,
                dropna=False
            )
            .agg(
                sales=("sales", "sum"),
                profit=("profit", "sum"),
                sales_target=(
                    "sales_target",
                    "sum"
                ),
                profit_target=(
                    "profit_target",
                    "sum"
                ),
                units_sold=(
                    "units_sold",
                    "sum"
                ),
                transactions=(
                    "sales",
                    "count"
                ),
            )
            .reset_index()
        )

        grouped["sales_achievement"] = (
            grouped.apply(
                lambda row:
                self._achievement(
                    row["sales"],
                    row["sales_target"]
                ),
                axis=1
            )
        )

        grouped["profit_achievement"] = (
            grouped.apply(
                lambda row:
                self._achievement(
                    row["profit"],
                    row["profit_target"]
                ),
                axis=1
            )
        )

        grouped["sales_gap"] = (
            grouped.apply(
                lambda row:
                self._gap(
                    row["sales"],
                    row["sales_target"]
                ),
                axis=1
            )
        )

        grouped["profit_gap"] = (
            grouped.apply(
                lambda row:
                self._gap(
                    row["profit"],
                    row["profit_target"]
                ),
                axis=1
            )
        )

        grouped["sales_status"] = (
            grouped["sales_achievement"]
            .apply(self._status)
        )

        grouped["profit_status"] = (
            grouped["profit_achievement"]
            .apply(self._status)
        )

        grouped["performance_score"] = (
            grouped.apply(
                lambda row:
                self._performance_score(
                    row["sales_achievement"],
                    row["profit_achievement"]
                ),
                axis=1
            )
        )

        grouped["sales_target_gap_percent"] = (
            grouped.apply(
                lambda row:
                round(
                    (
                        row["sales"]
                        - row["sales_target"]
                    )
                    / row["sales_target"]
                    * 100,
                    2
                )
                if row["sales_target"] != 0
                else None,
                axis=1
            )
        )

        grouped["profit_target_gap_percent"] = (
            grouped.apply(
                lambda row:
                round(
                    (
                        row["profit"]
                        - row["profit_target"]
                    )
                    / row["profit_target"]
                    * 100,
                    2
                )
                if row["profit_target"] != 0
                else None,
                axis=1
            )
        )

        return grouped

    def _overall_analysis(self):

        required = [
            "sales",
            "profit",
            "sales_target",
            "profit_target",
        ]

        if any(
            column not in self.df.columns
            for column in required
        ):
            return None

        actual_sales = self.df[
            "sales"
        ].sum()

        target_sales = self.df[
            "sales_target"
        ].sum()

        actual_profit = self.df[
            "profit"
        ].sum()

        target_profit = self.df[
            "profit_target"
        ].sum()

        sales_achievement = (
            self._achievement(
                actual_sales,
                target_sales
            )
        )

        profit_achievement = (
            self._achievement(
                actual_profit,
                target_profit
            )
        )

        return {
            "actual_sales": round(
                actual_sales,
                2
            ),

            "sales_target": round(
                target_sales,
                2
            ),

            "sales_gap": self._gap(
                actual_sales,
                target_sales
            ),

            "sales_achievement": (
                sales_achievement
            ),

            "sales_status": self._status(
                sales_achievement
            ),

            "actual_profit": round(
                actual_profit,
                2
            ),

            "profit_target": round(
                target_profit,
                2
            ),

            "profit_gap": self._gap(
                actual_profit,
                target_profit
            ),

            "profit_achievement": (
                profit_achievement
            ),

            "profit_status": self._status(
                profit_achievement
            ),

            "performance_score": (
                self._performance_score(
                    sales_achievement,
                    profit_achievement
                )
            ),
        }

    def _records(self, dataframe, dimension):

        if dataframe is None:
            return []

        records = []

        for _, row in dataframe.iterrows():

            name = row[dimension]

            if pd.isna(name):
                name = "Unknown"

            records.append({
                dimension: str(name),

                "sales": round(
                    float(row["sales"]),
                    2
                ),

                "profit": round(
                    float(row["profit"]),
                    2
                ),

                "sales_target": round(
                    float(row["sales_target"]),
                    2
                ),

                "profit_target": round(
                    float(row["profit_target"]),
                    2
                ),

                "sales_gap": round(
                    float(row["sales_gap"]),
                    2
                ),

                "profit_gap": round(
                    float(row["profit_gap"]),
                    2
                ),

                "sales_achievement": (
                    row["sales_achievement"]
                    if pd.notna(
                        row["sales_achievement"]
                    )
                    else None
                ),

                "profit_achievement": (
                    row["profit_achievement"]
                    if pd.notna(
                        row["profit_achievement"]
                    )
                    else None
                ),

                "sales_status": (
                    row["sales_status"]
                ),

                "profit_status": (
                    row["profit_status"]
                ),

                "performance_score": (
                    row["performance_score"]
                    if pd.notna(
                        row["performance_score"]
                    )
                    else None
                ),

                "units_sold": int(
                    row["units_sold"]
                ),

                "transactions": int(
                    row["transactions"]
                ),
            })

        return records

    def analyze(self):

        overall = self._overall_analysis()

        if overall is None:

            return {
                "status": "Target data unavailable"
            }

        dimensions = [
            "employee_name",
            "department",
            "product",
            "region",
            "customer_name",
            "sales_channel",
            "customer_segment",
        ]

        dimension_results = {}

        for dimension in dimensions:

            result = self._dimension_analysis(
                dimension
            )

            if result is not None:

                dimension_results[
                    dimension
                ] = self._records(
                    result,
                    dimension
                )

        employee_data = (
            dimension_results.get(
                "employee_name",
                []
            )
        )

        department_data = (
            dimension_results.get(
                "department",
                []
            )
        )

        product_data = (
            dimension_results.get(
                "product",
                []
            )
        )

        region_data = (
            dimension_results.get(
                "region",
                []
            )
        )

        customer_data = (
            dimension_results.get(
                "customer_name",
                []
            )
        )

        channel_data = (
            dimension_results.get(
                "sales_channel",
                []
            )
        )

        segment_data = (
            dimension_results.get(
                "customer_segment",
                []
            )
        )

        def highest(
            records,
            field
        ):

            if not records:
                return None

            return max(
                records,
                key=lambda x:
                x[field]
                if x[field] is not None
                else float("-inf")
            )

        def lowest(
            records,
            field
        ):

            if not records:
                return None

            return min(
                records,
                key=lambda x:
                x[field]
                if x[field] is not None
                else float("inf")
            )

        def count_status(
            records,
            field
        ):

            meeting = sum(
                1
                for record in records
                if record[field] == "Meeting Target"
            )

            below = sum(
                1
                for record in records
                if record[field] == "Below Target"
            )

            no_target = sum(
                1
                for record in records
                if record[field] == "No Target"
            )

            return {
                "meeting": meeting,
                "below": below,
                "no_target": no_target,
            }

        def build_summary(
            records
        ):

            if not records:
                return None

            highest_sales = highest(
                records,
                "sales_achievement"
            )

            lowest_sales = lowest(
                records,
                "sales_achievement"
            )

            highest_profit = highest(
                records,
                "profit_achievement"
            )

            lowest_profit = lowest(
                records,
                "profit_achievement"
            )

            largest_sales_gap = lowest(
                records,
                "sales_gap"
            )

            largest_profit_gap = lowest(
                records,
                "profit_gap"
            )

            highest_score = highest(
                records,
                "performance_score"
            )

            status = count_status(
                records,
                "sales_status"
            )

            return {
                "highest_sales_achievement": (
                    highest_sales
                ),

                "lowest_sales_achievement": (
                    lowest_sales
                ),

                "highest_profit_achievement": (
                    highest_profit
                ),

                "lowest_profit_achievement": (
                    lowest_profit
                ),

                "largest_sales_gap": (
                    largest_sales_gap
                ),

                "largest_profit_gap": (
                    largest_profit_gap
                ),

                "highest_performance_score": (
                    highest_score
                ),

                "meeting_sales_target": (
                    status["meeting"]
                ),

                "below_sales_target": (
                    status["below"]
                ),

                "no_sales_target": (
                    status["no_target"]
                ),
            }

        return {
            "status": "Success",

            "overall": overall,

            "employee_targets": employee_data,
            "department_targets": department_data,
            "product_targets": product_data,
            "region_targets": region_data,
            "customer_targets": customer_data,
            "channel_targets": channel_data,
            "segment_targets": segment_data,

            "employee_summary": build_summary(
                employee_data
            ),

            "department_summary": build_summary(
                department_data
            ),

            "product_summary": build_summary(
                product_data
            ),

            "region_summary": build_summary(
                region_data
            ),

            "customer_summary": build_summary(
                customer_data
            ),

            "channel_summary": build_summary(
                channel_data
            ),

            "segment_summary": build_summary(
                segment_data
            ),
        }

    def _print_dimension(
        self,
        title,
        records,
        dimension
    ):

        if not records:
            return

        print()
        print(title)
        print("-" * 70)

        ranked = sorted(
            records,
            key=lambda x:
            x["performance_score"]
            if x["performance_score"]
            is not None
            else -1,
            reverse=True
        )

        for index, row in enumerate(
            ranked,
            start=1
        ):

            print()
            print(
                f"{index}. "
                f"{row[dimension]}"
            )

            print(
                f"   Actual sales        : "
                f"{row['sales']}"
            )

            print(
                f"   Sales target        : "
                f"{row['sales_target']}"
            )

            print(
                f"   Sales gap           : "
                f"{row['sales_gap']}"
            )

            print(
                f"   Sales achievement   : "
                f"{row['sales_achievement']}%"
            )

            print(
                f"   Sales status        : "
                f"{row['sales_status']}"
            )

            print(
                f"   Actual profit       : "
                f"{row['profit']}"
            )

            print(
                f"   Profit target       : "
                f"{row['profit_target']}"
            )

            print(
                f"   Profit gap          : "
                f"{row['profit_gap']}"
            )

            print(
                f"   Profit achievement  : "
                f"{row['profit_achievement']}%"
            )

            print(
                f"   Profit status       : "
                f"{row['profit_status']}"
            )

            print(
                f"   Performance score   : "
                f"{row['performance_score']}"
            )

    def print_report(self):

        result = self.analyze()

        print("\n" + "=" * 70)
        print("TARGET / KPI PERFORMANCE ANALYSIS")
        print("=" * 70)

        if result["status"] != "Success":

            print()
            print(result["status"])

            return result

        overall = result["overall"]

        print()
        print("OVERALL TARGET PERFORMANCE")
        print("-" * 70)

        print(
            f"Actual sales          : "
            f"{overall['actual_sales']}"
        )

        print(
            f"Sales target          : "
            f"{overall['sales_target']}"
        )

        print(
            f"Sales gap             : "
            f"{overall['sales_gap']}"
        )

        print(
            f"Sales achievement     : "
            f"{overall['sales_achievement']}%"
        )

        print(
            f"Sales status          : "
            f"{overall['sales_status']}"
        )

        print()

        print(
            f"Actual profit         : "
            f"{overall['actual_profit']}"
        )

        print(
            f"Profit target         : "
            f"{overall['profit_target']}"
        )

        print(
            f"Profit gap            : "
            f"{overall['profit_gap']}"
        )

        print(
            f"Profit achievement    : "
            f"{overall['profit_achievement']}%"
        )

        print(
            f"Profit status         : "
            f"{overall['profit_status']}"
        )

        print(
            f"Overall KPI score     : "
            f"{overall['performance_score']}"
        )

        summaries = [
            (
                "EMPLOYEE TARGET SUMMARY",
                result["employee_summary"],
                "employee_name",
            ),
            (
                "DEPARTMENT TARGET SUMMARY",
                result["department_summary"],
                "department",
            ),
            (
                "PRODUCT TARGET SUMMARY",
                result["product_summary"],
                "product",
            ),
            (
                "REGION TARGET SUMMARY",
                result["region_summary"],
                "region",
            ),
            (
                "CUSTOMER TARGET SUMMARY",
                result["customer_summary"],
                "customer_name",
            ),
            (
                "CHANNEL TARGET SUMMARY",
                result["channel_summary"],
                "sales_channel",
            ),
            (
                "SEGMENT TARGET SUMMARY",
                result["segment_summary"],
                "customer_segment",
            ),
        ]

        for title, summary, dimension in summaries:

            if summary is None:
                continue

            print()
            print(title)
            print("-" * 70)

            highest_sales = (
                summary[
                    "highest_sales_achievement"
                ]
            )

            lowest_sales = (
                summary[
                    "lowest_sales_achievement"
                ]
            )

            highest_profit = (
                summary[
                    "highest_profit_achievement"
                ]
            )

            lowest_profit = (
                summary[
                    "lowest_profit_achievement"
                ]
            )

            largest_sales_gap = (
                summary[
                    "largest_sales_gap"
                ]
            )

            largest_profit_gap = (
                summary[
                    "largest_profit_gap"
                ]
            )

            highest_score = (
                summary[
                    "highest_performance_score"
                ]
            )

            print(
                f"Meeting sales target : "
                f"{summary['meeting_sales_target']}"
            )

            print(
                f"Below sales target   : "
                f"{summary['below_sales_target']}"
            )

            print(
                f"No sales target      : "
                f"{summary['no_sales_target']}"
            )

            if highest_sales:
                print(
                    f"Highest sales achievement : "
                    f"{highest_sales[dimension]} "
                    f"({highest_sales['sales_achievement']}%)"
                )

            if lowest_sales:
                print(
                    f"Lowest sales achievement  : "
                    f"{lowest_sales[dimension]} "
                    f"({lowest_sales['sales_achievement']}%)"
                )

            if highest_profit:
                print(
                    f"Highest profit achievement: "
                    f"{highest_profit[dimension]} "
                    f"({highest_profit['profit_achievement']}%)"
                )

            if lowest_profit:
                print(
                    f"Lowest profit achievement : "
                    f"{lowest_profit[dimension]} "
                    f"({lowest_profit['profit_achievement']}%)"
                )

            if largest_sales_gap:
                print(
                    f"Largest sales gap         : "
                    f"{largest_sales_gap[dimension]} "
                    f"({largest_sales_gap['sales_gap']})"
                )

            if largest_profit_gap:
                print(
                    f"Largest profit gap        : "
                    f"{largest_profit_gap[dimension]} "
                    f"({largest_profit_gap['profit_gap']})"
                )

            if highest_score:
                print(
                    f"Highest KPI score         : "
                    f"{highest_score[dimension]} "
                    f"({highest_score['performance_score']})"
                )

        self._print_dimension(
            "EMPLOYEE TARGET DETAILS",
            result["employee_targets"],
            "employee_name"
        )

        self._print_dimension(
            "DEPARTMENT TARGET DETAILS",
            result["department_targets"],
            "department"
        )

        self._print_dimension(
            "PRODUCT TARGET DETAILS",
            result["product_targets"],
            "product"
        )

        self._print_dimension(
            "REGION TARGET DETAILS",
            result["region_targets"],
            "region"
        )

        self._print_dimension(
            "CUSTOMER TARGET DETAILS",
            result["customer_targets"],
            "customer_name"
        )

        self._print_dimension(
            "CHANNEL TARGET DETAILS",
            result["channel_targets"],
            "sales_channel"
        )

        self._print_dimension(
            "SEGMENT TARGET DETAILS",
            result["segment_targets"],
            "customer_segment"
        )

        print("\n" + "=" * 70)

        return result