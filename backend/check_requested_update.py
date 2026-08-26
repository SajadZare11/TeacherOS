from __future__ import annotations

import py_compile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

REQUIRED_FILES = (
    "account_panel.py",
    "activity_generator.py",
    "keyboards.py",
    "lesson_planner.py",
    "main.py",
    "payment_panel.py",
    "payment_server.py",
    "quiz_generator.py",
    "subscription_service.py",
    "worksheet_generator.py",
)


def _read(name: str) -> str:
    path = BACKEND_DIR / name
    raw = path.read_bytes()
    if raw.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")):
        raise RuntimeError(f"{name} contains a BOM. Save it as UTF-8 without BOM.")
    return raw.decode("utf-8")


def main() -> None:
    print("TeacherOS requested-feature check\n")

    for name in REQUIRED_FILES:
        path = BACKEND_DIR / name
        if not path.is_file():
            raise RuntimeError(f"Missing file: backend/{name}")
        _read(name)
        py_compile.compile(str(path), doraise=True)
    print("✅ All changed Python files exist, compile, and use UTF-8 without BOM")

    quiz = _read("quiz_generator.py")
    keyboards = _read("keyboards.py")
    required_quiz_markers = (
        "quiz_question_count_keyboard",
        "quiz_count_custom",
        "question_count_custom",
        "_MIN_QUESTION_COUNT = 1",
        "_MAX_QUESTION_COUNT = 50",
        '"question_count": question_count',
        "Step 6 of 6",
    )
    missing = [marker for marker in required_quiz_markers if marker not in quiz + keyboards]
    if missing:
        raise RuntimeError("Assessment question-count flow is incomplete: " + ", ".join(missing))
    print("✅ Assessment supports 5–30 quick choices and a custom 1–50 count")

    callbacks = (
        "quiz_count_5",
        "quiz_count_10",
        "quiz_count_15",
        "quiz_count_20",
        "quiz_count_25",
        "quiz_count_30",
        "quiz_count_custom",
        "export_library_999999_all_0",
        "pdf_library_999999_all_0",
    )
    oversized = [value for value in callbacks if len(value.encode("utf-8")) > 64]
    if oversized:
        raise RuntimeError("Telegram callback data is too long: " + ", ".join(oversized))
    print("✅ New Telegram callback data stays within the 64-byte limit")

    for name in (
        "lesson_planner.py",
        "activity_generator.py",
        "worksheet_generator.py",
        "quiz_generator.py",
    ):
        source = _read(name)
        if "generated_material_export_keyboard" not in source:
            raise RuntimeError(f"Immediate exports are missing from {name}")
        if "download Word or PDF immediately" not in source:
            raise RuntimeError(f"Export confirmation is missing from {name}")
    if "export_library_{material_id}_all_0" not in keyboards:
        raise RuntimeError("Direct Word export callback is missing")
    if "pdf_library_{material_id}_all_0" not in keyboards:
        raise RuntimeError("Direct PDF export callback is missing")
    print("✅ Lesson, Activity, Worksheet, and Assessment show immediate Word/PDF buttons")

    payment_panel = _read("payment_panel.py")
    payment_server = _read("payment_server.py")
    account_panel = _read("account_panel.py")
    payment_markers = (
        "پلن‌های TeacherOS",
        "سوابق پرداخت",
        "ورود به صفحه پرداخت",
        "بررسی وضعیت پرداخت",
        "تأیید خرید پلن",
        "پرداخت با موفقیت تأیید شد",
        'lang="fa" dir="rtl"',
        "نتیجه پرداخت زرین‌پال",
        "🪪 پلن من",
    )
    combined = payment_panel + payment_server + keyboards + account_panel
    missing = [marker for marker in payment_markers if marker not in combined]
    if missing:
        raise RuntimeError("Persian payment UI is incomplete: " + ", ".join(missing))
    print("✅ Payment, plan, history, status, and callback pages are Persian and RTL")

    requirements = PROJECT_ROOT / "requirements.txt"
    if requirements.is_file():
        raw = requirements.read_bytes()
        if raw.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")):
            raise RuntimeError("requirements.txt still contains a BOM")
        raw.decode("utf-8")
        print("✅ requirements.txt is UTF-8 without BOM")

    print("\n✅ Requested TeacherOS update check passed")


if __name__ == "__main__":
    main()
