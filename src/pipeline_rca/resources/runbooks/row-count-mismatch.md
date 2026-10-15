# Row Count Mismatch Runbook

## Symptoms

A load or transformation produces fewer or more rows than the source manifest, previous control total, or documented invariant predicts.

## Evidence to collect

- Actual and expected counts with the provenance of the expected value.
- Time window, partition, filter predicates, and source batch identifiers.
- Upstream and downstream counts for adjacent transformation stages.
- Failed quality checks and changes to transformation code or configuration.

## Diagnostic procedure

1. Verify that actual and expected counts describe the same partition, time window, and filtering rules.
2. Compare counts stage by stage to locate the first point of divergence.
3. Check duplicate-key counts and null rates alongside row counts.
4. Inspect transformation logs for dropped rows, failed joins, invalid records, and changed filters.
5. Avoid treating a mismatch as proof of a particular transformation bug without corroborating evidence.

## Safe response

Return the earliest observed divergence and its evidence references. Keep query execution read-only and bounded. A remediation proposal should identify the affected partitions and expected recomputation cost; do not run a backfill as part of diagnosis.

## Related diagnostic codes

- `DATASET_ROW_COUNT_MISMATCH`
- `DATASET_DUPLICATE_KEYS`
- `DATASET_NULL_VALUES`
