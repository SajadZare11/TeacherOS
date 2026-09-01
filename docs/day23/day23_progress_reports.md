# TeacherOS Day 23: Editable, Evidence-Safe Progress Reports

## 1. Overview & Objective
Day 23 provides English teachers with the ability to turn teacher-confirmed lesson outcomes, approved evidence analyses, and syllabus records into structured, high-utility whole-class summaries, end-of-unit progress reports, and instructional reflections.

### Key Outgrowths & Disciplines:
1. **Three V1 Report Archetypes**:
   - `whole_class_summary`: High-level synthesis of taught lessons, demonstrated strengths, and priority target objectives.
   - `end_of_unit_summary`: Unit-grounded progress report directly tracking coursebook unit objectives without copyrighted text scraping.
   - `teacher_reflection`: Pedagogical self-review and adaptation log for the teacher's professional development.
   *(Note: Individual learner report generation is explicitly deferred until learner profiling and multi-party consent mechanisms are implemented).*
2. **Strict Evidence-Safe Invariant**:
   - Every generated report is grounded **strictly** in approved records (`lesson_outcomes`, `evidence_analysis_results`, `writing_feedback_records`, `class_objectives`).
   - **Never invent attendance, effort, behavior, home support, medical/psychological diagnosis, or exact proficiency percentages.**
   - If evidence is lacking for a period, the report transparently displays: *"Insufficient recorded lesson evidence for this reporting period. Teacher observation or outcome check-in records are required."*
3. **Teacher Approval & Versioned Audit Trail**:
   - Reports default to `draft` status and cannot be exported as share-safe final reports without explicit teacher approval (`approve_progress_report`).
   - Every section edit (`teacher_comments`, `next_steps_text`, `strengths_text`, `priorities_text`) increments `version` and records a detailed audit log in `progress_report_revisions`.
4. **Dual Share-Safe Document Exports**:
   - **Word (`.docx`)**: Clean, formatted Microsoft Word document with headings, bullet points, and an explicit privacy footer.
   - **PDF (`.pdf`)**: Structured document produced via ReportLab with typography, dividers, and compliance notices.
5. **Orphan & Purge Safety**:
   - When underlying evidence items or batches are deleted/purged, `handle_deleted_source` flags the source IDs without breaking or altering previously approved reports.

---

## 2. Database Architecture (Schema v23)

### `class_progress_reports` Table
```sql
CREATE TABLE IF NOT EXISTS class_progress_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_uuid TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    class_id INTEGER NOT NULL,
    report_type TEXT NOT NULL CHECK (
        report_type IN ('whole_class_summary', 'end_of_unit_summary', 'teacher_reflection')
    ),
    title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 3 AND 200),
    reporting_period_start TEXT NOT NULL,
    reporting_period_end TEXT NOT NULL,
    unit_id INTEGER,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'archived')),
    version INTEGER NOT NULL DEFAULT 1,
    learning_covered_text TEXT NOT NULL,
    strengths_text TEXT NOT NULL,
    priorities_text TEXT NOT NULL,
    change_observed_text TEXT NOT NULL,
    next_steps_text TEXT NOT NULL,
    teacher_comments TEXT,
    has_insufficient_evidence INTEGER NOT NULL DEFAULT 0 CHECK (has_insufficient_evidence IN (0, 1)),
    evidence_summary_json TEXT NOT NULL DEFAULT '{}',
    source_ids_json TEXT NOT NULL DEFAULT '[]',
    share_safe_verified INTEGER NOT NULL DEFAULT 0 CHECK (share_safe_verified IN (0, 1)),
    approved_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    FOREIGN KEY (unit_id) REFERENCES class_curriculum_units(id) ON DELETE SET NULL
);
```

### `progress_report_revisions` Table
```sql
CREATE TABLE IF NOT EXISTS progress_report_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    field_changed TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (report_id) REFERENCES class_progress_reports(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

---

## 3. UI & Callback Interface (Prefix: `v1|rp|`)
All inline keyboard callback buttons strictly comply with Telegram's 64-byte payload limit.

| Action | Description | Sample Callback |
| :--- | :--- | :--- |
| `home` | Reports dashboard overview | `v1\|rp\|home\|1\|1` |
| `list` | List existing reports | `v1\|rp\|list\|1\|1` |
| `new` | Choose report structure | `v1\|rp\|new\|1\|1` |
| `tcls` | Generate Whole-Class Summary | `v1\|rp\|tcls\|1\|1` |
| `tunt` | Generate End-of-Unit Summary | `v1\|rp\|tunt\|1\|1` |
| `tref` | Generate Teacher Reflection | `v1\|rp\|tref\|1\|1` |
| `view` | View formatted report details | `v1\|rp\|view\|1\|1` |
| `appr` | Approve report as final / share-safe | `v1\|rp\|appr\|1\|1` |
| `esec` | Open section edit selector | `v1\|rp\|esec\|1\|1` |
| `ecom` | Edit Teacher Comments | `v1\|rp\|ecom\|1\|1` |
| `enxt` | Edit Next Steps | `v1\|rp\|enxt\|1\|1` |
| `estr` | Edit Observed Strengths | `v1\|rp\|estr\|1\|1` |
| `epri` | Edit Priorities | `v1\|rp\|epri\|1\|1` |
| `exw` | Export Word document (`.docx`) | `v1\|rp\|exw\|1\|1` |
| `exp` | Export PDF document (`.pdf`) | `v1\|rp\|exp\|1\|1` |

---

## 4. Verification & Testing
- **Unit Test Suite (`tests/test_day23_progress_reports.py`)**: 10 tests covering schema validation, honest evidence boundaries, three report archetypes, section editing & versioning, approval gates, Word/PDF binary generation, and multi-tenant isolation.
- **Cumulative Test Suite**: 234 automated tests passing with 0 failures and 0 errors.
- **Acceptance Gate (`backend/day23_acceptance_check.py`)**: 10/10 acceptance criteria passing.
