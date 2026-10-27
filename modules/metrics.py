"""
metrics.py
----------
All calculations: engagement rates, totals, group comparisons, trends and rankings.
These functions contain no Streamlit code, so they are easy to test.

ENGAGEMENT RATE FORMULAS
    Engagement Rate (% of reach)            = (Likes + Comments + Shares) / Reach       x 100
    Impressions-Based Engagement Rate (%)   = (Likes + Comments + Shares) / Impressions x 100
The two rates use different denominators, so they are NEVER mixed or compared as equal.
If the 'shares' column does not exist, only Likes + Comments are used (and we say so).
If the denominator is 0 or missing, the rate is "unavailable" (NaN) - never divided by zero.
"""

import numpy as np
import pandas as pd

RATE_REACH = "engagement_rate_reach"
RATE_IMPRESSIONS = "engagement_rate_impressions"
RATE_LABELS = {
    RATE_REACH: "Engagement Rate (% of reach)",
    RATE_IMPRESSIONS: "Impressions-Based Engagement Rate (% of impressions)",
}
METRIC_LABELS = {
    "likes": "Likes", "comments": "Comments", "shares": "Shares",
    "impressions": "Impressions", "reach": "Reach", "clicks": "Clicks",
    "interactions": "Interactions (likes + comments + shares)",
    RATE_REACH: RATE_LABELS[RATE_REACH],
    RATE_IMPRESSIONS: RATE_LABELS[RATE_IMPRESSIONS],
}
MIN_POSTS_PER_GROUP = 3     # groups with fewer posts are flagged as "low sample"
NOT_AVAILABLE = "Not available in this dataset"


# ----------------------------------------------------------------------------
# Engagement columns
# ----------------------------------------------------------------------------
def engagement_components(df):
    """Which of likes / comments / shares exist in this dataset."""
    return [c for c in ("likes", "comments", "shares") if c in df.columns]


def add_engagement_columns(df):
    """
    Return a copy of df with extra columns:
      interactions                 likes + comments (+ shares). Missing if ANY component is missing for that post.
      engagement_rate_reach        only where reach > 0
      engagement_rate_impressions  only where impressions > 0
    """
    out = df.copy()
    components = engagement_components(out)
    out["interactions"] = out[components].sum(axis=1, min_count=len(components))
    for denominator, rate_col in (("reach", RATE_REACH), ("impressions", RATE_IMPRESSIONS)):
        if denominator in out.columns:
            safe_denominator = out[denominator].where(out[denominator] > 0)   # 0 or NaN -> NaN (no divide-by-zero)
            out[rate_col] = out["interactions"] / safe_denominator * 100
    return out


def choose_rate(df):
    """
    Pick ONE engagement rate for the whole analysis (so rates are always comparable).
    Prefers the reach-based rate; uses the impressions-based rate only if it has more valid values.
    Returns (column_name or None, label, explanation).
    """
    valid = {col: int(df[col].notna().sum()) for col in (RATE_REACH, RATE_IMPRESSIONS) if col in df.columns}
    valid = {col: n for col, n in valid.items() if n > 0}
    components = " + ".join(c.capitalize() for c in engagement_components(df))
    if not valid:
        return None, "Engagement rate", (
            "Engagement rate cannot be calculated because no valid reach or impressions values are available. "
            "Rankings use a selected raw metric instead."
        )
    column = max(valid, key=lambda c: (valid[c], c == RATE_REACH))
    denominator = "Reach" if column == RATE_REACH else "Impressions"
    note = f"Calculated as ({components}) / {denominator} x 100, only for posts where {denominator.lower()} is greater than 0."
    if "shares" not in df.columns:
        note += " Shares are not in this dataset, so they are not included."
    if len(valid) == 2:
        other = RATE_IMPRESSIONS if column == RATE_REACH else RATE_REACH
        note += f" The {RATE_LABELS[other]} also exists but is not used here because the two rates are not equivalent."
    return column, RATE_LABELS[column], note


def available_metric_options(df, rate_col):
    """{column: label} of every metric the user can rank or chart by, in a sensible order."""
    options = {}
    if rate_col:
        options[rate_col] = RATE_LABELS[rate_col]
    for col in ("interactions", "likes", "comments", "shares", "reach", "impressions", "clicks"):
        if col in df.columns and df[col].notna().any():
            options[col] = METRIC_LABELS[col]
    return options


# ----------------------------------------------------------------------------
# Filtering
# ----------------------------------------------------------------------------
def apply_filters(df, start=None, end=None, platforms=None, content_types=None, topics=None):
    """Return only the posts matching all filters. None means 'do not filter on this'."""
    mask = pd.Series(True, index=df.index)
    if start is not None:
        mask &= df["post_date"] >= pd.Timestamp(start)
    if end is not None:
        mask &= df["post_date"] <= pd.Timestamp(end)
    for column, chosen in (("platform", platforms), ("content_type", content_types), ("topic", topics)):
        if chosen is not None and column in df.columns:
            mask &= df[column].isin(chosen)
    return df[mask].copy()


# ----------------------------------------------------------------------------
# Totals and summary
# ----------------------------------------------------------------------------
def metric_total(df, column):
    """Sum of a column, or None if the column is missing / completely empty (never a fake 0)."""
    if column not in df.columns or df[column].notna().sum() == 0:
        return None
    return float(df[column].sum())


def post_ranking_basis(df, rate_col):
    """The column used to decide 'best' and 'lowest' post, plus its label."""
    if rate_col and df[rate_col].notna().sum() >= 2:
        return rate_col, RATE_LABELS[rate_col]
    return "interactions", "Interactions (raw count - not comparable across different audience sizes)"


def best_and_worst_posts(df, rate_col):
    """
    Returns dict(best=row, worst=row or None, basis_label=str), or None when there are no rated posts.
    'worst' is None if fewer than 2 posts can be compared.
    """
    basis, label = post_ranking_basis(df, rate_col)
    ranked = df.dropna(subset=[basis])
    if ranked.empty:
        return None
    best = ranked.loc[ranked[basis].idxmax()]
    worst = ranked.loc[ranked[basis].idxmin()] if len(ranked) >= 2 and ranked[basis].nunique() > 1 else None
    return {"best": best, "worst": worst, "basis": basis, "basis_label": label}


def summarize(df, rate_col):
    """Headline numbers for a (filtered) dataset. Unavailable values are None."""
    summary = {"posts": len(df)}
    for col in ("likes", "comments", "shares", "impressions", "reach", "clicks", "interactions"):
        summary["total_" + col] = metric_total(df, col)
    if rate_col and rate_col in df.columns and df[rate_col].notna().any():
        summary["avg_rate"] = float(df[rate_col].mean())
        summary["posts_with_rate"] = int(df[rate_col].notna().sum())
    else:
        summary["avg_rate"] = None
        summary["posts_with_rate"] = 0
    return summary


# ----------------------------------------------------------------------------
# Group comparisons (platform / content type / topic)
# ----------------------------------------------------------------------------
def group_summary(df, by, rate_col):
    """One row per group (e.g. per platform) with counts, totals and average engagement."""
    if by not in df.columns or df.empty:
        return pd.DataFrame()
    rows = []
    for label, part in df.groupby(by):
        row = {by: label, "posts": len(part)}
        for col in ("likes", "comments", "shares"):
            if col in df.columns:
                row["total_" + col] = part[col].sum(min_count=1)
        row["avg_interactions"] = part["interactions"].mean()
        if rate_col:
            row["avg_engagement_rate"] = part[rate_col].mean()
            row["posts_with_rate"] = int(part[rate_col].notna().sum())
        row["enough_posts"] = len(part) >= MIN_POSTS_PER_GROUP
        rows.append(row)
    result = pd.DataFrame(rows)
    sort_col = "avg_engagement_rate" if rate_col else "avg_interactions"
    return result.sort_values(sort_col, ascending=False, na_position="last").reset_index(drop=True)


# ----------------------------------------------------------------------------
# Trends over time
# ----------------------------------------------------------------------------
def choose_frequency(df):
    """Pick day / week / month grouping from the length of the date range. Returns (pandas_freq, name)."""
    if df.empty:
        return "D", "day"
    span_days = (df["post_date"].max() - df["post_date"].min()).days
    if span_days <= 45:
        return "D", "day"
    if span_days <= 200:
        return "W-MON", "week"
    return "MS", "month"


def time_series(df, rate_col, freq):
    """Totals per time period (periods without posts are left out)."""
    if df.empty:
        return pd.DataFrame()
    grouped = df.groupby(pd.Grouper(key="post_date", freq=freq))
    out = pd.DataFrame({"posts": grouped.size()})
    for col in ("likes", "comments", "shares", "interactions"):
        if col in df.columns:
            out[col] = grouped[col].sum(min_count=1)
    if rate_col:
        out["avg_engagement_rate"] = grouped[rate_col].mean()
    out = out[out["posts"] > 0].reset_index()
    return out


def compare_periods(df, period_a, period_b, rate_col):
    """
    Compare two date periods, each given as (start, end). Returns a DataFrame with one row per period
    and the same columns for both, so the two are directly comparable.
    """
    rows = []
    for name, (start, end) in (("Period A", period_a), ("Period B", period_b)):
        part = apply_filters(df, start=start, end=end)
        row = {
            "period": name,
            "from": pd.Timestamp(start).date(),
            "to": pd.Timestamp(end).date(),
            "posts": len(part),
            "total_interactions": part["interactions"].sum(min_count=1),
            "avg_interactions_per_post": part["interactions"].mean(),
        }
        if rate_col:
            row["avg_engagement_rate"] = part[rate_col].mean()
        rows.append(row)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Ranking posts
# ----------------------------------------------------------------------------
def rank_posts(df, metric, ascending=False):
    """Posts sorted by a metric (posts missing that metric are left out). Adds a 'rank' column."""
    if metric not in df.columns:
        return pd.DataFrame()
    ranked = df.dropna(subset=[metric]).sort_values(metric, ascending=ascending, kind="stable").copy()
    ranked.insert(0, "rank", range(1, len(ranked) + 1))
    return ranked


def explain_post(row, df, metric, metric_label):
    """A plain-English reason for a post's position, calculated from the data."""
    if metric not in df.columns or pd.isna(row.get(metric)):
        return f"{metric_label} is missing for this post, so it cannot be ranked."
    values = df[metric].dropna()
    value = float(row[metric])
    position = int((values > value).sum()) + 1
    median = float(values.median())
    text = f"Ranked #{position} of {len(values)} on {metric_label}: {format_number(value, 2)} vs. a median of {format_number(median, 2)}"
    if median > 0:
        text += f" ({(value - median) / median * 100:+.0f}% vs. median)."
    else:
        text += "."
    parts = {c: row[c] for c in ("likes", "comments", "shares") if c in row.index and pd.notna(row[c])}
    total = sum(parts.values())
    if total > 0 and len(parts) > 1:
        main = max(parts, key=parts.get)
        text += f" {main.capitalize()} made up {parts[main] / total * 100:.0f}% of its interactions."
    return text


# ----------------------------------------------------------------------------
# Formatting helpers (shared by the app and the reports)
# ----------------------------------------------------------------------------
def format_number(value, decimals=0):
    """1234.5 -> '1,235'. None / NaN -> 'Not available'."""
    if value is None or pd.isna(value):
        return "Not available"
    return f"{value:,.{decimals}f}"


def format_percent(value, decimals=2):
    """1.234 -> '1.23%'. None / NaN -> 'Not available'."""
    if value is None or pd.isna(value):
        return "Not available"
    return f"{value:.{decimals}f}%"
