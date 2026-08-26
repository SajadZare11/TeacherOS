# TeacherOS Day 1 Operations Runbook

## Scope

This runbook establishes the recoverable schema-v5 baseline before class-intelligence work begins. Run commands from the repository root. Never copy `.env`, `database/`, `backups/`, `exports/`, or teacher content into Git.

## Runtime

Create a fresh virtual environment if the existing one is missing or broken:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run all Python commands with UTF-8 mode on Windows:

```powershell
.\.venv\Scripts\python.exe -X utf8 backend/check_project.py
```

## Start

1. Confirm `.env` exists locally and contains the required names documented in the baseline report.
2. Run the project check.
3. Confirm port `PAYMENT_SERVER_PORT` is free.
4. Start the bot:

```powershell
.\.venv\Scripts\python.exe -X utf8 backend/main.py
```

Expected result: the database, payment callback server, admin configuration, and Telegram polling report ready. Do not leave two polling processes active for the same bot token.

## Stop

In the foreground terminal, press `Ctrl+C`. Confirm the Python process exits and the payment callback port is released. If running through systemd, use the service commands in `deploy/README.md`.

## Pre-change checkpoint

The backup command refuses a dirty worktree. Commit intended source changes first, then run:

```powershell
.\.venv\Scripts\python.exe -X utf8 backend/day1_backup_restore.py --label pre-class-intelligence
```

This creates a secret-safe `git archive` of `HEAD`, a consistent SQLite online backup, restores both into an isolated directory, verifies required code files, runs SQLite integrity checks, and compares schema/table counts. The artifacts and JSON verification report are written below `backups/day1/`, which is ignored by Git.

## Restore code

1. Stop TeacherOS.
2. Create an empty recovery directory outside the live checkout.
3. Extract `teacheros-code.zip` from the chosen Day 1 backup.
4. Create a fresh virtual environment and install `requirements.txt`.
5. Copy a valid local `.env` from the secret manager; never recover secrets from Git.
6. Run `backend/check_project.py` before switching traffic.

## Restore database

1. Stop TeacherOS and retain the failed database for forensics.
2. Copy the verified `teacheros-database.db` from the chosen backup to a temporary filename in `database/`.
3. Run `PRAGMA integrity_check` and confirm schema version 5.
4. Replace `database/teacheros.db` only while the bot and callback server are stopped.
5. Start TeacherOS, run the project check, then verify one owned library item and one sandbox payment lookup.

## Rollback

For application regressions, stop the service, deploy the Day 1 tag, recreate the virtual environment from the tagged `requirements.txt`, restore the paired verified database only when the change included data mutation, run the project check and smoke suite, then restart. Preserve logs and the failed database. Never downgrade the database by deleting columns or tables in place.
