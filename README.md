# SocialPulse – Social Media Engagement Analysis

> Turn social media performance data into actionable insights.

SocialPulse is a Streamlit web application that analyses social media post performance from a **CSV or Excel file that you provide**. It validates the data, calculates engagement metrics, compares platforms / content types / topics, shows trends, writes cautious plain-English insights, and exports cleaned data and reports (PDF, HTML, text, CSV, Excel).

* **No paid services.** Everything runs locally or on free Streamlit Community Cloud.
* **No live platform connections.** SocialPulse does **not** fetch data from Instagram, Facebook, YouTube, etc. You export your own analytics into a spreadsheet and upload it.
* **Privacy.** Uploaded data is processed inside the running app only. It is not sent to any external analytics service.

---

## 1. What you can do with it

| Section | What it does |
|---|---|
| Overview Dashboard | Totals, average engagement rate, best/lowest post, interactions over time |
| Data Upload | Download templates, upload CSV/Excel, map columns, see data-quality checks |
| Content Performance | Compare platforms, content types and topics; rank top/lowest posts with a reason for each rank |
| Trend Analysis | Interactive Plotly charts over time, group comparisons, two-period comparison |
| Post Explorer | Search, sort, inspect and download individual posts |
| Insights and Recommendations | Findings and cautious recommendations calculated from the current filters |
| Reports and Downloads | PDF / HTML / text reports, cleaned data and filtered data as CSV / Excel |
| Help and Data Guide | Column guide, formulas, privacy and limits |

**Demo Mode** uses a bundled **synthetic** dataset (`data/sample_social_media_posts.csv`, randomly generated – not real company data). **Upload My Data** uses your file. The active source is always shown at the top of the page, and the two are never mixed.

---

## 2. Technology

Python · Streamlit · Pandas · NumPy · Plotly · OpenPyXL (Excel) · ReportLab (PDF)

## 3. Project structure

```
socialpulse/
├── app.py                          # The screens (Streamlit interface)
├── requirements.txt                # Python packages
├── README.md
├── .gitignore
├── .streamlit/config.toml          # Streamlit settings (usage stats off)
├── data/
│   └── sample_social_media_posts.csv   # SYNTHETIC demo data
├── modules/
│   ├── data_loader.py              # Reads CSV / Excel files
│   ├── data_validation.py          # Column mapping, checks, cleaning, warnings
│   ├── metrics.py                  # Engagement rates, totals, groups, trends, rankings
│   ├── insights.py                 # Findings and recommendations
│   └── reports.py                  # Templates, CSV/Excel exports, PDF/HTML/text reports
└── tests/
    ├── helpers.py
    ├── test_data_validation.py
    ├── test_metrics.py
    └── test_exports_and_reports.py
```

---

## 4. Install and run on Windows 10/11 (VS Code)

### 4.1 One-time setup
1. Install **Python 3.11 or 3.12** from <https://www.python.org/downloads/>. On the first installer screen, **tick "Add python.exe to PATH"**.
2. Install **VS Code** from <https://code.visualstudio.com/> and the **Python** extension (Extensions icon → search "Python").

### 4.2 Open the project
1. Unzip the project folder (e.g. to `C:\Users\you\socialpulse`).
2. In VS Code: **File → Open Folder…** → select the `socialpulse` folder (the one containing `app.py`).
3. Open a terminal: **Terminal → New Terminal**.
   If the terminal says *PowerShell*, switch to **Command Prompt** using the dropdown (▼) next to the **+** icon. (PowerShell can block activation scripts.)

> **All commands below must be run from inside the `socialpulse` folder** (the folder that contains `app.py`). Check with `dir` – you should see `app.py` listed.

### 4.3 Create a virtual environment and install packages
```
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```
After activation, `(.venv)` appears at the start of the terminal line. If VS Code asks "We noticed a new environment", click **Yes**.

### 4.4 Run the app
```
python -m streamlit run app.py
```
The browser opens automatically (or go to <http://localhost:8501>). Stop the app with **Ctrl + C** in the terminal.

Next time, you only need `.venv\Scripts\activate` and the run command.

### 4.5 Run the tests
```
python -m unittest discover -s tests -v
```

---

## 5. Using the app

### Demo Mode
Leave **Data source = Demo Mode** in the sidebar. Everything works immediately with the synthetic sample.

### Using your own data
1. Go to **Data Upload** and click **Download CSV Template** (or **Download Excel Template**, which also has an *Instructions* sheet).
2. Open it in Excel and enter the data from **your own authorised social media analytics** (for example exports from Meta Business Suite, LinkedIn Analytics, YouTube Studio…).
3. Follow these rules:
   * Dates as `YYYY-MM-DD` where possible (e.g. `2026-03-15`).
   * Metrics as **numbers**, not text.
   * Leave unavailable metrics **blank** – do not type 0 or guess. Blank is treated as *missing*, never as zero.
   * Do not leave example rows in the file. Completely blank rows are ignored.
4. **Save from Excel:** *File → Save As → "CSV UTF-8 (Comma delimited) (*.csv)"* – or simply save as **Excel Workbook (*.xlsx)**.
5. Back in SocialPulse, use the upload box. Check the **preview**, **column mapping** (if your headings differ, pick the matching column from the drop-downs) and the **data check** messages.
6. Click **Analyse this file now** (or choose *Upload My Data* in the sidebar).
7. To use another file, choose a different file in the upload box. To go back to the demo, click **Remove file and return to Demo Mode**. Your original file is never modified.

### Columns

| Column | Required? | Meaning |
|---|---|---|
| post_id | Optional | Unique ID/name of the post (generated if missing) |
| post_date | **Required** | Publication date |
| platform | Optional | Instagram, Facebook, LinkedIn, X, … |
| content_type | Optional | Image, Video, Carousel, Text, … |
| caption | Optional | Post text or description |
| topic | Optional | Campaign / subject |
| likes | **Required** | Number of likes/reactions |
| comments | **Required** | Number of comments |
| shares | Optional | Number of shares/reposts |
| impressions | Optional | Times the post was displayed (can count one person several times) |
| reach | Optional | Unique accounts that saw the post |
| clicks | Optional | Link/post clicks |

If an optional column is missing, the app tells you which analyses are affected (for example: no `reach` → no reach-based engagement rate).

### What the data check handles
Empty files · blank template rows · missing required columns · different column names (mapping) · invalid dates · missing values (kept as missing) · duplicate rows / reused post IDs · negative numbers · text in numeric columns · zero reach/impressions · unexpected platform names (kept as typed) · inconsistent upper/lower case in labels · too few rows · filters that return nothing.

---

## 6. How engagement rate is calculated

```
Engagement Rate (%)                    = (Likes + Comments + Shares) ÷ Reach       × 100
Impressions-Based Engagement Rate (%)  = (Likes + Comments + Shares) ÷ Impressions × 100
```

* The two rates have different denominators and are **never mixed**. If both exist, one is chosen for the whole analysis (reach-based is preferred) and its name is shown on screen.
* If the `shares` column does not exist, only likes + comments are used and the app says so. If a post has a blank shares value, that post's rate is unavailable (not silently treated as 0).
* If reach/impressions is 0 or blank, the rate for that post is **unavailable** – there is no division by zero.
* If neither reach nor impressions exists, **no engagement rate is invented**; rankings then use a raw metric you choose (likes, comments, …) and are labelled as such.
* The "average engagement rate" is the mean of post-level rates. Summing post-level reach does **not** give unique people reached, because one person can see several posts.

## 7. How to read the results

* **Group comparisons** show the number of posts (n) behind each bar. Grey bars have fewer than 3 posts and are unreliable.
* **Insights** use wording like "In this dataset, video posts had a higher average engagement rate…" and always show how many posts they are based on. They describe patterns; they do **not** prove that a topic or format *caused* better results, and no statistical significance is claimed.
* Without reach/impressions, platforms are **not ranked**, because raw likes mostly reflect audience size.
* The "change over time" finding compares the first and second half of the selected date range and needs at least 6 posts.

## 8. Reports and downloads
* **PDF report**, **HTML report** (fallback; also printable to PDF) and **text summary** – built from the *current filters*.
* **Cleaned data** (all posts) and **filtered posts** as CSV or Excel, including calculated columns. Missing values stay blank.
* Templates and the example dataset are on the Data Upload page.

---

## 9. Put the project on GitHub
1. Create a free account at <https://github.com> and click **New repository**. Name it `socialpulse`, choose **Public**, and click **Create repository**.
2. Install **Git for Windows** from <https://git-scm.com/download/win>.
3. In the VS Code terminal (inside the project folder):
```
git init
git add .
git commit -m "SocialPulse first version"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/socialpulse.git
git push -u origin main
```
(Replace `YOUR-USERNAME`. GitHub may ask you to sign in in the browser.)
4. **Never upload private data.** `.gitignore` already excludes `.venv`, secrets and files named `my_data*`. Only the synthetic sample is included.

## 10. Deploy free on Streamlit Community Cloud
1. Go to <https://share.streamlit.io> and sign in with your GitHub account.
2. Click **Create app** (or **New app**) → choose **From existing repo**.
3. Select your repository `socialpulse`, branch **main**, and main file path **`app.py`**.
4. Click **Deploy**. The first build takes a few minutes while packages from `requirements.txt` install.
5. Open the public URL and test: Demo Mode, template download, uploading the example dataset, a report download.

> A public app is visible to anyone with the link. Anyone using it uploads their own data into their own session; do not ask others to upload confidential data to a demo you share publicly.

---

## 11. Known limitations
* Data entry is manual (CSV/Excel). There are **no live API connections**; direct integrations need authorised platform API access, permissions and extra configuration. The module structure makes it possible to add a new loader later.
* Old `.xls` files are not supported (save as `.xlsx` or CSV). Files over 20 MB are rejected.
* Dates are interpreted in the usual month/day/year or ISO way; `YYYY-MM-DD` is safest.
* The PDF uses a built-in font, so characters outside Western European text (emoji, Chinese, …) show as `?` in the PDF. The HTML report and exports keep all characters.
* Insights are rule-based summaries, not predictions, and no significance tests are used.
* Uploaded data lives in the current browser session; closing the tab or restarting the app clears it.

## 12. Future enhancements
Authorised API connectors · saved projects · time-of-day / weekday analysis · click-through rate analysis · hashtag analysis · statistical tests · multi-language reports.

## 13. Testing status
Automated tests cover loading (sample, CSV, Excel, empty, header-only, other encodings), validation (missing columns, bad dates, duplicates, missing/negative/text values, zero reach/impressions), engagement formulas, filters (including empty results), groups, trends, rankings, insights, CSV/Excel export and PDF/HTML/text reports. Run them with `python -m unittest discover -s tests -v`.
