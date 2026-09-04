from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
)

from bot.database.client import supabase

from bot.handlers.stages import (
    locked_stage_button,
    show_stages,
    stage_button,
)

from bot.handlers.subjects import (
    back_to_stages,
    subject_button,
)

from bot.handlers.content import (
    back_to_content,
    file_button,
    show_files,
)

from bot.handlers.admin import (
    admin_button,
    admin_command,
)

from bot.handlers.admin_subjects import (
    admin_subjects,
    delete_subject,
    manage_stage,
    manage_subject,
)

from bot.utils.config import (
    BOT_TOKEN,
    validate_config,
)


def main():
    validate_config()

    if not BOT_TOKEN:
        raise ValueError(
            "BOT_TOKEN is not configured."
        )

    response = (
        supabase
        .table("stages")
        .select("id")
        .limit(1)
        .execute()
    )

    print(
        f"Supabase connection successful: "
        f"{response.data}"
    )

    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            show_stages
        )
    )

    application.add_handler(
        CommandHandler(
            "admin",
            admin_command
        )
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

    application.add_handler(
        CallbackQueryHandler(
            show_files,
            pattern=r"^content:"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            file_button,
            pattern=r"^file:"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            back_to_content,
            pattern=r"^back_content:"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_subjects,
            pattern=r"^admin_subjects$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            manage_stage,
            pattern=r"^manage_stage:"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            manage_subject,
            pattern=r"^manage_subject:"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            delete_subject,
            pattern=r"^delete_subject:"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_button,
            pattern=r"^admin_(?!subjects$)"
        )
    )

    print(
        "University Student Bot is running..."
    )

    application.run_polling()


if __name__ == "__main__":
    main()
