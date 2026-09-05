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
    back_to_subjects,
    subject_button,
)
from bot.handlers.content import (
    back_to_content,
    file_button,
    show_files,
)
from bot.handlers.admin import (
    admin_back,
    admin_button,
    admin_command,
)
from bot.handlers.admin_subjects import (
    admin_subjects,
    back_to_stage_subjects,
    disable_subject,
    enable_subject,
    manage_stage,
    manage_subject,
    subject_conversation_handler,
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
    # =========================
    # Commands
    # =========================
    application.add_handler(
        CommandHandler(
            "start",
            show_stages,
        )
    )
    application.add_handler(
        CommandHandler(
            "admin",
            admin_command,
        )
    )
    # =========================
    # Admin Subject Conversation
    # =========================
    #
    # يجب تسجيل ConversationHandler قبل
    # الـ CallbackQueryHandlers العامة حتى
    # يستلم أزرار الإضافة والتعديل بشكل صحيح.
    #
    application.add_handler(
        subject_conversation_handler()
    )
    # =========================
    # Stages
    # =========================
    application.add_handler(
        CallbackQueryHandler(
            stage_button,
            pattern=r"^stage:",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            locked_stage_button,
            pattern=r"^locked:",
        )
    )
    # =========================
    # Subjects
    # =========================
    application.add_handler(
        CallbackQueryHandler(
            subject_button,
            pattern=r"^subject:",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            back_to_subjects,
            pattern=r"^back_subjects:",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            back_to_stages,
            pattern=r"^back_stages:",
        )
    )
    # =========================
    # Content
    # =========================
    application.add_handler(
        CallbackQueryHandler(
            show_files,
            pattern=r"^content:",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            file_button,
            pattern=r"^file:",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            back_to_content,
            pattern=r"^back_content:",
        )
    )
    # =========================
    # Admin Subjects
    # =========================
    application.add_handler(
        CallbackQueryHandler(
            admin_subjects,
            pattern=r"^admin_subjects$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            back_to_stage_subjects,
            pattern=r"^admin_stage_subjects:",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            manage_stage,
            pattern=r"^manage_stage:",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            manage_subject,
            pattern=r"^manage_subject:",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            disable_subject,
            pattern=r"^disable_subject:",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            enable_subject,
            pattern=r"^enable_subject:",
        )
    )
    # =========================
    # Admin Navigation
    # =========================
    application.add_handler(
        CallbackQueryHandler(
            admin_back,
            pattern=r"^admin_back$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            admin_button,
            pattern=r"^admin_(?!subjects$|back$|stage_subjects:)",
        )
    )
    # =========================
    # Start Bot
    # =========================
    print(
        "University Student Bot is running..."
    )
    application.run_polling(
        drop_pending_updates=True
    )
if __name__ == "__main__":
    main()
