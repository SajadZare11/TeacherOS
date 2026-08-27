# Day 5 migration and rollback runbook

## Safety model

Schema v6 is additive. It creates new tables, indexes, and ownership triggers, then adds one nullable foreign-key column to `materials`. It never drops, renames, rewrites, or makes a legacy column mandatory. Version 6 is recorded only after all migration statements succeed in the transaction.

The operational rollback is therefore feature rollback, not destructive schema rollback. New tables and the nullable column remain inert while their surfaces are disabled. This avoids an irreversible down migration and preserves any class data already collected.

## Before deployment

1. Stop application writers or use SQLite's online backup API to create a consistent database copy.
2. Keep that backup outside version control. Never copy database rows into reports or tickets.
3. Run the checker against the backup. It copies the supplied backup into a temporary directory and never migrates the source:

   ```powershell
   .\.venv-day1\Scripts\python.exe -X utf8 backend\day5_migration_check.py --real-copy "backups\teacheros_<timestamp>_pre-day5-v5.db"
   ```

4. Require `"passed": true` for every scenario. Stop the deployment on any row-count change, legacy-data hash change, duplicate column, missing legacy column, foreign-key error, or export failure.
5. Run the full automated suite and project checks.

## Deploy

Leave all new flags false for the schema-only rollout. Application startup calls `initialize_database()`, which applies v6 idempotently. A second startup is safe and changes neither rows nor columns.

Feature environment variables:

```text
TEACHEROS_FEATURE_CLASSES=false
TEACHEROS_FEATURE_CONTINUITY=false
TEACHEROS_FEATURE_EVIDENCE=false
TEACHEROS_FEATURE_DIFFERENTIATION=false
TEACHEROS_FEATURE_REPORTS=false
TEACHEROS_FEATURE_ENTITLEMENTS=false
```

Enable only the surface being deliberately rolled out. Continuity depends on Classes; Evidence and Differentiation depend on Classes plus Continuity; Reports additionally depends on Evidence. Entitlements is independent. Missing and unrecognized truth values fail closed.

## Roll back

1. Set the affected flag to `false`. For a complete class-memory rollback, set all six flags above to `false`.
2. Restart the process so the deployment environment is re-read.
3. Confirm `feature_flag_snapshot()` reports every surface ineffective and `quick_create_is_default()` is true.
4. Confirm the home screen still has Lesson Planner, Activities, Worksheets, Assessments, Search, and Account.
5. Do not remove schema v6 or `materials.class_id`. Leaving additive schema in place is the data-preserving rollback.

If application binaries must also be rolled back, deploy the previous binary after disabling the flags. Schema v5 code ignores the new tables and nullable column.

## Recovery boundary

Restore the pre-migration backup only if legacy data changed or database integrity failed. That is a stop-the-line incident: keep the failed database for investigation, restore via the existing backup/restore procedure, and do not re-enable rollout flags until the root cause is understood.
