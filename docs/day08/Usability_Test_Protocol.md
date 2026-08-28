# Day 8 dashboard usability test

## Gate

Observe at least five target teachers without coaching. At least 80% must choose **Plan Next Lesson** as the intended primary action, and each participant must identify the active class and recommended action within five seconds.

Do not record names, Telegram identifiers, schools, class labels, student information, health/disability information, or screen captures containing private content.

## Procedure

1. Prepare a synthetic class with a neutral label and a mix of bounded dashboard states.
2. Open its class dashboard before handing the phone to the participant.
3. Start timing when the screen becomes visible.
4. Ask: “Which class is active, and what does this screen recommend doing next?” Do not explain the buttons.
5. Stop timing when both are identified or at ten seconds.
6. Ask the participant to tap the action they believe is primary.
7. Record only elapsed seconds, whether both facts were correct within five seconds, the controlled chosen-action code, and a controlled friction code.

Allowed chosen-action codes: `plan_next`, `analyze`, `create`, `outcome`, `progress`, `library`, `profile`, `other`.

Allowed friction codes: `none`, `class_unclear`, `primary_unclear`, `too_much_text`, `button_order`, `terminology`, `other_deidentified`.

| Observation | Seconds | Class + action within 5s? | Chosen action | Friction code |
|---|---:|---|---|---|
| O01 | Not run | Not run | — | — |
| O02 | Not run | Not run | — | — |
| O03 | Not run | Not run | — | — |
| O04 | Not run | Not run | — | — |
| O05 | Not run | Not run | — | — |

Current status: **NOT RUN**. Calculate `plan_next selections ÷ completed observations`; the gate passes only at 0.80 or above with the five-second identification criterion met.
