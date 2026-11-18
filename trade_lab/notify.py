"""Telegram delivery with explicit handling of uncertain outcomes."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class NotifyError(RuntimeError):
    """Telegram delivery error.

    delivery_uncertain is true when the request may have reached Telegram
    even though the client did not receive a trustworthy success response.
    Such a result must not be retried automatically.
    """

    def __init__(self, message: str, *, delivery_uncertain: bool = False) -> None:
        super().__init__(message)
        self.delivery_uncertain = delivery_uncertain


def send_telegram(token: str, chat_id: str, text: str, timeout: float = 10.0) -> None:
    """Send a plain-text message without leaking the bot token."""
    if not token or not chat_id:
        raise NotifyError("BOT_TOKEN and CHAT_ID must both be set")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    ).encode("utf-8")
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        # Server errors and timeout-like HTTP responses may follow partial
        # remote processing. Treat them as uncertain; ordinary 4xx is rejection.
        uncertain = exc.code >= 500 or exc.code in {408, 425}
        raise NotifyError(
            f"Telegram returned HTTP {exc.code}",
            delivery_uncertain=uncertain,
        ) from None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        # The connection may have failed after Telegram accepted the message.
        raise NotifyError(
            f"Telegram request outcome is uncertain: {type(exc).__name__}",
            delivery_uncertain=True,
        ) from None

    if not isinstance(body, dict):
        raise NotifyError("Telegram returned an invalid response", delivery_uncertain=True)
    if not body.get("ok"):
        raise NotifyError("Telegram rejected the message")
