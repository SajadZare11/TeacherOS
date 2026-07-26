import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

from keyboards import (
    activity_type_keyboard,
    activity_confirm_keyboard,
    level_keyboard,
)

load_dotenv()

################
MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
###############

ACTIVITY_TYPE, LEVEL, TOPIC = range(3)
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

def load_activity_prompt():

    base_path = Path(__file__).resolve().parent.parent

    prompt_path = (
        base_path
        / "prompts"
        / "activity_generator.txt"
    )

    with open(prompt_path, "r", encoding="utf-8") as file:
        return file.read()


async def start_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data["activity"] = {}
    await query.edit_message_text(

        text=(
            "🎲 Activity Generator\n\n"
            "Step 1 of 4\n\n"
            "Choose an activity type."
        ),

        reply_markup=activity_type_keyboard()

    )

    return ACTIVITY_TYPE

async def activity_type_selected(update, context):

    query = update.callback_query

    await query.answer()

    activity = query.data.replace("activity_", "")

    context.user_data["activity"]["type"] = activity

    await query.edit_message_text(

        text=(
            "🎲 Activity Generator\n\n"
            "Step 2 of 4\n\n"
            "Choose the CEFR level."
        ),

        reply_markup=level_keyboard()

    )

    return LEVEL

async def activity_level_selected(update, context):

    query = update.callback_query

    await query.answer()

    level = query.data.replace("level_", "")

    context.user_data["activity"]["level"] = level

    await query.edit_message_text(

        text=(
            "🎲 Activity Generator\n\n"
            "Step 3 of 4\n\n"
            "Type the lesson topic."
        )

    )

    return TOPIC

async def activity_topic(update, context):

    activity = context.user_data.get("activity")

    if not activity:
        return


    activity["topic"] = update.message.text


    summary = (

        "🎲 Activity Generator\n\n"

        "Step 4 of 4\n\n"

        f"🎯 Type: {activity['type']}\n"
        f"📖 Level: {activity['level']}\n"
        f"📝 Topic: {activity['topic']}\n\n"

        "Ready to generate?"

    )


    await update.message.reply_text(

        summary,

        reply_markup=activity_confirm_keyboard()

    )


    return ConversationHandler.WAITING

async def generate_activity(update, context):

    query = update.callback_query
    activity = context.user_data["activity"]
    await query.answer()

    await query.edit_message_text(
        "🧠 Generating your lesson plan...\n\n"
        "This usually takes 10–20 seconds.\n\n"
        "Please don't close Telegram."
    )

    prompt = load_activity_prompt()

    prompt = (
        prompt

        .replace("{{activity}}", activity["type"])
        .replace("{{level}}", activity["level"])
        .replace("{{topic}}", activity["topic"])
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


    if (
            response is None
            or not response.choices
            or response.choices[0].message.content is None
    ):
        await query.message.reply_text(
            "Sorry, I could not generate the activity. Please try again."
        )
        return

    activity = response.choices[0].message.content

    max_length = 4000

    for i in range(0, len(activity), max_length):

        await query.message.reply_text(
            activity[i:i + max_length]
        )

    context.user_data.clear()

    return ConversationHandler.END

async def cancel(update, context):

    context.user_data.clear()

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "❌ Activity cancelled."
        )
    else:
        await update.message.reply_text(
            "❌ Activity cancelled."
        )

    return ConversationHandler.END

activity_handler = ConversationHandler(

    entry_points=[
        CallbackQueryHandler(
            start_activity,
            pattern="^activities$",
        ),
    ],

    states={

        ACTIVITY_TYPE: [
            CallbackQueryHandler(
                activity_type_selected,
                pattern="^activity_",
            )
        ],

        LEVEL: [
            CallbackQueryHandler(
                activity_level_selected,
                pattern="^level_",
            )
        ],

        TOPIC: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                activity_topic
            )
        ],

        ConversationHandler.WAITING: [

            CallbackQueryHandler(
                generate_activity,
                pattern="^generate_activity$",
            ),

            CallbackQueryHandler(
                cancel,
                pattern="^cancel_activity$",
            ),

        ],

    },

    fallbacks=[
        CommandHandler(
            "cancel",
            cancel,
        )
    ],

)
