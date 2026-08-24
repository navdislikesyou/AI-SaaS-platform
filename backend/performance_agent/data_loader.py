from pathlib import Path

import pandas as pd


class DataLoader:

    def __init__(self, file_path: str):

        self.file_path = Path(file_path)

    def load(self):

        if not self.file_path.exists():
            raise FileNotFoundError(
                f"Dataset not found: {self.file_path}"
            )

        df = pd.read_csv(self.file_path)

        # Remove completely empty rows/columns
        df = df.dropna(how="all")
        df = df.dropna(axis=1, how="all")

        # Clean column names
        df.columns = (
            df.columns
            .str.strip()
            .str.lower()
            .str.replace(" ", "_")
        )

        # Clean numeric-looking currency columns
        for column in df.columns:

            if df[column].dtype == "object":

                cleaned = (
                    df[column]
                    .astype(str)
                    .str.replace("$", "", regex=False)
                    .str.replace(",", "", regex=False)
                    .str.strip()
                )

                numeric = pd.to_numeric(
                    cleaned,
                    errors="coerce"
                )

                # Convert only if most values are numeric
                if numeric.notna().mean() > 0.8:
                    df[column] = numeric

        return df
    