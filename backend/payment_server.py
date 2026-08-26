from __future__ import annotations

import hashlib
import hmac
import html
import json
import logging
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from config import (
    LOCAL_PAYMENT_SIMULATOR,
    PAYMENT_SERVER_HOST,
    PAYMENT_SERVER_PORT,
    TELEGRAM_BOT_TOKEN,
    ZARINPAL_SANDBOX,
)
from database import (
    get_payment_by_callback_token_hash,
    mark_payment_cancelled,
    mark_payment_paid,
    record_payment_provider_note,
)
from payment_gateway import ZarinPalGatewayError, verify_zarinpal_payment
from subscription_service import format_subscription_expiry

logger = logging.getLogger(__name__)
_CALLBACK_PATTERN = re.compile(r"^/payments/zarinpal/callback/([A-Za-z0-9_-]{32,100})$")
_LOCAL_CHECKOUT_PATTERN = re.compile(r"^/payments/sandbox/checkout/([A-Za-z0-9_-]{32,100})$")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


_PERSIAN_DIGITS = str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬")


def _fa_number(value: object) -> str:
    try:
        text = f"{int(value):,}"
    except (TypeError, ValueError):
        text = str(value or "۰")
    return text.translate(_PERSIAN_DIGITS)


def _notify_telegram(chat_id: int, text: str) -> None:
    """Send a small notification without crossing event loops from the HTTP thread."""
    if not TELEGRAM_BOT_TOKEN or not isinstance(chat_id, int):
        return
    request = Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            response.read()
    except Exception:
        # Do not log the Telegram Bot API URL because it contains the bot token.
        logger.warning("Could not send the payment result to Telegram")


def process_zarinpal_callback(
    *,
    callback_token: str,
    authority: str,
    status: str,
    verifier: Callable[..., dict[str, Any]] = verify_zarinpal_payment,
    notify: Callable[[int, str], None] = _notify_telegram,
) -> dict[str, Any]:
    """Validate, verify, and idempotently settle one ZarinPal browser callback."""
    payment = get_payment_by_callback_token_hash(_token_hash(callback_token))
    if payment is None:
        return {
            "http_status": 404,
            "state": "not_found",
            "title": "پرداخت پیدا نشد",
            "message": "این لینک پرداخت نامعتبر یا منقضی شده است. لطفاً از داخل ربات یک سفارش جدید بسازید.",
        }

    stored_authority = str(payment.get("authority") or "")
    incoming_authority = str(authority or "").strip()
    if not stored_authority or not incoming_authority or not hmac.compare_digest(
        stored_authority,
        incoming_authority,
    ):
        return {
            "http_status": 400,
            "state": "authority_mismatch",
            "title": "امکان تأیید پرداخت وجود ندارد",
            "message": "اطلاعات تراکنش با سفارش TeacherOS مطابقت ندارد. برای امنیت شما هیچ پلنی فعال نشد.",
        }

    if str(payment.get("status")) == "paid":
        # Re-running the idempotent settlement also repairs a missing subscription row.
        payment = mark_payment_paid(
            payment_id=int(payment["id"]),
            authority=stored_authority,
            ref_id=payment.get("ref_id"),
            card_pan=payment.get("card_pan"),
            card_hash=payment.get("card_hash"),
            provider_code=int(payment.get("provider_code") or 101),
            provider_message=str(payment.get("provider_message") or "Previously verified"),
        )
        return {
            "http_status": 200,
            "state": "paid",
            "title": "پرداخت قبلاً تأیید شده است",
            "message": f"کد پیگیری: {payment.get('ref_id') or 'ثبت شده'}",
            "payment": payment,
        }

    if str(status or "").upper() != "OK":
        updated = mark_payment_cancelled(
            payment_id=int(payment["id"]),
            provider_message="ZarinPal returned Status=NOK",
        )
        notify(
            int(payment["telegram_user_id"]),
            "❌ پرداخت لغو شد یا ناموفق بود.\n\nهیچ پلنی برای شما فعال نشد.",
        )
        return {
            "http_status": 200,
            "state": "cancelled",
            "title": "پرداخت لغو شد",
            "message": "هیچ پرداخت موفقی تأیید نشد. می‌توانید به تلگرام برگردید و دوباره تلاش کنید.",
            "payment": updated or payment,
        }

    try:
        verified = verifier(
            amount=int(payment["amount"]),
            authority=stored_authority,
        )
    except ZarinPalGatewayError as exc:
        record_payment_provider_note(
            payment_id=int(payment["id"]),
            provider_code=exc.code,
            provider_message=str(exc),
        )
        return {
            "http_status": 502,
            "state": "verification_error",
            "title": "تأیید پرداخت هنوز کامل نشده است",
            "message": "TeacherOS هنوز نتوانسته نتیجه را از زرین‌پال تأیید کند. به تلگرام برگردید و وضعیت پرداخت را دوباره بررسی کنید.",
        }
    except Exception as exc:
        logger.exception("Unexpected ZarinPal verification failure")
        record_payment_provider_note(
            payment_id=int(payment["id"]),
            provider_code=None,
            provider_message=str(exc),
        )
        return {
            "http_status": 502,
            "state": "verification_error",
            "title": "تأیید پرداخت هنوز کامل نشده است",
            "message": "TeacherOS هنوز نتوانسته نتیجه را از زرین‌پال تأیید کند. به تلگرام برگردید و وضعیت پرداخت را دوباره بررسی کنید.",
        }

    updated = mark_payment_paid(
        payment_id=int(payment["id"]),
        authority=stored_authority,
        ref_id=verified.get("ref_id"),
        card_pan=verified.get("card_pan"),
        card_hash=verified.get("card_hash"),
        provider_code=int(verified.get("code") or 100),
        provider_message=str(verified.get("message") or "Verified"),
    )

    plan_code = str(updated.get("activated_plan") or updated.get("product_code") or "").lower()
    plan_name = {"pro": "Pro", "premium": "Premium"}.get(plan_code, "TeacherOS")
    expiry = updated.get("subscription_expires_at")
    mode_note = (
        "این یک اشتراک آزمایشی است و هیچ مبلغ واقعی پرداخت نشده است."
        if int(updated.get("is_sandbox") or 0)
        else "اشتراک شما با موفقیت فعال شد."
    )
    plan_lines = ""
    if plan_code:
        plan_lines = f"پلن: {plan_name}\n"
    if expiry:
        plan_lines += f"اعتبار تا: {format_subscription_expiry(expiry)}\n"
    notify(
        int(updated["telegram_user_id"]),
        "✅ پرداخت زرین‌پال با موفقیت تأیید شد\n\n"
        f"مبلغ: {_fa_number(updated['amount'])} تومان\n"
        f"کد پیگیری: {updated.get('ref_id') or 'تأیید شده'}\n"
        f"{plan_lines}\n"
        f"{mode_note}",
    )
    return {
        "http_status": 200,
        "state": "paid",
        "title": "پرداخت با موفقیت تأیید شد",
        "message": f"کد پیگیری: {updated.get('ref_id') or 'تأیید شده'}. اکنون می‌توانید به تلگرام برگردید.",
        "payment": updated,
    }



def process_local_sandbox_action(
    *,
    callback_token: str,
    action: str,
    notify: Callable[[int, str], None] = _notify_telegram,
) -> dict[str, Any]:
    """Settle a TeacherOS-only sandbox order without contacting a real gateway."""
    if not (ZARINPAL_SANDBOX and LOCAL_PAYMENT_SIMULATOR):
        return {
            "http_status": 404,
            "state": "not_found",
            "title": "پرداخت آزمایشی غیرفعال است",
            "message": "صفحه پرداخت آزمایشی محلی فعال نیست.",
        }

    payment = get_payment_by_callback_token_hash(_token_hash(callback_token))
    if payment is None:
        return {
            "http_status": 404,
            "state": "not_found",
            "title": "پرداخت پیدا نشد",
            "message": "این لینک پرداخت آزمایشی نامعتبر یا منقضی شده است.",
        }

    authority = str(payment.get("authority") or "")
    if not int(payment.get("is_sandbox") or 0) or not authority.startswith("LOCAL-SANDBOX-"):
        return {
            "http_status": 400,
            "state": "invalid",
            "title": "سفارش آزمایشی نامعتبر است",
            "message": "این سفارش متعلق به محیط آزمایشی TeacherOS نیست.",
        }

    if str(payment.get("status")) == "paid":
        updated = mark_payment_paid(
            payment_id=int(payment["id"]),
            authority=authority,
            ref_id=payment.get("ref_id") or f"LOCAL-{int(payment['id']):08d}",
            card_pan=payment.get("card_pan"),
            card_hash=payment.get("card_hash"),
            provider_code=int(payment.get("provider_code") or 101),
            provider_message="TeacherOS local sandbox previously verified",
        )
        return {
            "http_status": 200,
            "state": "paid",
            "title": "پرداخت آزمایشی قبلاً انجام شده است",
            "message": "اشتراک آزمایشی شما فعال است. به تلگرام برگردید.",
            "payment": updated,
        }

    normalized_action = str(action or "").strip().lower()
    if normalized_action == "cancel":
        updated = mark_payment_cancelled(
            payment_id=int(payment["id"]),
            provider_message="TeacherOS local sandbox payment cancelled",
        )
        notify(
            int(payment["telegram_user_id"]),
            "❌ پرداخت آزمایشی لغو شد.\n\nهیچ پلنی فعال نشد.",
        )
        return {
            "http_status": 200,
            "state": "cancelled",
            "title": "پرداخت آزمایشی لغو شد",
            "message": "هیچ مبلغی پرداخت نشد و هیچ پلنی فعال نشد.",
            "payment": updated or payment,
        }

    if normalized_action != "success":
        return {
            "http_status": 400,
            "state": "invalid",
            "title": "عملیات نامعتبر است",
            "message": "یکی از گزینه‌های پرداخت موفق یا لغو را انتخاب کنید.",
        }

    updated = mark_payment_paid(
        payment_id=int(payment["id"]),
        authority=authority,
        ref_id=f"LOCAL-{int(payment['id']):08d}",
        card_pan=None,
        card_hash=None,
        provider_code=100,
        provider_message="TeacherOS local sandbox verified",
    )
    plan_code = str(updated.get("activated_plan") or updated.get("product_code") or "").lower()
    plan_name = {"pro": "Pro", "premium": "Premium"}.get(plan_code, "TeacherOS")
    expiry = updated.get("subscription_expires_at")
    expiry_line = f"\nاعتبار تا: {format_subscription_expiry(expiry)}" if expiry else ""
    notify(
        int(updated["telegram_user_id"]),
        "✅ پرداخت آزمایشی با موفقیت تأیید شد\n\n"
        f"پلن: {plan_name}\n"
        f"مبلغ: {_fa_number(updated['amount'])} تومان"
        f"{expiry_line}\n\n"
        "هیچ مبلغ واقعی پرداخت نشد.",
    )
    return {
        "http_status": 200,
        "state": "paid",
        "title": "پرداخت آزمایشی موفق بود",
        "message": "اشتراک آزمایشی فعال شد. به تلگرام برگردید و بخش «پلن من» را باز کنید.",
        "payment": updated,
    }


def _render_local_checkout(payment: dict[str, Any], callback_token: str) -> bytes:
    plan_code = str(payment.get("product_code") or "").lower()
    plan_name = {"pro": "Pro", "premium": "Premium"}.get(plan_code, "TeacherOS")
    safe_token = html.escape(callback_token, quote=True)
    safe_order = html.escape(str(payment.get("order_id") or ""))
    amount = _fa_number(payment.get("amount") or 0)
    days = _fa_number(payment.get("subscription_days") or 0)
    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>پرداخت آزمایشی TeacherOS</title>
  <style>
    * {{ box-sizing:border-box; }}
    body {{ font-family:Tahoma,Arial,sans-serif;background:#f3f5f7;margin:0;padding:24px;color:#17202a; }}
    main {{ max-width:560px;margin:6vh auto;background:#fff;padding:30px;border-radius:18px;
            box-shadow:0 10px 35px rgba(0,0,0,.09); }}
    h1 {{ margin-top:0;font-size:26px; }}
    .badge {{ display:inline-block;background:#fff3cd;color:#714f00;padding:8px 12px;border-radius:999px; }}
    .box {{ background:#f7f9fb;border:1px solid #e3e8ee;border-radius:12px;padding:16px;margin:22px 0;line-height:2; }}
    button {{ width:100%;border:0;border-radius:12px;padding:14px;margin-top:10px;font-size:17px;cursor:pointer; }}
    .success {{ background:#167d3f;color:#fff; }} .cancel {{ background:#e9edf1;color:#26313d; }}
    small {{ display:block;margin-top:22px;color:#687684;line-height:1.8; }}
  </style>
</head>
<body><main>
  <span class="badge">محیط آزمایشی محلی — بدون پرداخت واقعی</span>
  <h1>تأیید پرداخت آزمایشی TeacherOS</h1>
  <div class="box">
    <b>پلن:</b> {html.escape(plan_name)}<br>
    <b>مبلغ نمایشی:</b> {amount:,} تومان<br>
    <b>مدت:</b> {days} روز<br>
    <b>سفارش:</b> {safe_order}
  </div>
  <form method="post" action="/payments/sandbox/checkout/{safe_token}">
    <button class="success" type="submit" name="action" value="success">✅ پرداخت آزمایشی موفق</button>
    <button class="cancel" type="submit" name="action" value="cancel">لغو پرداخت آزمایشی</button>
  </form>
  <small>این صفحه فقط هنگامی فعال است که ZARINPAL_SANDBOX=true و
  TEACHEROS_LOCAL_PAYMENT_SIMULATOR=true باشد. در حالت Live هرگز استفاده نمی‌شود.</small>
</main></body></html>""".encode("utf-8")

def _render_html(title: str, message: str, state: str) -> bytes:
    safe_title = html.escape(title)
    safe_message = html.escape(message)
    symbol = "✅" if state == "paid" else "❌" if state == "cancelled" else "⚠️"
    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    body {{ font-family: Tahoma, Arial, sans-serif; background:#f4f6f8; margin:0; padding:32px; }}
    main {{ max-width:560px; margin:8vh auto; background:#fff; padding:32px; border-radius:16px;
            box-shadow:0 8px 30px rgba(0,0,0,.08); text-align:center; }}
    .symbol {{ font-size:48px; }} h1 {{ margin:16px 0 10px; }} p {{ line-height:1.7; color:#38434f; }}
    small {{ color:#718096; }}
  </style>
</head>
<body><main><div class="symbol">{symbol}</div><h1>{safe_title}</h1><p>{safe_message}</p>
<small>TeacherOS · نتیجه پرداخت زرین‌پال</small></main></body></html>""".encode("utf-8")


class PaymentCallbackHandler(BaseHTTPRequestHandler):
    server_version = "TeacherOSPayment/1.0"

    def log_message(self, format: str, *args: object) -> None:
        # BaseHTTPRequestHandler normally logs the full path, which contains our secret callback token.
        logger.info("Payment callback HTTP request completed")

    def _send(self, status_code: int, body: bytes, content_type: str) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(200, b"TeacherOS payment callback is running", "text/plain; charset=utf-8")
            return

        local_match = _LOCAL_CHECKOUT_PATTERN.fullmatch(parsed.path)
        if local_match is not None:
            payment = get_payment_by_callback_token_hash(_token_hash(local_match.group(1)))
            if (
                payment is None
                or not ZARINPAL_SANDBOX
                or not LOCAL_PAYMENT_SIMULATOR
                or not int(payment.get("is_sandbox") or 0)
                or not str(payment.get("authority") or "").startswith("LOCAL-SANDBOX-")
            ):
                self._send(404, b"Not found", "text/plain; charset=utf-8")
                return
            if str(payment.get("status")) == "paid":
                body = _render_html(
                    "پرداخت آزمایشی قبلاً انجام شده است",
                    "اشتراک آزمایشی فعال است. به تلگرام برگردید.",
                    "paid",
                )
            elif str(payment.get("status")) == "cancelled":
                body = _render_html(
                    "پرداخت آزمایشی لغو شد",
                    "برای تلاش دوباره، از داخل تلگرام یک سفارش جدید بسازید.",
                    "cancelled",
                )
            else:
                body = _render_local_checkout(payment, local_match.group(1))
            self._send(200, body, "text/html; charset=utf-8")
            return

        match = _CALLBACK_PATTERN.fullmatch(parsed.path)
        if match is None:
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return

        query = parse_qs(parsed.query)
        authority = (query.get("Authority") or query.get("authority") or [""])[0]
        status = (query.get("Status") or query.get("status") or [""])[0]
        result = process_zarinpal_callback(
            callback_token=match.group(1),
            authority=authority,
            status=status,
        )
        body = _render_html(
            str(result["title"]),
            str(result["message"]),
            str(result["state"]),
        )
        self._send(int(result["http_status"]), body, "text/html; charset=utf-8")


    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        match = _LOCAL_CHECKOUT_PATTERN.fullmatch(parsed.path)
        if match is None:
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return

        try:
            content_length = min(int(self.headers.get("Content-Length", "0")), 4096)
        except ValueError:
            content_length = 0
        form = parse_qs(self.rfile.read(content_length).decode("utf-8", errors="replace"))
        action = (form.get("action") or [""])[0]
        result = process_local_sandbox_action(
            callback_token=match.group(1),
            action=action,
        )
        body = _render_html(
            str(result["title"]),
            str(result["message"]),
            str(result["state"]),
        )
        self._send(int(result["http_status"]), body, "text/html; charset=utf-8")


class _ReusableThreadingHTTPServer(ThreadingHTTPServer):
    """Allow clean bot restarts without leaving the callback port stuck."""

    allow_reuse_address = True
    daemon_threads = True


class PaymentCallbackServer:
    def __init__(self) -> None:
        self._server = _ReusableThreadingHTTPServer(
            (PAYMENT_SERVER_HOST, PAYMENT_SERVER_PORT),
            PaymentCallbackHandler,
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="teacheros-payment-callback",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()
        logger.info(
            "Payment callback server listening on %s:%s",
            PAYMENT_SERVER_HOST,
            PAYMENT_SERVER_PORT,
        )

    def stop(self) -> None:
        if self._thread.is_alive():
            self._server.shutdown()
            self._thread.join(timeout=5)
        self._server.server_close()


def start_payment_callback_server() -> PaymentCallbackServer:
    server = PaymentCallbackServer()
    server.start()
    return server
