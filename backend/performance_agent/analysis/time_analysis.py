import pandas as pd


class TimeAnalyzer:

    REQUIRED_COLUMNS = {"date"}

    def __init__(self, dataframe):
        self.df = dataframe.copy()

        missing = self.REQUIRED_COLUMNS - set(self.df.columns)

        if missing:
            raise KeyError(
                f"TimeAnalyzer requires column(s): {sorted(missing)}"
            )

        self.df["date"] = pd.to_datetime(
            self.df["date"],
            errors="coerce"
        )

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

        self.df = self.df.dropna(
            subset=["date"]
        )

        self.df["year"] = self.df["date"].dt.year
        self.df["month_number"] = self.df[
            "date"
        ].dt.month

        self.df["month_name"] = self.df[
            "date"
        ].dt.strftime("%B")

        self.df["year_month"] = (
            self.df["date"]
            .dt.to_period("M")
            .astype(str)
        )

    def _calculate_growth(self, current, previous):

        if previous is None:
            return None

        if pd.isna(previous):
            return None

        if previous == 0:
            return None

        return round(
            ((current - previous) / previous) * 100,
            2
        )

    def _monthly_table(self):

        aggregation = {
            "sales": ("sales", "sum"),
            "profit": ("profit", "sum"),
            "units_sold": ("units_sold", "sum"),
            "transactions": ("sales", "count"),
        }

        if "sales_target" in self.df.columns:
            aggregation["sales_target"] = (
                "sales_target",
                "sum"
            )

        if "profit_target" in self.df.columns:
            aggregation["profit_target"] = (
                "profit_target",
                "sum"
            )

        grouped = (
            self.df
            .groupby(
                [
                    "year",
                    "month_number",
                    "month_name",
                    "year_month",
                ],
                dropna=False
            )
            .agg(**aggregation)
            .reset_index()
            .sort_values(
                [
                    "year",
                    "month_number",
                ]
            )
            .reset_index(drop=True)
        )

        grouped["profit_margin"] = (
            grouped["profit"]
            / grouped["sales"]
            * 100
        ).replace(
            [float("inf"), -float("inf")],
            0
        ).fillna(0)

        if "sales_target" in grouped.columns:
            grouped["sales_achievement"] = (
                grouped["sales"]
                / grouped["sales_target"]
                * 100
            ).replace(
                [float("inf"), -float("inf")],
                0
            ).fillna(0)

        if "profit_target" in grouped.columns:
            grouped["profit_achievement"] = (
                grouped["profit"]
                / grouped["profit_target"]
                * 100
            ).replace(
                [float("inf"), -float("inf")],
                0
            ).fillna(0)

        grouped["previous_month_sales"] = (
            grouped["sales"].shift(1)
        )

        grouped["previous_month_profit"] = (
            grouped["profit"].shift(1)
        )

        grouped["monthly_sales_growth"] = None
        grouped["monthly_profit_growth"] = None

        for index in range(1, len(grouped)):

            current_sales = grouped.loc[
                index,
                "sales"
            ]

            previous_sales = grouped.loc[
                index - 1,
                "sales"
            ]

            current_profit = grouped.loc[
                index,
                "profit"
            ]

            previous_profit = grouped.loc[
                index - 1,
                "profit"
            ]

            grouped.loc[
                index,
                "monthly_sales_growth"
            ] = self._calculate_growth(
                current_sales,
                previous_sales
            )

            grouped.loc[
                index,
                "monthly_profit_growth"
            ] = self._calculate_growth(
                current_profit,
                previous_profit
            )

        return grouped

    def _yearly_table(self):

        aggregation = {
            "sales": ("sales", "sum"),
            "profit": ("profit", "sum"),
            "units_sold": ("units_sold", "sum"),
            "transactions": ("sales", "count"),
        }

        if "sales_target" in self.df.columns:
            aggregation["sales_target"] = (
                "sales_target",
                "sum"
            )

        if "profit_target" in self.df.columns:
            aggregation["profit_target"] = (
                "profit_target",
                "sum"
            )

        grouped = (
            self.df
            .groupby(
                "year",
                dropna=False
            )
            .agg(**aggregation)
            .reset_index()
            .sort_values("year")
            .reset_index(drop=True)
        )

        grouped["profit_margin"] = (
            grouped["profit"]
            / grouped["sales"]
            * 100
        ).replace(
            [float("inf"), -float("inf")],
            0
        ).fillna(0)

        if "sales_target" in grouped.columns:
            grouped["sales_achievement"] = (
                grouped["sales"]
                / grouped["sales_target"]
                * 100
            ).replace(
                [float("inf"), -float("inf")],
                0
            ).fillna(0)

        if "profit_target" in grouped.columns:
            grouped["profit_achievement"] = (
                grouped["profit"]
                / grouped["profit_target"]
                * 100
            ).replace(
                [float("inf"), -float("inf")],
                0
            ).fillna(0)

        grouped["previous_year_sales"] = (
            grouped["sales"].shift(1)
        )

        grouped["previous_year_profit"] = (
            grouped["profit"].shift(1)
        )

        grouped["yoy_sales_growth"] = None
        grouped["yoy_profit_growth"] = None

        for index in range(1, len(grouped)):

            current_sales = grouped.loc[
                index,
                "sales"
            ]

            previous_sales = grouped.loc[
                index - 1,
                "sales"
            ]

            current_profit = grouped.loc[
                index,
                "profit"
            ]

            previous_profit = grouped.loc[
                index - 1,
                "profit"
            ]

            grouped.loc[
                index,
                "yoy_sales_growth"
            ] = self._calculate_growth(
                current_sales,
                previous_sales
            )

            grouped.loc[
                index,
                "yoy_profit_growth"
            ] = self._calculate_growth(
                current_profit,
                previous_profit
            )

        return grouped

    def _comparable_periods(self):

        yearly_months = (
            self.df
            .groupby("year")["month_number"]
            .apply(
                lambda values:
                set(
                    values
                    .dropna()
                    .astype(int)
                )
            )
            .to_dict()
        )

        years = sorted(
            yearly_months.keys()
        )

        comparisons = []

        for index in range(1, len(years)):

            previous_year = years[
                index - 1
            ]

            current_year = years[
                index
            ]

            common_months = sorted(
                yearly_months[
                    previous_year
                ]
                &
                yearly_months[
                    current_year
                ]
            )

            if not common_months:
                continue

            previous_df = self.df[
                (
                    self.df["year"]
                    == previous_year
                )
                &
                (
                    self.df["month_number"]
                    .isin(common_months)
                )
            ]

            current_df = self.df[
                (
                    self.df["year"]
                    == current_year
                )
                &
                (
                    self.df["month_number"]
                    .isin(common_months)
                )
            ]

            previous_sales = previous_df[
                "sales"
            ].sum()

            current_sales = current_df[
                "sales"
            ].sum()

            previous_profit = previous_df[
                "profit"
            ].sum()

            current_profit = current_df[
                "profit"
            ].sum()

            comparisons.append({
                "previous_year": previous_year,
                "current_year": current_year,
                "common_months": common_months,
                "month_count": len(
                    common_months
                ),
                "previous_sales": round(
                    previous_sales,
                    2
                ),
                "current_sales": round(
                    current_sales,
                    2
                ),
                "sales_growth": (
                    self._calculate_growth(
                        current_sales,
                        previous_sales
                    )
                ),
                "previous_profit": round(
                    previous_profit,
                    2
                ),
                "current_profit": round(
                    current_profit,
                    2
                ),
                "profit_growth": (
                    self._calculate_growth(
                        current_profit,
                        previous_profit
                    )
                ),
            })

        return comparisons

    def _growth_streaks(self, monthly):

        growth_values = (
            monthly[
                "monthly_sales_growth"
            ]
            .dropna()
            .tolist()
        )

        positive_streak = 0
        negative_streak = 0

        longest_positive = 0
        longest_negative = 0

        for value in growth_values:

            if value > 0:

                positive_streak += 1
                negative_streak = 0

            elif value < 0:

                negative_streak += 1
                positive_streak = 0

            else:

                positive_streak = 0
                negative_streak = 0

            longest_positive = max(
                longest_positive,
                positive_streak
            )

            longest_negative = max(
                longest_negative,
                negative_streak
            )

        return {
            "longest_growth_streak":
                longest_positive,

            "longest_decline_streak":
                longest_negative,
        }

    def analyze(self):

        monthly = self._monthly_table()
        yearly = self._yearly_table()

        if monthly.empty:

            return {
                "status": "Time data unavailable"
            }

        best_month = monthly.loc[
            monthly["sales"].idxmax()
        ]

        worst_month = monthly.loc[
            monthly["sales"].idxmin()
        ]

        best_profit_month = monthly.loc[
            monthly["profit"].idxmax()
        ]

        worst_profit_month = monthly.loc[
            monthly["profit"].idxmin()
        ]

        best_year = yearly.loc[
            yearly["sales"].idxmax()
        ]

        worst_year = yearly.loc[
            yearly["sales"].idxmin()
        ]

        best_profit_year = yearly.loc[
            yearly["profit"].idxmax()
        ]

        worst_profit_year = yearly.loc[
            yearly["profit"].idxmin()
        ]

        comparable = (
            self._comparable_periods()
        )

        latest_comparison = (
            comparable[-1]
            if comparable
            else None
        )

        streaks = self._growth_streaks(
            monthly
        )

        monthly_records = []

        for _, row in monthly.iterrows():

            sales_growth = row[
                "monthly_sales_growth"
            ]

            profit_growth = row[
                "monthly_profit_growth"
            ]

            monthly_records.append({
                "year_month": row[
                    "year_month"
                ],

                "year": int(
                    row["year"]
                ),

                "month_number": int(
                    row["month_number"]
                ),

                "month_name": row[
                    "month_name"
                ],

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

                "profit_margin": round(
                    float(
                        row["profit_margin"]
                    ),
                    2
                ),

                "monthly_sales_growth": (
                    round(
                        float(sales_growth),
                        2
                    )
                    if pd.notna(
                        sales_growth
                    )
                    else None
                ),

                "monthly_profit_growth": (
                    round(
                        float(profit_growth),
                        2
                    )
                    if pd.notna(
                        profit_growth
                    )
                    else None
                ),
            })

        yearly_records = []

        for _, row in yearly.iterrows():

            sales_growth = row[
                "yoy_sales_growth"
            ]

            profit_growth = row[
                "yoy_profit_growth"
            ]

            yearly_records.append({
                "year": int(
                    row["year"]
                ),

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

                "profit_margin": round(
                    float(
                        row["profit_margin"]
                    ),
                    2
                ),

                "yoy_sales_growth": (
                    round(
                        float(sales_growth),
                        2
                    )
                    if pd.notna(
                        sales_growth
                    )
                    else None
                ),

                "yoy_profit_growth": (
                    round(
                        float(profit_growth),
                        2
                    )
                    if pd.notna(
                        profit_growth
                    )
                    else None
                ),
            })

        return {
            "status": "Success",

            "year_count": len(
                yearly
            ),

            "month_count": len(
                monthly
            ),

            "monthly": monthly_records,

            "yearly": yearly_records,

            "best_month": (
                best_month[
                    "year_month"
                ]
            ),

            "best_month_sales": round(
                float(
                    best_month["sales"]
                ),
                2
            ),

            "worst_month": (
                worst_month[
                    "year_month"
                ]
            ),

            "worst_month_sales": round(
                float(
                    worst_month["sales"]
                ),
                2
            ),

            "best_profit_month": (
                best_profit_month[
                    "year_month"
                ]
            ),

            "worst_profit_month": (
                worst_profit_month[
                    "year_month"
                ]
            ),

            "best_year": int(
                best_year["year"]
            ),

            "worst_year": int(
                worst_year["year"]
            ),

            "best_profit_year": int(
                best_profit_year["year"]
            ),

            "worst_profit_year": int(
                worst_profit_year["year"]
            ),

            "comparable_periods": (
                comparable
            ),

            "latest_comparison": (
                latest_comparison
            ),

            "longest_growth_streak": (
                streaks[
                    "longest_growth_streak"
                ]
            ),

            "longest_decline_streak": (
                streaks[
                    "longest_decline_streak"
                ]
            ),

            "average_monthly_sales": round(
                monthly["sales"].mean(),
                2
            ),

            "average_monthly_profit": round(
                monthly["profit"].mean(),
                2
            ),
        }

    def print_report(self):

        result = self.analyze()

        print("\n" + "=" * 70)
        print("TIME / TREND PERFORMANCE ANALYSIS")
        print("=" * 70)

        if result["status"] != "Success":

            print()
            print(result["status"])

            return result

        print()

        print(
            f"Years analyzed            : "
            f"{result['year_count']}"
        )

        print(
            f"Monthly periods analyzed  : "
            f"{result['month_count']}"
        )

        print(
            f"Average monthly sales     : "
            f"{result['average_monthly_sales']}"
        )

        print(
            f"Average monthly profit    : "
            f"{result['average_monthly_profit']}"
        )

        print()
        print("MONTHLY PERFORMANCE")
        print("-" * 70)

        print(
            f"Best month          : "
            f"{result['best_month']}"
        )

        print(
            f"Best month sales    : "
            f"{result['best_month_sales']}"
        )

        print(
            f"Worst month         : "
            f"{result['worst_month']}"
        )

        print(
            f"Worst month sales   : "
            f"{result['worst_month_sales']}"
        )

        print(
            f"Best profit month   : "
            f"{result['best_profit_month']}"
        )

        print(
            f"Worst profit month  : "
            f"{result['worst_profit_month']}"
        )

        print()
        print("YEARLY PERFORMANCE")
        print("-" * 70)

        print(
            f"Best year           : "
            f"{result['best_year']}"
        )

        print(
            f"Worst year          : "
            f"{result['worst_year']}"
        )

        print(
            f"Best profit year    : "
            f"{result['best_profit_year']}"
        )

        print(
            f"Worst profit year   : "
            f"{result['worst_profit_year']}"
        )

        print()
        print("YEAR-OVER-YEAR COMPARISON")
        print("-" * 70)

        if result["latest_comparison"]:

            comparison = (
                result["latest_comparison"]
            )

            month_names = [
                pd.Timestamp(
                    2000,
                    month,
                    1
                ).strftime("%B")
                for month in
                comparison[
                    "common_months"
                ]
            ]

            print(
                f"Previous year       : "
                f"{comparison['previous_year']}"
            )

            print(
                f"Current year        : "
                f"{comparison['current_year']}"
            )

            print(
                f"Comparable months   : "
                f"{', '.join(month_names)}"
            )

            sales_growth = (
                comparison[
                    "sales_growth"
                ]
            )

            profit_growth = (
                comparison[
                    "profit_growth"
                ]
            )

            print(
                f"Sales growth        : "
                f"{sales_growth}%"
            )

            print(
                f"Profit growth       : "
                f"{profit_growth}%"
            )

            print(
                "Comparison status   : Valid"
            )

        else:

            print(
                "Comparison status   : "
                "Not enough comparable periods"
            )

        print()
        print("GROWTH PATTERNS")
        print("-" * 70)

        print(
            f"Longest growth streak  : "
            f"{result['longest_growth_streak']} months"
        )

        print(
            f"Longest decline streak : "
            f"{result['longest_decline_streak']} months"
        )

        print()
        print("MONTHLY DETAILS")
        print("-" * 70)

        for row in result["monthly"]:

            print()
            print(
                f"{row['year_month']}"
            )

            print(
                f"   Sales             : "
                f"{row['sales']}"
            )

            print(
                f"   Profit            : "
                f"{row['profit']}"
            )

            print(
                f"   Units sold        : "
                f"{row['units_sold']}"
            )

            print(
                f"   Transactions      : "
                f"{row['transactions']}"
            )

            print(
                f"   Profit margin     : "
                f"{row['profit_margin']}%"
            )

            sales_growth = (
                row[
                    "monthly_sales_growth"
                ]
            )

            profit_growth = (
                row[
                    "monthly_profit_growth"
                ]
            )

            print(
                f"   Sales growth      : "
                f"{sales_growth}%"
            )

            print(
                f"   Profit growth     : "
                f"{profit_growth}%"
            )

        print()
        print("YEARLY DETAILS")
        print("-" * 70)

        for row in result["yearly"]:

            print()
            print(
                f"{row['year']}"
            )

            print(
                f"   Sales             : "
                f"{row['sales']}"
            )

            print(
                f"   Profit            : "
                f"{row['profit']}"
            )

            print(
                f"   Units sold        : "
                f"{row['units_sold']}"
            )

            print(
                f"   Transactions      : "
                f"{row['transactions']}"
            )

            print(
                f"   Profit margin     : "
                f"{row['profit_margin']}%"
            )

            print(
                f"   YoY sales growth  : "
                f"{row['yoy_sales_growth']}%"
            )

            print(
                f"   YoY profit growth : "
                f"{row['yoy_profit_growth']}%"
            )

        print("\n" + "=" * 70)

        return result