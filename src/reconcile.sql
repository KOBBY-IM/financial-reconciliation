-- Financial Reconciliation — SQL Version
-- Works with: PostgreSQL, BigQuery, Snowflake, DuckDB
-- (Minor syntax adjustments needed for MySQL / SQL Server)
--
-- Assumes two staging tables already loaded:
--   erp_ledger      (ref, description, amount)
--   bank_statement  (ref, description, amount)


-- STEP 1: STAGING — normalise both sources

CREATE OR REPLACE VIEW stg_erp AS
SELECT
    UPPER(TRIM(ref))              AS ref,
    INITCAP(TRIM(description))    AS description,
    CAST(amount AS NUMERIC(15,2)) AS amount
FROM erp_ledger
WHERE ref IS NOT NULL
  AND amount IS NOT NULL;


CREATE OR REPLACE VIEW stg_bank AS
SELECT
    UPPER(TRIM(ref))              AS ref,
    INITCAP(TRIM(description))    AS description,
    CAST(amount AS NUMERIC(15,2)) AS amount
FROM bank_statement
WHERE ref IS NOT NULL
  AND amount IS NOT NULL;


-- STEP 2: VALIDATE — check for duplicates

-- Run these as data quality checks before reconciling
-- If either query returns rows, investigate before proceeding

SELECT ref, COUNT(*) AS occurrences
FROM stg_erp
GROUP BY ref
HAVING COUNT(*) > 1;
-- Expected: 0 rows

SELECT ref, COUNT(*) AS occurrences
FROM stg_bank
GROUP BY ref
HAVING COUNT(*) > 1;
-- Expected: 0 rows


-- STEP 3: RECONCILE — full outer join

CREATE OR REPLACE VIEW reconciliation_report AS
SELECT
    COALESCE(a.ref, b.ref)              AS ref,
    COALESCE(a.description, b.description) AS description,
    a.amount                            AS amount_erp,
    b.amount                            AS amount_bank,

    -- Variance: positive = ERP higher, negative = Bank higher
    ROUND(
        COALESCE(a.amount, 0) - COALESCE(b.amount, 0),
    2)                                  AS variance,

    CASE
        WHEN a.ref IS NULL              THEN 'MISSING_IN_ERP'
        WHEN b.ref IS NULL              THEN 'MISSING_IN_BANK'
        WHEN a.amount = b.amount        THEN 'MATCH'
        ELSE                                 'DISCREPANCY'
    END                                 AS status

FROM      stg_erp  a
FULL OUTER JOIN stg_bank b ON a.ref = b.ref

ORDER BY
    CASE
        WHEN a.ref IS NULL OR b.ref IS NULL THEN 1
        WHEN a.amount != b.amount           THEN 2
        ELSE 3
    END,
    COALESCE(a.ref, b.ref);


-- STEP 4: SUMMARY METRICS

SELECT
    status,
    COUNT(*)                       AS record_count,
    SUM(ABS(variance))             AS total_variance
FROM reconciliation_report
GROUP BY status
ORDER BY
    CASE status
        WHEN 'MISSING_IN_ERP'  THEN 1
        WHEN 'MISSING_IN_BANK' THEN 2
        WHEN 'DISCREPANCY'     THEN 3
        WHEN 'MATCH'           THEN 4
    END;


-- STEP 5: EXPORT — items needing attention

SELECT *
FROM reconciliation_report
WHERE status != 'MATCH'
ORDER BY ABS(variance) DESC;


-- BONUS: running in DuckDB locally
-- (great for testing with CSV files)
--
-- duckdb
-- > CREATE TABLE erp_ledger AS SELECT * FROM read_csv_auto('data/erp_ledger.csv');
-- > CREATE TABLE bank_statement AS SELECT * FROM read_csv_auto('data/bank_statement.csv');
-- > -- then run this file:
-- > .read src/reconcile.sql
