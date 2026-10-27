"""Tests for loading files and validating data (modules/data_loader.py and modules/data_validation.py)."""
import io
import unittest

import numpy as np
import pandas as pd

from helpers import clean, good_rows, make_df
from modules import data_loader, data_validation as dv, reports


def csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8")


class TestLoadingFiles(unittest.TestCase):
    def test_sample_dataset_loads_and_validates(self):
        raw = data_loader.load_sample_data()
        mapping = dv.suggest_column_mapping(raw.columns)
        result = dv.validate_and_clean(dv.apply_mapping(raw, mapping))
        self.assertTrue(result.ok)
        self.assertEqual(result.rows_used, 72)
        self.assertEqual(set(result.available_metrics), {"likes", "comments", "shares", "impressions", "reach", "clicks"})

    def test_valid_csv_upload(self):
        raw = data_loader.read_data_file(io.BytesIO(csv_bytes(make_df(good_rows()))), "mine.csv")
        self.assertTrue(clean(raw).ok)
        self.assertEqual(len(raw), 6)

    def test_valid_excel_upload(self):
        buffer = io.BytesIO()
        make_df(good_rows()).to_excel(buffer, index=False)
        raw = data_loader.read_data_file(io.BytesIO(buffer.getvalue()), "mine.xlsx")
        result = clean(raw)
        self.assertTrue(result.ok)
        self.assertEqual(result.rows_used, 6)

    def test_excel_template_is_readable_and_blank(self):
        raw = data_loader.read_data_file(io.BytesIO(reports.template_excel_bytes()), "template.xlsx")
        self.assertEqual(list(raw.columns), dv.STANDARD_COLUMNS)
        self.assertFalse(clean(raw).ok)       # blank template rows are not real posts

    def test_csv_template_blank_rows_are_not_posts(self):
        raw = data_loader.read_data_file(io.BytesIO(reports.template_csv_bytes()), "template.csv")
        result = clean(raw)
        self.assertFalse(result.ok)
        self.assertTrue(any("blank" in e.lower() for e in result.errors))

    def test_semicolon_csv_and_cp1252_encoding(self):
        text = "post_date;likes;comments;caption\n2026-01-01;5;1;caf\u00e9 day\n2026-01-02;7;2;hello\n"
        raw = data_loader.read_data_file(io.BytesIO(text.encode("cp1252")), "euro.csv")
        self.assertEqual(list(raw.columns), ["post_date", "likes", "comments", "caption"])
        self.assertEqual(raw["caption"].iloc[0], "caf\u00e9 day")

    def test_zero_byte_file_gives_clear_error(self):
        with self.assertRaises(data_loader.DataLoadError):
            data_loader.read_data_file(io.BytesIO(b""), "empty.csv")

    def test_unsupported_file_types(self):
        for name in ("notes.txt", "old.xls"):
            with self.assertRaises(data_loader.DataLoadError):
                data_loader.read_data_file(io.BytesIO(b"abc"), name)

    def test_header_only_file_is_reported_as_empty(self):
        raw = data_loader.read_data_file(io.BytesIO(b"post_date,likes,comments\n"), "h.csv")
        result = clean(raw)
        self.assertFalse(result.ok)
        self.assertTrue(result.errors)


class TestValidationRules(unittest.TestCase):
    def test_empty_dataframe(self):
        self.assertFalse(dv.validate_and_clean(pd.DataFrame()).ok)
        self.assertFalse(dv.validate_and_clean(None).ok)

    def test_missing_required_column(self):
        df = make_df([["2026-01-01", 5]], ["post_date", "likes"])     # no comments
        result = clean(df)
        self.assertFalse(result.ok)
        self.assertIn("comments", result.errors[0])

    def test_invalid_dates_are_removed_and_reported(self):
        rows = good_rows(6)
        rows[1][1] = "not a date"
        rows[2][1] = None
        result = clean(make_df(rows))
        self.assertEqual(result.rows_used, 4)
        self.assertTrue(any("date" in w.lower() for w in result.warnings))

    def test_exact_duplicate_rows_removed(self):
        rows = good_rows(5)
        rows.append(list(rows[0]))
        result = clean(make_df(rows))
        self.assertEqual(result.rows_used, 5)
        self.assertTrue(any("duplicate" in w.lower() for w in result.warnings))

    def test_reused_post_id_removed(self):
        rows = good_rows(5)
        rows[3][0] = "P0"                      # same ID as the first post but different numbers
        result = clean(make_df(rows))
        self.assertEqual(result.rows_used, 4)

    def test_missing_numeric_values_stay_missing_not_zero(self):
        rows = good_rows(6)
        rows[2][8] = None                      # shares blank
        result = clean(make_df(rows))
        self.assertTrue(result.data["shares"].isna().sum() == 1)
        self.assertEqual((result.data["shares"] == 0).sum(), 0)
        self.assertTrue(any("shares" in w for w in result.warnings))

    def test_negative_values_become_missing(self):
        rows = good_rows(6)
        rows[0][6] = -4
        result = clean(make_df(rows))
        self.assertEqual(result.data["likes"].isna().sum(), 1)
        self.assertTrue(any("negative" in w.lower() for w in result.warnings))

    def test_text_in_numeric_column_becomes_missing(self):
        rows = good_rows(6)
        rows[1][7] = "lots"
        result = clean(make_df(rows))
        self.assertEqual(result.data["comments"].isna().sum(), 1)
        self.assertTrue(any("not valid numbers" in w for w in result.warnings))

    def test_thousands_separator_is_understood(self):
        rows = good_rows(6)
        rows[0][6] = "1,200"
        result = clean(make_df(rows))
        self.assertEqual(result.data["likes"].max(), 1200)

    def test_zero_reach_and_impressions_warn(self):
        rows = good_rows(6)
        rows[0][10] = 0
        rows[1][9] = 0
        result = clean(make_df(rows))
        self.assertTrue(any("'reach' is 0" in w for w in result.warnings))
        self.assertTrue(any("'impressions' is 0" in w for w in result.warnings))

    def test_missing_optional_columns_explain_effects(self):
        df = make_df([[f"2026-02-0{i + 1}", 10, 2] for i in range(6)], ["post_date", "likes", "comments"])
        result = clean(df)
        self.assertTrue(result.ok)
        for column in ("shares", "reach", "impressions", "clicks", "platform"):
            self.assertIn(column, result.missing_optional)
        self.assertTrue(any("reach" in e.lower() for e in result.effects_of_missing))
        self.assertTrue(all(pid.startswith("ROW-") for pid in result.data["post_id"]))

    def test_too_few_rows_warns(self):
        result = clean(make_df(good_rows(2)))
        self.assertTrue(result.ok)
        self.assertTrue(any("usable post" in w for w in result.warnings))

    def test_label_variants_are_unified_and_unknown_platform_kept(self):
        rows = good_rows(6)
        rows[0][2], rows[1][2], rows[2][2] = "instagram", "INSTAGRAM ", "MyNetwork"
        result = clean(make_df(rows))
        self.assertIn("MyNetwork", set(result.data["platform"]))
        self.assertEqual(sum(result.data["platform"].str.lower() == "instagram"), 5)
        self.assertEqual(result.data["platform"].value_counts()["Instagram"], 5)
        self.assertTrue(any("MyNetwork" in i for i in result.info))

    def test_original_dataframe_is_not_modified(self):
        original = make_df(good_rows(6))
        snapshot = original.copy(deep=True)
        clean(original)
        pd.testing.assert_frame_equal(original, snapshot)


class TestColumnMapping(unittest.TestCase):
    def test_aliases_are_detected(self):
        mapping = dv.suggest_column_mapping(["Date", "Network", "Format", "Likes", "Comment", "Link Clicks", "Views"])
        self.assertEqual(mapping["post_date"], "Date")
        self.assertEqual(mapping["platform"], "Network")
        self.assertEqual(mapping["content_type"], "Format")
        self.assertEqual(mapping["comments"], "Comment")
        self.assertEqual(mapping["clicks"], "Link Clicks")
        self.assertEqual(mapping["impressions"], "Views")

    def test_check_mapping_reports_missing_and_duplicate(self):
        mapping = {c: None for c in dv.STANDARD_COLUMNS}
        self.assertEqual(len(dv.check_mapping(mapping)), 3)
        mapping.update(post_date="A", likes="B", comments="B")
        self.assertTrue(any("more than one" in e for e in dv.check_mapping(mapping)))

    def test_apply_mapping_renames_without_changing_input(self):
        raw = pd.DataFrame({"Date": ["2026-01-01"], "Likes": [1], "Comment": [2]})
        snapshot = raw.copy(deep=True)
        mapped = dv.apply_mapping(raw, dv.suggest_column_mapping(raw.columns))
        self.assertEqual(list(mapped.columns), ["post_date", "likes", "comments"])
        pd.testing.assert_frame_equal(raw, snapshot)


if __name__ == "__main__":
    unittest.main()
