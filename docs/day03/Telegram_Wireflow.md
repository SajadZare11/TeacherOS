# TeacherOS Day 3 Telegram Wireflow

Status: **draft for comprehension testing**. This is a product contract, not an implemented UI.

## Flagship loop

```mermaid
flowchart LR
    H[H01 Home] --> C[CLS01/02 My Classes]
    C --> S[CLS03-06 Class setup]
    S --> CH[CLS07 Class home]
    CH --> P[PLN01-04 Plan and resource]
    P --> T[TEA01 Mark taught]
    T --> O[OUT01-02 30-second outcome]
    O --> E[EVD01-05 Evidence and approval]
    E --> D[DIA01-02 Approved diagnosis]
    D --> F[FUP01-02 Accepted follow-up]
    F --> N[NXT01-02 Next lesson]
    N --> CH
```

The only north-star completion edge is `NXT01 → NXT02`: the accepted follow-up is attached to a saved next resource and `loop_completed` is emitted once. Every earlier step is funnel progress, not completed value.

## Entry and class setup

```mermaid
flowchart TD
    H[H01 Home] -->|My Classes| L{Any classes?}
    L -->|No| E[CLS01 Empty]
    L -->|Yes| LS[CLS02 List]
    E -->|Create first class| N[CLS03 Name]
    LS -->|New class| N
    LS -->|Open| CH[CLS07 Class home]
    N --> P[CLS04 Profile buttons]
    P --> G[CLS05 Goal]
    G --> R[CLS06 Review]
    R -->|Create, idempotent| CH
    R -->|Edit| N
    N -->|Back| LS
    P -->|Back| N
    G -->|Back| P
    R -->|Back| G
    LS -->|Main menu| H
```

Telegram displays one short input at a time. The teacher never enters student names. Button groups capture level, learner-count band, cadence, and goal; a short private class label and optional note are the only free text. Saved context is editable at review.

## Plan, teach, and outcome

```mermaid
flowchart TD
    CH[CLS07 Class home] --> B[PLN01 Plan brief]
    B -->|Generate| W[PLN02 Progress]
    W -->|Success| V[PLN03 Preview]
    W -->|Timeout/failure| X[PLN04 Failure]
    X -->|Retry same request| W
    X -->|Back with draft| B
    V -->|Use for class| CH2[Class timeline: planned]
    CH2 --> M[TEA01 Mark taught]
    M -->|Confirm| O[OUT01 Outcome buttons]
    O -->|Save| S[OUT02 Saved]
    S -->|Add evidence| EP[EVD01 Privacy]
    S -->|Later| CH3[Class timeline: evidence pending]
    B -->|Back| CH
    M -->|Back| CH2
    O -->|Back; draft persists| M
```

Export or download does not mark a lesson taught. The outcome uses bounded buttons and a review step; it is not a narrative report.

## Evidence, diagnosis, and teacher control

```mermaid
flowchart TD
    EP[EVD01 Privacy + consent] -->|Consent| U[EVD02 Upload or structured counts]
    EP -->|Continue without evidence| CH[Class timeline: pending]
    U -->|Process| P[EVD03 Processing]
    P -->|Reliable extraction| R[EVD04 Review extraction]
    P -->|Failure/insufficient| A[EVD05 Needs attention]
    R -->|Approve| D[DIA01 Proposed diagnosis]
    R -->|Edit| R
    R -->|Reject| A
    A -->|Manual counts| R
    A -->|Retry| P
    A -->|Delete| DC[DEL01 Confirmation]
    D -->|Approve or edit| DA[DIA02 Approved]
    D -->|Reject| CH
    DA --> F[FUP01 Follow-up proposal]
    F -->|Accept or edit| FA[FUP02 Accepted]
    F -->|Reject| CH
    FA --> N[NXT01 Next lesson brief]
    N -->|Generate + attach| C[NXT02 Loop complete]
```

Evidence is optional and requires separate consent. Upload is not approval. Extraction is not diagnosis. Diagnosis is a proposal until the teacher approves it. Rejection has no hidden mutation.

## Deletion and downgrade

```mermaid
flowchart TD
    X[Owned resource/evidence/class/account] --> Q{Delete requested}
    Q --> S[Explain exact scope and cascade]
    S -->|Cancel| X
    S -->|Confirm| O{Ownership + revision valid?}
    O -->|No| R[REC01 Safe recovery; reveal no details]
    O -->|Yes| J[Idempotent deletion job]
    J --> D[DEL03 Receipt and deadline]
    D --> P[Safe parent screen]
    G[Plan downgrade] --> RO[Excess classes read-only]
    RO --> EX[Export and deletion remain available]
```

Raw evidence is purged immediately after confirmation. Class metadata may have a seven-day soft-delete window, but raw evidence cannot be restored. Downgrade is never deletion.

## Universal retry and stale-state recovery

```mermaid
flowchart TD
    A[Any callback] --> V{Owned, current revision, flag available?}
    V -->|Yes| I{Mutation?}
    I -->|No| S[Render current state]
    I -->|Yes| K[Apply idempotency key]
    K --> C{Commit known?}
    C -->|Success| S
    C -->|Confirmed failure| E[REC02 Retry with draft]
    C -->|Unknown| U[Retry same key; do not duplicate]
    V -->|No| R[REC01 Explain no change]
    R --> H[Current class or Home button]
    E --> H
```

No recovery message tells the teacher to type `/start`. A visible inline Home action always exists.

## Screen completeness checklist

The machine-readable screen catalog contains 33 contracted states across entry, setup, plan, teach, outcome, evidence, diagnosis, follow-up, next lesson, shared data controls, deletion, and recovery. Every record defines:

- primary action;
- Back/escape route;
- empty behavior;
- retry behavior;
- confirmation behavior;
- recovery behavior;
- compact callback examples.

Run `python backend/day3_contract_check.py` to verify completeness, callback grammar, event metadata, flags, deletion rules, and the unresolved approval gates.
