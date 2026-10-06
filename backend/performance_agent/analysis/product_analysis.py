import pandas as pd


class ProductAnalyzer:

    def __init__(self, dataframe):
        self.df = dataframe.copy()

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
                ).fillna(0)

    def _build_product_table(self):

        required = [
            "product",
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

        if "gross_sales" in self.df.columns:
            aggregation["gross_sales"] = (
                "gross_sales",
                "sum"
            )

        if "discount" in self.df.columns:
            aggregation["discount"] = (
                "discount",
                "sum"
            )

        if "cogs" in self.df.columns:
            aggregation["cogs"] = (
                "cogs",
                "sum"
            )

        if "product_id" in self.df.columns:

            aggregation["product_id"] = (
                "product_id",
                "first"
            )

        if "product_category" in self.df.columns:

            aggregation["product_category"] = (
                "product_category",
                "first"
            )

        grouped = (
            self.df
            .groupby(
                "product",
                dropna=False
            )
            .agg(**aggregation)
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

        average_sales_contribution = (
            grouped["sales_contribution"].mean()
        )

        if average_sales_contribution > 0:

            grouped["sales_contribution_index"] = (
                grouped["sales_contribution"]
                / average_sales_contribution
                * 100
            )

        else:

            grouped["sales_contribution_index"] = 0

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
            + grouped["sales_contribution_index"].clip(
                upper=120
            ) * 0.10
        ).clip(
            lower=0,
            upper=100
        ).round(2)

        return grouped

    def analyze(self):

        products = self._build_product_table()

        if products.empty:
            return {
                "status": "Product data unavailable",
                "products": {},
            }

        by_sales = products.sort_values(
            "sales",
            ascending=False
        )

        by_profit = products.sort_values(
            "profit",
            ascending=False
        )

        by_margin = products.sort_values(
            "profit_margin",
            ascending=False
        )

        by_score = products.sort_values(
            "performance_score",
            ascending=False
        )

        low_profit = products.sort_values(
            "profit",
            ascending=True
        )

        high_sales_low_margin = products[
            products["sales"] >= products["sales"].median()
        ].sort_values(
            "profit_margin",
            ascending=True
        )

        low_sales_high_margin = products[
            products["sales"] <= products["sales"].median()
        ].sort_values(
            "profit_margin",
            ascending=False
        )

        records = {}

        for _, row in products.iterrows():

            product = row["product"]

            record = {
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

                "sales_contribution": round(
                    float(row["sales_contribution"]),
                    2
                ),

                "profit_contribution": round(
                    float(row["profit_contribution"]),
                    2
                ),

                "sales_achievement": round(
                    float(row["sales_achievement"]),
                    2
                ),

                "profit_achievement": round(
                    float(row["profit_achievement"]),
                    2
                ),

                "performance_score": round(
                    float(row["performance_score"]),
                    2
                ),
            }

            if "product_id" in products.columns:
                record["product_id"] = row[
                    "product_id"
                ]

            if "product_category" in products.columns:
                record["product_category"] = row[
                    "product_category"
                ]

            if "gross_sales" in products.columns:
                record["gross_sales"] = round(
                    float(row["gross_sales"]),
                    2
                )

            if "discount" in products.columns:
                record["discount"] = round(
                    float(row["discount"]),
                    2
                )

            if "cogs" in products.columns:
                record["cogs"] = round(
                    float(row["cogs"]),
                    2
                )

            records[product] = record

        return {
            "status": "Success",

            "product_count": len(
                products
            ),

            "products": records,

            "top_product_by_sales": (
                by_sales.iloc[0]["product"]
            ),

            "lowest_product_by_sales": (
                by_sales.iloc[-1]["product"]
            ),

            "top_product_by_profit": (
                by_profit.iloc[0]["product"]
            ),

            "lowest_product_by_profit": (
                low_profit.iloc[0]["product"]
            ),

            "top_product_by_margin": (
                by_margin.iloc[0]["product"]
            ),

            "lowest_product_by_margin": (
                by_margin.iloc[-1]["product"]
            ),

            "top_product_by_score": (
                by_score.iloc[0]["product"]
            ),

            "lowest_product_by_score": (
                by_score.iloc[-1]["product"]
            ),

            "high_sales_low_margin_product": (
                high_sales_low_margin.iloc[0]["product"]
                if not high_sales_low_margin.empty
                else None
            ),

            "low_sales_high_margin_product": (
                low_sales_high_margin.iloc[0]["product"]
                if not low_sales_high_margin.empty
                else None
            ),

            "average_profit_margin": round(
                products["profit_margin"].mean(),
                2
            ),

            "average_sales_achievement": round(
                products["sales_achievement"].mean(),
                2
            ),

            "average_profit_achievement": round(
                products["profit_achievement"].mean(),
                2
            ),

            "average_performance_score": round(
                products["performance_score"].mean(),
                2
            ),
        }

    def print_report(self):

        result = self.analyze()

        print("\n" + "=" * 70)
        print("PRODUCT PERFORMANCE ANALYSIS")
        print("=" * 70)

        if result["status"] != "Success":

            print()
            print(result["status"])

            return result

        print()

        print(
            f"Products analyzed          : "
            f"{result['product_count']}"
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
        print("TOP PRODUCTS")
        print("-" * 70)

        print(
            f"Highest sales  : "
            f"{result['top_product_by_sales']}"
        )

        print(
            f"Highest profit : "
            f"{result['top_product_by_profit']}"
        )

        print(
            f"Highest margin : "
            f"{result['top_product_by_margin']}"
        )

        print(
            f"Highest score  : "
            f"{result['top_product_by_score']}"
        )

        print()
        print("PRODUCTS NEEDING ATTENTION")
        print("-" * 70)

        print(
            f"Lowest sales   : "
            f"{result['lowest_product_by_sales']}"
        )

        print(
            f"Lowest profit  : "
            f"{result['lowest_product_by_profit']}"
        )

        print(
            f"Lowest margin  : "
            f"{result['lowest_product_by_margin']}"
        )

        print(
            f"Lowest score   : "
            f"{result['lowest_product_by_score']}"
        )

        print()
        print("OPPORTUNITY FLAGS")
        print("-" * 70)

        print(
            f"High sales / low margin : "
            f"{result['high_sales_low_margin_product']}"
        )

        print(
            f"Low sales / high margin : "
            f"{result['low_sales_high_margin_product']}"
        )

        print()
        print("PRODUCT DETAILS")
        print("-" * 70)

        ranked = sorted(
            result["products"].items(),
            key=lambda item:
                item[1]["performance_score"],
            reverse=True
        )

        for index, (product, data) in enumerate(
            ranked,
            start=1
        ):

            print()
            print(
                f"{index}. {product}"
            )

            if "product_id" in data:

                print(
                    f"   Product ID           : "
                    f"{data['product_id']}"
                )

            if "product_category" in data:

                print(
                    f"   Category             : "
                    f"{data['product_category']}"
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

        print("\n" + "=" * 70)

        return result