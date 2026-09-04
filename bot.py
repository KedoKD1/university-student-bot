from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from bot.database.client import test_database_connection
from bot.utils.config import BOT_TOKEN, validate_config


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return

    await update.message.reply_text(
        "🎓 مرحباً بك في بوت الطالب الجامعي\n\n"
        "البوت يعمل حالياً."
    )


def main():
    validate_config()

    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not configured.")

    database_result = test_database_connection()
    print(f"Supabase connection successful: {database_result}")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(
        CommandHandler("start", start)
    )

    print("University Student Bot is running...")

    application.run_polling()


if __name__ == "__main__":
    main()
