"""Tests for CSV / Excel export and report generation (modules/reports.py)."""
import io
import unittest

import pandas as pd

from helpers import good_rows, make_df
from modules import data_loader, data_validation as dv, insights, metrics, reports


def build_report(platforms=None):
    raw = data_loader.load_sample_data()
    result = dv.validate_and_clean(dv.apply_mapping(raw, dv.suggest_column_mapping(raw.columns)))
    df = metrics.add_engagement_columns(result.data)
    rate_col, rate_label, note = metrics.choose_rate(df)
    filtered = metrics.apply_filters(df, platforms=platforms)
    found = insights.generate_insights(filtered, rate_col, rate_label)
    return df, filtered, reports.build_report_data(filtered, "Demo Mode (test)", "all dates", "none", rate_col, note,
                                                    found, result.warnings, len(df))


class TestExports(unittest.TestCase):
    def test_csv_export_round_trip(self):
        df, _, _ = build_report()
        raw = data_loader.read_data_file(io.BytesIO(reports.dataframe_to_csv_bytes(df)), "out.csv")
        self.assertEqual(len(raw), len(df))
        self.assertEqual(raw["post_date"].iloc[0], df["post_date"].iloc[0].strftime("%Y-%m-%d"))

    def test_excel_export_round_trip_with_extra_sheet(self):
        df, _, report = build_report()
        data = reports.dataframe_to_excel_bytes(df, "Cleaned data", {"Summary": pd.DataFrame(report["summary_rows"], columns=["Measure", "Value"])})
        book = pd.ExcelFile(io.BytesIO(data))
        self.assertEqual(book.sheet_names, ["Cleaned data", "Summary"])
        self.assertEqual(len(book.parse("Cleaned data")), len(df))

    def test_missing_values_stay_blank_in_export(self):
        df, _, _ = build_report()
        text = reports.dataframe_to_csv_bytes(df).decode("utf-8-sig")
        self.assertNotIn("nan", text.lower().replace("finance", ""))

    def test_templates(self):
        csv_text = reports.template_csv_bytes().decode("utf-8-sig").splitlines()
        self.assertEqual(csv_text[0].split(","), dv.STANDARD_COLUMNS)
        self.assertEqual(len(csv_text), 4)                                     # header + 3 blank rows
        book = pd.ExcelFile(io.BytesIO(reports.template_excel_bytes()))
        self.assertEqual(book.sheet_names, ["Template", "Instructions"])

    def test_example_dataset_download_matches_file(self):
        self.assertEqual(data_loader.sample_file_bytes(), data_loader.SAMPLE_DATA_PATH.read_bytes())


class TestReports(unittest.TestCase):
    def test_pdf_report_is_generated(self):
        _, _, report = build_report()
        pdf = reports.build_pdf_report(report)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 3000)

    def test_html_and_text_reports_contain_current_numbers(self):
        _, filtered, report = build_report(platforms=["LinkedIn"])
        html = reports.build_html_report(report).decode("utf-8")
        text = reports.build_summary_text(report).decode("utf-8")
        self.assertIn("SocialPulse", html)
        self.assertIn(f"Posts analysed: {len(filtered)}", html)
        self.assertIn(f"Posts analysed: {len(filtered)}", text)
        self.assertIn("LinkedIn", " ".join(report["top_posts"]["platform"].unique()))

    def test_report_changes_with_filters(self):
        _, _, full = build_report()
        _, _, partial = build_report(platforms=["X"])
        self.assertNotEqual(full["summary_rows"], partial["summary_rows"])

    def test_html_report_escapes_user_text(self):
        _, _, report = build_report()
        report["findings"] = [{"title": "<script>alert(1)</script>", "text": "x", "posts": 1}]
        self.assertNotIn("<script>alert(1)</script>", reports.build_html_report(report).decode("utf-8"))

    def test_pdf_handles_unusual_characters(self):
        _, _, report = build_report()
        report["findings"] = [{"title": "Emoji \U0001F600 & <tags> \u4e2d\u6587", "text": "caf\u00e9 \u2013 test", "posts": 1}]
        self.assertTrue(reports.build_pdf_report(report).startswith(b"%PDF"))

    def test_report_for_data_with_no_reach_or_impressions(self):
        rows = [[f"2026-01-{i + 1:02d}", 10 + i, 5] for i in range(8)]
        result = dv.validate_and_clean(make_df(rows, ["post_date", "likes", "comments"]))
        df = metrics.add_engagement_columns(result.data)
        rate_col, rate_label, note = metrics.choose_rate(df)
        found = insights.generate_insights(df, rate_col, rate_label, result.effects_of_missing)
        report = reports.build_report_data(df, "test", "all", "none", rate_col, note, found, result.warnings, len(df))
        self.assertTrue(reports.build_pdf_report(report).startswith(b"%PDF"))
        self.assertIn("Not available", " ".join(v for _, v in report["summary_rows"]))


if __name__ == "__main__":
    unittest.main()
