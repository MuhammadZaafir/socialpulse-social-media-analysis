"""Shared helpers for the tests: put the project folder on the import path and build small datasets."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from modules import data_validation


def make_df(rows, columns=None):
    """Build a small raw DataFrame. Default columns are the full standard set."""
    columns = columns or data_validation.STANDARD_COLUMNS
    return pd.DataFrame(rows, columns=columns)


def clean(df):
    """Run the normal validation on a DataFrame that already uses standard column names."""
    return data_validation.validate_and_clean(df)


def good_rows(n=6):
    """n valid rows for the full standard column set."""
    return [[f"P{i}", f"2026-01-{i + 1:02d}", "Instagram", "Video" if i % 2 else "Image", f"caption {i}", "Tips",
             10 + i, 2, 1, 1000, 800, 20] for i in range(n)]
