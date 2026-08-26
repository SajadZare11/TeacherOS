# TeacherOS Day 3

Day 3 defines one closed teaching loop and the measurement system that can prove or disprove its value.

## Delivered

- `TeacherOS_Product_Contract.md`: promise, users/jobs hypotheses, flagship loop, scope, non-goals, requirements, analytics, privacy, entitlements, deletion, flags, release gates, and comprehension protocol.
- `Telegram_Wireflow.md`: complete flagship-loop, deletion, retry, and stale-state flows.
- `contracts/day03/product_contract.json`: authoritative event, callback, flag, entitlement, deletion, and release-gate definitions.
- `contracts/day03/screens.json`: every contracted Telegram screen/state with Back, empty, retry, confirmation, recovery, and callback behavior.
- `Teacher_Comprehension_Record_Template.md`: privacy-safe, unaided test record for the unresolved human acceptance gate.
- `backend/day3_contract_check.py`: deterministic structural validator and honest approval check.

## Current status

The contract is structurally valid but approval is **blocked**:

- Day 2 research gate: closed.
- Day 3 teacher comprehension test: not yet run.
- Class-intelligence flags: specified default-off; not yet implemented.

This is intentional. No interview, comprehension result, or pilot outcome has been fabricated.

## Run the checks

```powershell
.\.venv-day1\Scripts\python.exe -X utf8 backend/day3_contract_check.py
.\.venv-day1\Scripts\python.exe -X utf8 backend/day3_contract_check.py --require-approval
```

The first command exits successfully when the contract is structurally sound and prints the blockers. The second command is a release gate and exits nonzero until research and comprehension evidence are complete.
