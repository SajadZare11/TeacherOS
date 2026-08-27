# TeacherOS Day 4

Day 4 creates the testable AI quality, privacy, and safety foundation that must exist before student evidence reaches an LLM.

## Delivered

- `contracts/day04/data_policy.json`: five data classes with retention, deletion, logging, backup, access, encryption, and provider rules.
- `contracts/day04/safety_contract.json`: risk model, perfect safety thresholds, quality baselines, and ten operational risks.
- `contracts/day04/golden_cases.json`: 40 artificial A1-C1 cases across ages and classroom conditions, including eight evidence prompt injections.
- `contracts/day04/schemas/`: closed lesson-plan and evidence-follow-up JSON schemas.
- `backend/day4_quality_gate.py`: synthetic fixture/live runner, deterministic validators, prompt boundary, score-only writer, privacy audit, and fail-closed gate.
- `outputs/day04/fixture_scores.json`: 40/40 deterministic harness baseline.
- `outputs/day04/live_scores.json`: current-model score-only baseline; 37/40 and release-blocked.
- `Data_Handling_Standard.md`: human-readable lifecycle and provider operating rules.
- `Teacher_Consent_and_AI_Labels.md`: consent, anonymization warning, retention confirmation, AI limitations, failure, and deletion copy.
- `Incident_Playbook.md`: data exposure/cross-user, billing, harmful output, unavailable AI, and secret-exposure response.
- `Baseline_Report.md`: metrics, failures, decision, and remediation.
- `tests/test_day4_quality_gate.py`: contract, privacy, invariant, mutation, fixture, and repository-baseline tests.

## Current decision

Day 4’s foundation is implemented, and the current model has been measured. Release remains **blocked** because three of 20 lesson-plan cases had inconsistent answer keys. Safety invariants passed 100%, but that does not override quality failure. Day 2 research and Day 3 comprehension are also still blocked.

Student evidence remains disabled. The live run used artificial content only and persisted no prompt or response text.

## Commands

```powershell
.\.venv-day1\Scripts\python.exe -X utf8 backend/day4_quality_gate.py --mode fixture --require-pass
.\.venv-day1\Scripts\python.exe -X utf8 backend/day4_quality_gate.py --mode live --concurrency 2 --require-pass
.\.venv-day1\Scripts\python.exe -X utf8 backend/day4_quality_gate.py --rescore outputs/day04/live_scores.json --require-pass
.\.venv-day1\Scripts\python.exe -X utf8 -m unittest tests.test_day4_quality_gate -v
```
