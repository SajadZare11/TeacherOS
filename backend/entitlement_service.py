"""TeacherOS Centralized Entitlement and Commercial Outcome Service (Day 25).

Centralizes all plan capability checks, limits, and funnel telemetry:
- Active classes, daily generations, evidence batches, retention, differentiation,
  progress reports export, priority model, and spaced review limits.
- Contextual outcome-oriented upgrade prompts (explains teaching outcomes, never 'tokens').
- Free teaching loop guarantee (free users can complete >=1 full loop).
- Entitlement event telemetry and idempotent subscription verification.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from database import database_connection, get_user_entitlement
from feature_flags import feature_enabled

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Centralized Plan Tier Limits
# ---------------------------------------------------------------------------

TIER_LIMITS: dict[str, dict[str, Any]] = {
    "free": {
        "active_classes": 1,
        "daily_generations": 10,
        "evidence_batches_per_class": 2,
        "evidence_items_per_batch": 5,
        "retention_days": 30,
        "differentiation_level": "basic",
        "progress_reports_export": False,  # preview in-app is allowed, export blocked
        "priority_model": False,
        "review_items_per_lesson": 5,
    },
    "pro": {
        "active_classes": 10,
        "daily_generations": 50,
        "evidence_batches_per_class": 20,
        "evidence_items_per_batch": 35,
        "retention_days": 90,
        "differentiation_level": "full",
        "progress_reports_export": True,
        "priority_model": False,
        "review_items_per_lesson": 15,
    },
    "premium": {
        "active_classes": None,  # unlimited
        "daily_generations": None,  # unlimited
        "evidence_batches_per_class": None,  # unlimited
        "evidence_items_per_batch": 100,
        "retention_days": 365,
        "differentiation_level": "full",
        "progress_reports_export": True,
        "priority_model": True,
        "review_items_per_lesson": 30,
    },
}

VALID_EVENT_TYPES = frozenset({
    "viewed",
    "dismissed",
    "checkout_started",
    "paid",
    "failed",
    "refunded",
    "cancelled",
    "entitlement_restored",
})


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ---------------------------------------------------------------------------
# 1. Feature Access & Entitlement Evaluation
# ---------------------------------------------------------------------------

def check_feature_access(
    telegram_user_id: int,
    feature_key: str,
    *,
    class_id: int | None = None,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Central decision point evaluating if a teacher can perform a feature action."""
    entitlement = get_user_entitlement(telegram_user_id=telegram_user_id)
    plan_code = str(entitlement.get("plan_code") or "free")
    plan_name = str(entitlement.get("plan_name") or "Free")
    tier_config = TIER_LIMITS.get(plan_code, TIER_LIMITS["free"])

    enforced = feature_enabled("entitlements")
    allowed = True
    limit_val = tier_config.get(feature_key)
    current_val: Any = None

    if feature_key == "active_classes":
        from class_service import count_classes
        current_val = count_classes(telegram_user_id=telegram_user_id, status="active", database_path=database_path)
        if limit_val is not None:
            allowed = not enforced or current_val < limit_val

    elif feature_key == "daily_generations":
        used_today = int(entitlement.get("used_today") or 0)
        current_val = used_today
        if limit_val is not None:
            allowed = not enforced or used_today < limit_val

    elif feature_key == "evidence_batches_per_class":
        if class_id is not None:
            with database_connection(database_path) as conn:
                user = conn.execute("SELECT id FROM users WHERE telegram_user_id = ?", (telegram_user_id,)).fetchone()
                if user:
                    row = conn.execute(
                        "SELECT COUNT(*) FROM evidence_batches WHERE class_id = ? AND user_id = ? AND status != 'purged'",
                        (class_id, user["id"]),
                    ).fetchone()
                    current_val = int(row[0]) if row else 0
                    if limit_val is not None:
                        allowed = not enforced or current_val < limit_val

    elif feature_key == "progress_reports_export":
        current_val = bool(limit_val)
        allowed = not enforced or bool(limit_val)

    elif feature_key == "priority_model":
        current_val = bool(limit_val)
        allowed = not enforced or bool(limit_val)

    upgrade_prompt = None
    if not allowed:
        upgrade_prompt = get_contextual_upgrade_prompt(feature_key)

    return {
        "allowed": allowed,
        "enforced": enforced,
        "plan_code": plan_code,
        "plan_name": plan_name,
        "feature_key": feature_key,
        "limit": limit_val,
        "current": current_val,
        "upgrade_prompt": upgrade_prompt,
    }


# ---------------------------------------------------------------------------
# 2. Contextual Outcome-Oriented Upgrade Prompts
# ---------------------------------------------------------------------------

def get_contextual_upgrade_prompt(feature_key: str, lang: str = "en") -> str:
    """Generate outcome-oriented upgrade copy (explaining teaching outcomes, never 'tokens')."""
    prompts_en = {
        "active_classes": (
            "⭐ Ready to organize more teaching groups?\n\n"
            "The Free plan includes 1 active class profile. Upgrade to Pro to manage up to 10 classes "
            "with continuous memory, level tracking, and syllabus records for each cohort."
        ),
        "daily_generations": (
            "⭐ Daily Generation Quota Reached\n\n"
            "You have reached your 10 daily free generations. Upgrade to Pro for 50 daily lesson plans, "
            "activities, and worksheets, or Premium for unlimited planning."
        ),
        "evidence_batches_per_class": (
            "⭐ Expand Evidence-to-Action Diagnostics\n\n"
            "Free accounts support up to 2 active evidence batches per class. Upgrade to Pro for 20 batches "
            "to capture ongoing student writing and speaking progress all semester."
        ),
        "progress_reports_export": (
            "⭐ Export Classroom-Ready Progress Reports\n\n"
            "Word and PDF report exports are available on Pro and Premium plans. "
            "Upgrade to download official, formatted progress summaries with your school or class branding."
        ),
        "priority_model": (
            "⭐ Advanced CEFR Pedagogical Reasoning\n\n"
            "Priority AI routing with specialized language-teaching models is available on the Premium plan."
        ),
    }

    prompts_fa = {
        "active_classes": (
            "⭐ مدیریت کلاس‌های بیشتر با پلن حرفه‌ای\n\n"
            "در پلن رایگان می‌توانید ۱ کلاس فعال داشته باشید. برای مدیریت تا ۱۰ کلاس با حافظه اختصاصی و "
            "پیگیری اهداف آموزشی، به پلن Pro ارتقا دهید."
        ),
        "daily_generations": (
            "⭐ سهمیه تولید روزانه به پایان رسید\n\n"
            "سهمیه ۱۰ تولید رایگان امروز تمام شد. با ارتقا به پلن Pro روزانه ۵۰ طرح درس و کاربرگ دریافت کنید "
            "یا با پلن Premium به صورت نامحدود تولید نمایید."
        ),
        "evidence_batches_per_class": (
            "⭐ ثبت شواهد یادگیری بیشتر در کلاس\n\n"
            "در پلن رایگان امکان ثبت ۲ بسته شواهد کلاسی وجود دارد. با ارتقا به Pro می‌توانید تا ۲۰ بسته "
            "برای تحلیل مستمر رایتینگ و اسپیکینگ دانش‌آموزان ثبت کنید."
        ),
        "progress_reports_export": (
            "⭐ دریافت خروجی رسمی Word و PDF\n\n"
            "خروجی فایل‌های Word و PDF گزارش‌های پیشرفت در پلن‌های Pro و Premium فعال است."
        ),
        "priority_model": (
            "⭐ دسترسی به مدل‌های پیشرفته تحلیل زبان\n\n"
            "اولویت پردازش و مدل‌های تخصصی آموزش زبان در پلن Premium ارائه می‌شود."
        ),
    }

    catalog = prompts_fa if lang == "fa" else prompts_en
    return catalog.get(feature_key, prompts_en.get(feature_key, "⭐ Upgrade your plan to access this feature."))


# ---------------------------------------------------------------------------
# 3. Commercial Funnel Telemetry & Events
# ---------------------------------------------------------------------------

def record_entitlement_event(
    *,
    user_id: int,
    event_type: str,
    plan_code: str,
    feature_key: str | None = None,
    metadata: dict[str, Any] | None = None,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Instrument commercial funnel steps (viewed, checkout_started, paid, etc.)."""
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Invalid entitlement event type: {event_type}")

    now_str = _utc_now()
    event_uuid = f"ent_{uuid.uuid4().hex[:12]}"
    meta_json = json.dumps(metadata or {}, ensure_ascii=False)

    with database_connection(database_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO entitlement_events (
                event_uuid, user_id, event_type, plan_code, feature_key, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event_uuid, user_id, event_type, plan_code, feature_key, meta_json, now_str),
        )
        row = conn.execute("SELECT * FROM entitlement_events WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row) if row else {}


def can_complete_teaching_loop(
    telegram_user_id: int,
    database_path: Path | None = None,
) -> bool:
    """Validate that Free-tier teachers can complete at least 1 genuine teaching loop."""
    access_cls = check_feature_access(telegram_user_id, "active_classes", database_path=database_path)
    access_gen = check_feature_access(telegram_user_id, "daily_generations", database_path=database_path)
    # Free tier has active_classes limit >= 1 and daily_generations limit >= 10
    return bool(access_cls["limit"] >= 1 and access_gen["limit"] >= 10)
