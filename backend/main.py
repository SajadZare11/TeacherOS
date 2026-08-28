from __future__ import annotations

import logging

from telegram import BotCommand, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from account_panel import account_callback
from class_panel import class_callback, home_callback
from class_dashboard_panel import get_class_dashboard_text
from class_setup_panel import get_class_setup_text
from feedback_panel import feedback_callback, feedback_command, get_feedback_text
from activity_generator import activity_callback, get_activity_topic
from admin_panel import (
    admin_callback,
    admin_command,
    admin_feedback_command,
    admin_grant_command,
    admin_plans_command,
    admin_revenue_command,
    admin_revoke_command,
    admin_stats_command,
    admin_users_command,
    myid_command,
)
from config import (
    TELEGRAM_BOT_TOKEN,
    admin_setting_problem,
    is_admin_telegram_user,
    validate_settings,
)
from database import (
    get_user_entitlement,
    initialize_database,
    record_general_generation,
    register_telegram_user,
)
from keyboards import start_menu_keyboard, subscription_limit_keyboard
from home_ui import teacheros_home_text
from lesson_planner import get_lesson_topic, lesson_callback
from launch_info import (
    about_command,
    launch_info_callback,
    privacy_command,
    terms_command,
)
from library_search import get_search_query, search_callback, search_command
from openrouter_client import generate_text
from prompt_loader import load_system_prompt, validate_prompt_files
from pdf_export import pdf_export_callback
from payment_panel import payment_callback, payments_command, upgrade_command
from payment_server import start_payment_callback_server
from quiz_generator import get_quiz_topic, quiz_callback
from teacher_library import library_callback, library_command
from usage_tracking import usage_callback, usage_command
from worksheet_generator import get_worksheet_topic, worksheet_callback
from word_export import word_export_callback
from subscription_service import (
    generation_access_for_user,
    generation_block_message,
    selected_openrouter_model,
)

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

    if update.effective_user is not None:
        try:
            register_telegram_user(update.effective_user)
        except Exception:
            logger.exception("Could not register Telegram user in the database")

    plan_line = "Plan: Free"
    if update.effective_user is not None and isinstance(getattr(update.effective_user, "id", None), int):
        try:
            entitlement = get_user_entitlement(telegram_user_id=update.effective_user.id)
            plan_line = f"Plan: {entitlement['plan_name']}"
            if entitlement.get("remaining") is not None:
                plan_line += f" · {entitlement['remaining']} generations left today"
        except Exception:
            logger.exception("Could not load plan for start menu")

    await update.message.reply_text(
        teacheros_home_text(plan_line),
        reply_markup=start_menu_keyboard(
            show_admin=is_admin_telegram_user(
                getattr(update.effective_user, "id", None)
            )
        ),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    await update.message.reply_text(
        "📚 TeacherOS Help\n\n"
        "Use /start to open the main menu.\n"
        "Use /library to browse your saved materials.\n"
        "Use /search to find saved materials by topic, title, level, or content.\n"
        "Use /usage to view your generation and export totals.\n"
        "برای مشاهده پلن و خرید اشتراک از /plan یا /upgrade استفاده کنید.\n"
        "برای مشاهده سوابق پرداخت خصوصی خود از /payments استفاده کنید.\n"
        "Use /feedback to send a fast rating.\n"
        "Use /about to learn what TeacherOS does.\n"
        "Use /privacy and /terms to read the launch policies.\n"
        "Use /myid to view your Telegram user ID.\n"
        "Use /cancel to stop the current lesson, activity, worksheet, or assessment flow.\n"
        "Every completed generation is saved automatically."
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    if update.message is not None:
        await update.message.reply_text(
            "❌ Current operation cancelled.",
            reply_markup=start_menu_keyboard(),
        )


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    await query.answer()
    context.user_data.clear()
    await query.edit_message_text(
        "⚠️ That old menu option is no longer available. Choose an option below.",
        reply_markup=start_menu_keyboard(),
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    lesson = context.user_data.get("lesson")
    activity = context.user_data.get("activity")
    worksheet = context.user_data.get("worksheet")
    quiz = context.user_data.get("quiz")
    library_search = context.user_data.get("library_search")
    feedback = context.user_data.get("feedback")
    class_setup = context.user_data.get("class_setup")
    class_edit = context.user_data.get("class_edit")

    # A feature-specific text handler will process the message first.
    if isinstance(lesson, dict) and lesson.get("state"):
        return
    if isinstance(activity, dict) and activity.get("state"):
        return
    if isinstance(worksheet, dict) and worksheet.get("state"):
        return
    if isinstance(quiz, dict) and quiz.get("state"):
        return
    if isinstance(library_search, dict) and library_search.get("state"):
        return
    if isinstance(feedback, dict) and feedback.get("state"):
        return
    if isinstance(class_setup, dict) and class_setup.get("state"):
        return
    if isinstance(class_edit, dict) and class_edit.get("state"):
        return

    user_message = (update.message.text or "").strip()
    if not user_message:
        return

    user = update.effective_user
    if user is None or not isinstance(getattr(user, "id", None), int):
        return
    access = generation_access_for_user(user.id)
    if not bool(access.get("allowed")):
        await update.message.reply_text(
            generation_block_message(access),
            reply_markup=subscription_limit_keyboard(),
        )
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
            ],
            model=selected_openrouter_model(access),
        )
    except Exception:
        logger.exception("General TeacherOS chat request failed")
        await update.message.reply_text(
            "❌ I could not contact OpenRouter.\n\n"
            "Check your internet connection, .env file, API key, and selected model."
        )
        return

    try:
        record_general_generation(
            telegram_user=user,
            metadata={"surface": "general_chat"},
        )
    except Exception:
        logger.exception("AI response succeeded but usage could not be recorded")

    for start in range(0, len(ai_response), 4000):
        await update.message.reply_text(ai_response[start : start + 4000])


async def post_init(application: Application) -> None:
    """Publish the Telegram command menu and public bot description."""
    commands = [
        BotCommand("start", "Open the TeacherOS main menu"),
        BotCommand("help", "Show help and available commands"),
        BotCommand("library", "Browse saved teaching materials"),
        BotCommand("search", "Search your private library"),
        BotCommand("usage", "View generations and exports"),
        BotCommand("plan", "مشاهده پلن و خرید اشتراک"),
        BotCommand("feedback", "Rate TeacherOS quickly"),
        BotCommand("about", "About TeacherOS"),
        BotCommand("privacy", "Read the privacy notice"),
        BotCommand("terms", "Read the terms of use"),
        BotCommand("cancel", "Cancel the current creation flow"),
    ]
    try:
        await application.bot.set_my_commands(commands)
        await application.bot.set_my_short_description(
            "AI lesson-creation workspace for English teachers."
        )
        await application.bot.set_my_description(
            "Create lesson plans, activities, worksheets, and assessments. "
            "Save, search, and export everything from Telegram."
        )
    except Exception:
        logger.warning("Could not update Telegram command menu or bot description")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled Telegram bot error", exc_info=context.error)

    if isinstance(update, Update) and update.effective_message is not None:
        try:
            await update.effective_message.reply_text(
                "❌ Something unexpected happened. Choose an option below and try again.",
                reply_markup=start_menu_keyboard(),
            )
        except Exception:
            logger.exception("Could not send the fallback error message")


def main() -> None:
    validate_settings()
    validate_prompt_files()
    database_path = initialize_database()

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .concurrent_updates(False)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("library", library_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("usage", usage_command))
    app.add_handler(CommandHandler("upgrade", upgrade_command))
    app.add_handler(CommandHandler("plan", upgrade_command))
    app.add_handler(CommandHandler("payments", payments_command))
    app.add_handler(CommandHandler("feedback", feedback_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("terms", terms_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("admin_users", admin_users_command))
    app.add_handler(CommandHandler("admin_stats", admin_stats_command))
    app.add_handler(CommandHandler("admin_revenue", admin_revenue_command))
    app.add_handler(CommandHandler("admin_plans", admin_plans_command))
    app.add_handler(CommandHandler("admin_feedback", admin_feedback_command))
    app.add_handler(CommandHandler("admin_grant", admin_grant_command))
    app.add_handler(CommandHandler("admin_revoke", admin_revoke_command))

    app.add_handler(CallbackQueryHandler(lesson_callback, pattern=r"^lesson(?:$|_)"))
    app.add_handler(CallbackQueryHandler(activity_callback, pattern=r"^activity_"))
    app.add_handler(CallbackQueryHandler(worksheet_callback, pattern=r"^worksheet_"))
    app.add_handler(CallbackQueryHandler(quiz_callback, pattern=r"^quiz_"))
    app.add_handler(CallbackQueryHandler(library_callback, pattern=r"^library_"))
    app.add_handler(CallbackQueryHandler(search_callback, pattern=r"^search_"))
    app.add_handler(CallbackQueryHandler(usage_callback, pattern=r"^usage_"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^admin_"))
    app.add_handler(CallbackQueryHandler(account_callback, pattern=r"^account_"))
    app.add_handler(CallbackQueryHandler(feedback_callback, pattern=r"^feedback_"))
    app.add_handler(CallbackQueryHandler(launch_info_callback, pattern=r"^info_"))
    app.add_handler(CallbackQueryHandler(payment_callback, pattern=r"^(?:payment_|plan_)"))
    app.add_handler(CallbackQueryHandler(word_export_callback, pattern=r"^export_"))
    app.add_handler(CallbackQueryHandler(pdf_export_callback, pattern=r"^pdf_"))
    app.add_handler(CallbackQueryHandler(home_callback, pattern=r"^home_"))
    app.add_handler(
        CallbackQueryHandler(class_callback, pattern=r"^v1\|(?:cl|rc)\|")
    )
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu_"))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, get_class_dashboard_text),
        group=0,
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, get_class_setup_text),
        group=1,
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, get_search_query),
        group=2,
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, get_lesson_topic),
        group=3,
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, get_activity_topic),
        group=4,
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, get_worksheet_topic),
        group=5,
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, get_quiz_topic),
        group=6,
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, get_feedback_text),
        group=7,
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
        group=8,
    )

    app.add_error_handler(error_handler)

    try:
        payment_server = start_payment_callback_server()
    except OSError as exc:
        raise RuntimeError(
            "TeacherOS could not start the payment callback server on "
            f"{exc}. Close any older TeacherOS process, or change PAYMENT_SERVER_PORT in .env."
        ) from exc

    print(f"TeacherOS database ready: {database_path}")
    admin_problem = admin_setting_problem()
    if admin_problem:
        print(f"TeacherOS admin panel locked: {admin_problem}")
    else:
        print("TeacherOS admin owner configured")
    print("TeacherOS payment callback server is running")
    print("TeacherOS Bot is running...")
    try:
        app.run_polling(drop_pending_updates=True)
    finally:
        payment_server.stop()


if __name__ == "__main__":
    main()
