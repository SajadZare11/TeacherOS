# TeacherOS access and response-time notes

## User entry points

The enabled Classes home is intentionally small and routes every capability through a visible next step:

- **My Classes** opens class setup, class context, lesson continuity, evidence, differentiation, and progress/report tools.
- **Quick Create** preserves the four standalone generators: Lesson Planner, Activities, Worksheets, and Assessments.
- **Analyze Work** starts the evidence-analysis flow.
- **Search** opens the private library search.
- **Account** contains usage, plan/payment, general Library, feedback, help, policies, and the owner-only admin entry when configured.

Telegram's command menu publishes `/start`, `/help`, `/lesson`, `/activity`, `/worksheet`, `/assessment`, `/library`, `/account`, `/search`, `/usage`, `/plan`, `/feedback`, `/about`, `/privacy`, `/terms`, and `/cancel`. Generated materials are saved automatically and can be reopened or exported from Library.

The Classes-off rollback is also supported: disabling `TEACHEROS_FEATURE_CLASSES` restores the four generators plus Search and Account instead of leaving users on an unusable class-only screen.

## Response-time controls

AI requests are bounded and configurable through environment variables:

| Setting | Default | Purpose |
| --- | ---: | --- |
| `OPENROUTER_REQUEST_TIMEOUT_SECONDS` | `15` | Maximum time for one provider attempt |
| `OPENROUTER_TOTAL_TIMEOUT_SECONDS` | `35` | Maximum time across the fallback chain |
| `OPENROUTER_MAX_FALLBACK_MODELS` | `3` | Prevents a long fallback list from multiplying wait time |
| `TEACHEROS_MAX_CONCURRENT_UPDATES` | `8` | Lets independent teachers continue while one request is running |

The OpenRouter client keeps the configured model ordering, caps attempts, and applies the total deadline. The AI gateway uses the same values, so direct and class-aware generation paths have one consistent timeout policy. Prompt loading is cached and feature prompts use the maintained compact system prompt rather than resending every long reference file on every request.

For a consistently fast paid model, operators may increase the timeout values or set a model-specific fallback list. Do not put secrets in this document or in public website files.
