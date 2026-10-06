"""Canonical dataset loading.

Thin wrapper over :mod:`performance_agent.dataset`, kept so the existing check
scripts that call ``DataLoader`` keep working. New code should prefer
:func:`performance_agent.dataset.load_clean_dataset`.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from performance_agent.dataset import (
    load_clean_dataset,
    load_dataset,
    normalize_column_names,
    standardize_dataframe,
    strip_currency,
)


class DataLoader:
    """Load a dataset file into a normalized DataFrame.

    Retained for backwards compatibility. Delegates to the functions in
    :mod:`performance_agent.dataset` rather than duplicating the logic.
    """

    def __init__(self, file_path: str) -> None:
        """Initialize the loader.

        Args:
            file_path: Path to the dataset file.
        """
        self.file_path = Path(file_path)

    def load(self) -> pd.DataFrame:
        """Read and normalize the dataset.

        Returns:
            A DataFrame with lowercase snake_case columns and numeric currency
            columns.

        Raises:
            FileNotFoundError: If the path does not exist.
            ValueError: If the extension is not supported.
        """
        return load_clean_dataset(self.file_path)