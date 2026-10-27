"""
insights.py
-----------
Turns the numbers into plain-English findings and cautious recommendations.

Rules followed here:
* Every finding is calculated from the dataset passed in (the currently filtered data).
* Every finding states how many posts it is based on.
* Language is cautious ("In this dataset ..."). We never claim a cause or statistical significance.
* Groups with fewer than MIN_POSTS_PER_GROUP posts are not compared.
"""

import pandas as pd

from modules import metrics
from modules.metrics import MIN_POSTS_PER_GROUP, format_number, format_percent

MIN_POSTS_FOR_TREND = 6        # at least 3 posts in each half of the period
SIMILAR_THRESHOLD = 0.10       # leaders less than 10% ahead are described as "similar"
DIMENSIONS = {"platform": "platform", "content_type": "content type", "topic": "topic"}


def _value_text(value, rate_col):
    """Format a group average either as a percentage (rates) or as a plain number (interactions)."""
    return format_percent(value) if rate_col else format_number(value, 1)


def _post_label(row):
    caption = f' - "{row["caption"][:60]}"' if row.get("caption") else ""
    return f'{row["post_id"]} ({row["post_date"].date()}, {row["platform"]}){caption}'


def _finding(title, text, posts):
    return {"title": title, "text": text, "posts": int(posts)}


def _best_and_worst_finding(df, rate_col):
    pair = metrics.best_and_worst_posts(df, rate_col)
    if pair is None:
        return None
    basis, label = pair["basis"], pair["basis_label"]
    best = pair["best"]
    shown = format_percent(best[basis]) if basis != "interactions" else format_number(best[basis])
    text = f"Highest {label}: {_post_label(best)} with {shown}."
    if pair["worst"] is not None:
        worst = pair["worst"]
        shown_w = format_percent(worst[basis]) if basis != "interactions" else format_number(worst[basis])
        text += f" Lowest: {_post_label(worst)} with {shown_w}."
    return _finding("Best and lowest-performing posts", text, df[basis].notna().sum())


def _group_finding(df, dimension, name, rate_col, rate_label):
    """Compare groups (e.g. content types). Returns (finding or None, leader_name or None)."""
    if dimension not in df.columns or df[dimension].nunique() < 2:
        return None, None
    if dimension == "platform" and not rate_col:
        # Raw counts across platforms mostly reflect audience size, so we do not rank them.
        return _finding(
            "Platform comparison not shown",
            "Reach or impressions are needed to compare platforms fairly. Without them, raw likes and comments "
            "mostly reflect each platform's audience size.", len(df)), None

    table = metrics.group_summary(df, dimension, rate_col)
    table = table[table["enough_posts"]]
    table = table[table["avg_engagement_rate" if rate_col else "avg_interactions"].notna()]
    skipped = df[dimension].nunique() - len(table)
    if len(table) < 2:
        return _finding(
            f"{name.capitalize()} comparison",
            f"Not enough posts per {name} to compare (each group needs at least {MIN_POSTS_PER_GROUP} posts).",
            len(df)), None

    value_col = "avg_engagement_rate" if rate_col else "avg_interactions"
    top, bottom = table.iloc[0], table.iloc[-1]
    measure = f"average {rate_label}" if rate_col else "average interactions per post (likes + comments + shares)"
    relative_gap = (top[value_col] - bottom[value_col]) / bottom[value_col] if bottom[value_col] > 0 else float("inf")

    if relative_gap < SIMILAR_THRESHOLD:
        text = (f"In this dataset, {name}s performed similarly on {measure}: "
                f"{top[dimension]} {_value_text(top[value_col], rate_col)} vs. "
                f"{bottom[dimension]} {_value_text(bottom[value_col], rate_col)}.")
        leader = None
    else:
        text = (f"In this dataset, {top[dimension]} had the highest {measure} "
                f"({_value_text(top[value_col], rate_col)} across {int(top['posts'])} posts), compared with "
                f"{bottom[dimension]} at {_value_text(bottom[value_col], rate_col)} across {int(bottom['posts'])} posts.")
        leader = top[dimension]
    if skipped > 0:
        text += f" {skipped} {name}(s) with fewer than {MIN_POSTS_PER_GROUP} posts were left out."
    if not rate_col:
        text += " (Raw counts - no reach or impressions available, so audience size may influence this.)"
    return _finding(f"{name.capitalize()} comparison", text, table["posts"].sum()), leader


def _trend_finding(df, rate_col, rate_label):
    """Compare the first half and the second half of the selected date range."""
    if len(df) < MIN_POSTS_FOR_TREND:
        return None
    start, end = df["post_date"].min(), df["post_date"].max()
    if (end - start).days < 14:
        return None
    midpoint = start + (end - start) / 2
    first, second = df[df["post_date"] <= midpoint], df[df["post_date"] > midpoint]
    column = rate_col if rate_col else "interactions"
    if min(first[column].notna().sum(), second[column].notna().sum()) < 3:
        return None
    a, b = first[column].mean(), second[column].mean()
    if a <= 0:
        return None
    change = (b - a) / a * 100
    measure = rate_label if rate_col else "interactions per post"
    fmt = (lambda v: format_percent(v)) if rate_col else (lambda v: format_number(v, 1))
    if abs(change) < 5:
        direction = "changed little"
    else:
        direction = "increased" if change > 0 else "decreased"
    text = (f"In this dataset, average {measure} {direction} between the first half of the period "
            f"({start.date()} to {midpoint.date()}: {fmt(a)}, {len(first)} posts) and the second half "
            f"({(midpoint + pd.Timedelta(days=1)).date()} to {end.date()}: {fmt(b)}, {len(second)} posts); change {change:+.1f}%.")
    return _finding("Change over time", text, len(first) + len(second)), direction


def _investigation_finding(df, rate_col):
    """Posts with above-median reach but a very low engagement rate."""
    if not rate_col or "reach" not in df.columns or df[rate_col].notna().sum() < MIN_POSTS_PER_GROUP:
        return None
    reach_median = df["reach"].median()
    rate_median = df[rate_col].median()
    flagged = df[(df["reach"] >= reach_median) & (df[rate_col] < rate_median * 0.5)]
    flagged = flagged.sort_values("reach", ascending=False).head(3)
    if flagged.empty:
        return None
    lines = "; ".join(f"{_post_label(r)} - rate {format_percent(r[rate_col])}, reach {format_number(r['reach'])}"
                      for _, r in flagged.iterrows())
    text = (f"These posts reached at least the median audience but had less than half the median engagement rate "
            f"({format_percent(rate_median)}): {lines}.")
    return _finding("Posts that may deserve a closer look", text, len(flagged)), list(flagged["post_id"])


def generate_insights(df, rate_col, rate_label, missing_effects=None):
    """
    Build findings, recommendations and limitations from the (filtered) dataset.
    Returns {"findings": [...], "recommendations": [...], "limitations": [...]}.
    """
    findings, recommendations, limitations = [], [], []
    if df.empty:
        return {"findings": [], "recommendations": [], "limitations": ["There are no posts in the current selection."]}

    if len(df) < metrics.MIN_POSTS_PER_GROUP * 2:
        limitations.append(f"Only {len(df)} post(s) are selected. Findings are descriptive and should not be generalised.")
        recommendations.append({"text": "Collect and upload more posts before drawing conclusions.",
                                "basis": f"{len(df)} posts in the current selection."})

    best_worst = _best_and_worst_finding(df, rate_col)
    if best_worst:
        findings.append(best_worst)

    leaders = {}
    for dimension, name in DIMENSIONS.items():
        finding, leader = _group_finding(df, dimension, name, rate_col, rate_label)
        if finding:
            findings.append(finding)
        leaders[dimension] = leader

    trend = _trend_finding(df, rate_col, rate_label)
    if trend:
        findings.append(trend[0])
        if trend[1] == "decreased":
            recommendations.append({
                "text": "Review the most recent posts and compare them with earlier ones (topic, format, timing) "
                        "to look for possible reasons for the lower engagement.",
                "basis": trend[0]["title"] + ": " + trend[0]["text"][:120] + "..."})

    flagged = _investigation_finding(df, rate_col)
    if flagged:
        findings.append(flagged[0])
        recommendations.append({
            "text": f"Review caption, creative and timing of {', '.join(flagged[1])} to understand the low engagement.",
            "basis": "These posts had above-median reach but under half the median engagement rate."})

    phrasing = {   # how each dimension reads naturally in a sentence
        "platform": "more posts on {leader}",
        "content_type": "more {leader} posts",
        "topic": "more posts about {leader}",
    }
    for dimension, leader in leaders.items():
        if leader:
            recommendations.append({
                "text": f"Consider testing {phrasing[dimension].format(leader=leader)} and compare the results next period. "
                        f"This dataset shows higher observed engagement for {leader}, but it cannot show that {leader} caused it.",
                "basis": f"{DIMENSIONS[dimension].capitalize()} comparison (see findings)."})

    if not rate_col:
        limitations.append(metrics.choose_rate(df)[2])
        recommendations.append({
            "text": "Add reach or impressions to your data so engagement rates can be calculated and compared fairly.",
            "basis": "No valid reach or impressions values in the current data."})
    for effect in (missing_effects or []):
        limitations.append(effect)
    if "reach" in df.columns:
        limitations.append("Summing post-level reach does not give unique accounts reached: the same person may see several posts.")
    limitations.append("Differences between groups are observations, not proof of cause, and no statistical significance test is applied.")

    if not recommendations:
        recommendations.append({
            "text": "No clear action stands out in this selection. Keep tracking results and re-check when more posts are available.",
            "basis": f"{len(df)} posts analysed."})
    return {"findings": findings, "recommendations": recommendations, "limitations": limitations}
