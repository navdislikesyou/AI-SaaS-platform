import pandas as pd


class ChannelAnalyzer:

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

        average_margin = grouped["profit_margin"].mean()

        if average_margin > 0:
            grouped["margin_index"] = (
                grouped["profit_margin"]
                / average_margin
                * 100
            )
        else:
            grouped["margin_index"] = 0

        average_sales = grouped["sales"].mean()

        if average_sales > 0:
            grouped["sales_index"] = (
                grouped["sales"]
                / average_sales
                * 100
            )
        else:
            grouped["sales_index"] = 0

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
            + grouped["sales_index"].clip(
                upper=120
            ) * 0.10
        ).clip(
            lower=0,
            upper=100
        ).round(2)

        return grouped

    def _build_channel_table(self):

        required = [
            "sales_channel",
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
                "sales_channel",
                dropna=False
            )
            .agg(**aggregation)
            .reset_index()
        )

        return self._calculate_metrics(grouped)

    def _build_region_channel_table(self):

        required = [
            "region",
            "sales_channel",
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

        grouped = (
            self.df
            .groupby(
                [
                    "region",
                    "sales_channel",
                ],
                dropna=False
            )
            .agg(
                sales=("sales", "sum"),
                profit=("profit", "sum"),
                units_sold=("units_sold", "sum"),
                transactions=("sales", "count"),
            )
            .reset_index()
        )

        grouped["profit_margin"] = (
            grouped["profit"]
            / grouped["sales"]
            * 100
        ).replace(
            [float("inf"), -float("inf")],
            0
        ).fillna(0)

        return grouped

    def _build_segment_channel_table(self):

        required = [
            "customer_segment",
            "sales_channel",
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

        grouped = (
            self.df
            .groupby(
                [
                    "customer_segment",
                    "sales_channel",
                ],
                dropna=False
            )
            .agg(
                sales=("sales", "sum"),
                profit=("profit", "sum"),
                units_sold=("units_sold", "sum"),
                transactions=("sales", "count"),
            )
            .reset_index()
        )

        grouped["profit_margin"] = (
            grouped["profit"]
            / grouped["sales"]
            * 100
        ).replace(
            [float("inf"), -float("inf")],
            0
        ).fillna(0)

        return grouped

    def analyze(self):

        channels = self._build_channel_table()
        region_channels = self._build_region_channel_table()
        segment_channels = self._build_segment_channel_table()

        if channels.empty:
            return {
                "status": "Sales channel data unavailable",
                "channels": {},
                "regions": {},
                "segments": {},
            }

        by_sales = channels.sort_values(
            "sales",
            ascending=False
        )

        by_profit = channels.sort_values(
            "profit",
            ascending=False
        )

        by_margin = channels.sort_values(
            "profit_margin",
            ascending=False
        )

        by_score = channels.sort_values(
            "performance_score",
            ascending=False
        )

        high_sales_low_margin = channels[
            channels["sales"] >= channels["sales"].median()
        ].sort_values(
            "profit_margin",
            ascending=True
        )

        low_sales_high_margin = channels[
            channels["sales"] <= channels["sales"].median()
        ].sort_values(
            "profit_margin",
            ascending=False
        )

        channel_records = {}

        for _, row in channels.iterrows():

            channel = row["sales_channel"]

            channel_records[channel] = {
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

        region_records = {}

        if not region_channels.empty:

            for _, row in region_channels.iterrows():

                region = row["region"]
                channel = row["sales_channel"]

                if region not in region_records:
                    region_records[region] = {}

                region_records[region][channel] = {
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
                        float(row["profit_margin"]),
                        2
                    ),
                }

        segment_records = {}

        if not segment_channels.empty:

            for _, row in segment_channels.iterrows():

                segment = row[
                    "customer_segment"
                ]

                channel = row[
                    "sales_channel"
                ]

                if segment not in segment_records:
                    segment_records[segment] = {}

                segment_records[segment][channel] = {
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
                        float(row["profit_margin"]),
                        2
                    ),
                }

        return {
            "status": "Success",

            "channel_count": len(
                channels
            ),

            "channels": channel_records,

            "region_channels": region_records,

            "segment_channels": segment_records,

            "top_channel_by_sales": (
                by_sales.iloc[0]["sales_channel"]
            ),

            "lowest_channel_by_sales": (
                by_sales.iloc[-1]["sales_channel"]
            ),

            "top_channel_by_profit": (
                by_profit.iloc[0]["sales_channel"]
            ),

            "lowest_channel_by_profit": (
                by_profit.iloc[-1]["sales_channel"]
            ),

            "top_channel_by_margin": (
                by_margin.iloc[0]["sales_channel"]
            ),

            "lowest_channel_by_margin": (
                by_margin.iloc[-1]["sales_channel"]
            ),

            "top_channel_by_score": (
                by_score.iloc[0]["sales_channel"]
            ),

            "lowest_channel_by_score": (
                by_score.iloc[-1]["sales_channel"]
            ),

            "high_sales_low_margin_channel": (
                high_sales_low_margin.iloc[0][
                    "sales_channel"
                ]
                if not high_sales_low_margin.empty
                else None
            ),

            "low_sales_high_margin_channel": (
                low_sales_high_margin.iloc[0][
                    "sales_channel"
                ]
                if not low_sales_high_margin.empty
                else None
            ),

            "average_profit_margin": round(
                channels["profit_margin"].mean(),
                2
            ),

            "average_sales_achievement": round(
                channels["sales_achievement"].mean(),
                2
            ),

            "average_profit_achievement": round(
                channels["profit_achievement"].mean(),
                2
            ),

            "average_performance_score": round(
                channels["performance_score"].mean(),
                2
            ),
        }

    def print_report(self):

        result = self.analyze()

        print("\n" + "=" * 70)
        print("SALES CHANNEL PERFORMANCE ANALYSIS")
        print("=" * 70)

        if result["status"] != "Success":

            print()
            print(result["status"])

            return result

        print()

        print(
            f"Channels analyzed         : "
            f"{result['channel_count']}"
        )

        print(
            f"Average profit margin     : "
            f"{result['average_profit_margin']}%"
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
        print("TOP CHANNELS")
        print("-" * 70)

        print(
            f"Highest sales  : "
            f"{result['top_channel_by_sales']}"
        )

        print(
            f"Highest profit : "
            f"{result['top_channel_by_profit']}"
        )

        print(
            f"Highest margin : "
            f"{result['top_channel_by_margin']}"
        )

        print(
            f"Highest score  : "
            f"{result['top_channel_by_score']}"
        )

        print()
        print("CHANNELS NEEDING ATTENTION")
        print("-" * 70)

        print(
            f"Lowest sales   : "
            f"{result['lowest_channel_by_sales']}"
        )

        print(
            f"Lowest profit  : "
            f"{result['lowest_channel_by_profit']}"
        )

        print(
            f"Lowest margin  : "
            f"{result['lowest_channel_by_margin']}"
        )

        print(
            f"Lowest score   : "
            f"{result['lowest_channel_by_score']}"
        )

        print()
        print("CHANNEL OPPORTUNITIES")
        print("-" * 70)

        print(
            f"High sales / low margin : "
            f"{result['high_sales_low_margin_channel']}"
        )

        print(
            f"Low sales / high margin : "
            f"{result['low_sales_high_margin_channel']}"
        )

        print()
        print("CHANNEL DETAILS")
        print("-" * 70)

        ranked = sorted(
            result["channels"].items(),
            key=lambda item:
                item[1]["performance_score"],
            reverse=True
        )

        for index, (channel, data) in enumerate(
            ranked,
            start=1
        ):

            print()
            print(
                f"{index}. {channel}"
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

        if result["region_channels"]:

            print()
            print("CHANNEL BY REGION")
            print("-" * 70)

            for region, channel_data in (
                result["region_channels"].items()
            ):

                print()
                print(
                    f"{region}"
                )

                for channel, data in sorted(
                    channel_data.items(),
                    key=lambda item:
                        item[1]["sales"],
                    reverse=True
                ):

                    print(
                        f"   {channel}"
                    )

                    print(
                        f"      Sales       : "
                        f"{data['sales']}"
                    )

                    print(
                        f"      Profit      : "
                        f"{data['profit']}"
                    )

                    print(
                        f"      Margin      : "
                        f"{data['profit_margin']}%"
                    )

        if result["segment_channels"]:

            print()
            print("CHANNEL BY CUSTOMER SEGMENT")
            print("-" * 70)

            for segment, channel_data in (
                result["segment_channels"].items()
            ):

                print()
                print(
                    f"{segment}"
                )

                for channel, data in sorted(
                    channel_data.items(),
                    key=lambda item:
                        item[1]["sales"],
                    reverse=True
                ):

                    print(
                        f"   {channel}"
                    )

                    print(
                        f"      Sales       : "
                        f"{data['sales']}"
                    )

                    print(
                        f"      Profit      : "
                        f"{data['profit']}"
                    )

                    print(
                        f"      Margin      : "
                        f"{data['profit_margin']}%"
                    )

        print("\n" + "=" * 70)

        return result