"""TeacherOS CEFR Curriculum & Communicative Discipline Validator (Day 22).

Enforces professional English-teaching pedagogy:
- Communicative can-do goals with observable action verbs.
- Rejects generic topical plans lacking language outcomes.
- Validates task authenticity, level demand, scaffolding, timing,
  check-for-learning alignment, and pronunciation focus.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

# Observable communicative action verbs (CEFR Can-Do aligned)
_CAN_DO_VERBS = (
    r"\b(describe|explain|negotiate|ask and answer|discuss|compare|contrast|"
    r"draft|write|present|summarize|argue|interview|apologize|order|request|"
    r"clarify|express|justify|persuade|advise|narrate|report|roleplay|participate in)\b"
)

# Vague, unobservable, non-communicative phrases
_GENERIC_NON_COMMUNICATIVE = (
    r"\b(learn about|know about|understand the topic|read about the topic|"
    r"talk about weather generally|generic conversation|practice English)\b"
)

# Communicative task indicators
_COMMUNICATIVE_TASK_MARKERS = (
    r"\b(role-?play|simulation|information gap|debate|jigsaw|peer interview|"
    r"group discussion|collaborative task|problem-solving|presentation|email draft|"
    r"dialogue|case study|decision-making|survey)\b"
)

# Explicit Check for Learning / Assessment indicators
_CHECK_FOR_LEARNING_MARKERS = (
    r"\b(check for learning|exit ticket|assessment|rubric|peer evaluation|"
    r"observation checklist|concept check questions?|ccqs?|success criteria|"
    r"reflection questions?|monitoring focus|demonstration of can-do)\b"
)

# Scaffolding / Stage indicators
_SCAFFOLDING_STAGE_MARKERS = (
    r"\b(lead-?in|warm-?up|controlled practice|guided practice|freer practice|"
    r"semi-controlled|model dialogue|elicitation|scaffold(ing)?|staged?)\b"
)

# Pronunciation & Phonological indicators
_PRONUNCIATION_MARKERS = (
    r"\b(pronunciation|intonation|sentence stress|word stress|connected speech|"
    r"weak forms|linking|vowel sounds?|consonant clusters?|phonetic|rhythm)\b"
)


@dataclass(frozen=True)
class CurriculumValidationResult:
    passed: bool
    overall_score: int  # 0 to 100
    scores: dict[str, int]
    feedback_notes: list[str]
    missing_criteria: list[str]


def validate_can_do_wording(text: str) -> tuple[bool, str | None]:
    """Validate that objectives use observable, communicative can-do phrasing."""
    normalized = re.sub(r"\s+", " ", text.casefold())
    if re.search(_GENERIC_NON_COMMUNICATIVE, normalized):
        return False, "Contains vague/unobservable phrasing (e.g. 'learn about'). Use observable can-do verbs."
    if re.search(_CAN_DO_VERBS, normalized) or "can " in normalized or "able to" in normalized:
        return True, None
    return False, "Missing observable can-do action verb (e.g. 'describe', 'negotiate', 'clarify')."


def validate_communicative_outcome(text: str) -> tuple[bool, str | None]:
    """Verify that the lesson culminates in an authentic communicative task."""
    normalized = re.sub(r"\s+", " ", text.casefold())
    if re.search(_COMMUNICATIVE_TASK_MARKERS, normalized):
        return True, None
    return False, "Missing an authentic communicative task (e.g. roleplay, debate, information gap, collaborative task)."


def validate_check_for_learning(text: str) -> tuple[bool, str | None]:
    """Verify explicit assessment or check for learning aligned to can-do target."""
    normalized = re.sub(r"\s+", " ", text.casefold())
    if re.search(_CHECK_FOR_LEARNING_MARKERS, normalized):
        return True, None
    return False, "Missing explicit check for learning (e.g. CCQs, exit ticket, success criteria, rubric)."


def validate_scaffolding(text: str) -> tuple[bool, str | None]:
    """Verify clear pedagogical staging from controlled to freer communicative practice."""
    normalized = re.sub(r"\s+", " ", text.casefold())
    if re.search(_SCAFFOLDING_STAGE_MARKERS, normalized):
        return True, None
    return False, "Missing explicit staging (e.g. warm-up -> controlled practice -> freer production)."


def validate_timing_breakdown(text: str, duration_minutes: int = 60) -> tuple[bool, str | None]:
    """Verify timing breakdown presence and feasibility."""
    normalized = re.sub(r"\s+", " ", text.casefold())
    if re.search(r"\b\d{1,2}\s*(mins?|minutes?)\b", normalized):
        return True, None
    return False, "Missing stage-by-stage minute allocations."


def validate_pronunciation_presence(text: str) -> tuple[bool, str | None]:
    """Check for pronunciation / phonological awareness where relevant."""
    normalized = re.sub(r"\s+", " ", text.casefold())
    if re.search(_PRONUNCIATION_MARKERS, normalized):
        return True, None
    return False, "No phonological or pronunciation focus identified (stress, intonation, connected speech)."


def evaluate_lesson_curriculum_discipline(
    text: str,
    *,
    level: str = "B1",
    duration_minutes: int = 60,
    is_speaking_focus: bool = True,
) -> CurriculumValidationResult:
    """Rigorous evaluation of English lesson quality and communicative discipline."""
    scores: dict[str, int] = {}
    missing: list[str] = []
    feedback: list[str] = []

    # 1. Can-Do Wording
    cd_pass, cd_msg = validate_can_do_wording(text)
    scores["can_do_wording"] = 100 if cd_pass else 0
    if not cd_pass:
        missing.append("can_do_wording")
        feedback.append(cd_msg or "Improve can-do statement precision.")

    # 2. Communicative Task Outcome
    comm_pass, comm_msg = validate_communicative_outcome(text)
    scores["communicative_outcome"] = 100 if comm_pass else 0
    if not comm_pass:
        missing.append("communicative_outcome")
        feedback.append(comm_msg or "Add communicative task structure.")

    # 3. Check for Learning Alignment
    cfl_pass, cfl_msg = validate_check_for_learning(text)
    scores["assessment_alignment"] = 100 if cfl_pass else 0
    if not cfl_pass:
        missing.append("assessment_alignment")
        feedback.append(cfl_msg or "Add explicit check for learning.")

    # 4. Scaffolding & Staging
    scaff_pass, scaff_msg = validate_scaffolding(text)
    scores["scaffolding"] = 100 if scaff_pass else 0
    if not scaff_pass:
        missing.append("scaffolding")
        feedback.append(scaff_msg or "Stage lesson from controlled to freer production.")

    # 5. Timing Feasibility
    time_pass, time_msg = validate_timing_breakdown(text, duration_minutes)
    scores["timing"] = 100 if time_pass else 0
    if not time_pass:
        missing.append("timing")
        feedback.append(time_msg or "Add stage timings.")

    # 6. Pronunciation (weighted optional based on lesson focus)
    pron_pass, pron_msg = validate_pronunciation_presence(text)
    if is_speaking_focus:
        scores["pronunciation_focus"] = 100 if pron_pass else 40
        if not pron_pass:
            feedback.append("Consider adding stress or intonation notes for speaking confidence.")
    else:
        scores["pronunciation_focus"] = 100

    # Overall calculation: Must pass can_do_wording, communicative_outcome, and assessment_alignment to pass overall!
    core_passed = cd_pass and comm_pass and cfl_pass
    overall_score = int(round(sum(scores.values()) / len(scores)))
    passed = bool(core_passed and overall_score >= 70)

    return CurriculumValidationResult(
        passed=passed,
        overall_score=overall_score,
        scores=scores,
        feedback_notes=feedback,
        missing_criteria=missing,
    )
