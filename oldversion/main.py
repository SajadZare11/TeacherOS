##
import os
from lesson_planner import (
    lesson_callback,
    get_topic,
)
from activity_generator import activity_handler
from dotenv import load_dotenv
from openai import OpenAI
from telegram.constants import ChatAction
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from keyboards import (
    level_keyboard,
    activity_confirm_keyboard,
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from pathlib import Path

def load_system_prompt():

    base_path = Path(__file__).resolve().parent.parent

    prompt_path = (
        base_path
        / "prompts"
        / "teacheros_system_prompt.txt"
    )

    with open(prompt_path, "r", encoding="utf-8") as file:
        return file.read()


# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# -----------------------------
# OpenRouter Client
# -----------------------------
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# -----------------------------
# /start
# -----------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        [
            InlineKeyboardButton(
                "📚 Lesson Planner",
                callback_data="lesson"
            ),
            InlineKeyboardButton(
                "🎲 Activities",
                callback_data="activities"
            ),
        ],
        [
            InlineKeyboardButton(
                "📝 Worksheets",
                callback_data="worksheets"
            ),
            InlineKeyboardButton(
                "✅ Assessments",
                callback_data="assessments"
            ),
        ],
        [
            InlineKeyboardButton(
                "📁 Library",
                callback_data="library"
            ),
            InlineKeyboardButton(
                "👤 Account",
                callback_data="account"
            ),
        ],
    ]

    await update.message.reply_text(
        "👋 *Welcome to TeacherOS*\n\n"
        "Your AI assistant for English teachers.\n\n"
        "Choose what you'd like to create today.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )

# -----------------------------
# /help
# -----------------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 TeacherOS Help\n\n"
        "Just send any message and I will reply using OpenRouter."
    )

# -----------------------------
# Handle user messages
# -----------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_message = update.message.text
    # User is inside the Lesson Planner
    lesson = context.user_data.get("lesson")

    if lesson and lesson.get("state"):
        return
    
    # -----------------------------
    # Ignore messages that belong to Activity Generator
    # -----------------------------
    if "activity" in context.user_data:
        return

    try:

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING
        )

        response = client.chat.completions.create(
            model="nvidia/nemotron-3-super-120b-a12b:free",
            messages=[
                {
                    "role": "system",
                    "content": load_system_prompt()
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        )

        ai_response = response.choices[0].message.content

        # Telegram has a 4096 character limit
        max_length = 4000

        for i in range(0, len(ai_response), max_length):
            await update.message.reply_text(
                ai_response[i:i + max_length]
            )

    except Exception as e:
        await update.message.reply_text(
            f"❌ Error:\n{str(e)}"
        )
# -----------------------------
# Main
# -----------------------------
def main():

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(activity_handler)
    app.add_handler(
        CallbackQueryHandler(
            lesson_callback,
            pattern="^(lesson|level_|grammar_|duration_|generate|cancel).*$"
        )
    )

    # Then the normal chat handler
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            get_topic
        ),
        group=1
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ),
        group=2
    )


    print("TeacherOS Bot is running...")

    app.run_polling()

# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    main()

