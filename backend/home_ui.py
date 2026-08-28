from __future__ import annotations

from feature_flags import feature_enabled


def teacheros_home_text(plan_line: str | None = None) -> str:
    """Return home copy that always matches the active home keyboard."""
    lines = ["👋 Welcome to TeacherOS", "", "Your AI assistant for English teachers."]
    if plan_line:
        lines.extend([plan_line, ""])
    else:
        lines.append("")
    if feature_enabled("classes"):
        lines.append(
            "Choose My Classes for recurring teaching, or Quick Create for one-off work."
        )
    else:
        lines.append("Choose what you'd like to create today.")
    return "\n".join(lines)
