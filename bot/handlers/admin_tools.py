from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    filters,
)

from bot.database.client import supabase
from bot.handlers.admin import is_admin


ROLE_USERNAME = 10


ROLE_NAMES = {
    "owner": "👑 Owner",
    "admin": "🛡️ Admin",
    "moderator": "🔧 Moderator",
}


async def get_admin(user_id):
    response = (
        supabase
        .table("admins")
        .select(
            "id, telegram_id, role, is_active"
        )
        .eq("telegram_id", user_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    rows = response.data or []

    return rows[0] if rows else None


async def is_owner(user_id):
    admin = await get_admin(user_id)

    return (
        admin is not None
        and admin.get("role") == "owner"
    )


def tools_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📊 حالة البوت",
                callback_data="bot_status",
            )
        ],
        [
            InlineKeyboardButton(
                "👥 إدارة المشرفين",
                callback_data="admin_roles",
            )
        ],
        [
            InlineKeyboardButton(
                "📝 أوصاف الإرسال",
                callback_data="bundle_descriptions",
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ لوحة الإدارة",
                callback_data="admin_back",
            )
        ],
    ])


async def admin_tools(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    await query.answer()

    await query.edit_message_text(
        "🧰 أدوات الإدارة\n\n"
        "اختر العملية:",
        reply_markup=tools_keyboard(),
    )


async def bot_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_admin(query.from_user.id):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    await query.answer()

def count_rows(
    table,
    active_only=False,
):
    builder = (
        supabase
        .table(table)
        .select(
            "*",
            count="exact",
        )
    )

    if active_only:
        builder = builder.eq(
            "is_active",
            True,
        )

    try:
        result = builder.execute()
        return result.count or 0
    except Exception as exc:
        print(
            f"COUNT ERROR [{table}]:",
            type(exc).__name__,
            exc,
        )
        return 0

    users = count_rows("telegram_users")

    admins = count_rows(
        "admins",
        active_only=True,
    )

    files = count_rows(
        "files",
        active_only=True,
    )

    summaries = count_rows(
        "summaries",
        active_only=True,
    )

    drawings = count_rows(
        "drawings",
        active_only=True,
    )

    schedules = count_rows(
        "schedules",
        active_only=True,
    )

    chats = count_rows(
        "bot_chats",
        active_only=True,
    )

    owner_count = 0
    admin_count = 0
    moderator_count = 0

    try:
        response = (
            supabase
            .table("admins")
            .select("role")
            .eq("is_active", True)
            .execute()
        )

        for row in response.data or []:
            role = row.get("role")

            if role == "owner":
                owner_count += 1

            elif role == "admin":
                admin_count += 1

            elif role == "moderator":
                moderator_count += 1

    except Exception:
        pass

    text = (
        "📊 حالة البوت\n\n"
        "🟢 الحالة: يعمل\n\n"
        "👥 الإحصائيات\n"
        f"• المستخدمون: {users}\n"
        f"• الكروبات/القنوات المسجلة: {chats}\n\n"
        "🛡️ الإدارة\n"
        f"• 👑 Owners: {owner_count}\n"
        f"• 🛡️ Admins: {admin_count}\n"
        f"• 🔧 Moderators: {moderator_count}\n"
        f"• مجموع المشرفين: {admins}\n\n"
        "📚 المحتوى\n"
        f"• 📄 الملفات: {files}\n"
        f"• 📝 الملخصات: {summaries}\n"
        f"• 🎨 الرسومات: {drawings}\n"
        f"• 📅 الجداول: {schedules}"
    )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔄 تحديث",
                    callback_data="bot_status",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ أدوات الإدارة",
                    callback_data="admin_tools",
                )
            ],
        ]),
    )


async def admin_roles(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_owner(query.from_user.id):
        await query.answer(
            "⛔ هذا الخيار للـ Owner فقط.",
            show_alert=True,
        )
        return

    await query.answer()

    response = (
        supabase
        .table("admins")
        .select(
            "id, telegram_id, role, is_active"
        )
        .eq("is_active", True)
        .order("id")
        .execute()
    )

    admins = response.data or []

    usernames = {}

    try:
        users_response = (
            supabase
            .table("telegram_users")
            .select(
                "telegram_id, username"
            )
            .execute()
        )

        usernames = {
            str(row["telegram_id"]): row.get(
                "username"
            )
            for row in (
                users_response.data or []
            )
            if row.get("username")
        }

    except Exception:
        pass

    keyboard = [
        [
            InlineKeyboardButton(
                "➕ إعطاء رتبة",
                callback_data="role_add",
            )
        ]
    ]

    for admin in admins:
        role = admin.get(
            "role",
            "moderator",
        )

        telegram_id = str(
            admin["telegram_id"]
        )

        username = usernames.get(
            telegram_id
        )

        identity = (
            f"@{username}"
            if username
            else telegram_id
        )

        keyboard.append([
            InlineKeyboardButton(
                text=(
                    f"{ROLE_NAMES.get(role, role)}"
                    f" • {identity}"
                ),
                callback_data=(
                    f"role_manage:"
                    f"{admin['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ أدوات الإدارة",
            callback_data="admin_tools",
        )
    ])

    await query.edit_message_text(
        "👥 إدارة المشرفين\n\n"
        "اختر المشرف:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


async def role_add_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return ConversationHandler.END

    if not await is_owner(
        query.from_user.id
    ):
        await query.answer(
            "⛔ هذا الخيار للـ Owner فقط.",
            show_alert=True,
        )
        return ConversationHandler.END

    await query.answer()

    await query.edit_message_text(
        "➕ إضافة مشرف\n\n"
        "أرسل Username الخاص بالشخص.\n"
        "مثال: @username\n\n"
        "⚠️ لازم الشخص يكون قد استخدم "
        "البوت مرة واحدة على الأقل حتى "
        "أگدر أتعرف عليه."
    )

    return ROLE_USERNAME


async def role_receive_username(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ROLE_USERNAME

    username = (
        update.message.text or ""
    ).strip()

    username = username.lstrip(
        "@"
    ).strip()

    if not username or " " in username:
        await update.message.reply_text(
            "❌ Username غير صحيح.\n"
            "أرسله بهذا الشكل:\n"
            "@username"
        )

        return ROLE_USERNAME

    try:
        response = (
            supabase
            .table("telegram_users")
            .select(
                "telegram_id, username, "
                "first_name, last_name"
            )
            .ilike(
                "username",
                username,
            )
            .limit(1)
            .execute()
        )

    except Exception as exc:
        print(
            "ROLE USERNAME LOOKUP ERROR:",
            type(exc).__name__,
            exc,
        )

        await update.message.reply_text(
            "❌ تعذر البحث عن Username.\n"
            "تأكد أن جدول telegram_users موجود."
        )

        return ConversationHandler.END

    rows = response.data or []

    if not rows:
        await update.message.reply_text(
            "❌ ما لكيت هذا Username.\n\n"
            "تأكد من كتابته صحيح، وتأكد أن "
            "الشخص استخدم البوت مرة واحدة "
            "على الأقل."
        )

        return ROLE_USERNAME

    target_id = rows[0]["telegram_id"]

    target_username = (
        rows[0].get("username")
        or username
    )

    target_name = " ".join(
        part
        for part in [
            rows[0].get("first_name"),
            rows[0].get("last_name"),
        ]
        if part
    ).strip()

    context.user_data[
        "role_target_id"
    ] = target_id

    context.user_data[
        "role_target_username"
    ] = target_username

    name_line = (
        f"👤 الاسم: {target_name}\n"
        if target_name
        else ""
    )

    await update.message.reply_text(
        "👤 تم العثور على المستخدم.\n\n"
        f"@{target_username}\n"
        f"{name_line}\n"
        "اختر الرتبة:",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🛡️ Admin",
                    callback_data="set_role:admin",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔧 Moderator",
                    callback_data="set_role:moderator",
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ إلغاء",
                    callback_data="cancel_role",
                )
            ],
        ]),
    )

    return ConversationHandler.END


async def set_role(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_owner(
        query.from_user.id
    ):
        await query.answer(
            "⛔ هذا الخيار للـ Owner فقط.",
            show_alert=True,
        )
        return

    target_id = context.user_data.get(
        "role_target_id"
    )

    target_username = (
        context.user_data.get(
            "role_target_username",
            "المستخدم",
        )
    )

    if not target_id:
        await query.answer(
            "❌ لم يتم تحديد المستخدم.",
            show_alert=True,
        )
        return

    role = query.data.split(
        ":",
        1,
    )[1]

    try:
        existing = (
            supabase
            .table("admins")
            .select("id")
            .eq(
                "telegram_id",
                target_id,
            )
            .limit(1)
            .execute()
        )

        rows = existing.data or []

        if rows:
            (
                supabase
                .table("admins")
                .update({
                    "role": role,
                    "is_active": True,
                })
                .eq(
                    "id",
                    rows[0]["id"],
                )
                .execute()
            )

        else:
            (
                supabase
                .table("admins")
                .insert({
                    "telegram_id": target_id,
                    "role": role,
                    "is_active": True,
                })
                .execute()
            )

    except Exception as exc:
        print(
            "ROLE SAVE ERROR:",
            type(exc).__name__,
            exc,
        )

        await query.answer(
            "❌ تعذر حفظ الرتبة.",
            show_alert=True,
        )

        return

    context.user_data.pop(
        "role_target_id",
        None,
    )

    context.user_data.pop(
        "role_target_username",
        None,
    )

    await query.answer(
        (
            f"✅ تم إعطاء "
            f"{ROLE_NAMES.get(role, role)} "
            f"لـ @{target_username}."
        ),
        show_alert=True,
    )

    await admin_roles(
        update,
        context,
    )


async def role_manage(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_owner(
        query.from_user.id
    ):
        await query.answer(
            "⛔ هذا الخيار للـ Owner فقط.",
            show_alert=True,
        )
        return

    admin_id = query.data.split(
        ":",
        1,
    )[1]

    response = (
        supabase
        .table("admins")
        .select(
            "id, telegram_id, role"
        )
        .eq("id", admin_id)
        .limit(1)
        .execute()
    )

    rows = response.data or []

    if not rows:
        await query.answer(
            "❌ المشرف غير موجود.",
            show_alert=True,
        )
        return

    admin = rows[0]

    username = None

    try:
        user_response = (
            supabase
            .table("telegram_users")
            .select("username")
            .eq(
                "telegram_id",
                admin["telegram_id"],
            )
            .limit(1)
            .execute()
        )

        if user_response.data:
            username = (
                user_response.data[0]
                .get("username")
            )

    except Exception:
        pass

    identity = (
        f"@{username}"
        if username
        else str(admin["telegram_id"])
    )

    await query.answer()

    await query.edit_message_text(
        "👤 إدارة المشرف\n\n"
        f"👤 المستخدم: {identity}\n"
        f"🏷️ الرتبة: "
        f"{ROLE_NAMES.get(admin['role'], admin['role'])}\n\n"
        "اختر العملية:",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🛡️ تحويل إلى Admin",
                    callback_data=(
                        f"change_role:"
                        f"{admin['id']}:admin"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "🔧 تحويل إلى Moderator",
                    callback_data=(
                        f"change_role:"
                        f"{admin['id']}:moderator"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ إزالة الرتبة",
                    callback_data=(
                        f"remove_role:"
                        f"{admin['id']}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="admin_roles",
                )
            ],
        ]),
    )


async def change_role(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_owner(
        query.from_user.id
    ):
        await query.answer(
            "⛔ هذا الخيار للـ Owner فقط.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    admin_id = parts[1]
    role = parts[2]

    try:
        (
            supabase
            .table("admins")
            .update({
                "role": role,
                "is_active": True,
            })
            .eq(
                "id",
                admin_id,
            )
            .execute()
        )

    except Exception as exc:
        print(
            "ROLE CHANGE ERROR:",
            exc,
        )

        await query.answer(
            "❌ تعذر تغيير الرتبة.",
            show_alert=True,
        )

        return

    await query.answer(
        "✅ تم تغيير الرتبة.",
        show_alert=True,
    )

    await admin_roles(
        update,
        context,
    )


async def remove_role(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await is_owner(
        query.from_user.id
    ):
        await query.answer(
            "⛔ هذا الخيار للـ Owner فقط.",
            show_alert=True,
        )
        return

    admin_id = query.data.split(
        ":",
        1,
    )[1]

    try:
        (
            supabase
            .table("admins")
            .update({
                "is_active": False,
            })
            .eq(
                "id",
                admin_id,
            )
            .execute()
        )

    except Exception as exc:
        print(
            "ROLE REMOVE ERROR:",
            exc,
        )

        await query.answer(
            "❌ تعذر إزالة الرتبة.",
            show_alert=True,
        )

        return

    await query.answer(
        "✅ تمت إزالة الرتبة.",
        show_alert=True,
    )

    await admin_roles(
        update,
        context,
    )


async def cancel_role(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data.pop(
        "role_target_id",
        None,
    )

    context.user_data.pop(
        "role_target_username",
        None,
    )

    if update.message:
        await update.message.reply_text(
            "❌ تم إلغاء العملية."
        )

    return ConversationHandler.END


def role_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                role_add_start,
                pattern=r"^role_add$",
            )
        ],
        states={
            ROLE_USERNAME: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    role_receive_username,
                )
            ]
        },
        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_role,
            )
        ],
        allow_reentry=True,
    )
