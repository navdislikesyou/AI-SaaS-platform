from pathlib import Path

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).parent
SOURCE_FILE = BASE_DIR / "data" / "Financials.csv"
OUTPUT_FILE = BASE_DIR / "data" / "Financials_standardized.csv"


def clean_money(series):
    return pd.to_numeric(
        series.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.replace("-", "0", regex=False)
        .str.strip(),
        errors="coerce"
    )


def create_dataset():

    df = pd.read_csv(SOURCE_FILE)

    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )

    rng = np.random.default_rng(42)

    employees = [
        (
            "E001",
            "Aarav Sharma",
            "Sales Executive",
            "Rohan Mehta",
            "SMB Sales"
        ),
        (
            "E002",
            "Priya Singh",
            "Sales Executive",
            "Rohan Mehta",
            "Enterprise Sales"
        ),
        (
            "E003",
            "Rahul Verma",
            "Senior Sales Executive",
            "Rohan Mehta",
            "Public Sector Sales"
        ),
        (
            "E004",
            "Ananya Patel",
            "Sales Executive",
            "Sneha Kapoor",
            "Midmarket Sales"
        ),
        (
            "E005",
            "Karan Gupta",
            "Sales Executive",
            "Sneha Kapoor",
            "SMB Sales"
        ),
        (
            "E006",
            "Meera Joshi",
            "Account Manager",
            "Sneha Kapoor",
            "Enterprise Sales"
        ),
        (
            "E007",
            "Arjun Malhotra",
            "Account Manager",
            "Vikram Rao",
            "Public Sector Sales"
        ),
        (
            "E008",
            "Ishita Sharma",
            "Sales Executive",
            "Vikram Rao",
            "Midmarket Sales"
        ),
        (
            "E009",
            "Aditya Jain",
            "Senior Sales Executive",
            "Vikram Rao",
            "SMB Sales"
        ),
        (
            "E010",
            "Neha Agarwal",
            "Sales Executive",
            "Rohan Mehta",
            "Public Sector Sales"
        ),
    ]

    customers = [
        (
            "C001",
            "Northstar Industries",
            "Government"
        ),
        (
            "C002",
            "Vertex Solutions",
            "Enterprise"
        ),
        (
            "C003",
            "Bluewave Technologies",
            "Midmarket"
        ),
        (
            "C004",
            "Greenfield Group",
            "Government"
        ),
        (
            "C005",
            "Summit Retail",
            "Small Business"
        ),
        (
            "C006",
            "Pioneer Systems",
            "Enterprise"
        ),
        (
            "C007",
            "Horizon Corp",
            "Midmarket"
        ),
        (
            "C008",
            "Atlas Services",
            "Small Business"
        ),
        (
            "C009",
            "Crestline Ltd",
            "Government"
        ),
        (
            "C010",
            "Nova Industries",
            "Enterprise"
        ),
    ]

    countries = [
        "Canada",
        "Germany",
        "France",
        "Mexico",
        "United States",
    ]

    regions = {
        "Canada": "North America",
        "Germany": "Europe",
        "France": "Europe",
        "Mexico": "North America",
        "United States of America": "North America",
    }

    products = [
        (
            "P001",
            "Carretera",
            "Road Bikes"
        ),
        (
            "P002",
            "Montana",
            "Mountain Bikes"
        ),
        (
            "P003",
            "Paseo",
            "Leisure Bikes"
        ),
        (
            "P004",
            "VTT",
            "Mountain Bikes"
        ),
        (
            "P005",
            "Amarilla",
            "Accessories"
        ),
    ]

    # ------------------------------------------------------------
    # DATE
    # ------------------------------------------------------------

    if "date" in df.columns:

        df["date"] = pd.to_datetime(
            df["date"],
            dayfirst=True,
            errors="coerce"
        )

    elif (
        "year" in df.columns
        and "month_number" in df.columns
    ):

        source_year = pd.to_numeric(
            df["year"],
            errors="coerce"
        ).fillna(2014).astype(int)

        source_month = pd.to_numeric(
            df["month_number"],
            errors="coerce"
        ).fillna(1).astype(int)

        source_month = source_month.clip(
            lower=1,
            upper=12
        )

        df["date"] = pd.to_datetime(
            {
                "year": source_year,
                "month": source_month,
                "day": 1,
            },
            errors="coerce"
        )

    else:

        df["date"] = pd.date_range(
            start="2014-01-01",
            periods=len(df),
            freq="D"
        )

    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month_name()

    # ------------------------------------------------------------
    # SALES
    # ------------------------------------------------------------

    if "sales" in df.columns:

        df["sales"] = clean_money(
            df["sales"]
        )

    else:

        df["sales"] = rng.uniform(
            5000,
            50000,
            len(df)
        ).round(2)

    df["sales"] = df["sales"].fillna(
        df["sales"].median()
    )

    # ------------------------------------------------------------
    # UNITS SOLD
    # ------------------------------------------------------------

    if "units_sold" in df.columns:

        df["units_sold"] = clean_money(
            df["units_sold"]
        )

    else:

        df["units_sold"] = rng.integers(
            50,
            2000,
            len(df)
        )

    df["units_sold"] = (
        df["units_sold"]
        .fillna(0)
    )

    # ------------------------------------------------------------
    # PROFIT
    # ------------------------------------------------------------

    if "profit" in df.columns:

        df["profit"] = clean_money(
            df["profit"]
        )

    else:

        df["profit"] = (
            df["sales"]
            * rng.uniform(
                0.08,
                0.30,
                len(df)
            )
        ).round(2)

    df["profit"] = (
        df["profit"]
        .fillna(0)
    )

    # ------------------------------------------------------------
    # COUNTRY
    # ------------------------------------------------------------

    if "country" not in df.columns:

        df["country"] = rng.choice(
            countries,
            len(df)
        )

    else:

        df["country"] = (
            df["country"]
            .fillna("United States")
            .astype(str)
            .str.strip()
        )

    # ------------------------------------------------------------
    # PRODUCT
    # ------------------------------------------------------------

    if "product" not in df.columns:

        product_indexes = rng.integers(
            0,
            len(products),
            len(df)
        )

        df["product_id"] = [
            products[i][0]
            for i in product_indexes
        ]

        df["product"] = [
            products[i][1]
            for i in product_indexes
        ]

        df["product_category"] = [
            products[i][2]
            for i in product_indexes
        ]

    else:

        df["product"] = (
            df["product"]
            .astype(str)
            .str.strip()
        )

        unique_products = (
            df["product"]
            .dropna()
            .unique()
        )

        product_map = {
            product: f"P{index:03d}"
            for index, product
            in enumerate(
                unique_products,
                start=1
            )
        }

        df["product_id"] = (
            df["product"]
            .map(product_map)
        )

        product_categories = {
            "Carretera": "Road Bikes",
            "Montana": "Mountain Bikes",
            "Paseo": "Leisure Bikes",
            "VTT": "Mountain Bikes",
            "Velo": "Road Bikes",
            "Amarilla": "Accessories",
        }

        df["product_category"] = (
            df["product"]
            .map(product_categories)
            .fillna("General Products")
        )

    # ------------------------------------------------------------
    # COMPANY
    # ------------------------------------------------------------

    df["company"] = (
        "Apex Business Solutions"
    )

    df["business_unit"] = (
        "Commercial Operations"
    )

    # ------------------------------------------------------------
    # EMPLOYEES
    # ------------------------------------------------------------

    employee_indexes = rng.integers(
        0,
        len(employees),
        len(df)
    )

    df["employee_id"] = [
        employees[i][0]
        for i in employee_indexes
    ]

    df["employee_name"] = [
        employees[i][1]
        for i in employee_indexes
    ]

    df["employee_role"] = [
        employees[i][2]
        for i in employee_indexes
    ]

    df["manager"] = [
        employees[i][3]
        for i in employee_indexes
    ]

    df["department"] = [
        employees[i][4]
        for i in employee_indexes
    ]

    # ------------------------------------------------------------
    # CUSTOMERS
    # ------------------------------------------------------------

    customer_indexes = rng.integers(
        0,
        len(customers),
        len(df)
    )

    df["customer_id"] = [
        customers[i][0]
        for i in customer_indexes
    ]

    df["customer_name"] = [
        customers[i][1]
        for i in customer_indexes
    ]

    df["customer_segment"] = [
        customers[i][2]
        for i in customer_indexes
    ]

    # ------------------------------------------------------------
    # REGION
    # ------------------------------------------------------------

    df["region"] = (
        df["country"]
        .map(regions)
        .fillna("Other")
    )

    # ------------------------------------------------------------
    # SALES CHANNEL
    # ------------------------------------------------------------

    channels = [
        "Direct Sales",
        "Online",
        "Partner",
        "Retail",
    ]

    df["sales_channel"] = rng.choice(
        channels,
        len(df)
    )

    # ------------------------------------------------------------
    # UNIT PRICE
    # ------------------------------------------------------------

    if "sale_price" in df.columns:

        df["unit_price"] = clean_money(
            df["sale_price"]
        )

    else:

        df["unit_price"] = (
            df["sales"]
            / df["units_sold"]
        ).replace(
            [np.inf, -np.inf],
            np.nan
        ).fillna(0)

    # ------------------------------------------------------------
    # GROSS SALES
    # ------------------------------------------------------------

    if "gross_sales" in df.columns:

        df["gross_sales"] = clean_money(
            df["gross_sales"]
        )

    else:

        df["gross_sales"] = (
            df["sales"]
            * rng.uniform(
                1.02,
                1.15,
                len(df)
            )
        ).round(2)

    # ------------------------------------------------------------
    # DISCOUNT
    # ------------------------------------------------------------

    if "discounts" in df.columns:

        df["discount"] = clean_money(
            df["discounts"]
        ).fillna(0)

    else:

        df["discount"] = (
            df["gross_sales"]
            - df["sales"]
        ).clip(
            lower=0
        ).round(2)

    # ------------------------------------------------------------
    # COGS
    # ------------------------------------------------------------

    if "cogs" in df.columns:

        df["cogs"] = clean_money(
            df["cogs"]
        ).fillna(0)

    else:

        df["cogs"] = (
            df["sales"]
            - df["profit"]
        ).clip(
            lower=0
        ).round(2)

    # ------------------------------------------------------------
    # EMPLOYEE TARGETS
    # ------------------------------------------------------------

    employee_target_factors = {
        "E001": 0.92,
        "E002": 0.97,
        "E003": 1.08,
        "E004": 0.95,
        "E005": 1.12,
        "E006": 1.10,
        "E007": 0.94,
        "E008": 0.98,
        "E009": 1.05,
        "E010": 1.15,
    }

    sales_target_factor = (
        df["employee_id"]
        .map(employee_target_factors)
        .fillna(1.0)
    )

    profit_target_factor = (
        sales_target_factor
        + 0.02
    )

    df["sales_target"] = (
        df["sales"]
        * sales_target_factor
    ).round(2)

    df["profit_target"] = (
        df["profit"]
        * profit_target_factor
    ).round(2)

    # ------------------------------------------------------------
    # FINAL SCHEMA
    # ------------------------------------------------------------

    columns = [
        "date",
        "year",
        "month",
        "company",
        "business_unit",
        "department",
        "employee_id",
        "employee_name",
        "employee_role",
        "manager",
        "customer_id",
        "customer_name",
        "customer_segment",
        "country",
        "region",
        "product_id",
        "product",
        "product_category",
        "sales_channel",
        "units_sold",
        "unit_price",
        "gross_sales",
        "discount",
        "sales",
        "cogs",
        "profit",
        "sales_target",
        "profit_target",
    ]

    df = df[columns]

    # ------------------------------------------------------------
    # SAVE
    # ------------------------------------------------------------

    df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    # ------------------------------------------------------------
    # OUTPUT
    # ------------------------------------------------------------

    print("=" * 70)
    print("STANDARDIZED DATASET CREATED")
    print("=" * 70)

    print()

    print(f"Rows    : {len(df)}")
    print(f"Columns : {len(df.columns)}")

    print()

    print("Date range:")
    print("-" * 70)

    print(
        f"{df['date'].min().date()} "
        f"to "
        f"{df['date'].max().date()}"
    )

    print()

    print("Year distribution:")
    print("-" * 70)

    print(
        df["year"]
        .value_counts()
        .sort_index()
    )

    print()

    print("Department distribution:")
    print("-" * 70)

    print(
        df["department"]
        .value_counts()
        .sort_index()
    )

    print()

    print("Employee distribution:")
    print("-" * 70)

    print(
        df[
            [
                "employee_id",
                "employee_name",
                "department",
            ]
        ]
        .drop_duplicates()
        .sort_values("employee_id")
        .to_string(index=False)
    )

    print()

    print("First 5 rows:")
    print("-" * 70)

    print(
        df.head().to_string(
            index=False
        )
    )

    print()

    print(
        f"Saved to: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    create_dataset()