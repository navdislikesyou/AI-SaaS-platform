"""Dataset loading and standardization.

Single source of truth for turning a file on disk into a clean DataFrame. The
logic here was previously split across two places that disagreed:
``performance_agent.data_loader.DataLoader`` normalized column names, while
``performance_agent.performance_agent.load_input_file`` did not. Because every
analyzer looks up lowercase snake_case columns such as ``sales`` and ``date``,
an unnormalized frame silently disabled whole modules -- running the agent
against the raw ``Financials.csv`` failed the ``time`` module with
``TimeAnalyzer requires column(s): ['date']``.

``DataLoader`` remains as a thin wrapper over these functions so existing check
scripts keep working.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

#: File extensions the agent can read.
SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".xls")

#: Fraction of values that must parse as numeric before a currency-looking
#: column is converted. Below this threshold the column is probably text.
_NUMERIC_CONVERSION_THRESHOLD = 0.8


def load_dataset(file_path: str | Path) -> pd.DataFrame:
    """Read a CSV or Excel file into a raw DataFrame.

    Applies no cleanup beyond what the reader itself does. Callers normally
    want :func:`load_clean_dataset`, which also normalizes the frame.

    Args:
        file_path: Path to a ``.csv``, ``.xlsx``, or ``.xls`` file.

    Returns:
        The DataFrame exactly as the reader produced it.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the extension is not supported.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Input file not found: {path}"
        )

    extension = path.suffix.lower()

    if extension == ".csv":
        return pd.read_csv(path)

    if extension in (".xlsx", ".xls"):
        return pd.read_excel(path)

    raise ValueError(
        "Unsupported file type. Use CSV or Excel."
    )


def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Rewrite column names to lowercase snake_case.

    Every analyzer resolves columns by lowercase snake_case name, so this is
    what makes a raw export usable without hand-editing the header row.

    Args:
        df: The DataFrame to normalize.

    Returns:
        A copy with normalized column names.
    """
    result = df.copy()

    result.columns = (
        result.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )

    return result


def strip_currency(df: pd.DataFrame) -> pd.DataFrame:
    """Convert currency-formatted text columns to numbers.

    Handles ``$1,234.50`` style values by removing the symbol and thousands
    separators. A column is only converted when most of its values parse as
    numeric, which keeps genuine text columns such as ``region`` intact.

    The ``object`` dtype check is deliberate and load-bearing. pandas 3 changes
    the default string dtype, which would stop this matching and silently
    disable currency stripping. The backend pins ``pandas<3`` for that reason.

    Args:
        df: The DataFrame to clean.

    Returns:
        A copy with numeric-looking currency columns converted.
    """
    result = df.copy()

    for column in result.columns:

        if result[column].dtype != "object":
            continue

        cleaned = (
            result[column]
            .astype(str)
            .str.replace("$", "", regex=False)
            .str.replace(",", "", regex=False)
            .str.strip()
        )

        numeric = pd.to_numeric(
            cleaned,
            errors="coerce"
        )

        if numeric.notna().mean() > _NUMERIC_CONVERSION_THRESHOLD:
            result[column] = numeric

    return result


def standardize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Drop empty rows and columns and trim header whitespace.

    Preserved verbatim from the original pipeline, including its behavior of
    only stripping whitespace from column names rather than rewriting them.
    Use :func:`load_clean_dataset` when a normalized frame is wanted.

    Args:
        df: The DataFrame to standardize.

    Returns:
        A standardized copy.
    """
    result = df.copy()

    result = result.dropna(how="all")

    result.columns = [
        str(column).strip()
        for column in result.columns
    ]

    result = result.dropna(axis=1, how="all")

    return result


def load_clean_dataset(
    file_path: str | Path,
    *,
    strip_currency_symbols: bool = True,
) -> pd.DataFrame:
    """Load a dataset and return it ready for the analyzers.

    This is the canonical entry point for both the CLI and the service layer.
    It reads the file, drops empty rows and columns, normalizes column names to
    lowercase snake_case, and optionally strips currency symbols.

    Args:
        file_path: Path to a ``.csv``, ``.xlsx``, or ``.xls`` file.
        strip_currency_symbols: Whether to convert currency-formatted text
            columns to numbers. Disable to preserve raw text values.

    Returns:
        A normalized DataFrame.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the extension is not supported.
    """
    df = load_dataset(file_path)

    df = standardize_dataframe(df)

    df = normalize_column_names(df)

    if strip_currency_symbols:
        df = strip_currency(df)

    return df