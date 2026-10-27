"""
data_validation.py
------------------
Everything about checking and cleaning the user's data lives here.

Main steps:
1. suggest_column_mapping()  -> guess which column in the file matches each SocialPulse column
2. check_mapping()           -> make sure the mapping is usable
3. apply_mapping()           -> rename the user's columns to SocialPulse's standard names
4. validate_and_clean()      -> validate values, remove problems, and explain what happened

Important rule: a MISSING metric is never turned into 0. Missing stays missing (NaN).
The user's original file is never modified; we only work on copies in memory.
"""

import math
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# Column definitions
# ----------------------------------------------------------------------------
STANDARD_COLUMNS = [
    "post_id", "post_date", "platform", "content_type", "caption", "topic",
    "likes", "comments", "shares", "impressions", "reach", "clicks",
]
REQUIRED_COLUMNS = ["post_date", "likes", "comments"]
NUMERIC_COLUMNS = ["likes", "comments", "shares", "impressions", "reach", "clicks"]
LABEL_COLUMNS = ["platform", "content_type", "topic"]

UNSPECIFIED = "Not specified"       # label used when a text category is blank
MIN_ROWS_RECOMMENDED = 5            # fewer usable rows than this -> warning
KNOWN_PLATFORMS = [
    "Instagram", "Facebook", "LinkedIn", "X", "Twitter", "YouTube", "TikTok",
    "Pinterest", "Threads", "Snapchat", "Reddit",
]

# Used by the Help page, the Excel template, and the column-mapping screen.
COLUMN_GUIDE = {
    "post_id": ("Optional", "A unique ID or short name for the post.", "P001"),
    "post_date": ("REQUIRED", "Date the post was published. Use YYYY-MM-DD.", "2026-03-15"),
    "platform": ("Optional", "Social network name.", "Instagram"),
    "content_type": ("Optional", "Format of the post (Image, Video, Carousel, Text...).", "Video"),
    "caption": ("Optional", "Post text or a short description.", "3 quick tips for beginners"),
    "topic": ("Optional", "Subject or campaign of the post.", "Tips & Tutorials"),
    "likes": ("REQUIRED", "Number of likes/reactions (a number, not text).", "132"),
    "comments": ("REQUIRED", "Number of comments (a number).", "19"),
    "shares": ("Optional", "Number of shares/reposts. Leave blank if unavailable.", "20"),
    "impressions": ("Optional", "Times the post was displayed (can count the same person twice).", "4178"),
    "reach": ("Optional", "Unique accounts that saw the post.", "3445"),
    "clicks": ("Optional", "Link/post clicks. Leave blank if unavailable.", "115"),
}

# What is lost when an OPTIONAL column is not in the file.
MISSING_COLUMN_EFFECTS = {
    "post_id": "Post IDs were generated automatically from row numbers.",
    "platform": "Platform comparisons are not possible (all posts are labelled 'Not specified').",
    "content_type": "Content-type comparisons are not possible.",
    "caption": "Captions will not be shown or searchable.",
    "topic": "Topic comparisons are not possible.",
    "shares": "Shares are unavailable, so engagement uses only likes and comments.",
    "impressions": "Impressions-based engagement rate is unavailable.",
    "reach": "Reach-based engagement rate is unavailable.",
    "clicks": "Click totals are unavailable.",
}

# Alternative headings people commonly use (compared after normalising, see _normalise_name).
ALIASES = {
    "post_id": ["postid", "id", "post", "postnumber", "postname"],
    "post_date": ["date", "postdate", "publishdate", "publisheddate", "posteddate", "dateposted", "createdat", "day"],
    "platform": ["network", "channel", "socialplatform", "socialnetwork", "platformname"],
    "content_type": ["contenttype", "type", "format", "posttype", "mediatype", "contentformat"],
    "caption": ["text", "message", "description", "posttext", "content", "title"],
    "topic": ["category", "theme", "campaign", "subject", "tag"],
    "likes": ["like", "reactions", "totallikes", "likescount"],
    "comments": ["comment", "totalcomments", "commentscount", "replies"],
    "shares": ["share", "reposts", "retweets", "totalshares", "sharescount"],
    "impressions": ["impression", "views", "totalimpressions", "impressionscount"],
    "reach": ["totalreach", "uniquereach", "accountsreached", "reachcount"],
    "clicks": ["click", "linkclicks", "totalclicks", "clickscount"],
}


# ----------------------------------------------------------------------------
# Result object
# ----------------------------------------------------------------------------
@dataclass
class ValidationResult:
    """Everything the app needs to know after checking a file."""
    data: pd.DataFrame = None                    # cleaned data (None if there was a fatal error)
    errors: list = field(default_factory=list)   # problems that stop the analysis
    warnings: list = field(default_factory=list) # problems that were handled but the user should know
    info: list = field(default_factory=list)     # neutral notes
    rows_in_file: int = 0                        # rows with any content (blank template rows excluded)
    rows_used: int = 0                           # rows left after cleaning
    available_metrics: list = field(default_factory=list)
    missing_optional: list = field(default_factory=list)  # optional columns/metrics that are unavailable

    @property
    def ok(self):
        """True when the data can be analysed."""
        return not self.errors and self.data is not None and len(self.data) > 0

    @property
    def effects_of_missing(self):
        """Plain-English list of analyses affected by missing optional columns."""
        return [MISSING_COLUMN_EFFECTS[c] for c in self.missing_optional if c in MISSING_COLUMN_EFFECTS]


# ----------------------------------------------------------------------------
# Step 1-3: column mapping
# ----------------------------------------------------------------------------
def _normalise_name(name):
    """'Post Date ' -> 'postdate' (lower case, letters and digits only)."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def suggest_column_mapping(file_columns):
    """
    Guess which column of the user's file matches each standard column.
    Returns {standard_name: file_column_name or None}.
    """
    normalised = {}
    for col in file_columns:
        normalised.setdefault(_normalise_name(col), col)   # first column wins if two look alike

    mapping, used = {}, set()
    for std in STANDARD_COLUMNS:
        found = None
        for candidate in [std.replace("_", "")] + ALIASES[std]:
            source = normalised.get(candidate)
            if source is not None and source not in used:
                found = source
                break
        mapping[std] = found
        if found is not None:
            used.add(found)
    return mapping


def check_mapping(mapping):
    """Return a list of error messages (empty list = mapping is fine)."""
    errors = []
    for col in REQUIRED_COLUMNS:
        if not mapping.get(col):
            errors.append(f"Required column '{col}' is not mapped. Please choose which column in your file contains it.")
    chosen = [v for v in mapping.values() if v]
    for source in sorted(set(chosen)):
        if chosen.count(source) > 1:
            errors.append(f"The file column '{source}' is mapped to more than one SocialPulse column.")
    return errors


def apply_mapping(raw_df, mapping):
    """Return a NEW DataFrame that uses the standard column names. The input is not changed."""
    renamed = {}
    for std, source in mapping.items():
        if source and source in raw_df.columns:
            renamed[std] = raw_df[source]
    return pd.DataFrame(renamed)


# ----------------------------------------------------------------------------
# Step 4: cleaning helpers
# ----------------------------------------------------------------------------
def _to_number(value):
    """Convert one cell to a float. Anything unusable becomes NaN (never 0)."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
        number = float(value)
    else:
        text = str(value).strip().replace(",", "")   # allow "1,200"
        if text == "":
            return np.nan
        try:
            number = float(text)
        except ValueError:
            return np.nan
    return number if math.isfinite(number) else np.nan


def _is_blank(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return bool(pd.isna(value))


def _unify_labels(series):
    """
    Make labels consistent: ' instagram', 'Instagram' and 'INSTAGRAM' become one label.
    The most common spelling is used.
    """
    cleaned = series.map(lambda v: UNSPECIFIED if _is_blank(v) else " ".join(str(v).split()))
    lowered = cleaned.str.lower()
    best_spelling = {}
    for key in lowered.unique():
        spellings = cleaned[lowered == key]
        best_spelling[key] = spellings.value_counts().index[0]
    return lowered.map(best_spelling)


def _row_list(source_rows, limit=5):
    """'rows 3, 7, 9' text used in messages (numbers match the spreadsheet row numbers)."""
    rows = [str(int(r)) for r in list(source_rows)[:limit]]
    extra = len(source_rows) - len(rows)
    return ", ".join(rows) + (f" and {extra} more" if extra > 0 else "")


# ----------------------------------------------------------------------------
# Step 4: main validation
# ----------------------------------------------------------------------------
def validate_and_clean(mapped_df):
    """
    Check and clean a DataFrame that already uses standard column names.
    Returns a ValidationResult (see top of file).
    """
    result = ValidationResult()

    if mapped_df is None or mapped_df.shape[1] == 0 or len(mapped_df) == 0:
        result.errors.append("The file is empty: it has no data rows. Please add your posts and upload it again.")
        return result

    work = mapped_df.copy()
    work["_source_row"] = np.arange(len(work)) + 2   # row 1 of the spreadsheet is the header

    # Missing required columns -> stop early
    missing_required = [c for c in REQUIRED_COLUMNS if c not in work.columns]
    if missing_required:
        result.errors.append(
            "Required column(s) missing: " + ", ".join(missing_required)
            + ". Use the column-mapping step or download the CSV template."
        )
        return result

    # Remove completely blank rows (e.g. the empty rows in our template). They are NOT real posts.
    content_cols = [c for c in work.columns if c != "_source_row"]
    blank_mask = work[content_cols].apply(lambda col: col.map(_is_blank)).all(axis=1)
    if blank_mask.any():
        result.info.append(f"{int(blank_mask.sum())} completely blank row(s) were ignored (not counted as posts).")
    work = work[~blank_mask].copy()
    result.rows_in_file = len(work)
    if work.empty:
        result.errors.append("The file contains only blank rows. Please enter your post data.")
        return result

    # ---- Dates ----
    if pd.api.types.is_datetime64_any_dtype(work["post_date"]):
        parsed = work["post_date"]
    else:
        parsed = pd.to_datetime(work["post_date"], errors="coerce", format="mixed")
    if getattr(parsed.dt, "tz", None) is not None:
        parsed = parsed.dt.tz_localize(None)
    work["post_date"] = parsed.dt.normalize()
    bad_date = work["post_date"].isna()
    if bad_date.any():
        result.warnings.append(
            f"{int(bad_date.sum())} row(s) removed because the date is missing or not understood "
            f"(spreadsheet rows: {_row_list(work.loc[bad_date, '_source_row'])}). Use YYYY-MM-DD."
        )
        work = work[~bad_date].copy()

    # ---- Numeric columns ----
    for col in [c for c in NUMERIC_COLUMNS if c in work.columns]:
        original = work[col]
        converted = original.map(_to_number)

        # text that could not be read as a number (e.g. "n/a", "about 100")
        not_readable = converted.isna() & ~original.map(_is_blank)
        if not_readable.any():
            result.warnings.append(
                f"'{col}': {int(not_readable.sum())} value(s) are not valid numbers and were treated as missing "
                f"(rows: {_row_list(work.loc[not_readable, '_source_row'])})."
            )
        # negative numbers are impossible for these metrics
        negative = converted < 0
        if negative.any():
            result.warnings.append(
                f"'{col}': {int(negative.sum())} negative value(s) are invalid and were treated as missing "
                f"(rows: {_row_list(work.loc[negative, '_source_row'])})."
            )
            converted = converted.mask(negative)
        work[col] = converted.astype("float64")

    # ---- Duplicates ----
    check_cols = [c for c in work.columns if c != "_source_row"]
    exact_duplicates = work.duplicated(subset=check_cols, keep="first")
    if exact_duplicates.any():
        result.warnings.append(f"{int(exact_duplicates.sum())} exact duplicate row(s) were removed (first copy kept).")
        work = work[~exact_duplicates].copy()
    if "post_id" in work.columns:
        has_id = ~work["post_id"].map(_is_blank)
        same_id = work["post_id"].where(has_id).duplicated(keep="first") & has_id
        if same_id.any():
            result.warnings.append(
                f"{int(same_id.sum())} row(s) reused an existing post_id and were removed (first copy kept; "
                f"rows: {_row_list(work.loc[same_id, '_source_row'])})."
            )
            work = work[~same_id].copy()

    # ---- Text labels ----
    if "platform" in work.columns:
        work["platform"] = _unify_labels(work["platform"])
        canonical = {p.lower(): p for p in KNOWN_PLATFORMS}
        work["platform"] = work["platform"].map(lambda v: canonical.get(v.lower(), v))
        unexpected = sorted(set(work["platform"]) - set(KNOWN_PLATFORMS) - {UNSPECIFIED})
        if unexpected:
            result.info.append("Unrecognised platform name(s) kept exactly as typed: " + ", ".join(unexpected) + ".")
    for col in ["content_type", "topic"]:
        if col in work.columns:
            work[col] = _unify_labels(work[col])
    for col in LABEL_COLUMNS:
        if col in work.columns and (work[col] == UNSPECIFIED).any():
            result.info.append(f"'{col}' was blank for {int((work[col] == UNSPECIFIED).sum())} post(s); labelled '{UNSPECIFIED}'.")

    # ---- Fill in optional text columns that do not exist (labels only, never metrics) ----
    for col in LABEL_COLUMNS:
        if col not in work.columns:
            work[col] = UNSPECIFIED
            result.missing_optional.append(col)
    if "caption" not in work.columns:
        work["caption"] = ""
        result.missing_optional.append("caption")
    else:
        work["caption"] = work["caption"].map(lambda v: "" if _is_blank(v) else str(v).strip())
    if "post_id" not in work.columns:
        work["post_id"] = [f"ROW-{int(r)}" for r in work["_source_row"]]
        result.missing_optional.append("post_id")
    else:
        work["post_id"] = [
            f"ROW-{int(r)}" if _is_blank(v) else str(v).strip()
            for v, r in zip(work["post_id"], work["_source_row"])
        ]

    # ---- Metric availability ----
    for col in NUMERIC_COLUMNS:
        if col not in work.columns:
            result.missing_optional.append(col)
        elif work[col].isna().all():
            result.warnings.append(f"'{col}' has no usable values, so it is treated as not available.")
            work = work.drop(columns=[col])
            result.missing_optional.append(col)
        else:
            result.available_metrics.append(col)
            blanks = int(work[col].isna().sum())
            if blanks:
                result.warnings.append(f"'{col}' is blank for {blanks} of {len(work)} post(s). These stay missing (not zero).")
    for col in ("impressions", "reach"):
        if col in work.columns:
            zeros = int((work[col] == 0).sum())
            if zeros:
                result.warnings.append(f"'{col}' is 0 for {zeros} post(s); engagement rates cannot be calculated for them.")

    # ---- Final checks ----
    work = work.drop(columns=["_source_row"])
    ordered = [c for c in STANDARD_COLUMNS if c in work.columns]
    work = work[ordered].sort_values("post_date", kind="stable").reset_index(drop=True)

    result.rows_used = len(work)
    if work.empty:
        result.errors.append("No usable rows remain after cleaning. Please check the warnings above and fix the file.")
        return result
    if len(work) < MIN_ROWS_RECOMMENDED:
        result.warnings.append(
            f"Only {len(work)} usable post(s). Charts will work, but comparisons need more posts "
            f"(at least {MIN_ROWS_RECOMMENDED} recommended) to be meaningful."
        )
    result.data = work
    return result
