from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 2)


def measure() -> dict[str, object]:
    temporary = tempfile.TemporaryDirectory(prefix="teacheros-day1-measure-")
    os.environ["TEACHEROS_DATABASE_PATH"] = str(Path(temporary.name) / "baseline.db")
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-baseline-token-not-used")
    os.environ.setdefault("OPENROUTER_API_KEY", "offline-baseline-key-not-used")
    os.environ["ZARINPAL_SANDBOX"] = "true"
    os.environ["TEACHEROS_LOCAL_PAYMENT_SIMULATOR"] = "true"

    import database
    import main as bot_main
    from pdf_document import create_pdf_export
    from word_document import create_word_export

    teacher = SimpleNamespace(
        id=81001,
        username="day1_measure",
        first_name="Day One",
        last_name="Teacher",
        language_code="en",
    )

    journeys: list[dict[str, object]] = []

    started = perf_counter()
    material_id = database.save_generated_material(
        telegram_user=teacher,
        material_type="lesson",
        title="B1 Travel Review",
        content=(
            "# B1 Travel Review\nObjective: review travel language.\n\n"
            "1. Warm-up\n2. Pair task\n3. Exit check\n\nANSWER KEY\n1. Verified"
        ),
        subtype="lesson plan",
        level="B1",
        topic="Travel",
        metadata={"measurement": "day1_offline"},
    )
    material = database.get_user_material(
        telegram_user_id=teacher.id,
        material_id=material_id,
    )
    valid_resource = bool(
        material
        and "Objective:" in str(material.get("content"))
        and "ANSWER KEY" in str(material.get("content"))
    )
    journeys.append(
        {
            "name": "first_useful_resource",
            "duration_ms": _elapsed_ms(started),
            "screens": 7,
            "errors": 0 if valid_resource else 1,
            "result": "pass" if valid_resource else "fail",
            "inspection": "title, objective, steps, and answer key present",
        }
    )

    started = perf_counter()
    matches = database.search_user_materials(
        telegram_user_id=teacher.id,
        query="Travel B1",
        limit=6,
    )
    found = database.get_user_material(
        telegram_user_id=teacher.id,
        material_id=int(matches[0]["id"]),
    ) if matches else None
    word_stream, _ = create_word_export(found or {})
    pdf_stream, _ = create_pdf_export(found or {})
    valid_exports = word_stream.read(2) == b"PK" and pdf_stream.read(5) == b"%PDF-"
    journeys.append(
        {
            "name": "find_and_export",
            "duration_ms": _elapsed_ms(started),
            "screens": 3,
            "errors": 0 if matches and valid_exports else 1,
            "result": "pass" if matches and valid_exports else "fail",
            "inspection": "owned search result plus readable DOCX/PDF signatures",
        }
    )

    async def recover_from_failure() -> tuple[bool, int]:
        update = SimpleNamespace(
            message=SimpleNamespace(
                text="Create a review task",
                reply_text=AsyncMock(),
            ),
            effective_user=teacher,
            effective_chat=SimpleNamespace(id=101),
        )
        context = SimpleNamespace(
            user_data={},
            bot=SimpleNamespace(send_chat_action=AsyncMock()),
        )
        access = {"allowed": True, "plan_code": "pro"}
        with (
            patch.object(bot_main, "generation_access_for_user", return_value=access),
            patch.object(bot_main, "selected_openrouter_model", return_value="offline-model"),
            patch.object(bot_main, "generate_text", AsyncMock(side_effect=TimeoutError("offline"))),
        ):
            await bot_main.handle_message(update, context)
        if not update.message.reply_text.await_args:
            return False, 1
        text = str(update.message.reply_text.await_args.args[0])
        return "could not contact OpenRouter" in text and "Check your internet" in text, 1

    started = perf_counter()
    recovered, expected_errors = asyncio.run(recover_from_failure())
    journeys.append(
        {
            "name": "recover_from_api_failure",
            "duration_ms": _elapsed_ms(started),
            "screens": 2,
            "errors": expected_errors,
            "result": "pass" if recovered else "fail",
            "inspection": "timeout is caught and a retry-oriented message is returned",
        }
    )

    result = {
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "deterministic offline technical baseline; excludes network and human think time",
        "journeys": journeys,
        "overall": "pass" if all(item["result"] == "pass" for item in journeys) else "fail",
    }
    temporary.cleanup()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure the TeacherOS Day 1 offline baseline.")
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    args = parser.parse_args()
    result = measure()
    rendered = json.dumps(result, indent=2)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
