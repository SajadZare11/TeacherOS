######

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

from keyboards import (
    level_keyboard,
    grammar_keyboard,
    duration_keyboard,
    confirm_keyboard,
    activity_type_keyboard,
)

from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from pathlib import Path
from openai import OpenAI
from telegram import Update

################
MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
###############

def load_lesson_prompt():

    base_path = Path(__file__).resolve().parent.parent

    prompt_path = (
        base_path
        / "prompts"
        / "lesson_planner.txt"
    )

    with open(prompt_path, "r", encoding="utf-8") as file:
        return file.read()

LESSON_PROMPT = load_lesson_prompt()
# OpenRouter client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

async def lesson_callback(update, context):

    query = update.callback_query
    from telegram.error import TimedOut, NetworkError

    try:
        await query.answer()
    except (TimedOut, NetworkError):
        pass

    data = query.data

    if data == "library":
        await query.edit_message_text(
            "📚 Your TeacherOS Library\n\n"
            "Your saved resources will appear here."
        )

        return

    if data == "settings":
        await query.edit_message_text(
            "⚙️ TeacherOS Settings\n\n"
            "Settings panel."
        )

        return

    if data == "about":
        await query.edit_message_text(
            "ℹ️ TeacherOS\n\n"
            "Created by @SajadZare11.\n\n"
            "AI assistant for English teachers."
        )

        return

    # ---------- Lesson Planner ----------
    if data == "lesson":
        context.user_data.clear()
        context.user_data["lesson"] = {}

        await query.edit_message_text(

            text=(
                "📚 Lesson Planner\n\n"
                "Step 1 of 5\n\n"
                "Choose your CEFR level."
            ),

            reply_markup=level_keyboard(),

        )

        return

    # ---------- Level ----------
    if data.startswith("level_"):
        level = data.replace("level_", "")

        context.user_data["lesson"]["level"] = level
        context.user_data["lesson"]["waiting_topic"] = True
        context.user_data["lesson"]["state"] = "topic"

        await query.edit_message_text(

            text=(
                "📚 Lesson Planner\n\n"
                "Step 2 of 5\n\n"
                "✏️ Type today's lesson topic."
                "Example:\n Travel\n  Food\n  Technology\n  Shopping\n  Health\n"
            )

        )

        return
    # ---------- Grammar ----------
    if data.startswith("grammar_"):
        grammar = data.replace("grammar_", "")

        context.user_data["lesson"]["grammar"] = grammar

        context.user_data["lesson"]["state"] = "duration"

        await query.edit_message_text(

            text=(

                "📚 Lesson Planner\n\n"

                "Step 4 of 5\n\n"

                "Choose the lesson duration."

            ),

            reply_markup=duration_keyboard()

        )

        return

    # ---------- Duration ----------
    if data.startswith("duration_"):
        duration = data.replace("duration_", "")

        context.user_data["lesson"]["duration"] = duration

        context.user_data["lesson"]["state"] = "confirm"

        lesson = context.user_data["lesson"]

        summary = (
            "📚 Lesson Planner\n\n"
            "Step 5 of 5\n\n"
            "Please review your lesson.\n\n"
            f"📖 Level: {lesson['level']}\n"
            f"📝 Topic: {lesson['topic']}\n"
            f"📚 Grammar: {lesson['grammar']}\n"
            f"⏰ Duration: {lesson['duration']} minutes"
        )

        await query.edit_message_text(

            text=summary,

            reply_markup=confirm_keyboard()

        )

        return
    # ---------- Cancel ----------
    if data == "cancel":
        context.user_data.clear()

        await query.edit_message_text(

            "❌ Lesson Planner cancelled."

        )

        return
    # ---------- Generate ----------
    if data == "generate":
        await generate_lesson(update, context)

        return

    ##########

    await query.edit_message_text(
        text=(
            "📚 Lesson Planner\n\n"
            "Step 1 of 5\n\n"
            "Choose your CEFR level."
        ),
        reply_markup=level_keyboard()
    )

async def generate_lesson(update, context):
    lesson = context.user_data["lesson"]
    query = update.callback_query

    await query.edit_message_text(
        "🧠 Generating your activity......\n\n"
        "This usually takes 10–20 seconds.\n\n"
        "Please don't close Telegram."
    )

    prompt = LESSON_PROMPT
    prompt = (
        prompt
        .replace("{{level}}", lesson["level"])
        .replace("{{topic}}", lesson["topic"])
        .replace("{{grammar}}", lesson["grammar"])
        .replace("{{duration}}", lesson["duration"])
        .replace("{{vocabulary}}", "")
        .replace("{{goals}}", "")
    )
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

    except Exception as e:

        await query.edit_message_text(

            f"❌ Failed to generate lesson.\n\n{e}"

        )

        return

    if not response.choices:
        await query.edit_message_text(
            "Sorry, I couldn't generate the lesson. Contact us if the problem persists.! "
        )
        return

    lesson = response.choices[0].message.content

    max_length = 4000

    for i in range(0, len(lesson), max_length):

        await query.message.reply_text(
            lesson[i:i + max_length]
        )
    context.user_data.clear()

async def get_topic(update, context):

    if "lesson" not in context.user_data:
        return

    if context.user_data["lesson"].get("waiting_topic") != True:
        return


    context.user_data["lesson"]["topic"] = update.message.text

    context.user_data["lesson"]["waiting_topic"] = False


    context.user_data["lesson"]["state"] = "grammar"


    await update.message.reply_text(

        "📚 Lesson Planner\n\n"
        "Step 3 of 5\n\n"
        "Choose the grammar focus.",

        reply_markup=grammar_keyboard()

    )