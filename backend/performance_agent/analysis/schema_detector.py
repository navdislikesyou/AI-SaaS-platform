class SchemaDetector:

    REQUIRED_FIELDS = {
        "date": "Date of the transaction or sale",
        "sales": "Net sales or revenue generated",
        "profit": "Profit generated",
        "units_sold": "Number of units sold",
        "product": "Product name",
        "country": "Country associated with the sale",
        "customer_segment": "Customer or business segment",
    }

    RECOMMENDED_FIELDS = {
        "year": "Calendar or financial year",
        "month": "Month of the transaction",
        "company": "Company or organization name",
        "business_unit": "Business unit or division",
        "department": "Department responsible for the activity",
        "employee_id": "Unique employee identifier",
        "employee_name": "Employee or salesperson name",
        "employee_role": "Employee's role or designation",
        "manager": "Employee's manager",
        "customer_id": "Unique customer identifier",
        "customer_name": "Customer name",
        "region": "Geographical region",
        "product_id": "Unique product identifier",
        "product_category": "Product category",
        "sales_channel": "Channel through which the sale occurred",
        "unit_price": "Selling price per unit",
        "gross_sales": "Sales before discounts",
        "discount": "Discount amount",
        "cogs": "Cost of goods sold",
        "sales_target": "Sales target",
        "profit_target": "Profit target",
    }

    OPTIONAL_FIELDS = {
        "customer_type": "Type of customer",
        "customer_lifetime_value": "Estimated customer lifetime value",
        "customer_acquisition_cost": "Customer acquisition cost",
        "product_subcategory": "Product subcategory",
        "brand": "Product brand",
        "order_id": "Unique order identifier",
        "transaction_id": "Unique transaction identifier",
        "invoice_id": "Invoice identifier",
        "order_status": "Order status",
        "order_type": "Order type",
        "state": "State or province",
        "city": "City",
        "postal_code": "Postal or ZIP code",
        "distribution_channel": "Distribution channel",
        "marketing_channel": "Marketing channel",
        "inventory": "Current inventory level",
        "inventory_value": "Value of inventory",
        "opening_inventory": "Inventory at the beginning of the period",
        "closing_inventory": "Inventory at the end of the period",
        "reorder_level": "Inventory reorder threshold",
        "supplier_id": "Supplier identifier",
        "supplier": "Supplier name",
        "supplier_cost": "Supplier or purchasing cost",
        "marketing_cost": "Marketing expenditure",
        "shipping_cost": "Shipping expenditure",
        "labor_cost": "Labor expenditure",
        "operating_expense": "Operating expenses",
        "returns": "Number of returned units",
        "return_value": "Value of returned goods",
        "return_rate": "Percentage of sales returned",
        "refund": "Refund amount",
        "complaints": "Customer complaint count",
        "tickets": "Customer support ticket count",
        "customer_satisfaction": "Customer satisfaction score",
        "nps": "Net Promoter Score",
        "campaign": "Marketing campaign",
        "campaign_id": "Marketing campaign identifier",
        "leads": "Number of leads",
        "conversions": "Number of conversions",
        "conversion_rate": "Lead conversion rate",
        "marketing_roi": "Marketing return on investment",
        "subscription_id": "Subscription identifier",
        "subscription_type": "Subscription plan",
        "monthly_recurring_revenue": "Monthly recurring revenue",
        "annual_recurring_revenue": "Annual recurring revenue",
        "churn": "Customer churn",
        "renewals": "Subscription renewals",
        "payment": "Payment amount",
        "payment_status": "Payment status",
        "payment_method": "Payment method",
        "outstanding_amount": "Outstanding amount",
        "invoice_amount": "Invoice amount",
        "tax": "Tax amount",
        "tax_rate": "Tax rate",
        "currency": "Currency",
        "exchange_rate": "Currency exchange rate",
        "shipping_method": "Shipping method",
        "shipping_status": "Shipping status",
        "delivery_date": "Actual delivery date",
        "expected_delivery_date": "Expected delivery date",
        "delivery_days": "Delivery duration",
        "forecast_sales": "Forecasted sales",
        "forecast_profit": "Forecasted profit",
        "forecast_units": "Forecasted units",
        "forecast_date": "Forecast period",
        "contract_id": "Contract identifier",
        "contract_value": "Contract value",
        "contract_start": "Contract start date",
        "contract_end": "Contract end date",
        "opportunity_id": "Sales opportunity identifier",
        "opportunity": "Sales opportunity",
        "deal_stage": "Sales opportunity stage",
        "deal_probability": "Probability of winning the opportunity",
        "deal_value": "Potential deal value",
        "performance_score": "Performance score",
        "growth_rate": "Growth rate",
        "retention_rate": "Customer retention rate",
    }

    def __init__(self, dataframe):
        self.dataframe = dataframe
        self.columns = {
            str(column).strip().lower()
            for column in dataframe.columns
        }

    def detect(self):
        required = {
            field: field in self.columns
            for field in self.REQUIRED_FIELDS
        }

        recommended = {
            field: field in self.columns
            for field in self.RECOMMENDED_FIELDS
        }

        optional = {
            field: field in self.columns
            for field in self.OPTIONAL_FIELDS
        }

        known_fields = (
            set(self.REQUIRED_FIELDS)
            | set(self.RECOMMENDED_FIELDS)
            | set(self.OPTIONAL_FIELDS)
        )

        unknown = sorted(
            self.columns - known_fields
        )

        return {
            "required": required,
            "recommended": recommended,
            "optional": optional,
            "unknown": unknown,
        }

    def validate(self):
        result = self.detect()

        missing_required = [
            field
            for field, available in result["required"].items()
            if not available
        ]

        result["valid"] = len(missing_required) == 0
        result["missing_required"] = missing_required

        return result

    def print_schema(self):
        result = self.validate()

        print("\n" + "=" * 70)
        print("ENTERPRISE DATA SCHEMA")
        print("=" * 70)

        print("\nREQUIRED FIELDS")
        print("-" * 70)

        for field, description in self.REQUIRED_FIELDS.items():
            if result["required"][field]:
                print(f"✓ {field:<25} Available")
            else:
                print(f"✗ {field:<25} Missing")

        print("\nRECOMMENDED FIELDS")
        print("-" * 70)

        for field, description in self.RECOMMENDED_FIELDS.items():
            if result["recommended"][field]:
                print(f"✓ {field:<25} Available")
            else:
                print(f"- {field:<25} Not provided")

        print("\nOPTIONAL FIELDS")
        print("-" * 70)

        available_optional = 0

        for field, description in self.OPTIONAL_FIELDS.items():
            if result["optional"][field]:
                available_optional += 1
                print(f"✓ {field:<25} Available")

        if available_optional == 0:
            print("No optional fields provided.")

        print("\nUNKNOWN FIELDS")
        print("-" * 70)

        if result["unknown"]:
            for field in result["unknown"]:
                print(f"? {field}")
        else:
            print("None")

        print("\n" + "=" * 70)

        if result["valid"]:
            print("DATASET STATUS: VALID")
        else:
            print("DATASET STATUS: INVALID")

            print("\nMissing required fields:")

            for field in result["missing_required"]:
                print(f"- {field}")

        print("=" * 70)

        return result