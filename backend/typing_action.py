from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from telegram.constants import ChatAction


@asynccontextmanager
async def typing_heartbeat(
    bot: Any,
    chat_id: int | None,
    *,
    interval: float = 4.0,
) -> AsyncIterator[None]:
    """Maintain Telegram 'typing...' action continuously during async operations."""
    if chat_id is None or bot is None:
        yield
        return

    task: asyncio.Task[None] | None = None

    async def _loop() -> None:
        while True:
            try:
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except Exception:
                pass
            await asyncio.sleep(interval)

    try:
        task = asyncio.create_task(_loop())
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
