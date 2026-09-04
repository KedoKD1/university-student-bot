from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from bot.database.client import supabase
from bot.handlers.stages import show_stages
from bot.utils.config import BOT_TOKEN, validate_config


def main():
    validate_config()

    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not configured.")

    # Test Supabase connection
    response = (
        supabase
        .table("stages")
        .select("id")
        .limit(1)
        .execute()
    )

    print(f"Supabase connection successful: {response.data}")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(
        CommandHandler("start", show_stages)
    )

    print("University Student Bot is running...")

    application.run_polling()


if __name__ == "__main__":
    main()
