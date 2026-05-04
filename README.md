# Financial Reconciliation ETL Pipeline

A production-style ETL pipeline that compares two financial ledgers — for example an ERP system export and a bank statement — identifies discrepancies, missing records, and exact matches, and outputs a structured reconciliation report.

Built as part of a Data & Business Analyst portfolio to demonstrate end-to-end ETL thinking, data validation, and business-facing reporting.

---

## What it does

```
Source A (ERP)     Source B (Bank)
      │                   │
      ▼                   ▼
   EXTRACT            EXTRACT
      │                   │
      ▼                   ▼
  VALIDATE           VALIDATE
  (nulls, dupes,     (nulls, dupes,
   schema check)      schema check)
      │                   │
      ▼                   ▼
  TRANSFORM          TRANSFORM
  (normalise refs,   (normalise refs,
   clean amounts)     clean amounts)
      │                   │
      └──────┬────────────┘
             ▼
         RECONCILE
      (FULL OUTER JOIN
       on ref key)
             │
             ▼
          REPORT
      (summary + CSV)
```

Each record is classified as:

| Status | Meaning |
|---|---|
| `MATCH` | Ref exists in both sources with identical amount |
| `DISCREPANCY` | Ref exists in both but amounts differ |
| `MISSING_IN_B` | Ref only in Source A (ERP) — not found in bank |
| `MISSING_IN_A` | Ref only in Source B (Bank) — not in ERP |

---

## Project structure

```
financial-reconciliation/
├── src/
│   ├── reconcile.py      ← main ETL pipeline (Python)
│   └── reconcile.sql     ← SQL version (PostgreSQL / DuckDB)
├── tests/
│   └── test_reconcile.py ← pytest unit tests
├── data/
│   └── sample/
│       ├── erp_ledger.csv
│       └── bank_statement.csv
├── output/               ← generated reports saved here
├── requirements.txt
└── README.md
```

---

## Quickstart

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/financial-reconciliation.git
cd financial-reconciliation
pip install -r requirements.txt
```

### 2. Run with sample data

```bash
python src/reconcile.py \
  --source-a data/sample/erp_ledger.csv \
  --source-b data/sample/bank_statement.csv \
  --output output/report.csv
```

### 3. Run with your own data

Your CSV files need at minimum three columns. The pipeline auto-detects common column name variations:

| Field | Accepted column names |
|---|---|
| Reference key | `ref`, `reference`, `invoice_ref`, `id`, `transaction_id` |
| Description | `desc`, `description`, `narrative`, `details`, `memo` |
| Amount | `amount`, `amt`, `value`, `debit`, `credit`, `total` |

Currency symbols (`€`, `$`, `£`) and comma separators are stripped automatically.

```bash
python src/reconcile.py \
  --source-a path/to/your_erp.csv \
  --source-b path/to/your_bank.csv \
  --output output/my_report.csv
```

### 4. Run the tests

```bash
pytest tests/ -v
```

### 5. Run the Streamlit app (upload your files)

```bash
streamlit run app.py
```

In the app, choose **Upload CSV files** and upload:

- **Source A (CSV):** your ERP/ledger export
- **Source B (CSV):** your bank statement export

Both files should include fields for reference, description, and amount (aliases are auto-detected as shown above).  
You can also click **Download Source A template** and **Download Source B template** to get ready-made CSV formats.

---

## SQL version

If you prefer to run reconciliation inside a database:

```bash
# With DuckDB (local, no server needed)
duckdb
> CREATE TABLE erp_ledger AS SELECT * FROM read_csv_auto('data/sample/erp_ledger.csv');
> CREATE TABLE bank_statement AS SELECT * FROM read_csv_auto('data/sample/bank_statement.csv');
> .read src/reconcile.sql
```

The SQL file also works with PostgreSQL, BigQuery, and Snowflake with minor adjustments noted in the file.

---

## Sample output

```
── STEP 1: EXTRACT ──────────────────────────────────
[EXTRACT] Source A (ERP): 8 records loaded from 'erp_ledger.csv'
[EXTRACT] Source B (Bank): 8 records loaded from 'bank_statement.csv'

── STEP 2: VALIDATE ─────────────────────────────────
[VALIDATE] Source A: schema OK — 8 clean records
[VALIDATE] Source B: schema OK — 8 clean records

── STEP 3: TRANSFORM ────────────────────────────────
[TRANSFORM] Source A: refs normalised, amounts parsed, whitespace stripped
[TRANSFORM] Source B: refs normalised, amounts parsed, whitespace stripped

── STEP 4: RECONCILE ────────────────────────────────
[RECONCILE] Matched:       6
[RECONCILE] Discrepancies: 1
[RECONCILE] Missing:       2
[RECONCILE] Total variance: 1,720.00

── STEP 5: REPORT ───────────────────────────────────

============================================================
RECONCILIATION REPORT
============================================================
  MATCH                6
  MISSING_IN_B         1
  MISSING_IN_A         1
  DISCREPANCY          1

  Total absolute variance: 1,720.00
============================================================

Items requiring attention:
   ref          desc  amount_a  amount_b  variance        status
INV-006  Office Supplies    620.0     890.0    -270.0   DISCREPANCY
INV-008   Legal Retainer   5000.0      None    5000.0  MISSING_IN_B
INV-009  Maintenance Fee     None    1450.0   -1450.0  MISSING_IN_A
```

---

## Tech stack

| Tool | Purpose |
|---|---|
| Python 3.11+ | ETL pipeline |
| pandas | Data manipulation |
| pytest | Unit testing |
| SQL (PostgreSQL / DuckDB) | Database-native version |

---

## Extending this project

Ideas for taking it further (great talking points in interviews):

- **Scheduling** — wrap in Airflow or cron to run nightly
- **Multi-currency** — add FX rate lookup via an API before comparison
- **Email alerts** — send a summary email when variance exceeds a threshold
- **Database source** — replace CSV input with a SQLAlchemy connection to a live ERP
- **Dashboard** — pipe the output into a Power BI or Tableau report

---

## Author

Built by [Your Name] · [LinkedIn](https://linkedin.com/in/yourprofile) · [Portfolio](https://yourportfolio.com)
