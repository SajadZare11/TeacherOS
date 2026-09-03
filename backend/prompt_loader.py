from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from config import PROJECT_ROOT

PROMPTS_DIR = PROJECT_ROOT / "prompts"

CORE_PROMPTS = (
    "teacheros_identity",
    "classroom_design_standards",
    "educational_standards",
    "writing_standards",
    "formatting_standards",
    "humanization_rules",
    "quality_assurance",
)


def _candidate_paths(relative_path: str | Path) -> tuple[Path, ...]:
    path = PROMPTS_DIR / Path(relative_path)

    if path.suffix:
        return path, path.with_suffix("")

    return path.with_suffix(".txt"), path


def find_prompt(relative_path: str | Path) -> Path | None:
    for candidate in _candidate_paths(relative_path):
        if candidate.is_file():
            return candidate
    return None


@lru_cache(maxsize=64)
def load_prompt(relative_path: str | Path, *, required: bool = True) -> str:
    prompt_path = find_prompt(relative_path)

    if prompt_path is None:
        if not required:
            return ""

        checked = "\n".join(f"- {path}" for path in _candidate_paths(relative_path))
        raise FileNotFoundError(
            f"Prompt file not found for '{relative_path}'. Checked:\n{checked}"
        )

    text = prompt_path.read_text(encoding="utf-8").strip()
    if required and not text:
        raise ValueError(f"Prompt file is empty: {prompt_path}")

    return text


@lru_cache(maxsize=1)
def load_system_prompt() -> str:
    # Use the existing combined system prompt when present.
    combined = load_prompt("teacheros_system_prompt", required=False)
    if combined:
        return combined

    core_sections = [
        load_prompt(Path("core") / name, required=False)
        for name in CORE_PROMPTS
    ]
    core_sections = [section for section in core_sections if section]

    if not core_sections:
        raise FileNotFoundError(
            "No TeacherOS system prompt was found. Add prompts/teacheros_system_prompt.txt "
            "or at least one prompt inside prompts/core/."
        )

    return "\n\n".join(core_sections)


@lru_cache(maxsize=16)
def load_feature_prompt(feature_name: str, template_name: str | None = None) -> str:
    # Feature prompt files are self-contained and already define the teacher's
    # role, methodology, CEFR standards, and rules. Omitting the redundant
    # 4,300-char system prompt cuts input latency in half on LLM providers.
    sections: list[str] = [load_prompt(Path("features") / feature_name)]

    if template_name:
        template = load_prompt(Path("templates") / template_name, required=False)
        if template:
            sections.append(template)

    return "\n\n".join(sections)


def validate_prompt_files() -> None:
    # Load them now so startup fails with a useful message instead of failing
    # after the teacher has already clicked Generate.
    load_system_prompt()
    load_feature_prompt("lesson_planner", "lesson_template")
    load_feature_prompt("activity_generator", "activity_template")
    load_feature_prompt("worksheet_generator", "worksheet_template")
    load_feature_prompt("quiz_generator", "quiz_template")
