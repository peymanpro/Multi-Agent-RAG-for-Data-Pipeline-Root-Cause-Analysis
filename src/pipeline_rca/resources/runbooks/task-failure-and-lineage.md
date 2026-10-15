# Task Failure and Lineage Runbook

## Symptoms

A producer task failed or timed out, downstream jobs were skipped or ran with stale data, or the declared dependency graph contains a cycle.

## Evidence to collect

- Task ID, run ID, status, start/end timestamps, and sanitized error message.
- Declared upstream/downstream edges and source of lineage metadata.
- Latest successful run for the producer and first affected downstream stage.
- Whether a task was retried, skipped, or allowed to continue with partial output.

## Diagnostic procedure

1. Confirm the failed task and its run identifier.
2. Walk downstream lineage to list potentially affected consumers.
3. Distinguish graph reachability from proof that every descendant consumed bad data.
4. Check for cycles or missing dependency edges in the declared lineage.
5. Correlate timestamps and run IDs before linking a producer failure to a report discrepancy.

## Safe response

Generate an impact report, but do not terminate jobs, delete outputs, or replay tasks automatically. Mark impact as potential until execution evidence confirms which descendants actually ran against affected inputs.

## Related diagnostic codes

- `PIPELINE_TASK_FAILED`
- `LINEAGE_CYCLE_DETECTED`
