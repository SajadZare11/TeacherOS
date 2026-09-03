from __future__ import annotations

from feature_flags import feature_enabled
from string_catalog import tr


def teacheros_home_text(plan_line: str | None = None, lang: str = "en") -> str:
    """Return home copy matching the active home keyboard."""
    if lang == "fa":
        lines = [
            "👋 به TeacherOS خوش آمدید ✨",
            "",
            "دستیار هوشمند شما برای تدریس زبان انگلیسی 🎒",
        ]
        if plan_line:
            lines.extend([plan_line, ""])
        else:
            lines.append("")
        if feature_enabled("classes"):
            lines.append(
                "🎒 برای مدیریت و ذخیره حافظه کلاس‌هایتان «کلاس‌های من» را انتخاب کنید، یا برای ساخت فوری محتوا از «ساخت سریع» استفاده کنید ✨"
            )
        else:
            lines.append("ابزار مورد نظر خود را برای شروع انتخاب کنید.")
        return "\n".join(lines)

    lines = [
        "👋 Hi Teacher! Welcome to TeacherOS ✨",
        "",
        "I'm your AI co-teacher and assistant, here to save you hours of lesson prep.",
    ]
    if plan_line:
        lines.extend([plan_line, ""])
    else:
        lines.append("")
    if feature_enabled("classes"):
        lines.append(
            "Choose My Classes for recurring teaching with memory, or Quick Create for fast one-off work! 🎒"
        )
    else:
        lines.append("Choose what you'd like to create today.")
    return "\n".join(lines)
