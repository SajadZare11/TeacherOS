"""TeacherOS Retrieval & Spaced-Review Telegram UI Panel (Day 20).

Handles all interactive callback queries and text entries for the transparent
spaced-retrieval queue.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from telegram import Update
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import ContextTypes

from class_service import get_class
from database import register_telegram_user
from retrieval_review_keyboards import (
    _base36,
    add_category_keyboard,
    add_confirm_keyboard,
    confidence_picker_keyboard,
    due_item_card_keyboard,
    intervals_settings_keyboard,
    queue_browser_keyboard,
    queue_item_actions_keyboard,
    review_dashboard_keyboard,
    review_result_keyboard,
    snooze_picker_keyboard,
)
from retrieval_review_service import (
    CATEGORY_ICONS,
    CATEGORY_LABELS,
    DEFAULT_INTERVALS,
    add_review_item,
    archive_item,
    count_due_items,
    count_queue_items,
    get_class_intervals,
    get_due_items,
    get_review_item,
    get_review_queue,
    get_review_queue_stats,
    override_review_schedule,
    pause_item,
    record_review,
    resume_item,
    snooze_item,
    update_class_intervals,
    update_confidence,
)

logger = logging.getLogger(__name__)

_CALLBACK_PATTERN = re.compile(
    r"^v1\|rv\|(?P<action>[a-z0-9_]{1,10})\|"
    r"(?P<object_id>[0-9a-z_]{1,20})\|(?P<revision>[0-9a-z]{1,6})$"
)

CATEGORY_CODE_MAP = {
    "vc": "vocabulary",
    "gr": "grammar",
    "pr": "pronunciation",
    "fl": "functional_language",
    "ce": "common_error",
    "es": "exam_strategy",
}


def _decode_b36(val: str) -> int:
    try:
        return int(val, 36)
    except (ValueError, TypeError):
        return 0


async def _answer_query(query: Any, text: str | None = None) -> None:
    if query is None:
        return
    try:
        await query.answer(text=text)
    except (TimedOut, NetworkError, BadRequest):
        pass


async def _safe_edit(query: Any, text: str, *, reply_markup: Any) -> None:
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


# ---------------------------------------------------------------------------
# Callback Query Handler
# ---------------------------------------------------------------------------

async def handle_retrieval_review_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Route and dispatch all retrieval spaced-review callbacks."""
    query = update.callback_query
    if query is None or not query.data:
        return

    match = _CALLBACK_PATTERN.match(query.data)
    if not match:
        return

    action = match.group("action")
    raw_object = match.group("object_id")
    raw_rev = match.group("revision")
    revision = _decode_b36(raw_rev)

    tg_user = update.effective_user
    if tg_user is None or not isinstance(getattr(tg_user, "id", None), int):
        return

    tg_user_id = tg_user.id
    user_id = register_telegram_user(tg_user)

    # -----------------------------------------------------------------------
    # Action: Review Dashboard (home)
    # -----------------------------------------------------------------------
    if action == "home":
        class_id = _decode_b36(raw_object)
        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query)
        due_count = count_due_items(user_id=user_id, class_id=class_id)
        stats = get_review_queue_stats(user_id=user_id, class_id=class_id)
        intervals = get_class_intervals(user_id=user_id, class_id=class_id)

        lines = [
            f"🔁 Spaced-Review Queue · {owned['display_name']}",
            "",
            f"🎯 Due for Retrieval: {due_count}",
            f"📋 Active Queue Items: {stats['active']}",
            f"⏸ Paused: {stats['paused']} · ⏰ Snoozed: {stats['snoozed']}",
            f"⚙ Intervals: {intervals} days",
            "",
            "Review previously taught language at transparent, configurable intervals.",
            "Status remains a flexible planning aid under your direct control.",
        ]

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=review_dashboard_keyboard(
                class_id=class_id,
                revision=revision,
                due_count=due_count,
                total_count=stats["total"],
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: Interactive Due Review (due, rev, rr, rp, rf)
    # -----------------------------------------------------------------------
    if action == "due":
        class_id = _decode_b36(raw_object)
        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query)
        due_items = get_due_items(user_id=user_id, class_id=class_id, limit=1)
        if not due_items:
            await _safe_edit(
                query,
                f"🎉 Great job! No items are currently due for {owned['display_name']}.\n\n"
                "Items will automatically return when their scheduled intervals arrive.",
                reply_markup=review_dashboard_keyboard(
                    class_id=class_id,
                    revision=revision,
                    due_count=0,
                    total_count=count_queue_items(user_id=user_id, class_id=class_id),
                ),
            )
            return

        it = due_items[0]
        cat_icon = CATEGORY_ICONS.get(it["category"], "•")
        cat_name = CATEGORY_LABELS.get(it["category"], it["category"].title())

        text = (
            f"🔁 Retrieval Review (Due Now)\n\n"
            f"🏫 Class: {owned['display_name']}\n"
            f"{cat_icon} Category: {cat_name}\n"
            f"📊 Stage: {it['interval_stage'] + 1} of {len(it['intervals'])}\n\n"
            f"❓ Prompt:\n{it['prompt_text']}\n\n"
            "Try to recall the target language, then tap below to check your answer."
        )

        await _safe_edit(
            query,
            text,
            reply_markup=due_item_card_keyboard(
                item_id=it["id"],
                class_id=class_id,
                revision=revision,
                revealed=False,
            ),
        )
        return

    if action == "rev":
        item_id = _decode_b36(raw_object)
        it = get_review_item(user_id=user_id, item_id=item_id)
        if not it:
            await _answer_query(query, "Item not found.")
            return

        await _answer_query(query)
        cat_icon = CATEGORY_ICONS.get(it["category"], "•")
        cat_name = CATEGORY_LABELS.get(it["category"], it["category"].title())

        text = (
            f"🔁 Retrieval Review (Answer Revealed)\n\n"
            f"{cat_icon} Category: {cat_name}\n"
            f"📊 Stage: {it['interval_stage'] + 1} of {len(it['intervals'])}\n\n"
            f"❓ Prompt:\n{it['prompt_text']}\n\n"
            f"✅ Target Answer:\n{it['target_answer']}\n"
        )
        if it.get("notes"):
            text += f"\n📝 Notes: {it['notes']}\n"

        text += "\nHow well was this recalled?"

        await _safe_edit(
            query,
            text,
            reply_markup=due_item_card_keyboard(
                item_id=it["id"],
                class_id=it["class_id"],
                revision=revision,
                revealed=True,
            ),
        )
        return

    if action in {"rr", "rp", "rf"}:
        item_id = _decode_b36(raw_object)
        result_map = {
            "rr": "remembered",
            "rp": "partly_remembered",
            "rf": "forgotten",
        }
        res_name = result_map[action]
        updated = record_review(user_id=user_id, item_id=item_id, result=res_name)
        if not updated:
            await _answer_query(query, "Item not found.")
            return

        await _answer_query(query, f"Recorded: {res_name.replace('_', ' ').title()}")
        class_id = updated["class_id"]
        more_due = count_due_items(user_id=user_id, class_id=class_id) > 0

        res_msg = {
            "remembered": "✅ Remembered! Spacing advanced to next interval.",
            "partly_remembered": "◐ Partly remembered. Interval kept at current stage.",
            "forgotten": "↻ Needs review. Interval stepped back to reinforce recall.",
        }[res_name]

        text = (
            f"📈 Review Recorded\n\n"
            f"{res_msg}\n\n"
            f"📅 Next Review Date: {updated['next_review_date']}\n"
            f"📊 Stage: {updated['interval_stage'] + 1} of {len(updated['intervals'])}\n"
            f"🔁 Total Reviews: {updated['review_count']}"
        )

        await _safe_edit(
            query,
            text,
            reply_markup=review_result_keyboard(
                item_id=item_id,
                class_id=class_id,
                revision=revision,
                has_more_due=more_due,
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: Snooze (snz, s1, s3, s7)
    # -----------------------------------------------------------------------
    if action == "snz":
        item_id = _decode_b36(raw_object)
        it = get_review_item(user_id=user_id, item_id=item_id)
        if not it:
            await _answer_query(query, "Item not found.")
            return

        await _answer_query(query)
        await _safe_edit(
            query,
            f"⏰ Snooze Item: '{it['prompt_text'][:40]}'\n\n"
            "Choose how long to postpone this review without affecting its spacing stage.",
            reply_markup=snooze_picker_keyboard(
                item_id=item_id,
                class_id=it["class_id"],
                revision=revision,
            ),
        )
        return

    if action in {"s1", "s3", "s7"}:
        item_id = _decode_b36(raw_object)
        days = {"s1": 1, "s3": 3, "s7": 7}[action]
        updated = snooze_item(user_id=user_id, item_id=item_id, days=days)
        if not updated:
            await _answer_query(query, "Item not found.")
            return

        await _answer_query(query, f"Snoozed for {days} day(s)")
        await _safe_edit(
            query,
            f"⏰ Item Snoozed\n\n"
            f"'{updated['prompt_text']}'\n\n"
            f"Postponed until: {updated['next_review_date']}\n"
            "It will not appear in due review sessions until then.",
            reply_markup=queue_item_actions_keyboard(
                item_id=item_id,
                class_id=updated["class_id"],
                revision=revision,
                status=updated["status"],
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: Pause, Resume, Archive
    # -----------------------------------------------------------------------
    if action == "ps":
        item_id = _decode_b36(raw_object)
        updated = pause_item(user_id=user_id, item_id=item_id)
        if not updated:
            await _answer_query(query, "Item not found.")
            return
        await _answer_query(query, "Item paused.")
        await _safe_edit(
            query,
            f"⏸ Item Paused\n\n'{updated['prompt_text']}'\n\n"
            "This item is paused and will not appear in review sessions until resumed.",
            reply_markup=queue_item_actions_keyboard(
                item_id=item_id,
                class_id=updated["class_id"],
                revision=revision,
                status=updated["status"],
            ),
        )
        return

    if action == "rs":
        item_id = _decode_b36(raw_object)
        updated = resume_item(user_id=user_id, item_id=item_id)
        if not updated:
            await _answer_query(query, "Item not found.")
            return
        await _answer_query(query, "Item resumed.")
        await _safe_edit(
            query,
            f"▶ Item Resumed\n\n'{updated['prompt_text']}'\n\n"
            f"Next review scheduled for: {updated['next_review_date']}",
            reply_markup=queue_item_actions_keyboard(
                item_id=item_id,
                class_id=updated["class_id"],
                revision=revision,
                status=updated["status"],
            ),
        )
        return

    if action == "ar":
        item_id = _decode_b36(raw_object)
        updated = archive_item(user_id=user_id, item_id=item_id)
        if not updated:
            await _answer_query(query, "Item not found.")
            return
        await _answer_query(query, "Item archived.")
        await _safe_edit(
            query,
            f"🗃 Item Archived\n\n'{updated['prompt_text']}'\n\n"
            "This item has been removed from active circulation.",
            reply_markup=review_dashboard_keyboard(
                class_id=updated["class_id"],
                revision=revision,
                due_count=count_due_items(user_id=user_id, class_id=updated["class_id"]),
                total_count=count_queue_items(user_id=user_id, class_id=updated["class_id"]),
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: Confidence Selection (cf, cfl, cfm, cfh)
    # -----------------------------------------------------------------------
    if action == "cf":
        item_id = _decode_b36(raw_object)
        it = get_review_item(user_id=user_id, item_id=item_id)
        if not it:
            await _answer_query(query, "Item not found.")
            return
        await _answer_query(query)
        await _safe_edit(
            query,
            f"📊 Teacher Confidence Tag · '{it['prompt_text'][:35]}'\n\n"
            f"Current Confidence: {it['confidence'].title()}\n\n"
            "Set your qualitative confidence level as a teaching planning aid.",
            reply_markup=confidence_picker_keyboard(
                item_id=item_id,
                class_id=it["class_id"],
                revision=revision,
                current_confidence=it["confidence"],
            ),
        )
        return

    if action in {"cfl", "cfm", "cfh"}:
        item_id = _decode_b36(raw_object)
        c_map = {"cfl": "low", "cfm": "medium", "cfh": "high"}
        conf = c_map[action]
        updated = update_confidence(user_id=user_id, item_id=item_id, confidence=conf)
        if not updated:
            await _answer_query(query, "Item not found.")
            return
        await _answer_query(query, f"Confidence set to {conf.title()}")
        await _safe_edit(
            query,
            f"✅ Confidence Updated\n\n"
            f"'{updated['prompt_text']}'\n\n"
            f"Confidence: {updated['confidence'].title()}",
            reply_markup=queue_item_actions_keyboard(
                item_id=item_id,
                class_id=updated["class_id"],
                revision=revision,
                status=updated["status"],
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: Item Inspection (it)
    # -----------------------------------------------------------------------
    if action == "it":
        item_id = _decode_b36(raw_object)
        it = get_review_item(user_id=user_id, item_id=item_id)
        if not it:
            await _answer_query(query, "Item not found.")
            return
        await _answer_query(query)
        cat_icon = CATEGORY_ICONS.get(it["category"], "•")
        cat_name = CATEGORY_LABELS.get(it["category"], it["category"].title())

        lines = [
            f"📋 Review Item Details",
            "",
            f"{cat_icon} Category: {cat_name}",
            f"❓ Prompt: {it['prompt_text']}",
            f"✅ Target: {it['target_answer']}",
        ]
        if it.get("notes"):
            lines.append(f"📝 Notes: {it['notes']}")
        lines.extend([
            "",
            f"📊 Status: {it['status'].title()}",
            f"📈 Confidence: {it['confidence'].title()}",
            f"📅 Next Review: {it['next_review_date']}",
            f"🔢 Stage: {it['interval_stage'] + 1} of {len(it['intervals'])}",
            f"🔁 Total Reviews: {it['review_count']}",
            f"📌 Source: {it['source_type'].replace('_', ' ').title()}",
        ])

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=queue_item_actions_keyboard(
                item_id=item_id,
                class_id=it["class_id"],
                revision=revision,
                status=it["status"],
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: Queue Browser (q, qp, qf)
    # -----------------------------------------------------------------------
    if action in {"q", "qp", "qf"}:
        class_id = 0
        page = 0
        current_filter = "active"

        if action == "q":
            class_id = _decode_b36(raw_object)
        elif action == "qp":
            parts = raw_object.split("_")
            page = int(parts[0]) if parts[0].isdigit() else 0
            class_id = _decode_b36(parts[1]) if len(parts) > 1 else 0
        elif action == "qf":
            f_code = raw_object[0] if raw_object else "1"
            class_id_str = raw_object[1:] if len(raw_object) > 1 else ""
            class_id = _decode_b36(class_id_str)
            f_map = {"0": "all", "1": "active", "2": "due", "3": "paused"}
            current_filter = f_map.get(f_code, "active")

        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query)
        page_size = 5
        total_items = count_queue_items(
            user_id=user_id,
            class_id=class_id,
            status_filter=current_filter,
        )
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        page = max(0, min(page, total_pages - 1))

        items = get_review_queue(
            user_id=user_id,
            class_id=class_id,
            status_filter=current_filter,
            limit=page_size,
            offset=page * page_size,
        )

        header = (
            f"📋 Queue Browser · {owned['display_name']}\n"
            f"Filter: {current_filter.title()} ({total_items} items) · Page {page + 1}/{total_pages}\n\n"
            "Select an item to view details, snooze, or pause:"
        )

        await _safe_edit(
            query,
            header,
            reply_markup=queue_browser_keyboard(
                class_id=class_id,
                revision=revision,
                items=items,
                page=page,
                total_pages=total_pages,
                current_filter=current_filter,
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: Manual Add Item (add, acat, aok, acx)
    # -----------------------------------------------------------------------
    if action == "add":
        class_id = _decode_b36(raw_object)
        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query)
        context.user_data["review_add"] = {
            "class_id": class_id,
            "revision": revision,
            "state": "category",
        }

        await _safe_edit(
            query,
            f"➕ Add Review Item · Step 1 of 3\n\n"
            f"Class: {owned['display_name']}\n\n"
            "Select the language category for this review item:",
            reply_markup=add_category_keyboard(class_id=class_id, revision=revision),
        )
        return

    if action == "acat":
        parts = raw_object.split("_")
        cat_code = parts[0] if parts else "vc"
        class_id = _decode_b36(parts[1]) if len(parts) > 1 else 0
        category = CATEGORY_CODE_MAP.get(cat_code, "vocabulary")

        await _answer_query(query)
        context.user_data["review_add"] = {
            "class_id": class_id,
            "revision": revision,
            "category": category,
            "state": "prompt",
        }

        cat_icon = CATEGORY_ICONS.get(category, "•")
        cat_name = CATEGORY_LABELS.get(category, category.title())

        await _safe_edit(
            query,
            f"➕ Add Review Item · Step 2 of 3\n\n"
            f"{cat_icon} Category: {cat_name}\n\n"
            "Type the prompt or question students will see:\n"
            "(e.g., 'What phrasal verb means to postpone a meeting?')",
            reply_markup=None,
        )
        return

    if action == "aok":
        class_id = _decode_b36(raw_object)
        draft = context.user_data.pop("review_add", None)
        if not draft or not draft.get("prompt") or not draft.get("answer"):
            await _answer_query(query, "Draft expired.")
            return

        added = add_review_item(
            user_id=user_id,
            class_id=class_id,
            category=draft["category"],
            prompt_text=draft["prompt"],
            target_answer=draft["answer"],
            source_type="manual",
        )
        await _answer_query(query, "Review item saved!")

        cat_icon = CATEGORY_ICONS.get(added["category"], "•")
        text = (
            f"✅ Review Item Saved to Queue!\n\n"
            f"{cat_icon} Category: {CATEGORY_LABELS.get(added['category'])}\n"
            f"❓ Prompt: {added['prompt_text']}\n"
            f"✅ Target: {added['target_answer']}\n\n"
            f"📅 First Review Date: {added['next_review_date']}"
        )

        await _safe_edit(
            query,
            text,
            reply_markup=review_dashboard_keyboard(
                class_id=class_id,
                revision=revision,
                due_count=count_due_items(user_id=user_id, class_id=class_id),
                total_count=count_queue_items(user_id=user_id, class_id=class_id),
            ),
        )
        return

    if action == "acx":
        class_id = _decode_b36(raw_object)
        context.user_data.pop("review_add", None)
        await _answer_query(query, "Cancelled.")
        await _safe_edit(
            query,
            "❌ Adding review item cancelled.",
            reply_markup=review_dashboard_keyboard(
                class_id=class_id,
                revision=revision,
                due_count=count_due_items(user_id=user_id, class_id=class_id),
                total_count=count_queue_items(user_id=user_id, class_id=class_id),
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: Interval Settings (set, irst)
    # -----------------------------------------------------------------------
    if action == "set":
        class_id = _decode_b36(raw_object)
        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query)
        intervals = get_class_intervals(user_id=user_id, class_id=class_id)

        text = (
            f"⚙ Spaced-Review Intervals · {owned['display_name']}\n\n"
            f"Current Schedule: {intervals} days\n\n"
            "How it works:\n"
            f"• 1st Review: {intervals[0]} days after introduction\n"
            f"• 2nd Review: +{intervals[1]} days if remembered\n"
            f"• 3rd Review: +{intervals[2]} days\n"
            f"• 4th+ Review: +{intervals[3]} days\n\n"
            "Spacing is deterministic, transparent, and never black-box."
        )

        await _safe_edit(
            query,
            text,
            reply_markup=intervals_settings_keyboard(class_id=class_id, revision=revision),
        )
        return

    if action == "irst":
        class_id = _decode_b36(raw_object)
        update_class_intervals(user_id=user_id, class_id=class_id, intervals=DEFAULT_INTERVALS)
        await _answer_query(query, "Intervals reset to defaults.")
        await _safe_edit(
            query,
            f"✅ Spaced-review intervals reset to standard: {DEFAULT_INTERVALS} days.",
            reply_markup=intervals_settings_keyboard(class_id=class_id, revision=revision),
        )
        return

    # -----------------------------------------------------------------------
    # Action: Stats (stats)
    # -----------------------------------------------------------------------
    if action == "stats":
        class_id = _decode_b36(raw_object)
        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query)
        stats = get_review_queue_stats(user_id=user_id, class_id=class_id)

        lines = [
            f"📊 Queue Statistics · {owned['display_name']}",
            "",
            f"• Total Managed Items: {stats['total']}",
            f"• Active Items: {stats['active']}",
            f"• Due for Retrieval: {stats['due']}",
            f"• Snoozed: {stats['snoozed']}",
            f"• Paused: {stats['paused']}",
            f"• Archived: {stats['archived']}",
            "",
            "Breakdown by Language Category:",
        ]
        for cat, cnt in stats["by_category"].items():
            icon = CATEGORY_ICONS.get(cat, "•")
            name = CATEGORY_LABELS.get(cat, cat.title())
            lines.append(f"  {icon} {name}: {cnt}")

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=review_dashboard_keyboard(
                class_id=class_id,
                revision=revision,
                due_count=stats["due"],
                total_count=stats["total"],
            ),
        )
        return


# ---------------------------------------------------------------------------
# Message Handler for Manual Text Input
# ---------------------------------------------------------------------------

async def handle_retrieval_review_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle text input during manual review item creation."""
    if update.message is None or not update.message.text:
        return

    draft = context.user_data.get("review_add")
    if not isinstance(draft, dict) or not draft.get("state"):
        return

    user_text = update.message.text.strip()
    if len(user_text) < 2 or len(user_text) > 500:
        await update.message.reply_text("Please enter text between 2 and 500 characters.")
        return

    state = draft["state"]
    class_id = int(draft["class_id"])
    revision = int(draft.get("revision", 0))

    if state == "prompt":
        draft["prompt"] = user_text
        draft["state"] = "answer"
        await update.message.reply_text(
            "➕ Add Review Item · Step 3 of 3\n\n"
            "Now type the target answer or model language:\n"
            "(e.g., 'call off / put off')"
        )
        return

    if state == "answer":
        draft["answer"] = user_text
        draft["state"] = "confirm"

        category = draft.get("category", "vocabulary")
        cat_icon = CATEGORY_ICONS.get(category, "•")
        cat_name = CATEGORY_LABELS.get(category, category.title())

        summary = (
            f"🔍 Review Item Preview\n\n"
            f"{cat_icon} Category: {cat_name}\n"
            f"❓ Prompt: {draft['prompt']}\n"
            f"✅ Target: {draft['answer']}\n\n"
            "Ready to save into your spaced-review queue?"
        )

        await update.message.reply_text(
            summary,
            reply_markup=add_confirm_keyboard(class_id=class_id, revision=revision),
        )
        return
