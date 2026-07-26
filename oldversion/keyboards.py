from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import ReplyKeyboardMarkup

from telegram import ReplyKeyboardMarkup

def home_keyboard():

    keyboard = [
        ["🚀 Start here"], #this should act as /start command and lead to keyboard start command
        ["📁 Library", "⚙ Settings"],
        ["ℹ About TeacherOS"]
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        is_persistent=True
    )


def main_menu_keyboard():

    keyboard = [
        ["📚 Lesson Planner", "🎲 Activities"],
        ["📝 Worksheets", "✅ Assessments"],
        ["📁 Library", "👤 Account"]
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        is_persistent=True
    )


def level_keyboard():

    keyboard = [

        [
            InlineKeyboardButton("A1", callback_data="level_A1"),
            InlineKeyboardButton("A2", callback_data="level_A2"),
        ],

        [
            InlineKeyboardButton("B1", callback_data="level_B1"),
            InlineKeyboardButton("B2", callback_data="level_B2"),
        ],

        [
            InlineKeyboardButton("C1", callback_data="level_C1"),
            InlineKeyboardButton("C2", callback_data="level_C2"),
        ],

    ]

    return InlineKeyboardMarkup(keyboard)


def grammar_keyboard():

    keyboard = [

        [
            InlineKeyboardButton(
                "Present Simple",
                callback_data="grammar_Present Simple"
            )
        ],

        [
            InlineKeyboardButton(
                "Present Continuous",
                callback_data="grammar_Present Continuous"
            )
        ],

        [
            InlineKeyboardButton(
                "Present Perfect",
                callback_data="grammar_Present Perfect"
            )
        ],

        [
            InlineKeyboardButton(
                "Present Perfect Continuous",
                callback_data="grammar_Present Perfect Continuous"
            )
        ],

        [
            InlineKeyboardButton(
                "Past Simple",
                callback_data="grammar_Past Simple"
            )
        ],

        [
            InlineKeyboardButton(
                "Past Continuous",
                callback_data="grammar_Past Continuous"
            )
        ],

        [
            InlineKeyboardButton(
                "Past Perfect",
                callback_data="grammar_Past Perfect"
            )
        ],

        [
            InlineKeyboardButton(
                "Past Perfect Continuous",
                callback_data="grammar_Past Perfect Continuous"
            )
        ],

        [
            InlineKeyboardButton(
                "Future Simple (Will)",
                callback_data="grammar_Future Simple"
            )
        ],

        [
            InlineKeyboardButton(
                "Be Going To",
                callback_data="grammar_Going To"
            )
        ],

        [
            InlineKeyboardButton(
                "Present Continuous (Future)",
                callback_data="grammar_Present Continuous Future"
            )
        ],

        [
            InlineKeyboardButton(
                "Future Continuous",
                callback_data="grammar_Future Continuous"
            )
        ],

        [
            InlineKeyboardButton(
                "Future Perfect",
                callback_data="grammar_Future Perfect"
            )
        ],

        [
            InlineKeyboardButton(
                "Modals",
                callback_data="grammar_Modals"
            )
        ],

        [
            InlineKeyboardButton(
                "Passive Voice",
                callback_data="grammar_Passive Voice"
            )
        ],

        [
            InlineKeyboardButton(
                "Reported Speech",
                callback_data="grammar_Reported Speech"
            )
        ],

        [
            InlineKeyboardButton(
                "Conditionals",
                callback_data="grammar_Conditionals"
            )
        ],

        [
            InlineKeyboardButton(
                "Relative Clauses",
                callback_data="grammar_Relative Clauses"
            )
        ],

        [
            InlineKeyboardButton(
                "Gerunds & Infinitives",
                callback_data="grammar_Gerunds & Infinitives"
            )
        ],

        [
            InlineKeyboardButton(
                "Articles",
                callback_data="grammar_Articles"
            )
        ],

        [
            InlineKeyboardButton(
                "Prepositions",
                callback_data="grammar_Prepositions"
            )
        ],

        [
            InlineKeyboardButton(
                "Skip Grammar",
                callback_data="grammar_None"
            )
        ],

    ]

    return InlineKeyboardMarkup(keyboard)

def confirm_keyboard():

    keyboard = [

        [
            InlineKeyboardButton(
                "🚀 Generate Lesson",
                callback_data="generate",
            )
        ],

        [
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data="cancel",
            )
        ]

    ]

    return InlineKeyboardMarkup(keyboard)


def duration_keyboard():

    keyboard = [

        [
            InlineKeyboardButton("30 min", callback_data="duration_30"),
        ],

        [
            InlineKeyboardButton("45 min", callback_data="duration_45"),
        ],

        [
            InlineKeyboardButton("60 min", callback_data="duration_60"),
        ],

        [
            InlineKeyboardButton("90 min", callback_data="duration_90"),
        ],

    ]

    return InlineKeyboardMarkup(keyboard)


def activity_type_keyboard():

    keyboard = [

        [
            InlineKeyboardButton(
                "🗣 Speaking",
                callback_data="activity_Speaking"
            )
        ],

        [
            InlineKeyboardButton(
                "🎭 Role Play",
                callback_data="activity_Role Play"
            )
        ],

        [
            InlineKeyboardButton(
                "⚖ Debate",
                callback_data="activity_Debate"
            )
        ],

        [
            InlineKeyboardButton(
                "👥 Pair Work",
                callback_data="activity_Pair Work"
            )
        ],

        [
            InlineKeyboardButton(
                "👨‍👩‍👧 Group Work",
                callback_data="activity_Group Work"
            )
        ],

        [
            InlineKeyboardButton(
                "🧩 Information Gap",
                callback_data="activity_Information Gap"
            )
        ],

        [
            InlineKeyboardButton(
                "❄ Icebreaker",
                callback_data="activity_Icebreaker"
            )
        ],

    ]

    return InlineKeyboardMarkup(keyboard)


def activity_confirm_keyboard():

    keyboard = [

        [
            InlineKeyboardButton(
                "🚀 Generate Activity",
                callback_data="generate_activity"
            )
        ],

        [
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data="cancel_activity"
            )
        ],

    ]

    return InlineKeyboardMarkup(keyboard)



