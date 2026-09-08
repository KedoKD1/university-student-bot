from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
)

from bot.database.client import supabase


from bot.handlers.main_menu import (
    show_main_menu,
    main_menu_button,
    back_main,
)


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
    show_file_section,
    show_files,
    show_summaries_or_drawings,
    show_summary_section,
    show_all_summaries,
    study_item_button,
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


from bot.handlers.admin_files import (
    admin_files,
    admin_file_stage,
    admin_file_subject,
    admin_file_subjects,
    admin_file_sections,
    admin_file_section,
    admin_file_list,
    manage_file,
    disable_file,
    enable_file,
    delete_file,
    confirm_delete_file,
    file_conversation_handler,
)


from bot.handlers.admin_summaries import (
    admin_summaries,
    admin_summary_stage,
    admin_summary_subject,
    admin_summary_subjects,
    admin_summary_sections,
    admin_summary_section,
    admin_summary_list,
    manage_summary,
    disable_summary,
    enable_summary,
    delete_summary,
    confirm_delete_summary,
    summary_conversation_handler,
)


from bot.handlers.admin_drawings import (
    admin_drawings,
    admin_drawing_stage,
    admin_drawing_subject,
    admin_drawing_subjects,
    admin_drawing_sections,
    admin_drawing_section,
    admin_drawing_list,
    manage_drawing,
    disable_drawing,
    enable_drawing,
    delete_drawing,
    confirm_delete_drawing,
    drawing_conversation_handler,
)


from bot.handlers.schedules import (
    show_schedules,
    student_schedule_stage,
    locked_schedule,
)


from bot.handlers.admin_schedules import (
    admin_schedules,
    admin_schedule_stage,
    delete_schedule,
    schedule_conversation_handler,
)


from bot.handlers.admin_tools import (
    admin_tools,
    bot_status,
    admin_roles,
    role_manage,
    change_role,
    remove_role,
    set_role,
    bulk_conversation_handler,
    role_conversation_handler,
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
            show_main_menu,
        )
    )

    application.add_handler(
        CommandHandler(
            "admin",
            admin_command,
        )
    )


    # =========================
    # Admin Conversations
    # =========================

    application.add_handler(
        subject_conversation_handler()
    )

    application.add_handler(
        file_conversation_handler()
    )

    application.add_handler(
        summary_conversation_handler()
    )

    application.add_handler(
        drawing_conversation_handler()
    )

    application.add_handler(
        schedule_conversation_handler()
    )

    application.add_handler(
        bulk_conversation_handler()
    )

    application.add_handler(
        role_conversation_handler()
    )


    # =========================
    # Student Schedule
    # =========================

    application.add_handler(
        CallbackQueryHandler(
            show_schedules,
            pattern=r"^main:schedule:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            student_schedule_stage,
            pattern=r"^student_schedule_stage:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            locked_schedule,
            pattern=r"^locked_schedule:",
        )
    )


    # =========================
    # Main Menu
    # =========================

    application.add_handler(
        CallbackQueryHandler(
            main_menu_button,
            pattern=r"^main:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            back_main,
            pattern=r"^back_main:",
        )
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
    # Student Files
    # =========================

    application.add_handler(
        CallbackQueryHandler(
            show_files,
            pattern=r"^content:files:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            show_file_section,
            pattern=r"^files_section:",
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
# Student Summaries
# =========================

application.add_handler(
    CallbackQueryHandler(
        show_all_summaries,
        pattern=r"^content:summaries:all:",
    )
)

application.add_handler(
    CallbackQueryHandler(
        show_summaries_or_drawings,
        pattern=r"^content:summaries:",
    )
)

application.add_handler(
    CallbackQueryHandler(
        show_summary_section,
        pattern=r"^summaries_section:",
    )
)


    # =========================
    # Student Drawings
    # =========================

    application.add_handler(
        CallbackQueryHandler(
            show_summaries_or_drawings,
            pattern=r"^content:drawings:",
        )
    )


    application.add_handler(
        CallbackQueryHandler(
            study_item_button,
            pattern=r"^study_item:",
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
    # Admin Files
    # =========================

    application.add_handler(
        CallbackQueryHandler(
            admin_files,
            pattern=r"^admin_files$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_file_stage,
            pattern=r"^admin_file_stage:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_file_subject,
            pattern=r"^admin_file_subject:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_file_subjects,
            pattern=r"^admin_file_subjects:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_file_sections,
            pattern=r"^admin_file_sections:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_file_section,
            pattern=r"^admin_file_section:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_file_list,
            pattern=r"^admin_file_list:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            manage_file,
            pattern=r"^manage_file:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            disable_file,
            pattern=r"^disable_file:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            enable_file,
            pattern=r"^enable_file:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            delete_file,
            pattern=r"^delete_file:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            confirm_delete_file,
            pattern=r"^confirm_delete_file:",
        )
    )


    # =========================
    # Admin Summaries
    # =========================

    application.add_handler(
        CallbackQueryHandler(
            admin_summaries,
            pattern=r"^admin_summaries$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_summary_stage,
            pattern=r"^admin_summary_stage:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_summary_subject,
            pattern=r"^admin_summary_subject:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_summary_subjects,
            pattern=r"^admin_summary_subjects:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_summary_sections,
            pattern=r"^admin_summary_sections:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_summary_section,
            pattern=r"^admin_summary_section:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_summary_list,
            pattern=r"^admin_summary_list:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            manage_summary,
            pattern=r"^manage_summary:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            disable_summary,
            pattern=r"^disable_summary:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            enable_summary,
            pattern=r"^enable_summary:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            delete_summary,
            pattern=r"^delete_summary:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            confirm_delete_summary,
            pattern=r"^confirm_delete_summary:",
        )
    )


    # =========================
    # Admin Drawings
    # =========================

    application.add_handler(
        CallbackQueryHandler(
            admin_drawings,
            pattern=r"^admin_drawings$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_drawing_stage,
            pattern=r"^admin_drawing_stage:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_drawing_subject,
            pattern=r"^admin_drawing_subject:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_drawing_subjects,
            pattern=r"^admin_drawing_subjects:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_drawing_sections,
            pattern=r"^admin_drawing_sections:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_drawing_section,
            pattern=r"^admin_drawing_section:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_drawing_list,
            pattern=r"^admin_drawing_list:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            manage_drawing,
            pattern=r"^manage_drawing:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            disable_drawing,
            pattern=r"^disable_drawing:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            enable_drawing,
            pattern=r"^enable_drawing:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            delete_drawing,
            pattern=r"^delete_drawing:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            confirm_delete_drawing,
            pattern=r"^confirm_delete_drawing:",
        )
    )


    # =========================
    # Admin Schedules
    # =========================

    application.add_handler(
        CallbackQueryHandler(
            admin_schedules,
            pattern=r"^admin_schedules$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_schedule_stage,
            pattern=r"^admin_schedule_stage:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            delete_schedule,
            pattern=r"^delete_schedule:",
        )
    )


    # =========================
    # Admin Tools
    # =========================

    application.add_handler(
        CallbackQueryHandler(
            admin_tools,
            pattern=r"^admin_tools$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            bot_status,
            pattern=r"^bot_status$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_roles,
            pattern=r"^admin_roles$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            role_manage,
            pattern=r"^role_manage:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            change_role,
            pattern=r"^change_role:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            remove_role,
            pattern=r"^remove_role:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            set_role,
            pattern=r"^set_role:",
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
            pattern=(
                r"^admin_"
                r"(?!subjects$|back$|files$|"
                r"summaries$|drawings$|schedules$|"
                r"tools$|roles$|"
                r"stage_subjects:|"
                r"file_|"
                r"summary_|"
                r"drawing_)"
            ),
        )
    )


    # =========================
    # Start
    # =========================

    print(
        "University Student Bot is running..."
    )

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
