# Duplicate Records Runbook

## Symptoms

A uniqueness check fails, row counts unexpectedly rise after a retry, or downstream aggregates become larger than expected.

## Evidence to collect

- Dataset and business key used by the uniqueness constraint.
- Number of duplicate keys, representative key values where data policy permits, and observation time.
- Batch ID, task run ID, retry history, and load mode.
- Whether the target write is append-only, replace-partition, merge/upsert, or otherwise idempotent.

## Diagnostic procedure

1. Confirm that the reported duplicate count is calculated against the intended key, not a display label.
2. Correlate duplicate records with batch and task-run identifiers.
3. Check whether a failed or timed-out run was replayed and whether the write operation is idempotent.
4. Verify that duplicates are not expected under the business model.
5. Keep the observed duplication separate from the unproven hypothesis that a retry caused it.

## Safe response

Do not delete records automatically. Produce a read-only investigation with affected partitions and candidate deduplication keys, then request a business-owner-approved remediation plan.

## Related diagnostic codes

- `DATASET_DUPLICATE_KEYS`
- `DATASET_ROW_COUNT_MISMATCH`
