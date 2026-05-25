"""
Tests for the financial reconciliation ETL pipeline.
Run with:  pytest tests/test_reconcile.py -v
"""

from io import BytesIO, StringIO

import pandas as pd
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from reconcile import validate, transform, reconcile, _clean_amount, load_ledger_csv


# Fixtures

@pytest.fixture
def clean_df_a():
    return pd.DataFrame({
        "ref":    ["INV-001", "INV-002", "INV-003"],
        "desc":   ["Consulting fees", "Software licences", "Hardware"],
        "amount": [12500.00, 4200.00, 8750.00],
    })

@pytest.fixture
def clean_df_b():
    return pd.DataFrame({
        "ref":    ["INV-001", "INV-002", "INV-004"],
        "desc":   ["Consulting fees", "Software licences", "Maintenance"],
        "amount": [12500.00, 3900.00, 1450.00],  # INV-002 has discrepancy
    })


# _clean_amount

class TestCleanAmount:
    def test_plain_float(self):
        assert _clean_amount(1234.56) == 1234.56

    def test_string_with_euro(self):
        assert _clean_amount("€1,234.56") == 1234.56

    def test_string_with_dollar(self):
        assert _clean_amount("$9,999.00") == 9999.00

    def test_string_with_commas(self):
        assert _clean_amount("10,000") == 10000.0

    def test_integer(self):
        assert _clean_amount(500) == 500.0

    def test_parentheses_negative(self):
        assert _clean_amount("($1,234.56)") == -1234.56


# load_ledger_csv

class TestLoadLedgerCsv:
    def test_detects_semicolon_delimiter(self):
        csv_data = StringIO("ref;description;amount\nA;Test;100\n")
        result = load_ledger_csv(csv_data)
        assert list(result.columns) == ["ref", "description", "amount"]
        assert result["amount"].iloc[0] == 100

    def test_reads_utf8_bom(self):
        csv_data = BytesIO("ref,description,amount\nA,Café,100\n".encode("utf-8-sig"))
        result = load_ledger_csv(csv_data)
        assert list(result.columns) == ["ref", "description", "amount"]
        assert result["description"].iloc[0] == "Café"


# validate

class TestValidate:
    def test_standard_columns(self):
        df = pd.DataFrame({"ref": ["A"], "description": ["Test"], "amount": [100]})
        result, issues = validate(df, "test")
        assert list(result.columns) == ["ref", "desc", "amount"]

    def test_alias_columns(self):
        df = pd.DataFrame({"invoice_ref": ["A"], "narrative": ["Test"], "value": [100]})
        result, issues = validate(df, "test")
        assert list(result.columns) == ["ref", "desc", "amount"]

    def test_alias_columns_with_spaces_and_punctuation(self):
        df = pd.DataFrame({"Invoice Ref": ["A"], "Memo": ["Test"], "Total Amount": [100]})
        result, issues = validate(df, "test")
        assert list(result.columns) == ["ref", "desc", "amount"]

    def test_drops_nulls(self):
        df = pd.DataFrame({"ref": ["A", None], "description": ["X", "Y"], "amount": [100, 200]})
        result, issues = validate(df, "test")
        assert len(result) == 1
        assert issues["nulls"] > 0

    def test_deduplicates(self):
        df = pd.DataFrame({"ref": ["A", "A"], "description": ["X", "X"], "amount": [100, 100]})
        result, issues = validate(df, "test")
        assert len(result) == 1
        assert issues["duplicates"] == 1

    def test_missing_column_raises(self):
        df = pd.DataFrame({"ref": ["A"], "amount": [100]})
        with pytest.raises(ValueError, match="desc"):
            validate(df, "test")


# transform

class TestTransform:
    def test_ref_uppercased(self):
        df = pd.DataFrame({"ref": ["inv-001"], "desc": ["test"], "amount": [100]})
        result = transform(df, "test")
        assert result["ref"].iloc[0] == "INV-001"

    def test_ref_stripped(self):
        df = pd.DataFrame({"ref": ["  INV-001  "], "desc": ["test"], "amount": [100]})
        result = transform(df, "test")
        assert result["ref"].iloc[0] == "INV-001"

    def test_amount_cleaned(self):
        df = pd.DataFrame({"ref": ["A"], "desc": ["test"], "amount": ["€1,200.00"]})
        result = transform(df, "test")
        assert result["amount"].iloc[0] == 1200.0


# reconcile

class TestReconcile:
    def test_match(self, clean_df_a, clean_df_b):
        result = reconcile(clean_df_a, clean_df_b)
        matched = result[result["status"] == "MATCH"]
        assert "INV-001" in matched["ref"].values

    def test_discrepancy(self, clean_df_a, clean_df_b):
        result = reconcile(clean_df_a, clean_df_b)
        disc = result[result["status"] == "DISCREPANCY"]
        assert "INV-002" in disc["ref"].values
        assert disc[disc["ref"] == "INV-002"]["variance"].iloc[0] == 300.0

    def test_missing_in_b(self, clean_df_a, clean_df_b):
        result = reconcile(clean_df_a, clean_df_b)
        missing = result[result["status"] == "MISSING_IN_B"]
        assert "INV-003" in missing["ref"].values

    def test_missing_in_a(self, clean_df_a, clean_df_b):
        result = reconcile(clean_df_a, clean_df_b)
        missing = result[result["status"] == "MISSING_IN_A"]
        assert "INV-004" in missing["ref"].values

    def test_all_refs_present(self, clean_df_a, clean_df_b):
        result = reconcile(clean_df_a, clean_df_b)
        all_refs = set(clean_df_a["ref"]) | set(clean_df_b["ref"])
        assert set(result["ref"]) == all_refs

    def test_perfect_match(self):
        df = pd.DataFrame({"ref": ["A", "B"], "desc": ["X", "Y"], "amount": [100.0, 200.0]})
        result = reconcile(df, df.copy())
        assert (result["status"] == "MATCH").all()
