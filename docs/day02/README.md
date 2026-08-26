# TeacherOS Day 2 Research System

## Objective

Choose one beachhead teacher and rank the real jobs TeacherOS should solve using observed behavior, not founder intuition.

## Current status

The Day 2 evidence gate is **closed**:

- Completed eligible interviews: 0 / 5 minimum
- Confirmed later-pilot recruits: 0 / 10 minimum and 15 maximum
- Problems independently repeated by at least three teachers: 0
- Day 6-23 feature bullets inventoried: 90 / 90
- Safety/reliability mappings approved without preference research: 57
- Product mappings awaiting witnessed-task evidence or a defer decision: 33
- Segment, anti-segment, product promise, and jobs: hypotheses, not validated findings

This is the correct status. Do not convert hypotheses into interview results, quotes, or scores.

## Files

- `outputs/day02/TeacherOS_Day02_Research_Workbook.xlsx`: editable source of truth for recruitment, interview evidence, job scores, all 90 feature mappings, safety requirements, and the decision gate.
- `docs/day02/Interview_Guide.md`: exact behavioral interview and artifact-walkthrough script.
- `docs/day02/Recruitment_Messages.md`: English and Persian recruitment copy plus eligibility screener.
- `docs/day02/Research_Privacy.md`: what may and may not enter Git.
- `backend/day2_research_gate.py`: deterministic validation of the workbook.

## Exact operating sequence

1. Open the workbook and start on **Recruitment**.
2. Contact candidates using the provided message. Keep names and contact information outside the workbook.
3. Screen for at least two recurring English lessons weekly and daily Telegram use.
4. Schedule at least five eligible interviews and recruit 10-15 eligible teachers for the later pilot.
5. Run each interview from the guide. Ask about the last real task, not opinions about AI.
6. Store names, handles, recordings, raw notes, and artifacts only under `research_private/day02/`.
7. Enter only anonymous IDs and de-identified observations in **Interviews**.
8. Review formula-driven **Job Scores**. A problem becomes repeated only after three independent completed eligible interviews.
9. Put no more than three repeated problem codes in **Decision**. Validate the segment, anti-segment, and promise only after reviewing the underlying artifacts.
10. In **Feature Map**, change each product hypothesis to either:
    - `witnessed_task`, with completed interview IDs and a repeated problem code; or
    - `defer`, with a clear reason that moves it to the post-30 backlog.
11. Run the gate:

```powershell
.\.venv-day1\Scripts\python.exe -X utf8 backend/day2_research_gate.py
```

12. Continue to Day 3 only when the command prints `DAY 2 GATE: OPEN`.

## Decision rule

Keep at most the top three repeated problems. A product feature with no repeated evidence is deferred. Safety, privacy, ownership, billing correctness, rollback, and evaluation work may remain because their justification is risk control rather than a preference claim.
