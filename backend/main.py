import os

from dotenv import load_dotenv
from openai import OpenAI

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
def load_system_prompt():
    with open("../prompts/teacheros_system_prompt.txt", "r", encoding="utf-8") as file:
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
    await update.message.reply_text(
        "👋 Welcome to TeacherOS!\n\n"
        "Send me a message and I will generate a response using AI."
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

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b:free",
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

    # Catch all text messages
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    print("TeacherOS Bot is running...")

    app.run_polling()

# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    main()

