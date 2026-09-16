import logging
import os
import traceback

from telegram import Update
from telegram.ext import ContextTypes


DEBUG_ENABLED = (
    os.getenv("LABBASE_DEBUG", "true").strip().lower()
    in {
        "1",
        "true",
        "yes",
        "on",
    }
)


LOGGER_NAME = "labbase"


logger = logging.getLogger(LOGGER_NAME)


def configure_logging():
    if not DEBUG_ENABLED:
        return

    root_logger = logging.getLogger()

    if not root_logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format=(
                "%(asctime)s | "
                "%(levelname)s | "
                "%(name)s | "
                "%(message)s"
            ),
        )
    else:
        root_logger.setLevel(logging.INFO)

    logger.info(
        "============================================================"
    )
    logger.info(
        "LABBASE DEBUG MODE ENABLED"
    )
    logger.info(
        "============================================================"
    )


def _user_info(update: Update) -> str:
    user = update.effective_user

    if user is None:
        return "user=None"

    username = (
        f"@{user.username}"
        if user.username
        else "no_username"
    )

    return (
        f"user_id={user.id} "
        f"username={username} "
        f"first_name={user.first_name!r}"
    )


def _chat_info(update: Update) -> str:
    chat = update.effective_chat

    if chat is None:
        return "chat=None"

    return (
        f"chat_id={chat.id} "
        f"chat_type={chat.type} "
        f"chat_title={chat.title!r}"
    )


def log_update(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not DEBUG_ENABLED:
        return

    try:
        logger.info(
            "-------------------- UPDATE START --------------------"
        )

        logger.info(
            "update_id=%s",
            update.update_id,
        )

        logger.info(
            "%s",
            _user_info(update),
        )

        logger.info(
            "%s",
            _chat_info(update),
        )

        if update.callback_query is not None:
            query = update.callback_query

            logger.info(
                "UPDATE TYPE: CALLBACK_QUERY"
            )

            logger.info(
                "callback_query_id=%s",
                query.id,
            )

            logger.info(
                "callback_data=%r",
                query.data,
            )

            if query.message is not None:
                logger.info(
                    "callback_message_id=%s",
                    query.message.message_id,
                )

        elif update.message is not None:
            message = update.message

            logger.info(
                "UPDATE TYPE: MESSAGE"
            )

            logger.info(
                "message_id=%s",
                message.message_id,
            )

            if message.text:
                safe_text = message.text[:500]

                logger.info(
                    "message_text=%r",
                    safe_text,
                )

            if message.document is not None:
                logger.info(
                    "message_document=True"
                )

            if message.photo:
                logger.info(
                    "message_photo=True"
                )

            if message.video is not None:
                logger.info(
                    "message_video=True"
                )

        elif update.inline_query is not None:
            logger.info(
                "UPDATE TYPE: INLINE_QUERY"
            )

        elif update.chat_member is not None:
            logger.info(
                "UPDATE TYPE: CHAT_MEMBER"
            )

        elif update.my_chat_member is not None:
            logger.info(
                "UPDATE TYPE: MY_CHAT_MEMBER"
            )

        elif update.channel_post is not None:
            logger.info(
                "UPDATE TYPE: CHANNEL_POST"
            )

        else:
            logger.info(
                "UPDATE TYPE: OTHER"
            )

        logger.info(
            "--------------------- UPDATE END ---------------------"
        )

    except Exception as exc:
        logger.error(
            "DEBUG LOGGER FAILED: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )


async def global_error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not DEBUG_ENABLED:
        return

    error = context.error

    logger.error(
        "============================================================"
    )

    logger.error(
        "UNHANDLED BOT ERROR"
    )

    logger.error(
        "error_type=%s",
        type(error).__name__
        if error is not None
        else "None",
    )

    logger.error(
        "error=%s",
        error,
    )

    if update is not None:
        try:
            if isinstance(update, Update):
                logger.error(
                    "error_update_id=%s",
                    update.update_id,
                )

                logger.error(
                    "error_%s",
                    _user_info(update),
                )

                logger.error(
                    "error_%s",
                    _chat_info(update),
                )

                if update.callback_query is not None:
                    logger.error(
                        "error_callback_data=%r",
                        update.callback_query.data,
                    )

                if (
                    update.message is not None
                    and update.message.text
                ):
                    logger.error(
                        "error_message_text=%r",
                        update.message.text[:500],
                    )

        except Exception:
            logger.error(
                "FAILED TO INSPECT ERROR UPDATE",
                exc_info=True,
            )

    if error is not None:
        logger.error(
            "FULL TRACEBACK:"
        )

        logger.error(
            "".join(
                traceback.format_exception(
                    type(error),
                    error,
                    error.__traceback__,
                )
            )
        )

    logger.error(
        "============================================================"
    )
