from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import ZARINPAL_MERCHANT_ID, ZARINPAL_SANDBOX


@dataclass(slots=True)
class ZarinPalGatewayError(RuntimeError):
    message: str
    code: int | None = None

    def __str__(self) -> str:
        return f"{self.message} (code {self.code})" if self.code is not None else self.message


def _api_origin() -> str:
    return "https://sandbox.zarinpal.com" if ZARINPAL_SANDBOX else "https://payment.zarinpal.com"


def _post_json(path: str, payload: dict[str, Any], *, timeout: int = 25) -> dict[str, Any]:
    request = Request(
        f"{_api_origin()}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "TeacherOS/1.0",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            raise ZarinPalGatewayError(
                f"ZarinPal returned HTTP {exc.code}",
                exc.code,
            ) from exc
        code, message = _extract_error(parsed)
        raise ZarinPalGatewayError(message or f"ZarinPal returned HTTP {exc.code}", code) from exc
    except URLError as exc:
        raise ZarinPalGatewayError(f"Could not connect to ZarinPal: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ZarinPalGatewayError("ZarinPal request timed out") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ZarinPalGatewayError("ZarinPal returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise ZarinPalGatewayError("ZarinPal returned an unexpected response")
    return parsed


def _extract_error(payload: dict[str, Any]) -> tuple[int | None, str]:
    errors = payload.get("errors")
    if isinstance(errors, dict):
        code = errors.get("code")
        message = errors.get("message")
        return _as_int(code), str(message or "ZarinPal rejected the request")
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            return _as_int(first.get("code")), str(first.get("message") or "ZarinPal rejected the request")
        return None, str(first)
    data = payload.get("data")
    if isinstance(data, dict):
        return _as_int(data.get("code")), str(data.get("message") or "ZarinPal rejected the request")
    return None, "ZarinPal rejected the request"


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def create_zarinpal_payment(
    *,
    amount: int,
    currency: str,
    description: str,
    callback_url: str,
    order_id: str,
) -> dict[str, Any]:
    """Create a ZarinPal payment request and return authority plus payment URL."""
    payload = {
        "merchant_id": ZARINPAL_MERCHANT_ID,
        "amount": amount,
        "currency": currency,
        "description": description[:500],
        "callback_url": callback_url,
        "metadata": {"order_id": order_id},
    }
    response = _post_json("/pg/v4/payment/request.json", payload)
    data = response.get("data")
    if not isinstance(data, dict):
        code, message = _extract_error(response)
        raise ZarinPalGatewayError(message, code)

    code = _as_int(data.get("code"))
    authority = str(data.get("authority") or "").strip()
    if code != 100 or not authority:
        error_code, message = _extract_error(response)
        raise ZarinPalGatewayError(message, error_code if error_code is not None else code)

    return {
        "code": code,
        "message": str(data.get("message") or "Success"),
        "authority": authority,
        "payment_url": f"{_api_origin()}/pg/StartPay/{authority}",
        "fee": _as_int(data.get("fee")),
        "fee_type": str(data.get("fee_type") or ""),
    }


def verify_zarinpal_payment(
    *,
    amount: int,
    authority: str,
) -> dict[str, Any]:
    """Verify a returned transaction server-to-server with the stored amount."""
    response = _post_json(
        "/pg/v4/payment/verify.json",
        {
            "merchant_id": ZARINPAL_MERCHANT_ID,
            "amount": amount,
            "authority": authority,
        },
    )
    data = response.get("data")
    if not isinstance(data, dict):
        code, message = _extract_error(response)
        raise ZarinPalGatewayError(message, code)

    code = _as_int(data.get("code"))
    if code not in {100, 101}:
        error_code, message = _extract_error(response)
        raise ZarinPalGatewayError(message, error_code if error_code is not None else code)

    return {
        "code": code,
        "message": str(data.get("message") or "Verified"),
        "ref_id": data.get("ref_id"),
        "card_pan": data.get("card_pan"),
        "card_hash": data.get("card_hash"),
        "fee": _as_int(data.get("fee")),
        "fee_type": str(data.get("fee_type") or ""),
    }
