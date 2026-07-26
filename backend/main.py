from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from activity_generator import activity_callback, get_activity_topic
from config import TELEGRAM_BOT_TOKEN, validate_settings
from keyboards import start_menu_keyboard
from lesson_planner import get_lesson_topic, lesson_callback
from openrouter_client import generate_text
from prompt_loader import load_system_prompt, validate_prompt_files
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

# Prevent HTTP request URLs and secret tokens from appearing in the terminal.
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    if update.message is None:
        return

    await update.message.reply_text(
        "👋 Welcome to TeacherOS\n\n"
        "Your AI assistant for English teachers.\n\n"
        "Choose what you'd like to create today.",
        reply_markup=start_menu_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    await update.message.reply_text(
        "📚 TeacherOS Help\n\n"
        "Use /start to open the menu.\n"
        "Use /cancel to stop the current lesson or activity flow."
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    if update.message is not None:
        await update.message.reply_text("❌ Current operation cancelled. Send /start to begin again.")


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    await query.answer()
    context.user_data.clear()
    messages = {
        "menu_worksheets": "📝 Worksheet Generator is not connected yet.",
        "menu_assessments": "✅ Assessment Generator is not connected yet.",
        "menu_library": "📁 Your TeacherOS Library will appear here after the database step.",
        "menu_account": "👤 Account settings are not connected yet.",
    }
    message = messages.get(query.data or "", "This menu option is not available yet.")
    await query.edit_message_text(f"{message}\n\nSend /start to return to the main menu.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    lesson = context.user_data.get("lesson")
    activity = context.user_data.get("activity")

    # A feature-specific text handler will process the message first.
    if isinstance(lesson, dict) and lesson.get("state"):
        return
    if isinstance(activity, dict) and activity.get("state"):
        return

    user_message = (update.message.text or "").strip()
    if not user_message:
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING,
    )

    try:
        ai_response = await generate_text(
            [
                {"role": "system", "content": load_system_prompt()},
                {"role": "user", "content": user_message},
            ]
        )
    except Exception:
        logger.exception("General TeacherOS chat request failed")
        await update.message.reply_text(
            "❌ I could not contact OpenRouter.\n\n"
            "Check your internet connection, .env file, API key, and selected model."
        )
        return

    for start in range(0, len(ai_response), 4000):
        await update.message.reply_text(ai_response[start : start + 4000])


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled Telegram bot error", exc_info=context.error)

    if isinstance(update, Update) and update.effective_message is not None:
        try:
            await update.effective_message.reply_text(
                "❌ Something unexpected happened. Send /start and try again."
            )
        except Exception:
            logger.exception("Could not send the fallback error message")


def main() -> None:
    validate_settings()
    validate_prompt_files()

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .concurrent_updates(False)
        .build()
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel_command))

    app.add_handler(CallbackQueryHandler(lesson_callback, pattern=r"^lesson(?:$|_)"))
    app.add_handler(CallbackQueryHandler(activity_callback, pattern=r"^activity_"))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu_"))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, get_lesson_topic),
        group=1,
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, get_activity_topic),
        group=2,
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
        group=3,
    )

    app.add_error_handler(error_handler)

    print("TeacherOS Bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

