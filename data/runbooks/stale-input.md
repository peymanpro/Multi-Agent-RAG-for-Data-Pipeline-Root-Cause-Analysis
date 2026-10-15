# Stale Input Runbook

## Symptoms

A scheduled report completed but reflects an old source snapshot, a freshness contract is breached, or downstream datasets stop advancing.

## Evidence to collect

- Latest event/partition timestamp and the expected freshness threshold.
- Evaluation timestamp with explicit time zone.
- Last successful producer run and most recent failed or skipped task.
- Source publication cadence, holidays, and known upstream maintenance windows.

## Diagnostic procedure

1. Compare the latest observed event time with an explicit timezone-aware evaluation time.
2. Convert timestamps to a common time zone before computing age.
3. Check whether the threshold is measured in wall-clock time or business time.
4. Trace lineage upstream to see whether the producer stopped, produced an empty partition, or the consumer stopped reading new data.
5. Account for clock skew and late-arriving data before assigning a cause.

## Safe response

A freshness breach is evidence that a contract was violated at the measured time. It does not alone identify why publication stopped. Do not trigger replays or backfills automatically; report the last observed good time and ask the data owner to confirm a recovery plan.

## Related diagnostic codes

- `DATASET_STALE_INPUT`
- `PIPELINE_TASK_FAILED`
