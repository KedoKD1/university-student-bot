from telegram import Update
from telegram.ext import ContextTypes, ApplicationHandlerStop

from bot.utils.permissions import (
    permission_for_callback,
    has_permission,
)
from bot.utils.debug_logger import (
    logger,
    DEBUG_ENABLED,
    log_error,
)


async def permission_guard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    callback_data = query.data or ""

    if not isinstance(callback_data, str):
        raise ApplicationHandlerStop

    if DEBUG_ENABLED:
        logger.info("[PERMISSION GUARD] CALLBACK RECEIVED")

    permission = permission_for_callback(
        callback_data
    )

    if DEBUG_ENABLED:
        logger.info(
            "[PERMISSION GUARD] PERMISSION RESOLUTION | "
            "permission=%r",
            permission,
        )

    # Not an admin-protected callback.
    if permission is None:
        if DEBUG_ENABLED:
            logger.info("[PERMISSION GUARD] NOT PROTECTED")

        return

    user = query.from_user

    if user is None:
        if DEBUG_ENABLED:
            logger.warning("[PERMISSION GUARD] NO USER FOUND")

        raise ApplicationHandlerStop

    # These destinations enforce view_admin themselves. Let an active
    # conversation clear its owned operation before a destination denial.
    if callback_data in {"admin_back", "admin_tools"}:
        return

    # Owned cancellation only clears local state; revoked grants must not trap it.
    if callback_data.split(":", 1)[0] in {"notify_cancel", "bundle_desc_cancel"}:
        return

    try:
        allowed = await has_permission(
            user.id,
            permission,
            refresh=True,
        )

        if DEBUG_ENABLED:
            logger.info(
                "[PERMISSION GUARD] RESULT | "
                "permission=%r | allowed=%s",
                permission,
                allowed,
            )

    except Exception as exc:
        log_error("[PERMISSION GUARD] PERMISSION CHECK ERROR", exc)

        raise ApplicationHandlerStop from exc

    if allowed:
        if DEBUG_ENABLED:
            logger.info("[PERMISSION GUARD] ALLOWED")

        return

    if DEBUG_ENABLED:
        logger.warning(
            "[PERMISSION GUARD] DENIED | "
            "permission=%r",
            permission,
        )

    try:
        await query.answer(
            "⛔ ليس لديك صلاحية لتنفيذ هذا الإجراء.",
            show_alert=True,
        )

    except Exception as exc:
        log_error("[PERMISSION GUARD] FAILED TO ANSWER QUERY", exc)

    raise ApplicationHandlerStop
