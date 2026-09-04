from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
)

from bot.handlers.subjects import (
    back_to_stages,
    subject_button,
)
from bot.database.client import supabase
from bot.handlers.stages import (
    locked_stage_button,
    show_stages,
    stage_button,
)
from bot.utils.config import BOT_TOKEN, validate_config


def main():
    validate_config()

    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not configured.")

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

    application.add_handler(
        CallbackQueryHandler(
            stage_button,
            pattern=r"^stage:"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            locked_stage_button,
            pattern=r"^locked:"
        )
    )

    application.add_handler(
    CallbackQueryHandler(
        subject_button,
        pattern=r"^subject:"
    )
)

application.add_handler(
    CallbackQueryHandler(
        back_to_stages,
        pattern=r"^back_stages:"
    )
)
    print("University Student Bot is running...")

    application.run_polling()


if __name__ == "__main__":
    main()
