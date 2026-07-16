from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ----------------------------------
# PASTE YOUR BOT TOKEN HERE
# ----------------------------------
TOKEN = "8869929482:AAF0PDICbAcSe5ohnyZgexcX8VBzJxWfck4"


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to TeacherOS!\n\n"
        "This is the first version of your AI assistant for English teachers.\n\n"
        "Available commands:\n"
        "/start\n"
        "/help"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 TeacherOS Help\n\n"
        "/start - Start the bot\n"
        "/help - Show help information"
    )


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))

    print("TeacherOS Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()