import pandas as pd


class RegionalAnalyzer:

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

    def _calculate_metrics(self, grouped):

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

        if "sales_target" in grouped.columns:

            grouped["sales_achievement"] = (
                grouped["sales"]
                / grouped["sales_target"]
                * 100
            ).replace(
                [float("inf"), -float("inf")],
                0
            ).fillna(0)

        else:

            grouped["sales_achievement"] = 0

        if "profit_target" in grouped.columns:

            grouped["profit_achievement"] = (
                grouped["profit"]
                / grouped["profit_target"]
                * 100
            ).replace(
                [float("inf"), -float("inf")],
                0
            ).fillna(0)

        else:

            grouped["profit_achievement"] = 0

        average_margin = (
            grouped["profit_margin"].mean()
        )

        if average_margin > 0:

            grouped["margin_index"] = (
                grouped["profit_margin"]
                / average_margin
                * 100
            )

        else:

            grouped["margin_index"] = 0

        average_contribution = (
            grouped["sales_contribution"].mean()
        )

        if average_contribution > 0:

            grouped["contribution_index"] = (
                grouped["sales_contribution"]
                / average_contribution
                * 100
            )

        else:

            grouped["contribution_index"] = 0

        grouped["performance_score"] = (
            grouped["sales_achievement"].clip(
                upper=120
            ) * 0.35
            + grouped["profit_achievement"].clip(
                upper=120
            ) * 0.35
            + grouped["margin_index"].clip(
                upper=120
            ) * 0.20
            + grouped["contribution_index"].clip(
                upper=120
            ) * 0.10
        ).clip(
            lower=0,
            upper=100
        ).round(2)

        return grouped

    def _build_region_table(self):

        required = [
            "region",
            "sales",
            "profit",
            "units_sold",
        ]

        missing = [
            column
            for column in required
            if column not in self.df.columns
        ]

        if missing:
            return pd.DataFrame()

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

        if "country" in self.df.columns:

            aggregation["countries"] = (
                "country",
                "nunique"
            )

        grouped = (
            self.df
            .groupby(
                "region",
                dropna=False
            )
            .agg(**aggregation)
            .reset_index()
        )

        return self._calculate_metrics(
            grouped
        )

    def _build_country_table(self):

        required = [
            "country",
            "region",
            "sales",
            "profit",
            "units_sold",
        ]

        missing = [
            column
            for column in required
            if column not in self.df.columns
        ]

        if missing:
            return pd.DataFrame()

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
                    "region",
                    "country",
                ],
                dropna=False
            )
            .agg(**aggregation)
            .reset_index()
        )

        return self._calculate_metrics(
            grouped
        )

    def analyze(self):

        regions = self._build_region_table()

        countries = self._build_country_table()

        if regions.empty:
            return {
                "status": "Regional data unavailable",
                "regions": {},
                "countries": {},
            }

        by_sales = regions.sort_values(
            "sales",
            ascending=False
        )

        by_profit = regions.sort_values(
            "profit",
            ascending=False
        )

        by_margin = regions.sort_values(
            "profit_margin",
            ascending=False
        )

        by_score = regions.sort_values(
            "performance_score",
            ascending=False
        )

        high_sales_low_margin = regions[
            regions["sales"] >= regions["sales"].median()
        ].sort_values(
            "profit_margin",
            ascending=True
        )

        region_records = {}

        for _, row in regions.iterrows():

            region = row["region"]

            region_records[region] = {
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

                "countries": int(
                    row["countries"]
                )
                if "countries" in row
                else 0,

                "sales_achievement": round(
                    float(row["sales_achievement"]),
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

        country_records = {}

        if not countries.empty:

            for _, row in countries.iterrows():

                region = row["region"]
                country = row["country"]

                if region not in country_records:
                    country_records[region] = {}

                country_records[region][country] = {
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

                    "sales_achievement": round(
                        float(row["sales_achievement"]),
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

                    "performance_score": round(
                        float(row["performance_score"]),
                        2
                    ),
                }

        best_country = None
        lowest_country = None

        if not countries.empty:

            country_sales = countries.sort_values(
                "sales",
                ascending=False
            )

            best_country = (
                f"{country_sales.iloc[0]['country']} "
                f"({country_sales.iloc[0]['region']})"
            )

            lowest_country = (
                f"{country_sales.iloc[-1]['country']} "
                f"({country_sales.iloc[-1]['region']})"
            )

        return {
            "status": "Success",

            "region_count": len(
                regions
            ),

            "country_count": (
                len(countries)
                if not countries.empty
                else 0
            ),

            "regions": region_records,

            "countries": country_records,

            "top_region_by_sales": (
                by_sales.iloc[0]["region"]
            ),

            "lowest_region_by_sales": (
                by_sales.iloc[-1]["region"]
            ),

            "top_region_by_profit": (
                by_profit.iloc[0]["region"]
            ),

            "lowest_region_by_profit": (
                by_profit.iloc[-1]["region"]
            ),

            "top_region_by_margin": (
                by_margin.iloc[0]["region"]
            ),

            "lowest_region_by_margin": (
                by_margin.iloc[-1]["region"]
            ),

            "top_region_by_score": (
                by_score.iloc[0]["region"]
            ),

            "lowest_region_by_score": (
                by_score.iloc[-1]["region"]
            ),

            "best_country_by_sales": best_country,

            "lowest_country_by_sales": lowest_country,

            "high_sales_low_margin_region": (
                high_sales_low_margin.iloc[0]["region"]
                if not high_sales_low_margin.empty
                else None
            ),

            "average_profit_margin": round(
                regions["profit_margin"].mean(),
                2
            ),

            "average_sales_achievement": round(
                regions["sales_achievement"].mean(),
                2
            ),

            "average_profit_achievement": round(
                regions["profit_achievement"].mean(),
                2
            ),

            "average_performance_score": round(
                regions["performance_score"].mean(),
                2
            ),
        }

    def print_report(self):

        result = self.analyze()

        print("\n" + "=" * 70)
        print("REGIONAL PERFORMANCE ANALYSIS")
        print("=" * 70)

        if result["status"] != "Success":

            print()
            print(result["status"])

            return result

        print()

        print(
            f"Regions analyzed           : "
            f"{result['region_count']}"
        )

        print(
            f"Countries analyzed         : "
            f"{result['country_count']}"
        )

        print(
            f"Average profit margin      : "
            f"{result['average_profit_margin']}%"
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
        print("TOP REGIONS")
        print("-" * 70)

        print(
            f"Highest sales  : "
            f"{result['top_region_by_sales']}"
        )

        print(
            f"Highest profit : "
            f"{result['top_region_by_profit']}"
        )

        print(
            f"Highest margin : "
            f"{result['top_region_by_margin']}"
        )

        print(
            f"Highest score  : "
            f"{result['top_region_by_score']}"
        )

        print()
        print("REGIONS NEEDING ATTENTION")
        print("-" * 70)

        print(
            f"Lowest sales  : "
            f"{result['lowest_region_by_sales']}"
        )

        print(
            f"Lowest profit : "
            f"{result['lowest_region_by_profit']}"
        )

        print(
            f"Lowest margin : "
            f"{result['lowest_region_by_margin']}"
        )

        print(
            f"Lowest score  : "
            f"{result['lowest_region_by_score']}"
        )

        print()
        print("OPPORTUNITY FLAGS")
        print("-" * 70)

        print(
            f"High sales / low margin : "
            f"{result['high_sales_low_margin_region']}"
        )

        print()
        print("COUNTRY HIGHLIGHTS")
        print("-" * 70)

        print(
            f"Highest country sales : "
            f"{result['best_country_by_sales']}"
        )

        print(
            f"Lowest country sales  : "
            f"{result['lowest_country_by_sales']}"
        )

        print()
        print("REGION DETAILS")
        print("-" * 70)

        ranked_regions = sorted(
            result["regions"].items(),
            key=lambda item:
                item[1]["performance_score"],
            reverse=True
        )

        for index, (region, data) in enumerate(
            ranked_regions,
            start=1
        ):

            print()
            print(
                f"{index}. {region}"
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
                f"   Countries            : "
                f"{data['countries']}"
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

            if region in result["countries"]:

                print()
                print("   Countries:")

                country_items = sorted(
                    result["countries"][region].items(),
                    key=lambda item:
                        item[1]["sales"],
                    reverse=True
                )

                for country, country_data in country_items:

                    print(
                        f"      {country}"
                    )

                    print(
                        f"         Sales       : "
                        f"{country_data['sales']}"
                    )

                    print(
                        f"         Profit      : "
                        f"{country_data['profit']}"
                    )

                    print(
                        f"         Margin      : "
                        f"{country_data['profit_margin']}%"
                    )

                    print(
                        f"         Performance : "
                        f"{country_data['performance_score']}"
                    )

        print("\n" + "=" * 70)

        return result