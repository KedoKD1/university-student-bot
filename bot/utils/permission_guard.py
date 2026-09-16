from telegram import Update
from telegram.ext import ContextTypes, ApplicationHandlerStop

from bot.utils.permissions import (
    permission_for_callback,
    has_permission,
)
from bot.utils.debug_logger import (
    logger,
    DEBUG_ENABLED,
)


async def permission_guard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    callback_data = query.data or ""

    if DEBUG_ENABLED:
        logger.info(
            "[PERMISSION GUARD] CALLBACK RECEIVED | "
            "user_id=%s | callback_data=%r",
            query.from_user.id
            if query.from_user
            else None,
            callback_data,
        )

    permission = permission_for_callback(
        callback_data
    )

    if DEBUG_ENABLED:
        logger.info(
            "[PERMISSION GUARD] PERMISSION RESOLUTION | "
            "callback_data=%r | permission=%r",
            callback_data,
            permission,
        )

    # Not an admin-protected callback.
    if permission is None:
        if DEBUG_ENABLED:
            logger.info(
                "[PERMISSION GUARD] NOT PROTECTED | "
                "callback_data=%r",
                callback_data,
            )

        return

    user = query.from_user

    if user is None:
        if DEBUG_ENABLED:
            logger.warning(
                "[PERMISSION GUARD] NO USER FOUND | "
                "callback_data=%r",
                callback_data,
            )

        return

    try:
        allowed = await has_permission(
            user.id,
            permission,
        )

        if DEBUG_ENABLED:
            logger.info(
                "[PERMISSION GUARD] RESULT | "
                "user_id=%s | permission=%r | allowed=%s",
                user.id,
                permission,
                allowed,
            )

    except Exception as exc:
        logger.error(
            "[PERMISSION GUARD] PERMISSION CHECK ERROR | "
            "user_id=%s | permission=%r | "
            "error_type=%s | error=%s",
            user.id,
            permission,
            type(exc).__name__,
            exc,
            exc_info=True,
        )

        raise

    if allowed:
        if DEBUG_ENABLED:
            logger.info(
                "[PERMISSION GUARD] ALLOWED | "
                "user_id=%s | callback_data=%r",
                user.id,
                callback_data,
            )

        return

    if DEBUG_ENABLED:
        logger.warning(
            "[PERMISSION GUARD] DENIED | "
            "user_id=%s | permission=%r | "
            "callback_data=%r",
            user.id,
            permission,
            callback_data,
        )

    try:
        await query.answer(
            "⛔ ليس لديك صلاحية لتنفيذ هذا الإجراء.",
            show_alert=True,
        )

    except Exception as exc:
        logger.error(
            "[PERMISSION GUARD] FAILED TO ANSWER QUERY | "
            "user_id=%s | callback_data=%r | "
            "error_type=%s | error=%s",
            user.id,
            callback_data,
            type(exc).__name__,
            exc,
            exc_info=True,
        )

    raise ApplicationHandlerStop
