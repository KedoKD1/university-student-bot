from telegram import Update
from telegram.ext import ContextTypes, ApplicationHandlerStop

from bot.utils.permissions import (
    permission_for_callback,
    has_permission,
)


async def permission_guard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    callback_data = query.data or ""

    permission = permission_for_callback(
        callback_data
    )

    # Not an admin-protected callback.
    if permission is None:
        return

    user = query.from_user

    if user is None:
        return

    allowed = await has_permission(
        user.id,
        permission,
    )

    if allowed:
        return

    try:
        await query.answer(
            "⛔ ليس لديك صلاحية لتنفيذ هذا الإجراء.",
            show_alert=True,
        )
    except Exception:
        pass

    raise ApplicationHandlerStop
