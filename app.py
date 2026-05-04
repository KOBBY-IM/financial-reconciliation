"""Streamlit app for the financial reconciliation pipeline."""

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))
from reconcile import reconcile, transform, validate  # noqa: E402


st.set_page_config(
    page_title="Financial Reconciliation Tool",
    page_icon="🔍",
    layout="wide",
)

st.markdown(
    """
    <style>
    /* Very visible size bump */
    html, body, [data-testid="stAppViewContainer"], .stApp {
        font-size: 24px !important;
    }
    [data-testid="stAppViewContainer"] p,
    [data-testid="stAppViewContainer"] li,
    [data-testid="stAppViewContainer"] label,
    [data-testid="stAppViewContainer"] span,
    [data-testid="stAppViewContainer"] div {
        font-size: 1.1em !important;
    }
    .stApp h1 { font-size: 3.2rem !important; }
    .stApp h2 { font-size: 2.5rem !important; }
    .stApp h3 { font-size: 2rem !important; }
    .stButton > button, .stDownloadButton > button {
        font-size: 1.15em !important;
        padding: 0.9rem 1.3rem !important;
    }
    [data-testid="stMetricLabel"] { font-size: 1.2em !important; }
    [data-testid="stMetricValue"] { font-size: 2.2em !important; }
    [data-testid="stDataFrame"] * { font-size: 1.05em !important; }
    table.result-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 0.5rem;
        margin-bottom: 1rem;
    }
    table.result-table th, table.result-table td {
        border: 1px solid rgba(255, 255, 255, 0.15);
        padding: 0.75rem 0.9rem;
        font-size: 1.15rem !important;
        line-height: 1.4;
        text-align: left;
        white-space: nowrap;
    }
    table.result-table th {
        background-color: rgba(255, 255, 255, 0.08);
        font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Financial Reconciliation Tool")
st.caption("Upload your two CSV files (or switch to sample data).")


SAMPLE_A_PATH = Path("data/sample/erp_ledger.csv")
SAMPLE_B_PATH = Path("data/sample/bank_statement.csv")


def load_sample_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not SAMPLE_A_PATH.exists() or not SAMPLE_B_PATH.exists():
        raise FileNotFoundError("Sample files not found in data/sample/")
    return pd.read_csv(SAMPLE_A_PATH), pd.read_csv(SAMPLE_B_PATH)


def build_template_csv(source_label: str) -> bytes:
    template = pd.DataFrame(
        {
            "ref": [f"{source_label}-001", f"{source_label}-002"],
            "desc": ["Example transaction one", "Example transaction two"],
            "amount": [1000.00, 2500.50],
        }
    )
    return template.to_csv(index=False).encode("utf-8")


def format_currency(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{value:,.2f}"


def to_display_frame(df: pd.DataFrame) -> pd.DataFrame:
    display = df.rename(
        columns={
            "ref": "Ref",
            "desc": "Description",
            "amount_a": "Source A",
            "amount_b": "Source B",
            "variance": "Variance",
            "status": "Status",
        }
    ).copy()
    display["Source A"] = display["Source A"].map(format_currency)
    display["Source B"] = display["Source B"].map(format_currency)
    display["Variance"] = display["Variance"].map(format_currency)
    return display


data_source = st.radio(
    "Data source",
    options=["Upload CSV files", "Use sample data"],
    index=0,
    horizontal=True,
)
use_sample = data_source == "Use sample data"

if use_sample:
    st.info("Running with bundled sample files from `data/sample/`.")
    try:
        df_raw_a, df_raw_b = load_sample_data()
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()
else:
    st.markdown("### Upload your files")
    st.markdown(
        """
        Upload exactly these two files:
        - **Source A (CSV):** ERP/ledger export
        - **Source B (CSV):** Bank statement export

        Each file must include columns for:
        - **Reference** (e.g. `ref`, `reference`, `invoice_ref`, `transaction_id`)
        - **Description** (e.g. `desc`, `description`, `narrative`, `memo`)
        - **Amount** (e.g. `amount`, `value`, `debit`, `credit`, `total`)
        """
    )
    template_col_a, template_col_b = st.columns(2)
    with template_col_a:
        st.download_button(
            label="Download Source A template",
            data=build_template_csv("ERP"),
            file_name="source_a_template.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with template_col_b:
        st.download_button(
            label="Download Source B template",
            data=build_template_csv("BANK"),
            file_name="source_b_template.csv",
            mime="text/csv",
            use_container_width=True,
        )

    col_a, col_b = st.columns(2)
    with col_a:
        file_a = st.file_uploader("Upload Source A (CSV)", type=["csv"])
        df_raw_a = pd.read_csv(file_a) if file_a is not None else None
    with col_b:
        file_b = st.file_uploader("Upload Source B (CSV)", type=["csv"])
        df_raw_b = pd.read_csv(file_b) if file_b is not None else None

    if df_raw_a is None or df_raw_b is None:
        st.info("Upload both source files to continue.")
        st.stop()

if st.button("Run reconciliation", type="primary"):
    try:
        clean_a, _ = validate(df_raw_a, "Source A")
        clean_b, _ = validate(df_raw_b, "Source B")
        norm_a = transform(clean_a, "Source A")
        norm_b = transform(clean_b, "Source B")
        result_df = reconcile(norm_a, norm_b)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    st.session_state["result"] = result_df

if "result" in st.session_state:
    report = st.session_state["result"]

    st.subheader("Results")
    col1, col2, col3 = st.columns(3)
    col1.metric("Matched", int((report["status"] == "MATCH").sum()))
    col2.metric("Discrepancies", int((report["status"] == "DISCREPANCY").sum()))
    col3.metric("Missing", int(report["status"].str.startswith("MISSING").sum()))

    display_report = to_display_frame(report)
    st.markdown(
        display_report.to_html(index=False, classes="result-table"),
        unsafe_allow_html=True,
    )

    csv_data = report.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download report CSV",
        data=csv_data,
        file_name="reconciliation_report.csv",
        mime="text/csv",
        use_container_width=True,
    )
