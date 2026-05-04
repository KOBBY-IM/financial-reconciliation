"""
Financial Reconciliation ETL Pipeline
Extract two ledger CSVs → Validate → Transform → Reconcile → Report

Usage:
    python src/reconcile.py --source-a data/erp_ledger.csv --source-b data/bank_statement.csv
    python src/reconcile.py --source-a data/erp_ledger.csv --source-b data/bank_statement.csv --output output/report.csv
"""

import argparse
import sys
from pathlib import Path

import pandas as pd



# STEP 1 — EXTRACT


def extract(filepath: str, source_name: str) -> pd.DataFrame:
    """Load a ledger CSV and return a raw DataFrame."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"[EXTRACT] File not found: {filepath}")

    df = pd.read_csv(path)
    print(f"[EXTRACT] {source_name}: {len(df)} records loaded from '{path.name}'")
    print(f"          Columns detected: {list(df.columns)}")
    return df



# STEP 2 — VALIDATE

REQUIRED_COLUMNS = {
    "ref":    ["ref", "reference", "invoice_ref", "inv_ref", "id", "transaction_id"],
    "desc":   ["desc", "description", "narrative", "details", "memo", "name"],
    "amount": ["amount", "amt", "value", "debit", "credit", "total", "sum"],
}


def _detect_column(df: pd.DataFrame, candidates: list[str], label: str) -> str:
    """Find the best matching column name from a list of candidates."""
    cols_lower = {c.lower(): c for c in df.columns}
    for candidate in candidates:
        if candidate.lower() in cols_lower:
            return cols_lower[candidate.lower()]
    raise ValueError(
        f"[VALIDATE] Could not find a '{label}' column. "
        f"Expected one of: {candidates}. Got: {list(df.columns)}"
    )


def validate(df: pd.DataFrame, source_name: str) -> tuple[pd.DataFrame, dict]:
    """
    Validate schema, detect issues, and return a normalised DataFrame
    with standardised column names: ref, desc, amount.
    """
    issues = {}

    # Auto-map columns
    col_ref    = _detect_column(df, REQUIRED_COLUMNS["ref"],    "ref")
    # Keep label as "desc" so validation errors align with canonical output/tests.
    col_desc   = _detect_column(df, REQUIRED_COLUMNS["desc"],   "desc")
    col_amount = _detect_column(df, REQUIRED_COLUMNS["amount"], "amount")

    df = df[[col_ref, col_desc, col_amount]].copy()
    df.columns = ["ref", "desc", "amount"]

    # Nulls
    null_count = df.isnull().sum().sum()
    if null_count:
        issues["nulls"] = null_count
        print(f"[VALIDATE] {source_name}: {null_count} null value(s) found — rows dropped")
        df = df.dropna()

    # Duplicates
    dup_count = df.duplicated(subset="ref").sum()
    if dup_count:
        issues["duplicates"] = dup_count
        print(f"[VALIDATE] {source_name}: {dup_count} duplicate ref(s) detected — keeping first occurrence")
        df = df.drop_duplicates(subset="ref", keep="first")

    print(f"[VALIDATE] {source_name}: schema OK — {len(df)} clean records")
    return df, issues


# STEP 3 — TRANSFORM

def _clean_amount(value) -> float:
    """Strip currency symbols, commas, whitespace and cast to float."""
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace(",", "").replace(" ", "")
    for symbol in ["€", "$", "£", "¥", "CHF", "USD", "EUR", "GBP"]:
        cleaned = cleaned.replace(symbol, "")
    return float(cleaned)


def transform(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """Normalise refs, clean amounts, strip whitespace."""
    df = df.copy()

    # Normalise ref: uppercase, strip whitespace
    df["ref"] = df["ref"].astype(str).str.strip().str.upper()

    # Normalise description
    df["desc"] = df["desc"].astype(str).str.strip().str.title()

    # Clean and cast amount
    df["amount"] = df["amount"].apply(_clean_amount)

    print(f"[TRANSFORM] {source_name}: refs normalised, amounts parsed, whitespace stripped")
    return df


# STEP 4 — RECONCILE

def reconcile(df_a: pd.DataFrame, df_b: pd.DataFrame) -> pd.DataFrame:
    """
    Match records from source A and source B on 'ref'.
    Returns a report DataFrame with match status and variance.
    """
    map_a = df_a.set_index("ref")
    map_b = df_b.set_index("ref")

    all_refs = set(map_a.index) | set(map_b.index)
    rows = []

    matched = discrepancy = missing = 0

    for ref in sorted(all_refs):
        in_a = ref in map_a.index
        in_b = ref in map_b.index

        amt_a = float(map_a.loc[ref, "amount"]) if in_a else None
        amt_b = float(map_b.loc[ref, "amount"]) if in_b else None
        desc  = map_a.loc[ref, "desc"] if in_a else map_b.loc[ref, "desc"]

        if in_a and in_b:
            variance = round(amt_a - amt_b, 2)
            if variance == 0:
                status = "MATCH"
                matched += 1
            else:
                status = "DISCREPANCY"
                discrepancy += 1
        elif in_a:
            variance = round(amt_a, 2)
            status = "MISSING_IN_B"
            missing += 1
        else:
            variance = round(-amt_b, 2)
            status = "MISSING_IN_A"
            missing += 1

        rows.append({
            "ref":       ref,
            "desc":      desc,
            "amount_a":  amt_a,
            "amount_b":  amt_b,
            "variance":  variance,
            "status":    status,
        })

    report = pd.DataFrame(rows)

    total_variance = report["variance"].abs().sum()

    print(f"[RECONCILE] Matched:       {matched}")
    print(f"[RECONCILE] Discrepancies: {discrepancy}")
    print(f"[RECONCILE] Missing:       {missing}")
    print(f"[RECONCILE] Total variance: {total_variance:,.2f}")

    return report



# STEP 5 — REPORT

def report(df: pd.DataFrame, output_path: str | None = None) -> None:
    """Print a summary and optionally export to CSV."""

    print("\n" + "=" * 60)
    print("RECONCILIATION REPORT")
    print("=" * 60)

    status_counts = df["status"].value_counts()
    for status, count in status_counts.items():
        print(f"  {status:<20} {count}")

    total_variance = df["variance"].abs().sum()
    print(f"\n  Total absolute variance: {total_variance:,.2f}")
    print("=" * 60)

    issues = df[df["status"] != "MATCH"]
    if not issues.empty:
        print("\nItems requiring attention:")
        print(issues[["ref", "desc", "amount_a", "amount_b", "variance", "status"]].to_string(index=False))
    else:
        print("\nAll records matched. No issues found.")

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        print(f"\n[REPORT] Full report saved to: {out}")


# PIPELINE RUNNER

def run_pipeline(source_a: str, source_b: str, output: str | None = None) -> pd.DataFrame:
    """Run the full ETL reconciliation pipeline end-to-end."""

    print("\n── STEP 1: EXTRACT ──────────────────────────────────")
    raw_a = extract(source_a, "Source A (ERP)")
    raw_b = extract(source_b, "Source B (Bank)")

    print("\n── STEP 2: VALIDATE ─────────────────────────────────")
    clean_a, issues_a = validate(raw_a, "Source A")
    clean_b, issues_b = validate(raw_b, "Source B")

    print("\n── STEP 3: TRANSFORM ────────────────────────────────")
    norm_a = transform(clean_a, "Source A")
    norm_b = transform(clean_b, "Source B")

    print("\n── STEP 4: RECONCILE ────────────────────────────────")
    result = reconcile(norm_a, norm_b)

    print("\n── STEP 5: REPORT ───────────────────────────────────")
    report(result, output)

    return result



# CLIENT ENTRY POINT

def main():
    parser = argparse.ArgumentParser(
        description="Financial Reconciliation ETL Pipeline"
    )
    parser.add_argument("--source-a", required=True, help="Path to Source A CSV (e.g. ERP ledger)")
    parser.add_argument("--source-b", required=True, help="Path to Source B CSV (e.g. bank statement)")
    parser.add_argument("--output",   default=None,  help="Optional path to save the report CSV")
    args = parser.parse_args()

    try:
        run_pipeline(args.source_a, args.source_b, args.output)
    except (FileNotFoundError, ValueError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
