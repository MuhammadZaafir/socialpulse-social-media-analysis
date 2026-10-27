"""Tests for calculations and insights (modules/metrics.py and modules/insights.py)."""
import unittest

import numpy as np
import pandas as pd

from helpers import clean, good_rows, make_df
from modules import data_loader, data_validation as dv, insights, metrics


def prepared(rows=None, columns=None):
    """Validate + add engagement columns, like the app does."""
    result = clean(make_df(rows if rows is not None else good_rows(), columns))
    assert result.ok, result.errors
    return metrics.add_engagement_columns(result.data)


def sample_df():
    raw = data_loader.load_sample_data()
    result = dv.validate_and_clean(dv.apply_mapping(raw, dv.suggest_column_mapping(raw.columns)))
    return metrics.add_engagement_columns(result.data)


class TestEngagementRate(unittest.TestCase):
    def test_reach_formula(self):
        # (10 + 5 + 5) / 200 * 100 = 10%
        df = prepared([["A", "2026-01-01", "X", "Image", "c", "t", 10, 5, 5, 400, 200, 1]] * 1 + good_rows(5))
        self.assertAlmostEqual(df.loc[df["post_id"] == "A", metrics.RATE_REACH].iloc[0], 10.0)

    def test_impressions_formula_is_separate(self):
        df = prepared([["A", "2026-01-01", "X", "Image", "c", "t", 10, 5, 5, 400, 200, 1]] + good_rows(5))
        row = df[df["post_id"] == "A"].iloc[0]
        self.assertAlmostEqual(row[metrics.RATE_IMPRESSIONS], 5.0)       # 20 / 400
        self.assertNotAlmostEqual(row[metrics.RATE_IMPRESSIONS], row[metrics.RATE_REACH])

    def test_zero_reach_gives_missing_rate_not_error(self):
        rows = good_rows(6)
        rows[0][10] = 0
        df = prepared(rows)
        self.assertTrue(np.isnan(df[metrics.RATE_REACH].iloc[0]))
        self.assertFalse(np.isinf(df[metrics.RATE_REACH]).any())

    def test_zero_impressions_gives_missing_rate(self):
        rows = good_rows(6)
        rows[0][9] = 0
        df = prepared(rows)
        self.assertTrue(np.isnan(df[metrics.RATE_IMPRESSIONS].iloc[0]))

    def test_shares_column_missing_uses_likes_and_comments_only(self):
        rows = [[f"2026-01-0{i + 1}", 10, 5, 100] for i in range(6)]
        df = prepared(rows, ["post_date", "likes", "comments", "reach"])
        self.assertEqual(df["interactions"].iloc[0], 15)
        self.assertAlmostEqual(df[metrics.RATE_REACH].iloc[0], 15.0)
        _, _, note = metrics.choose_rate(df)
        self.assertIn("Shares are not in this dataset", note)

    def test_blank_share_value_makes_that_posts_rate_missing(self):
        rows = good_rows(6)
        rows[3][8] = None
        df = prepared(rows)
        self.assertTrue(np.isnan(df["interactions"].iloc[3]))
        self.assertTrue(np.isnan(df[metrics.RATE_REACH].iloc[3]))

    def test_no_reach_or_impressions_means_no_rate(self):
        rows = [[f"2026-01-0{i + 1}", 10, 5] for i in range(6)]
        df = prepared(rows, ["post_date", "likes", "comments"])
        self.assertNotIn(metrics.RATE_REACH, df.columns)
        column, label, note = metrics.choose_rate(df)
        self.assertIsNone(column)
        self.assertIn("cannot be calculated", note)

    def test_choose_rate_prefers_reach_but_uses_impressions_when_reach_unusable(self):
        df = prepared()
        self.assertEqual(metrics.choose_rate(df)[0], metrics.RATE_REACH)
        rows = [[f"2026-01-0{i + 1}", 10, 5, 1000] for i in range(6)]
        only_impressions = prepared(rows, ["post_date", "likes", "comments", "impressions"])
        column, label, _ = metrics.choose_rate(only_impressions)
        self.assertEqual(column, metrics.RATE_IMPRESSIONS)
        self.assertIn("Impressions-Based", label)


class TestSummaries(unittest.TestCase):
    def test_unavailable_metrics_are_none_not_zero(self):
        rows = [[f"2026-01-0{i + 1}", 10, 5] for i in range(6)]
        df = prepared(rows, ["post_date", "likes", "comments"])
        summary = metrics.summarize(df, None)
        self.assertEqual(summary["total_likes"], 60)
        for key in ("total_shares", "total_reach", "total_impressions", "total_clicks", "avg_rate"):
            self.assertIsNone(summary[key])
        self.assertEqual(metrics.format_number(None), "Not available")

    def test_totals_follow_filters(self):
        df = sample_df()
        filtered = metrics.apply_filters(df, platforms=["LinkedIn"])
        self.assertEqual(metrics.summarize(filtered, metrics.RATE_REACH)["posts"], 11)
        self.assertEqual(metrics.summarize(filtered, metrics.RATE_REACH)["total_likes"], filtered["likes"].sum())
        self.assertLess(metrics.summarize(filtered, None)["total_likes"], metrics.summarize(df, None)["total_likes"])

    def test_empty_filter_result(self):
        df = sample_df()
        empty = metrics.apply_filters(df, start="2030-01-01")
        self.assertTrue(empty.empty)
        summary = metrics.summarize(empty, metrics.RATE_REACH)
        self.assertEqual(summary["posts"], 0)
        self.assertIsNone(summary["total_likes"])
        self.assertIsNone(metrics.best_and_worst_posts(empty, metrics.RATE_REACH))
        self.assertEqual(insights.generate_insights(empty, metrics.RATE_REACH, "x")["findings"], [])

    def test_best_and_worst_post(self):
        df = prepared()
        pair = metrics.best_and_worst_posts(df, metrics.RATE_REACH)
        self.assertEqual(pair["best"]["post_id"], "P5")
        self.assertEqual(pair["worst"]["post_id"], "P0")

    def test_worst_is_none_when_no_comparison_possible(self):
        df = prepared(good_rows(6)[:1] + [])  # one post only
        pair = metrics.best_and_worst_posts(df, metrics.RATE_REACH)
        self.assertIsNone(pair["worst"])


class TestGroupsTrendsRanking(unittest.TestCase):
    def test_group_summary_flags_small_groups(self):
        rows = good_rows(6)
        rows[0][2] = "Facebook"                     # a platform with just 1 post
        table = metrics.group_summary(prepared(rows), "platform", metrics.RATE_REACH)
        flags = dict(zip(table["platform"], table["enough_posts"]))
        self.assertFalse(flags["Facebook"])
        self.assertTrue(flags["Instagram"])
        self.assertEqual(table["posts"].sum(), 6)

    def test_time_series_and_frequency_choice(self):
        df = sample_df()
        freq, name = metrics.choose_frequency(df)
        self.assertEqual(name, "week")             # sample spans ~6 months
        series = metrics.time_series(df, metrics.RATE_REACH, freq)
        self.assertEqual(series["posts"].sum(), len(df))
        self.assertEqual(metrics.choose_frequency(df[df["post_date"] < "2026-01-20"])[1], "day")

    def test_compare_periods(self):
        df = sample_df()
        comparison = metrics.compare_periods(df, ("2026-01-01", "2026-03-31"), ("2026-04-01", "2026-06-30"), metrics.RATE_REACH)
        self.assertEqual(comparison["posts"].sum(), len(df))
        self.assertEqual(list(comparison["period"]), ["Period A", "Period B"])

    def test_rank_posts_and_explanation(self):
        df = prepared()
        ranked = metrics.rank_posts(df, "likes")
        self.assertEqual(ranked["post_id"].iloc[0], "P5")
        self.assertEqual(list(ranked["rank"]), [1, 2, 3, 4, 5, 6])
        text = metrics.explain_post(ranked.iloc[0], ranked, "likes", "Likes")
        self.assertIn("Ranked #1 of 6", text)
        self.assertEqual(metrics.rank_posts(df, "not_a_column").shape[0], 0)

    def test_rank_skips_posts_missing_the_metric(self):
        rows = good_rows(6)
        rows[2][10] = None
        ranked = metrics.rank_posts(prepared(rows), "reach")
        self.assertEqual(len(ranked), 5)


class TestInsights(unittest.TestCase):
    def test_findings_are_data_driven_and_state_post_counts(self):
        df = sample_df()
        result = insights.generate_insights(df, metrics.RATE_REACH, metrics.RATE_LABELS[metrics.RATE_REACH])
        titles = [f["title"] for f in result["findings"]]
        self.assertIn("Content type comparison", titles)
        content = next(f for f in result["findings"] if f["title"] == "Content type comparison")
        self.assertIn("Video", content["text"])
        self.assertIn("In this dataset", content["text"])
        self.assertGreater(content["posts"], 0)
        self.assertTrue(result["recommendations"])
        # The highest content type really is the one with the highest average rate:
        table = metrics.group_summary(df, "content_type", metrics.RATE_REACH)
        self.assertEqual(table["content_type"].iloc[0], "Video")

    def test_insights_change_with_the_filter(self):
        df = sample_df()
        label = metrics.RATE_LABELS[metrics.RATE_REACH]
        full = insights.generate_insights(df, metrics.RATE_REACH, label)
        only_x = insights.generate_insights(metrics.apply_filters(df, platforms=["X"]), metrics.RATE_REACH, label)
        self.assertNotEqual([f["text"] for f in full["findings"]], [f["text"] for f in only_x["findings"]])
        self.assertFalse(any(f["title"] == "Platform comparison" for f in only_x["findings"]))

    def test_small_samples_are_not_compared(self):
        df = prepared(good_rows(6)[:4])
        result = insights.generate_insights(df, metrics.RATE_REACH, "rate")
        text = " ".join(f["text"] for f in result["findings"])
        self.assertIn("Not enough posts", text)
        self.assertTrue(any("Only 4" in l for l in result["limitations"]))

    def test_no_rate_means_no_platform_ranking(self):
        rows = [[f"2026-01-{i + 1:02d}", "Instagram" if i % 2 else "Facebook", 10 + i, 5] for i in range(8)]
        df = prepared(rows, ["post_date", "platform", "likes", "comments"])
        result = insights.generate_insights(df, None, "Engagement rate")
        platform = next(f for f in result["findings"] if f["title"].startswith("Platform"))
        self.assertIn("not shown", platform["title"])
        self.assertTrue(any("reach or impressions" in r["text"].lower() for r in result["recommendations"]))


if __name__ == "__main__":
    unittest.main()
