"""
data_loader.py
--------------
Reads files (CSV or Excel) into pandas DataFrames.

This module only READS. It never changes the user's original file: the file is read
into memory and everything else happens on copies.
"""

import io
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DATA_PATH = PROJECT_ROOT / "data" / "sample_social_media_posts.csv"

MAX_FILE_SIZE_MB = 20
CSV_ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]   # Excel often saves CSV as cp1252


class DataLoadError(Exception):
    """Raised with a beginner-friendly message when a file cannot be read."""


def _read_csv_bytes(content):
    """Try several encodings and let pandas guess the separator (comma, semicolon or tab)."""
    last_error = None
    for encoding in CSV_ENCODINGS:
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError as error:
            last_error = error
            continue
        try:
            # dtype=str keeps values exactly as typed ("1,200", "n/a"); validation converts them later.
            return pd.read_csv(io.StringIO(text), sep=None, engine="python", dtype=str)
        except pd.errors.EmptyDataError:
            raise DataLoadError("The file is empty. Please add your data (use the CSV template) and try again.")
        except Exception:   # separator guessing can fail on tiny files, so retry with a plain comma
            try:
                return pd.read_csv(io.StringIO(text), dtype=str)
            except Exception as error:
                last_error = error
    raise DataLoadError(f"The CSV file could not be read ({last_error}). Try saving it as 'CSV UTF-8' from Excel.")


def _read_excel_bytes(content):
    """Read the 'Template' sheet if it exists, otherwise the first sheet."""
    try:
        workbook = pd.ExcelFile(io.BytesIO(content), engine="openpyxl")
    except Exception as error:
        raise DataLoadError(f"The Excel file could not be opened ({error}). Make sure it is a valid .xlsx file.")
    sheet = "Template" if "Template" in workbook.sheet_names else workbook.sheet_names[0]
    return workbook.parse(sheet_name=sheet)


def read_data_file(source, filename=None):
    """
    Read a CSV or Excel file.

    source   : a file path, or an uploaded file object (Streamlit UploadedFile / BytesIO)
    filename : name used to detect the file type (needed for uploaded objects)
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        filename = filename or path.name
        content = path.read_bytes()
    elif hasattr(source, "getvalue"):
        content = source.getvalue()
    else:
        content = source.read()

    if not filename:
        raise DataLoadError("Could not determine the file type. Please upload a .csv or .xlsx file.")
    if len(content) == 0:
        raise DataLoadError("The file is empty (0 bytes).")
    if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise DataLoadError(f"The file is larger than {MAX_FILE_SIZE_MB} MB. Please upload a smaller file.")

    extension = Path(filename).suffix.lower()
    if extension == ".csv":
        df = _read_csv_bytes(content)
    elif extension == ".xlsx":
        df = _read_excel_bytes(content)
    elif extension == ".xls":
        raise DataLoadError("Old .xls files are not supported. In Excel choose File > Save As > '.xlsx' or 'CSV UTF-8'.")
    else:
        raise DataLoadError(f"Unsupported file type '{extension}'. Please upload a .csv or .xlsx file.")

    # Remove columns with no heading at all (Excel sometimes adds empty trailing columns)
    df = df.loc[:, [not str(c).startswith("Unnamed:") or df[c].notna().any() for c in df.columns]]
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_sample_data():
    """Load the bundled SYNTHETIC demonstration dataset."""
    return read_data_file(SAMPLE_DATA_PATH)


def sample_file_bytes():
    """Raw bytes of the example dataset (for the download button)."""
    return SAMPLE_DATA_PATH.read_bytes()
