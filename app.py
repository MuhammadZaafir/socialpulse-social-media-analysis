"""
SocialPulse - Social Media Engagement Analysis
==============================================
Run with:  python -m streamlit run app.py

This file only builds the screens (the user interface).
The real work happens in the modules/ folder:
    data_loader.py       reads CSV / Excel files
    data_validation.py   checks and cleans the data
    metrics.py           calculations (engagement rate, totals, trends, rankings)
    insights.py          plain-English findings and recommendations
    reports.py           templates, CSV / Excel / PDF / HTML downloads
"""

from datetime import timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from modules import data_loader, data_validation, insights, metrics, reports

st.set_page_config(page_title="SocialPulse", page_icon="📈", layout="wide")

APP_TITLE = "SocialPulse – Social Media Engagement Analysis"
APP_SUBTITLE = "Turn social media performance data into actionable insights."
PAGES = [
    "Overview Dashboard", "Data Upload", "Content Performance", "Trend Analysis",
    "Post Explorer", "Insights and Recommendations", "Reports and Downloads", "Help and Data Guide",
]
DEMO_MODE, UPLOAD_MODE = "Demo Mode", "Upload My Data"
NO_COLUMN = "(not in my file)"
DIMENSIONS = {"platform": "Platform", "content_type": "Content type", "topic": "Topic"}

CARD_CSS = """
<style>
.sp-card {border:1px solid rgba(128,128,128,.35); border-radius:10px; padding:12px 14px;
          background:rgba(128,128,128,.08); margin-bottom:10px; min-height:112px;}
.sp-label {font-size:.85rem; opacity:.8;}
.sp-value {font-size:1.7rem; font-weight:700; line-height:1.3;}
.sp-na {font-size:1rem; font-weight:600; opacity:.7;}
.sp-note {font-size:.75rem; opacity:.7;}
</style>
"""


# =============================================================================
# Session state helpers
# =============================================================================
def init_state():
    """Create the values we remember between clicks."""
    st.session_state.setdefault("uploader_counter", 0)
    st.session_state.setdefault("upload_version", 0)


def clear_stored_upload():
    """Forget the uploaded file and its analysis (the user's original file is never touched)."""
    for key in ("upload_raw", "upload_name", "upload_file_sig", "upload_mapping", "upload_result", "upload_result_sig"):
        st.session_state.pop(key, None)


def return_to_demo():
    """Button callback: remove the uploaded file and go back to Demo Mode."""
    clear_stored_upload()
    st.session_state["uploader_counter"] += 1      # new key => the upload box becomes empty
    st.session_state["data_mode"] = DEMO_MODE


def use_uploaded_data():
    """Button callback: analyse the uploaded file."""
    st.session_state["data_mode"] = UPLOAD_MODE


# =============================================================================
# Loading the active dataset
# =============================================================================
@st.cache_data
def load_demo_result():
    """Load and validate the bundled synthetic sample data (cached because it never changes)."""
    raw = data_loader.load_sample_data()
    mapping = data_validation.suggest_column_mapping(raw.columns)
    return data_validation.validate_and_clean(data_validation.apply_mapping(raw, mapping))


def get_dataset(mode):
    """
    Return information about the active dataset, or None if (in Upload mode) nothing was uploaded yet.
    Keys: result, label, key, df (cleaned data with engagement columns, or None if invalid), rate info.
    """
    if mode == DEMO_MODE:
        result = load_demo_result()
        label = "Demo Mode – synthetic sample dataset (demonstration data, not real company data)"
        key = "demo"
    else:
        result = st.session_state.get("upload_result")
        if result is None:
            return None
        label = f"Uploaded file – {st.session_state.get('upload_name', 'unknown file')}"
        key = f"upload-{st.session_state.get('upload_version', 0)}-{hash(st.session_state.get('upload_result_sig'))}"

    dataset = {"result": result, "label": label, "key": key, "df": None}
    if result.ok:
        df = metrics.add_engagement_columns(result.data)
        rate_col, rate_label, rate_note = metrics.choose_rate(df)
        dataset.update(df=df, rate_col=rate_col, rate_label=rate_label, rate_note=rate_note)
    return dataset


def sidebar_filters(df, key):
    """Draw the filters in the sidebar and return (filtered_df, period_text, filters_text)."""
    st.sidebar.subheader("Filters")
    first, last = df["post_date"].min().date(), df["post_date"].max().date()
    picked = st.sidebar.date_input("Date range", value=(first, last), min_value=first, max_value=last, key=f"f_date_{key}")
    if isinstance(picked, (tuple, list)):
        start = picked[0] if len(picked) > 0 else first
        end = picked[1] if len(picked) > 1 else start
    else:
        start = end = picked

    choices = {}
    for column, label in DIMENSIONS.items():
        options = sorted(df[column].unique())
        choices[column] = st.sidebar.multiselect(label, options, default=options, key=f"f_{column}_{key}")

    filtered = metrics.apply_filters(df, start, end, choices["platform"], choices["content_type"], choices["topic"])

    period_text = f"{start} to {end}"
    parts = [f"Date: {period_text}"]
    for column, label in DIMENSIONS.items():
        all_values = sorted(df[column].unique())
        parts.append(f"{label}: " + ("all" if set(choices[column]) == set(all_values) else ", ".join(choices[column]) or "none"))
    st.sidebar.caption(f"Showing **{len(filtered)}** of **{len(df)}** posts")
    return filtered, period_text, "; ".join(parts)


# =============================================================================
# Small display helpers
# =============================================================================
def metric_card(label, value, note=""):
    """A dashboard number. value=None shows 'Not available in this dataset' instead of a misleading 0."""
    if value is None:
        value_html = "<div class='sp-value sp-na'>Not available in this dataset</div>"
    else:
        value_html = f"<div class='sp-value'>{value}</div>"
    st.markdown(f"<div class='sp-card'><div class='sp-label'>{label}</div>{value_html}"
                f"<div class='sp-note'>{note}</div></div>", unsafe_allow_html=True)


def number_or_none(value):
    return None if value is None else metrics.format_number(value)


def display_table(df, columns):
    """Select columns that exist and show dates as YYYY-MM-DD."""
    wanted = [c for c in dict.fromkeys(columns) if c in df.columns]
    shown = df[wanted].copy()
    if "post_date" in shown.columns:
        shown["post_date"] = shown["post_date"].dt.strftime("%Y-%m-%d")
    return shown


def rate_column_config():
    """Show rate columns as 5.19% in tables."""
    return {col: st.column_config.NumberColumn(label, format="%.2f%%") for col, label in metrics.RATE_LABELS.items()}


def style_figure(fig):
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), legend_title_text="")
    return fig


def group_chart(df, column, rate_col):
    """Bar chart comparing groups. Groups with too few posts are marked 'Low sample'."""
    table = metrics.group_summary(df, column, rate_col)
    if table.empty:
        return None, table
    value = "avg_engagement_rate" if rate_col else "avg_interactions"
    value_label = metrics.RATE_LABELS[rate_col] if rate_col else "Average interactions per post"
    table["group"] = table[column] + " (n=" + table["posts"].astype(str) + ")"
    table["sample"] = table["enough_posts"].map({True: "Enough posts", False: f"Low sample (<{metrics.MIN_POSTS_PER_GROUP} posts)"})
    fig = px.bar(table, x="group", y=value, color="sample", text_auto=".2f",
                 color_discrete_map={"Enough posts": "#1F77B4", f"Low sample (<{metrics.MIN_POSTS_PER_GROUP} posts)": "#BBBBBB"},
                 labels={"group": DIMENSIONS[column], value: value_label},
                 title=f"{value_label} by {DIMENSIONS[column].lower()}")
    return style_figure(fig), table


def show_validation(result):
    """Show errors, warnings and notes from data validation in plain language."""
    for message in result.errors:
        st.error(message)
    for message in result.warnings:
        st.warning(message)
    for message in result.info:
        st.info(message)
    for effect in result.effects_of_missing:
        st.info("Optional data not provided: " + effect)


def get_insights(ctx):
    return insights.generate_insights(ctx["filtered"], ctx["rate_col"], ctx["rate_label"], ctx["result"].effects_of_missing)


# =============================================================================
# Page: Overview Dashboard
# =============================================================================
def page_overview(ctx):
    df, all_df, rate_col = ctx["filtered"], ctx["df"], ctx["rate_col"]
    st.subheader("Overview Dashboard")
    st.write("SocialPulse analyses the performance of social media posts from a spreadsheet you provide. "
             "It calculates engagement, compares platforms, formats and topics, and explains the results in plain language.")
    st.caption(f"Numbers on this page cover the **filtered selection**: {len(df)} of {len(all_df)} posts ({ctx['period']}). "
               "Change the filters in the sidebar to update everything.")

    s = metrics.summarize(df, rate_col)
    row1 = st.columns(4)
    with row1[0]:
        metric_card("Total posts analysed", metrics.format_number(s["posts"]))
    with row1[1]:
        metric_card("Total likes", number_or_none(s["total_likes"]))
    with row1[2]:
        metric_card("Total comments", number_or_none(s["total_comments"]))
    with row1[3]:
        metric_card("Total shares", number_or_none(s["total_shares"]))
    row2 = st.columns(4)
    with row2[0]:
        metric_card("Total impressions", number_or_none(s["total_impressions"]))
    with row2[1]:
        metric_card("Total reach", number_or_none(s["total_reach"]), "Sum of post-level reach. The same person may be counted more than once.")
    with row2[2]:
        metric_card("Total clicks", number_or_none(s["total_clicks"]))
    with row2[3]:
        if s["avg_rate"] is None:
            metric_card("Average engagement rate", None, "Needs valid reach or impressions.")
        else:
            metric_card(f"Average {ctx['rate_label']}", metrics.format_percent(s["avg_rate"]),
                        f"Mean of {s['posts_with_rate']} posts with a valid rate.")

    pair = metrics.best_and_worst_posts(df, rate_col)
    st.markdown("#### Best and lowest-performing post")
    if pair is None:
        st.info("Not available: no post has the data needed for a comparison.")
    else:
        st.caption(f"Ranked by: {pair['basis_label']}")
        left, right = st.columns(2)
        shown = lambda row: (metrics.format_percent(row[pair["basis"]]) if pair["basis"] != "interactions"
                             else metrics.format_number(row[pair["basis"]]))
        best = pair["best"]
        left.success(f"**Best:** {best['post_id']} – {best['platform']}, {best['post_date'].date()}  \n"
                     f"{best['caption'][:90]}  \n**{shown(best)}**")
        if pair["worst"] is None:
            right.info("Lowest-performing post: at least two posts with different values are needed for a comparison.")
        else:
            worst = pair["worst"]
            right.error(f"**Lowest:** {worst['post_id']} – {worst['platform']}, {worst['post_date'].date()}  \n"
                        f"{worst['caption'][:90]}  \n**{shown(worst)}**")

    freq, freq_name = metrics.choose_frequency(df)
    series = metrics.time_series(df, rate_col, freq)
    if len(series) >= 2:
        fig = px.line(series, x="post_date", y="interactions", markers=True,
                      labels={"post_date": f"Start of {freq_name}", "interactions": "Interactions"},
                      title=f"Interactions per {freq_name} (likes + comments + shares)")
        st.plotly_chart(style_figure(fig))
    else:
        st.info("A trend chart needs posts in at least two different time periods.")

    with st.expander("How is engagement rate calculated?"):
        st.markdown(ctx["rate_note"])
        st.markdown("`Engagement Rate (%) = (Likes + Comments + Shares) / Reach × 100`  \n"
                    "`Impressions-Based Engagement Rate (%) = (Likes + Comments + Shares) / Impressions × 100`")
    with st.expander("Data-quality notes for this dataset"):
        show_validation(ctx["result"])
        if not (ctx["result"].warnings or ctx["result"].info or ctx["result"].effects_of_missing):
            st.write("No data-quality issues were detected.")


# =============================================================================
# Page: Data Upload
# =============================================================================
def page_upload():
    st.subheader("Data Upload")
    st.write("Use **Demo Mode** (sidebar) to explore the app with synthetic sample data, or **Upload My Data** to analyse "
             "your own spreadsheet. SocialPulse does not connect to Instagram, Facebook, YouTube or any other platform – "
             "you enter your own exported analytics into a spreadsheet and upload it here.")

    st.markdown("### Step 1 – Get a file to fill in")
    c1, c2, c3 = st.columns(3)
    c1.download_button("Download CSV Template", reports.template_csv_bytes(), "socialpulse_template.csv", "text/csv", key="dl_template_csv")
    c2.download_button("Download Excel Template", reports.template_excel_bytes(), "socialpulse_template.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dl_template_xlsx")
    c3.download_button("Download Example Dataset", data_loader.sample_file_bytes(), "socialpulse_example_dataset_SYNTHETIC.csv",
                       "text/csv", key="dl_example")
    st.caption("The example dataset is **synthetic demonstration data** (randomly generated). It is not real company data. "
               "The Excel template also includes an 'Instructions' sheet.")
    with st.expander("How to create your input file (beginner guide)"):
        show_input_guide()

    st.markdown("### Step 2 – Upload your file")
    uploaded = st.file_uploader("Choose a CSV (.csv) or Excel (.xlsx) file", type=["csv", "xlsx"],
                                key=f"uploader_{st.session_state['uploader_counter']}")
    if uploaded is not None:
        file_sig = (uploaded.name, uploaded.size)
        if st.session_state.get("upload_file_sig") != file_sig:      # a new or replaced file
            try:
                raw_new = data_loader.read_data_file(uploaded, uploaded.name)
            except data_loader.DataLoadError as error:
                clear_stored_upload()
                st.error(str(error))
                return
            clear_stored_upload()
            st.session_state.update(upload_raw=raw_new, upload_name=uploaded.name, upload_file_sig=file_sig)
            st.session_state["upload_version"] += 1

    raw = st.session_state.get("upload_raw")
    if raw is None:
        st.info("No file uploaded yet. The app is still usable in Demo Mode.")
        return

    st.success(f"File: **{st.session_state['upload_name']}** – {len(raw)} row(s), {len(raw.columns)} column(s). "
               "Your original file is never modified.")
    st.write("**Detected columns:** " + ", ".join(f"`{c}`" for c in raw.columns))
    st.markdown("**Preview of the file (first 15 rows, exactly as read):**")
    st.dataframe(raw.head(15).astype("string"), hide_index=True)   # text type: safe for mixed columns

    # ---- Step 3: column mapping ----
    st.markdown("### Step 3 – Check column mapping")
    suggested = data_validation.suggest_column_mapping(raw.columns)
    stored = st.session_state.get("upload_mapping", {})
    options = [NO_COLUMN] + list(raw.columns)
    unmapped_required = [c for c in data_validation.REQUIRED_COLUMNS if not suggested.get(c)]
    mapping = {}
    with st.expander("Match your column headings to SocialPulse columns", expanded=bool(unmapped_required)):
        st.caption("We guessed the matches automatically. Change them if your headings differ. * = required.")
        grid = st.columns(3)
        for position, std in enumerate(data_validation.STANDARD_COLUMNS):
            default = stored.get(std, suggested[std])
            index = options.index(default) if default in options else 0
            star = " *" if std in data_validation.REQUIRED_COLUMNS else ""
            choice = grid[position % 3].selectbox(f"{std}{star}", options, index=index,
                                                  key=f"map_{st.session_state['upload_version']}_{std}")
            mapping[std] = None if choice == NO_COLUMN else choice
    st.session_state["upload_mapping"] = mapping

    mapping_errors = data_validation.check_mapping(mapping)
    if mapping_errors:
        for message in mapping_errors:
            st.error(message)
        st.session_state.pop("upload_result", None)
        st.session_state.pop("upload_result_sig", None)
        st.button("Remove file and return to Demo Mode", on_click=return_to_demo, key="remove_btn_a")
        return

    # ---- Step 4: validation ----
    st.markdown("### Step 4 – Data check")
    result = data_validation.validate_and_clean(data_validation.apply_mapping(raw, mapping))
    show_validation(result)
    if result.ok:
        st.success(f"{result.rows_used} usable post(s) found ({result.rows_in_file} row(s) with content in the file). "
                   f"Available metrics: {', '.join(result.available_metrics)}.")
        st.markdown("**Cleaned data preview:**")
        st.dataframe(display_table(result.data, list(result.data.columns)).head(15), hide_index=True)

    # Remember the result. If it changed, rerun once so the sidebar filters update immediately.
    signature = (st.session_state["upload_name"], tuple(mapping.items()))
    if st.session_state.get("upload_result_sig") != signature:
        st.session_state["upload_result"] = result
        st.session_state["upload_result_sig"] = signature
        st.rerun()

    b1, b2 = st.columns(2)
    b1.button("Analyse this file now", on_click=use_uploaded_data, disabled=not result.ok, key="use_btn")
    b2.button("Remove file and return to Demo Mode", on_click=return_to_demo, key="remove_btn_b")
    st.caption("To replace the file, simply choose a different file in the upload box above.")
    if st.session_state.get("data_mode") != UPLOAD_MODE and result.ok:
        st.info("Click **Analyse this file now** (or choose 'Upload My Data' in the sidebar) to see your results.")


def show_input_guide():
    st.markdown("\n".join(f"{n}. {step}" for n, step in enumerate(reports.INPUT_STEPS, start=1)))
    st.markdown("**Example of a correctly filled file (synthetic values):**")
    example = pd.DataFrame([
        ["P001", "2026-03-02", "Instagram", "Video", "Behind the scenes at the studio", "Behind the Scenes", 120, 14, 9, 4100, 3300, 85],
        ["P002", "2026-03-05", "Facebook", "Image", "Spring sale starts today", "Promotions", 80, 6, 4, 2900, 2400, None],
    ], columns=data_validation.STANDARD_COLUMNS).astype("string")   # text type: mixed numbers/blanks display safely
    st.dataframe(example, hide_index=True)
    st.markdown("**What each column means:**")
    guide = pd.DataFrame([(name, *info) for name, info in data_validation.COLUMN_GUIDE.items()],
                         columns=["Column", "Required?", "Meaning", "Example"])
    st.dataframe(guide, hide_index=True)
    st.caption("Leave a cell blank if you do not have the value. Blank is treated as 'missing', not as zero.")


# =============================================================================
# Page: Content Performance
# =============================================================================
def page_content(ctx):
    df, rate_col = ctx["filtered"], ctx["rate_col"]
    st.subheader("Content Performance")
    if not rate_col:
        st.warning("No valid reach or impressions values: comparisons use raw interactions per post, which depend on audience size "
                   "and are not a fair way to rank platforms.")
    else:
        st.caption(f"Comparisons use: **{ctx['rate_label']}**. {ctx['rate_note']}")
    tab_groups, tab_posts = st.tabs(["Compare platforms, formats and topics", "Rank posts"])

    with tab_groups:
        for column, label in DIMENSIONS.items():
            st.markdown(f"#### By {label.lower()}")
            if df[column].nunique() == 1 and df[column].iloc[0] == data_validation.UNSPECIFIED:
                st.info(f"The '{column}' column was not provided, so this comparison is not available.")
                continue
            fig, table = group_chart(df, column, rate_col)
            if fig is None:
                st.info("Nothing to compare.")
                continue
            st.plotly_chart(fig)
            if (~table["enough_posts"]).any():
                st.caption(f"Grey bars have fewer than {metrics.MIN_POSTS_PER_GROUP} posts – treat them as unreliable.")
            shown = table.drop(columns=["group", "sample", "enough_posts"], errors="ignore")
            st.dataframe(shown.rename(columns=lambda c: c.replace("_", " ").capitalize()), hide_index=True)

    with tab_posts:
        options = metrics.available_metric_options(df, rate_col)
        if not options:
            st.info("No metric is available for ranking.")
            return
        choice = st.selectbox("Rank posts by", list(options), format_func=lambda c: options[c])
        count = int(st.number_input("Number of posts to show", min_value=1, max_value=50, value=5))
        ranked = metrics.rank_posts(df, choice)
        if ranked.empty:
            st.warning("No post has a value for this metric.")
            return
        st.caption(f"Ranking method: **{options[choice]}**. {len(df) - len(ranked)} post(s) without this value are left out.")
        columns = ["rank", "post_id", "post_date", "platform", "content_type", "topic", "caption", choice, "why"]
        for title, part in (("Top-performing posts", ranked.head(count)),
                            ("Lowest-performing posts", ranked.tail(count).iloc[::-1])):
            part = part.copy()
            part["rank"] = part["rank"].astype(int)
            part["why"] = part.apply(lambda r: metrics.explain_post(r, ranked, choice, options[choice]), axis=1)
            st.markdown(f"#### {title}")
            st.dataframe(display_table(part, columns), hide_index=True, column_config=rate_column_config())
        st.caption("With few posts, the same post can appear in both tables.")


# =============================================================================
# Page: Trend Analysis
# =============================================================================
def page_trends(ctx):
    df, rate_col = ctx["filtered"], ctx["rate_col"]
    st.subheader("Trend Analysis")
    auto_freq, auto_name = metrics.choose_frequency(df)
    choices = {f"Automatic ({auto_name})": auto_freq, "Daily": "D", "Weekly": "W-MON", "Monthly": "MS"}
    freq = choices[st.selectbox("Group posts by", list(choices))]
    series = metrics.time_series(df, rate_col, freq)
    if len(series) < 2:
        st.info("Time-based charts need posts in at least two different periods. Try widening the date filter or a finer grouping.")
    else:
        st.caption("Each point is one period; periods without posts are skipped.")
        axis = {"post_date": "Start of period"}
        st.plotly_chart(style_figure(px.line(series, x="post_date", y="interactions", markers=True,
                                             labels={**axis, "interactions": "Interactions"}, title="Engagement over time (interactions)")))
        st.plotly_chart(style_figure(px.line(series, x="post_date", y=["likes", "comments"], markers=True,
                                             labels={**axis, "value": "Count", "variable": "Metric"}, title="Likes and comments over time")))
        if "shares" in series.columns and series["shares"].notna().any():
            st.plotly_chart(style_figure(px.line(series, x="post_date", y="shares", markers=True,
                                                 labels={**axis, "shares": "Shares"}, title="Shares over time")))
        if rate_col and series["avg_engagement_rate"].notna().any():
            st.plotly_chart(style_figure(px.line(series, x="post_date", y="avg_engagement_rate", markers=True,
                                                 labels={**axis, "avg_engagement_rate": "Engagement rate (%)"},
                                                 title=f"{ctx['rate_label']} over time (average of posts in each period)")))

    st.markdown("### Performance by group")
    tabs = st.tabs(list(DIMENSIONS.values()))
    for tab, column in zip(tabs, DIMENSIONS):
        with tab:
            fig, _ = group_chart(df, column, rate_col)
            if fig is None or (df[column].nunique() == 1 and df[column].iloc[0] == data_validation.UNSPECIFIED):
                st.info(f"No '{column}' information is available.")
            else:
                st.plotly_chart(fig)

    st.markdown("### Top-performing posts")
    basis, basis_label = metrics.post_ranking_basis(df, rate_col)
    top = metrics.rank_posts(df, basis).head(10)
    if top.empty:
        st.info("No posts can be ranked.")
    else:
        top = top.assign(label=top["post_id"] + " (" + top["platform"] + ")")
        fig = px.bar(top, x=basis, y="label", orientation="h", labels={basis: basis_label, "label": "Post"},
                     title=f"Top {len(top)} posts by {basis_label}")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(style_figure(fig))

    st.markdown("### Compare two periods")
    first, last = df["post_date"].min().date(), df["post_date"].max().date()
    if (last - first).days < 1:
        st.info("A period comparison needs posts on at least two different dates.")
        return
    middle = first + (last - first) / 2
    left, right = st.columns(2)
    period_a = left.date_input("Period A", value=(first, middle), min_value=first, max_value=last, key=f"pa_{ctx['key']}")
    period_b = right.date_input("Period B", value=(middle + timedelta(days=1), last),
                                min_value=first, max_value=last, key=f"pb_{ctx['key']}")
    if not (isinstance(period_a, (tuple, list)) and len(period_a) == 2 and isinstance(period_b, (tuple, list)) and len(period_b) == 2):
        st.info("Please select both a start and an end date for each period.")
        return
    comparison = metrics.compare_periods(df, period_a, period_b, rate_col)
    st.dataframe(comparison.rename(columns=lambda c: c.replace("_", " ").capitalize()), hide_index=True)
    if period_a[1] >= period_b[0] and period_b[1] >= period_a[0]:
        st.warning("The two periods overlap, so the comparison is not clean.")
    if (comparison["posts"] < metrics.MIN_POSTS_PER_GROUP).any():
        st.warning(f"At least one period has fewer than {metrics.MIN_POSTS_PER_GROUP} posts, so the comparison is unreliable.")


# =============================================================================
# Page: Post Explorer
# =============================================================================
def page_explorer(ctx):
    df, rate_col = ctx["filtered"], ctx["rate_col"]
    st.subheader("Post Explorer")
    search = st.text_input("Search captions, topics, platforms or post IDs")
    view = df
    if search.strip():
        mask = pd.Series(False, index=df.index)
        for column in ("post_id", "caption", "topic", "platform", "content_type"):
            mask |= df[column].astype(str).str.contains(search.strip(), case=False, regex=False, na=False)
        view = df[mask]
    if view.empty:
        st.warning("No posts match your search and filters.")
        return

    sortable = ["post_date"] + [c for c in ("interactions", "likes", "comments", "shares", "reach", "impressions", "clicks",
                                              metrics.RATE_REACH, metrics.RATE_IMPRESSIONS) if c in view.columns]
    sort_left, sort_right = st.columns([3, 1])
    sort_by = sort_left.selectbox("Sort by", sortable, format_func=lambda c: metrics.METRIC_LABELS.get(c, "Post date"))
    descending = sort_right.checkbox("Highest first", value=True)
    view = view.sort_values(sort_by, ascending=not descending, na_position="last")

    metric_cols = [c for c in ("likes", "comments", "shares", "impressions", "reach", "clicks") if c in view.columns]
    view = view.assign(missing_metrics=view[metric_cols].isna().apply(lambda r: ", ".join(c for c in metric_cols if r[c]), axis=1))
    columns = ["post_id", "post_date", "platform", "content_type", "topic", "caption", *metric_cols,
               "interactions", metrics.RATE_REACH, metrics.RATE_IMPRESSIONS, "missing_metrics"]
    st.caption(f"{len(view)} post(s). Empty cells mean the value was missing in your file (not zero). "
               "Rates are empty when reach/impressions is missing or 0.")
    st.dataframe(display_table(view, columns), hide_index=True, column_config=rate_column_config())
    st.download_button("Download these records (CSV)", reports.dataframe_to_csv_bytes(view[[c for c in columns if c in view.columns and c != "missing_metrics"]]),
                       "socialpulse_filtered_posts.csv", "text/csv", key="dl_explorer")

    st.markdown("#### Inspect one post")
    chosen = st.selectbox("Post", view["post_id"].tolist())
    row = view[view["post_id"] == chosen].iloc[0]
    details = []
    for column in ["post_id", "post_date", "platform", "content_type", "topic", "caption", *metric_cols, "interactions",
                   metrics.RATE_REACH, metrics.RATE_IMPRESSIONS]:
        if column not in row.index:
            continue
        value = row[column]
        if column == "post_date":
            text = str(value.date())
        elif column in (metrics.RATE_REACH, metrics.RATE_IMPRESSIONS):
            text = metrics.format_percent(value) if pd.notna(value) else "Not available (reach/impressions missing or 0)"
        elif isinstance(value, float):
            text = metrics.format_number(value) if pd.notna(value) else "Missing"
        else:
            text = str(value)
        details.append((metrics.METRIC_LABELS.get(column, column.replace("_", " ").capitalize()), text))
    st.table(pd.DataFrame(details, columns=["Field", "Value"]).set_index("Field"))
    basis, basis_label = metrics.post_ranking_basis(df, rate_col)
    st.write(metrics.explain_post(row, df, basis, basis_label))


# =============================================================================
# Page: Insights and Recommendations
# =============================================================================
def page_insights(ctx):
    st.subheader("Insights and Recommendations")
    st.caption(f"Calculated from the current filtered selection ({len(ctx['filtered'])} posts). "
               "These are observations about this dataset, not proof of cause and effect.")
    result = get_insights(ctx)
    st.markdown("### Findings")
    if not result["findings"]:
        st.info("No findings could be calculated for this selection.")
    for finding in result["findings"]:
        with st.container(border=True):
            st.markdown(f"**{finding['title']}** · based on {finding['posts']} post(s)")
            st.write(finding["text"])
    st.markdown("### Recommendations")
    for rec in result["recommendations"]:
        with st.container(border=True):
            st.write(rec["text"])
            st.caption(f"Based on: {rec['basis']}")
    st.markdown("### Limitations of this analysis")
    for item in result["limitations"]:
        st.write(f"- {item}")


# =============================================================================
# Page: Reports and Downloads
# =============================================================================
def page_reports(ctx):
    df, all_df = ctx["filtered"], ctx["df"]
    st.subheader("Reports and Downloads")
    st.caption("All files are created in memory on the machine running the app. Nothing is sent to external services.")
    result = ctx["result"]
    warnings = result.warnings + result.effects_of_missing
    report = reports.build_report_data(df, ctx["label"], ctx["period"], ctx["filters"], ctx["rate_col"], ctx["rate_note"],
                                       get_insights(ctx), warnings, len(all_df))
    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    st.markdown("### Reports (use the current filters)")
    c1, c2, c3 = st.columns(3)
    try:
        c1.download_button("Download PDF report", reports.build_pdf_report(report), "socialpulse_report.pdf", "application/pdf", key="dl_pdf")
    except Exception as error:          # PDF is a bonus: if it fails, the HTML report still works
        c1.warning(f"The PDF report could not be created ({error}). Use the HTML report instead.")
    c2.download_button("Download HTML report", reports.build_html_report(report), "socialpulse_report.html", "text/html", key="dl_html")
    c3.download_button("Download summary (text)", reports.build_summary_text(report), "socialpulse_summary.txt", "text/plain", key="dl_txt")
    st.caption("Tip: open the HTML report in a browser and choose Print > Save as PDF for a second PDF option.")

    st.markdown("### Data")
    summary_sheet = pd.DataFrame(report["summary_rows"], columns=["Measure", "Value"])
    d1, d2 = st.columns(2)
    d1.download_button("Cleaned data – all posts (CSV)", reports.dataframe_to_csv_bytes(all_df), "socialpulse_cleaned_data.csv", "text/csv", key="dl_all_csv")
    d1.download_button("Cleaned data – all posts (Excel)", reports.dataframe_to_excel_bytes(all_df, "Cleaned data"), "socialpulse_cleaned_data.xlsx", xlsx, key="dl_all_xlsx")
    d2.download_button("Filtered posts (CSV)", reports.dataframe_to_csv_bytes(df), "socialpulse_filtered_posts.csv", "text/csv", key="dl_f_csv")
    d2.download_button("Filtered posts + summary (Excel)", reports.dataframe_to_excel_bytes(df, "Filtered posts", {"Summary": summary_sheet}),
                       "socialpulse_filtered_posts.xlsx", xlsx, key="dl_f_xlsx")
    st.caption("Cleaned data includes the calculated columns (interactions and engagement rates). Missing values stay blank.")


# =============================================================================
# Page: Help and Data Guide
# =============================================================================
def page_help():
    st.subheader("Help and Data Guide")
    st.markdown("### How to use SocialPulse")
    st.markdown("1. Choose **Demo Mode** or **Upload My Data** in the sidebar.\n"
                "2. In **Data Upload**, download the CSV/Excel template, fill it in, and upload it.\n"
                "3. Check the preview, column mapping and data-quality messages.\n"
                "4. Use the sidebar filters (dates, platform, content type, topic).\n"
                "5. Explore the dashboard, charts, post table and insights.\n"
                "6. Download the cleaned data and reports in **Reports and Downloads**.")
    st.markdown("### Creating your input file")
    show_input_guide()
    st.markdown("### Engagement rate formulas")
    st.markdown("- **Engagement Rate (%) = (Likes + Comments + Shares) ÷ Reach × 100**\n"
                "- **Impressions-Based Engagement Rate (%) = (Likes + Comments + Shares) ÷ Impressions × 100**\n"
                "- The two rates are never mixed. If reach and impressions are both available, one is chosen for the whole analysis and named on screen.\n"
                "- If shares are missing, only likes and comments are used and this is stated.\n"
                "- If reach/impressions is 0 or blank for a post, its rate is unavailable (no division by zero).\n"
                "- The average rate is the mean of post-level rates. Summed post-level reach is not the number of unique people reached.")
    st.markdown("### Privacy and limits")
    st.markdown("- Your file is processed inside the running app. SocialPulse does not send it to any external analytics service.\n"
                "- The app does **not** fetch live data and is **not** connected to any social platform. Direct API connections would need "
                "authorised access, permissions and extra setup.\n"
                "- Do not commit private datasets to a public GitHub repository.\n"
                "- Findings describe patterns in your data; they do not prove that a topic or format caused better results.")


# =============================================================================
# Main program
# =============================================================================
def main():
    init_state()
    st.markdown(CARD_CSS, unsafe_allow_html=True)

    st.sidebar.title("📈 SocialPulse")
    page = st.sidebar.radio("Navigate", PAGES, key="page")
    st.sidebar.divider()
    mode = st.sidebar.radio("Data source", [DEMO_MODE, UPLOAD_MODE], key="data_mode",
                            help="Demo Mode uses bundled synthetic data. Upload My Data uses the file you uploaded.")

    dataset = get_dataset(mode)
    ctx = None
    if dataset is not None and dataset["df"] is not None:
        filtered, period_text, filters_text = sidebar_filters(dataset["df"], dataset["key"])
        ctx = {**dataset, "filtered": filtered, "period": period_text, "filters": filters_text}

    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)
    if dataset is None:
        st.warning("**Active data source:** Upload My Data – no file uploaded yet.")
    else:
        st.info(f"**Active data source:** {dataset['label']}")

    if page == "Data Upload":
        page_upload()
        return
    if page == "Help and Data Guide":
        page_help()
        return

    # The remaining pages need a valid dataset.
    if dataset is None:
        st.info("Go to **Data Upload** to upload a file, or switch to **Demo Mode** in the sidebar.")
        return
    if ctx is None:
        st.error("The uploaded file cannot be analysed yet. Open **Data Upload** to see what needs to be fixed.")
        show_validation(dataset["result"])
        return
    if ctx["filtered"].empty:
        st.warning("No posts match the current filters. Widen the date range or select more platforms, content types or topics.")
        return

    pages = {
        "Overview Dashboard": page_overview,
        "Content Performance": page_content,
        "Trend Analysis": page_trends,
        "Post Explorer": page_explorer,
        "Insights and Recommendations": page_insights,
        "Reports and Downloads": page_reports,
    }
    pages[page](ctx)


main()
