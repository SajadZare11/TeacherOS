from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from config import (
    FREE_DAILY_GENERATION_LIMIT,
    LOCAL_PAYMENT_SIMULATOR,
    PAYMENT_CALLBACK_BASE_URL,
    PAYMENT_CURRENCY,
    PLAN_PRICES_TOMAN,
    PREMIUM_PRICE_TOMAN,
    PREMIUM_SUBSCRIPTION_DAYS,
    PRO_PRICE_TOMAN,
    PRO_SUBSCRIPTION_DAYS,
    ZARINPAL_SANDBOX,
    is_admin_telegram_user,
    payment_setting_problem,
    plan_duration_days,
)
from database import (
    create_payment_order,
    get_user_entitlement,
    get_user_payment,
    list_user_payments,
    mark_payment_failed,
    mark_payment_paid,
    record_payment_provider_note,
    set_payment_pending,
)
from keyboards import (
    payment_history_keyboard,
    payment_home_keyboard,
    payment_ready_keyboard,
    plan_confirmation_keyboard,
    start_menu_keyboard,
)
from payment_gateway import (
    ZarinPalGatewayError,
    create_zarinpal_payment,
    verify_zarinpal_payment,
)
from subscription_service import format_subscription_expiry

logger = logging.getLogger(__name__)

_STATUS_LABELS = {
    "created": "ایجاد شده",
    "pending": "در انتظار پرداخت",
    "paid": "پرداخت موفق",
    "failed": "ناموفق",
    "cancelled": "لغو شده",
}
_PLAN_NAMES_FA = {
    "free": "رایگان",
    "pro": "Pro",
    "premium": "Premium",
}
_PERSIAN_DIGITS = str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬")


def _fa_number(value: object) -> str:
    try:
        text = f"{int(value):,}"
    except (TypeError, ValueError):
        text = str(value or "۰")
    return text.translate(_PERSIAN_DIGITS)


def _plan_price(plan_code: str) -> int:
    try:
        return int(PLAN_PRICES_TOMAN[plan_code])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("پلن انتخاب‌شده معتبر نیست.") from exc


def _plan_name(plan_code: object) -> str:
    code = str(plan_code or "free").lower()
    return _PLAN_NAMES_FA.get(code, str(plan_code or "پلن"))


def _entitlement_text(entitlement: dict[str, Any]) -> str:
    plan = str(entitlement.get("plan_code") or "free")
    lines = [f"پلن فعلی شما: {_plan_name(plan)}"]
    if entitlement.get("expires_at"):
        mode = " · آزمایشی" if entitlement.get("is_sandbox") else ""
        lines.append(
            f"اعتبار تا: {format_subscription_expiry(entitlement['expires_at'])}{mode}"
        )
    if entitlement.get("daily_limit") is None:
        lines.append("تولید روزانه: نامحدود")
    else:
        lines.append(
            "مصرف امروز: "
            f"{_fa_number(entitlement.get('used_today') or 0)} از "
            f"{_fa_number(entitlement.get('daily_limit') or 0)} تولید"
        )
    return "\n".join(lines)


def _payment_home_text(entitlement: dict[str, Any]) -> str:
    if payment_setting_problem():
        return (
            "💳 پلن‌های TeacherOS\n\n"
            "در حال حاضر امکان ساخت لینک پرداخت وجود ندارد.\n"
            "لطفاً کمی بعد دوباره امتحان کنید یا با پشتیبانی TeacherOS تماس بگیرید.\n\n"
            "مدیر سیستم می‌تواند برای بررسی فنی دستور زیر را اجرا کند:\n"
            "python backend/check_project.py"
        )

    if ZARINPAL_SANDBOX and LOCAL_PAYMENT_SIMULATOR:
        mode_text = (
            "🧪 حالت آزمایشی فعال است؛ هیچ مبلغ واقعی از شما کم نمی‌شود. "
            "این صفحه فقط برای تست فرایند خرید است."
        )
    elif ZARINPAL_SANDBOX:
        mode_text = (
            "🧪 درگاه آزمایشی زرین‌پال فعال است؛ هیچ مبلغ واقعی پرداخت نمی‌شود "
            "و اشتراک ایجادشده فقط آزمایشی است."
        )
    else:
        mode_text = (
            "🔐 پرداخت امن از طریق زرین‌پال انجام می‌شود و پلن فقط بعد از "
            "تأیید رسمی تراکنش فعال خواهد شد."
        )

    return (
        "💳 پلن‌های TeacherOS\n\n"
        f"{_entitlement_text(entitlement)}\n\n"
        "🆓 پلن رایگان\n"
        f"• {_fa_number(FREE_DAILY_GENERATION_LIMIT)} تولید موفق در روز\n"
        "• کتابخانه، جست‌وجو و خروجی Word و PDF\n\n"
        f"⭐ پلن Pro — {_fa_number(PRO_PRICE_TOMAN)} تومان / "
        f"{_fa_number(PRO_SUBSCRIPTION_DAYS)} روز\n"
        "• تولید نامحدود\n"
        "• دسترسی به تمام ابزارهای ساخت و خروجی TeacherOS\n\n"
        f"👑 پلن Premium — {_fa_number(PREMIUM_PRICE_TOMAN)} تومان / "
        f"{_fa_number(PREMIUM_SUBSCRIPTION_DAYS)} روز\n"
        "• تولید نامحدود\n"
        "• دسترسی اولویت‌دار و امکان استفاده از مدل‌های بهتر\n\n"
        f"{mode_text}\n\n"
        "پلن موردنظر را از دکمه‌های زیر انتخاب کنید."
    )


def _plan_confirmation_text(plan_code: str) -> str:
    name = _plan_name(plan_code)
    price = _plan_price(plan_code)
    duration_days = plan_duration_days(plan_code)
    priority = "\n• دسترسی اولویت‌دار" if plan_code == "premium" else ""

    if ZARINPAL_SANDBOX and LOCAL_PAYMENT_SIMULATOR:
        mode = "آزمایشی محلی — بدون برداشت پول واقعی"
    elif ZARINPAL_SANDBOX:
        mode = "آزمایشی زرین‌پال — بدون برداشت پول واقعی"
    else:
        mode = "پرداخت واقعی از طریق زرین‌پال"

    return (
        f"{'👑' if plan_code == 'premium' else '⭐'} تأیید خرید پلن {name}\n\n"
        f"مبلغ: {_fa_number(price)} تومان\n"
        f"مدت اشتراک: {_fa_number(duration_days)} روز\n"
        "• تولید نامحدود با هوش مصنوعی"
        f"{priority}\n\n"
        f"وضعیت درگاه: {mode}\n\n"
        "پس از پرداخت، TeacherOS تراکنش را مستقیماً از زرین‌پال بررسی می‌کند. "
        "فعال‌شدن پلن فقط بعد از تأیید موفق انجام می‌شود."
    )


def _status_text(payment: dict[str, Any]) -> str:
    status = str(payment.get("status") or "unknown")
    mode = "آزمایشی" if int(payment.get("is_sandbox") or 0) else "واقعی"
    product = str(payment.get("product_code") or "").lower()
    lines = [
        "💳 وضعیت پرداخت",
        "",
        f"شماره سفارش: {payment.get('order_id')}",
        f"پلن: {_plan_name(product) if product else 'تست پرداخت'}",
        f"نوع پرداخت: {mode}",
        f"مبلغ: {_fa_number(payment.get('amount') or 0)} تومان",
        f"وضعیت: {_STATUS_LABELS.get(status, 'نامشخص')}",
    ]
    if payment.get("ref_id"):
        lines.append(f"کد پیگیری: {payment['ref_id']}")

    if status == "paid":
        activated_plan = payment.get("activated_plan") or product
        lines.extend(
            [
                "",
                "✅ پرداخت شما با موفقیت تأیید شد و اطلاعات تراکنش امن بررسی شد.",
            ]
        )
        if activated_plan:
            lines.append(f"پلن فعال‌شده: {_plan_name(activated_plan)}")
        if payment.get("subscription_expires_at"):
            lines.append(
                "اعتبار تا: "
                f"{format_subscription_expiry(payment['subscription_expires_at'])}"
            )
        if int(payment.get("is_sandbox") or 0):
            lines.append("این تراکنش آزمایشی بود و هیچ مبلغ واقعی پرداخت نشد.")
    elif status == "pending":
        lines.extend(
            [
                "",
                "ابتدا پرداخت را در صفحه زرین‌پال کامل کنید، سپس به تلگرام "
                "برگردید و دکمه «بررسی وضعیت پرداخت» را بزنید.",
            ]
        )
    elif status == "cancelled":
        lines.extend(["", "پرداخت لغو شد و هیچ پلنی فعال نشده است."])
    elif status == "failed":
        lines.extend(
            [
                "",
                "پرداخت تأیید نشد. مبلغی بابت پلن فعال نشده است؛ می‌توانید دوباره تلاش کنید.",
            ]
        )
    return "\n".join(lines)


def _history_text(payments: list[dict[str, Any]]) -> str:
    if not payments:
        return "🧾 سوابق پرداخت\n\nهنوز هیچ سفارش پرداختی ثبت نشده است."

    lines = ["🧾 سوابق پرداخت", "", "پنج سفارش آخر شما:"]
    for payment in payments:
        status = str(payment.get("status") or "unknown")
        mode = "آزمایشی" if int(payment.get("is_sandbox") or 0) else "واقعی"
        product = str(payment.get("product_code") or "")
        lines.extend(
            [
                "",
                f"#{_fa_number(payment['id'])} · {mode} · "
                f"{_STATUS_LABELS.get(status, 'نامشخص')}",
                f"{_plan_name(product) if product else 'تست پرداخت'} · "
                f"{_fa_number(payment.get('amount') or 0)} تومان",
                f"زمان ثبت: {payment.get('created_at')}",
                f"شماره سفارش: {payment.get('order_id')}",
            ]
        )
        if payment.get("ref_id"):
            lines.append(f"کد پیگیری: {payment['ref_id']}")
        if payment.get("subscription_expires_at"):
            lines.append(
                "اعتبار پلن تا: "
                f"{format_subscription_expiry(payment['subscription_expires_at'])}"
            )
    return "\n".join(lines)


async def _safe_edit(query: Any, text: str, *, reply_markup: Any) -> None:
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except Exception as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def _show_home(update: Update) -> None:
    user = update.effective_user
    if user is None or not isinstance(getattr(user, "id", None), int):
        return
    entitlement = get_user_entitlement(telegram_user_id=user.id)
    keyboard = payment_home_keyboard(
        sandbox=ZARINPAL_SANDBOX,
        pro_price=PRO_PRICE_TOMAN,
        premium_price=PREMIUM_PRICE_TOMAN,
    )
    if update.callback_query is not None:
        await _safe_edit(
            update.callback_query,
            _payment_home_text(entitlement),
            reply_markup=keyboard,
        )
    elif update.message is not None:
        await update.message.reply_text(
            _payment_home_text(entitlement),
            reply_markup=keyboard,
        )


async def upgrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await _show_home(update)


async def payments_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    user = update.effective_user
    if user is None or not isinstance(getattr(user, "id", None), int):
        return
    payments = list_user_payments(telegram_user_id=user.id, limit=5)
    if update.message is not None:
        await update.message.reply_text(
            _history_text(payments),
            reply_markup=payment_history_keyboard(),
        )


async def _create_plan_payment(update: Update, plan_code: str) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    if plan_code not in {"pro", "premium"}:
        await query.answer("این پلن معتبر نیست.", show_alert=True)
        return

    if payment_setting_problem():
        await query.answer(
            "درگاه پرداخت هنوز آماده نیست. لطفاً کمی بعد دوباره امتحان کنید.",
            show_alert=True,
        )
        return

    price = _plan_price(plan_code)
    duration_days = plan_duration_days(plan_code)
    plan_name = _plan_name(plan_code)
    await query.answer()
    await _safe_edit(
        query,
        f"⏳ در حال ساخت لینک امن پرداخت برای پلن {plan_name}...",
        reply_markup=payment_history_keyboard(),
    )

    callback_token = secrets.token_urlsafe(32)
    callback_token_hash = hashlib.sha256(callback_token.encode("utf-8")).hexdigest()
    try:
        order = create_payment_order(
            telegram_user=user,
            purpose=f"TeacherOS {plan_name} subscription — {duration_days} days",
            amount=price,
            currency=PAYMENT_CURRENCY,
            callback_token_hash=callback_token_hash,
            is_sandbox=ZARINPAL_SANDBOX,
            product_code=plan_code,
            subscription_days=duration_days,
        )
        if ZARINPAL_SANDBOX and LOCAL_PAYMENT_SIMULATOR:
            local_authority = f"LOCAL-SANDBOX-{order['order_id']}"
            local_url = (
                f"{PAYMENT_CALLBACK_BASE_URL}/payments/sandbox/checkout/{callback_token}"
            )
            payment = set_payment_pending(
                payment_id=int(order["id"]),
                authority=local_authority,
                payment_url=local_url,
                provider_code=100,
                provider_message="TeacherOS local sandbox order created",
            )
        else:
            callback_url = (
                f"{PAYMENT_CALLBACK_BASE_URL}/payments/zarinpal/callback/{callback_token}"
            )
            gateway_result = await asyncio.to_thread(
                create_zarinpal_payment,
                amount=int(order["amount"]),
                currency=str(order["currency"]),
                description=f"TeacherOS {plan_name} {order['order_id']}",
                callback_url=callback_url,
                order_id=str(order["order_id"]),
            )
            payment = set_payment_pending(
                payment_id=int(order["id"]),
                authority=str(gateway_result["authority"]),
                payment_url=str(gateway_result["payment_url"]),
                provider_code=int(gateway_result["code"]),
                provider_message=str(gateway_result["message"]),
            )
    except ZarinPalGatewayError as exc:
        logger.warning("ZarinPal plan request failed: %s", exc)
        if "order" in locals():
            mark_payment_failed(
                payment_id=int(order["id"]),
                provider_code=exc.code,
                provider_message=str(exc),
            )
        await _safe_edit(
            query,
            "❌ ساخت لینک پرداخت انجام نشد.\n\n"
            "لطفاً چند لحظه بعد دوباره امتحان کنید. اگر مشکل ادامه داشت، "
            "با پشتیبانی TeacherOS تماس بگیرید.",
            reply_markup=payment_home_keyboard(
                sandbox=ZARINPAL_SANDBOX,
                pro_price=PRO_PRICE_TOMAN,
                premium_price=PREMIUM_PRICE_TOMAN,
            ),
        )
        return
    except Exception:
        logger.exception("Could not create TeacherOS plan payment")
        if "order" in locals():
            mark_payment_failed(
                payment_id=int(order["id"]),
                provider_code=None,
                provider_message="Unexpected payment creation error",
            )
        await _safe_edit(
            query,
            "❌ TeacherOS نتوانست سفارش پرداخت را ایجاد کند.\n\n"
            "لطفاً دوباره امتحان کنید.",
            reply_markup=payment_home_keyboard(
                sandbox=ZARINPAL_SANDBOX,
                pro_price=PRO_PRICE_TOMAN,
                premium_price=PREMIUM_PRICE_TOMAN,
            ),
        )
        return

    next_step_text = (
        "در صفحه آزمایشی می‌توانید پرداخت موفق یا لغو پرداخت را شبیه‌سازی کنید."
        if ZARINPAL_SANDBOX and LOCAL_PAYMENT_SIMULATOR
        else "پس از بازگشت از زرین‌پال، TeacherOS نتیجه را بررسی و پلن را فعال می‌کند."
    )
    text = (
        f"{'🧪 ' if ZARINPAL_SANDBOX else ''}لینک پرداخت پلن {plan_name} آماده است\n\n"
        f"شماره سفارش: {payment['order_id']}\n"
        f"مبلغ: {_fa_number(payment['amount'])} تومان\n"
        f"مدت اشتراک: {_fa_number(duration_days)} روز\n"
        f"پرداخت واقعی: {'خیر' if ZARINPAL_SANDBOX else 'بله'}\n\n"
        f"{next_step_text}"
    )
    if ZARINPAL_SANDBOX:
        text += (
            "\n\nاین لینک آزمایشی را روی همان کامپیوتری باز کنید که ربات روی آن اجرا می‌شود."
        )
    await _safe_edit(
        query,
        text,
        reply_markup=payment_ready_keyboard(
            payment_id=int(payment["id"]),
            payment_url=str(payment["payment_url"]),
        ),
    )


async def payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or not isinstance(getattr(user, "id", None), int):
        return

    data = query.data or ""
    context.user_data.clear()

    if data == "payment_home":
        await query.answer()
        await _show_home(update)
        return

    if data in {"plan_select_pro", "plan_select_premium"}:
        plan_code = data.removeprefix("plan_select_")
        await query.answer()
        await _safe_edit(
            query,
            _plan_confirmation_text(plan_code),
            reply_markup=plan_confirmation_keyboard(plan_code=plan_code),
        )
        return

    if data in {"plan_buy_pro", "plan_buy_premium"}:
        await _create_plan_payment(update, data.removeprefix("plan_buy_"))
        return

    if data == "payment_create_test":
        await query.answer(
            "سفارش آزمایشی قدیمی با خرید آزمایشی پلن جایگزین شده است.",
            show_alert=True,
        )
        await _show_home(update)
        return

    if data == "payment_history":
        await query.answer()
        payments = list_user_payments(telegram_user_id=user.id, limit=5)
        await _safe_edit(
            query,
            _history_text(payments),
            reply_markup=payment_history_keyboard(),
        )
        return

    if data.startswith("payment_status_"):
        try:
            payment_id = int(data.rsplit("_", 1)[1])
        except (ValueError, IndexError):
            await query.answer("این دکمه پرداخت معتبر نیست.", show_alert=True)
            return

        payment = get_user_payment(
            telegram_user_id=user.id,
            payment_id=payment_id,
        )
        if payment is None:
            await query.answer("سفارش پرداخت پیدا نشد.", show_alert=True)
            return

        local_sandbox_order = str(payment.get("authority") or "").startswith(
            "LOCAL-SANDBOX-"
        )
        if (
            str(payment.get("status")) == "pending"
            and payment.get("authority")
            and not local_sandbox_order
        ):
            try:
                verified = await asyncio.to_thread(
                    verify_zarinpal_payment,
                    amount=int(payment["amount"]),
                    authority=str(payment["authority"]),
                )
            except ZarinPalGatewayError as exc:
                record_payment_provider_note(
                    payment_id=payment_id,
                    provider_code=exc.code,
                    provider_message=str(exc),
                )
            except Exception as exc:
                logger.warning(
                    "Payment refresh verification failed: %s",
                    type(exc).__name__,
                )
                record_payment_provider_note(
                    payment_id=payment_id,
                    provider_code=None,
                    provider_message="Temporary verification error",
                )
            else:
                mark_payment_paid(
                    payment_id=payment_id,
                    authority=str(payment["authority"]),
                    ref_id=verified.get("ref_id"),
                    card_pan=verified.get("card_pan"),
                    card_hash=verified.get("card_hash"),
                    provider_code=int(verified.get("code") or 100),
                    provider_message=str(verified.get("message") or "Verified"),
                )
            payment = (
                get_user_payment(
                    telegram_user_id=user.id,
                    payment_id=payment_id,
                )
                or payment
            )

        await query.answer()
        if payment.get("payment_url") and str(payment.get("status")) == "pending":
            keyboard = payment_ready_keyboard(
                payment_id=payment_id,
                payment_url=str(payment["payment_url"]),
            )
        else:
            keyboard = payment_history_keyboard()
        await _safe_edit(query, _status_text(payment), reply_markup=keyboard)
        return

    if data == "payment_main":
        await query.answer()
        await _safe_edit(
            query,
            "👋 منوی اصلی TeacherOS\n\nابزار موردنظر خود را انتخاب کنید.",
            reply_markup=start_menu_keyboard(
                show_admin=is_admin_telegram_user(user.id)
            ),
        )
        return

    await query.answer("این دکمه پرداخت دیگر معتبر نیست.", show_alert=True)
