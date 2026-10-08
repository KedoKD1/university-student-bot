import re

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

from bot.utils.permissions import (
    has_permission,
    require_callback_owner,
    clear_permission_cache,
    PERMISSION_VIEW_ADMIN,
    PERMISSION_VIEW_STATISTICS,
    PERMISSION_MANAGE_ADMINS,
    PERMISSION_MANAGE_DESCRIPTIONS,
)


ROLE_USERNAME = 10
ROLE_SELECTION = 11


ROLE_NAMES = {
    "owner": "👑 Owner",
    "admin": "🛡️ Admin",
    "moderator": "🔧 Moderator",
}


# ============================================================
# Tools keyboard
# ============================================================

async def tools_keyboard(
    user_id: int,
):
    keyboard = []

    # admin_tools already refreshed access for this menu. Button visibility
    # can reuse that DB snapshot; each selected action rechecks its permission.

    # --------------------------------------------------------
    # Bot status
    # --------------------------------------------------------

    if await has_permission(
        user_id,
        PERMISSION_VIEW_STATISTICS,
    ):
        keyboard.append([
            InlineKeyboardButton(
                "📊 حالة البوت",
                callback_data="bot_status",
            )
        ])

    # --------------------------------------------------------
    # Admin management
    # --------------------------------------------------------

    if await has_permission(
        user_id,
        PERMISSION_MANAGE_ADMINS,
    ):
        keyboard.append([
            InlineKeyboardButton(
                "👥 إدارة المشرفين",
                callback_data="admin_roles",
            )
        ])

    # --------------------------------------------------------
    # Bundle descriptions
    # --------------------------------------------------------

    if await has_permission(
        user_id,
        PERMISSION_MANAGE_DESCRIPTIONS,
    ):
        keyboard.append([
            InlineKeyboardButton(
                "📝 أوصاف الإرسال",
                callback_data="bundle_descriptions",
            )
        ])

    # --------------------------------------------------------
    # Back to admin panel
    # --------------------------------------------------------

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ لوحة الإدارة",
            callback_data="admin_back",
        )
    ])

    return InlineKeyboardMarkup(
        keyboard
    )


# ============================================================
# Admin tools
# ============================================================

async def admin_tools(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await has_permission(
        query.from_user.id,
        PERMISSION_VIEW_ADMIN,
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية.",
            show_alert=True,
        )
        return

    await query.answer()

    await query.edit_message_text(
        "🧰 أدوات الإدارة\n\n"
        "اختر العملية:",
        reply_markup=await tools_keyboard(
            query.from_user.id,
        ),
    )


# ============================================================
# Count rows
# ============================================================

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
        if table in {"files", "summaries", "drawings"}:
            builder = builder.is_("deleted_at", "null")

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


# ============================================================
# Bot status
# ============================================================

async def bot_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await has_permission(
        query.from_user.id,
        PERMISSION_VIEW_STATISTICS,
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية لعرض الإحصائيات.",
            show_alert=True,
        )
        return

    await query.answer()

    users = count_rows(
        "telegram_users"
    )

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
            .eq(
                "is_active",
                True,
            )
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


# ============================================================
# Admin roles
# ============================================================

async def admin_roles(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await has_permission(
        query.from_user.id,
        PERMISSION_MANAGE_ADMINS,
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية لإدارة المشرفين.",
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
        .eq(
            "is_active",
            True,
        )
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
                callback_data=f'role_add:{query.from_user.id}',
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


# ============================================================
# Start adding role
# ============================================================

def clear_role_conversation(context):
    for key in ("role_target_id", "role_target_username", "role_owner_id", "role_target_role"):
        context.admin_data.pop(key, None)


def role_selection_keyboard(target_id, owner_id, current_role=None):
    rows = [[InlineKeyboardButton(
        ROLE_NAMES[role], callback_data=f"set_role:{role}:{target_id}:{owner_id}"
    )] for role in ("admin", "moderator") if role != current_role]
    rows.append([InlineKeyboardButton("❌ إلغاء", callback_data="admin_roles")])
    return InlineKeyboardMarkup(rows)


async def role_add_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not await require_callback_owner(query):
        return None

    if query is None or query.from_user is None:
        return ConversationHandler.END

    if not await has_permission(
        query.from_user.id,
        PERMISSION_MANAGE_ADMINS,
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية لإدارة المشرفين.",
            show_alert=True,
        )
        return ConversationHandler.END

    clear_role_conversation(context)
    context.admin_data["role_owner_id"] = query.from_user.id

    context.admin_data.pop(
        "role_target_id",
        None,
    )

    context.admin_data.pop(
        "role_target_username",
        None,
    )

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


# ============================================================
# Receive username
# ============================================================

async def role_receive_username(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return ROLE_USERNAME

    user = update.effective_user
    if user is None or context.admin_data.get("role_owner_id") != user.id:
        return None
    if not await has_permission(user.id, PERMISSION_MANAGE_ADMINS, refresh=True):
        clear_role_conversation(context)
        await update.message.reply_text("⛔ ليس لديك صلاحية لإدارة المشرفين.")
        return ConversationHandler.END

    username = (
        update.message.text or ""
    ).strip()

    username = username.lstrip(
        "@"
    ).strip()

    if not re.fullmatch(r"[A-Za-z0-9_]{1,32}", username):
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
                username.replace("_", r"\_"),
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

        clear_role_conversation(context)
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

    # Never allow creating/changing an owner
    # through the normal role assignment flow.
    try:
        existing_owner = (
            supabase
            .table("admins")
            .select(
                "id, role, is_active"
            )
            .eq(
                "telegram_id",
                target_id,
            )
            .limit(1)
            .execute()
        )

        existing_rows = (
            existing_owner.data or []
        )

        if (
            existing_rows
            and existing_rows[0].get("role")
            == "owner"
        ):
            await update.message.reply_text(
                "⛔ لا يمكن تعديل رتبة Owner."
            )

            clear_role_conversation(context)
            return ConversationHandler.END

    except Exception as exc:
        print(
            "ROLE TARGET VALIDATION ERROR:",
            type(exc).__name__,
            exc,
        )

        await update.message.reply_text(
            "❌ تعذر التحقق من رتبة المستخدم."
        )

        clear_role_conversation(context)
        return ConversationHandler.END

    context.admin_data[
        "role_target_id"
    ] = target_id

    context.admin_data[
        "role_target_username"
    ] = target_username
    current = existing_rows[0] if existing_rows else {}
    context.admin_data["role_target_role"] = (current.get("role"), current.get("is_active") is True)

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
        reply_markup=role_selection_keyboard(
            target_id, user.id, current.get("role") if current.get("is_active") is True else None
        ),
    )

    return ROLE_SELECTION


# ============================================================
# Set role
# ============================================================

async def set_role(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not await require_callback_owner(query):
        return None

    if query is None or query.from_user is None:
        return

    if not await has_permission(
        query.from_user.id,
        PERMISSION_MANAGE_ADMINS,
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية لإدارة المشرفين.",
            show_alert=True,
        )
        return

    if context.admin_data.get("role_owner_id") != query.from_user.id:
        await query.answer("⛔ هذه العملية ليست لك.", show_alert=True)
        return None

    target_id = context.admin_data.get(
        "role_target_id"
    )

    target_username = (
        context.admin_data.get(
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

    parts = query.data.rsplit(":", 1)[0].split(
        ":",
    )

    if len(parts) != 3 or parts[2] != str(target_id):
        await query.answer(
            "❌ رتبة غير صحيحة.",
            show_alert=True,
        )
        return

    role = parts[1]

    if role not in {
        "admin",
        "moderator",
    }:
        await query.answer(
            "❌ لا يمكن تعيين هذه الرتبة.",
            show_alert=True,
        )
        return

    try:
        existing = (
            supabase
            .table("admins")
            .select(
                "id, role, is_active"
            )
            .eq(
                "telegram_id",
                target_id,
            )
            .limit(1)
            .execute()
        )

        rows = existing.data or []

        current = rows[0] if rows else {}
        snapshot = (current.get("role"), current.get("is_active") is True)
        if context.admin_data.get("role_target_role") != snapshot:
            clear_role_conversation(context)
            await query.answer("❌ تغيرت رتبة المستخدم. أعد فتح العملية.", show_alert=True)
            return ConversationHandler.END
        if snapshot == (role, True):
            clear_role_conversation(context)
            await query.answer("ℹ️ المستخدم يحمل هذه الرتبة بالفعل.", show_alert=True)
            return ConversationHandler.END

        if rows:
            current_role = rows[0].get(
                "role"
            )

            if current_role == "owner":
                await query.answer(
                    "⛔ لا يمكن تعديل رتبة Owner.",
                    show_alert=True,
                )
                return

            saved = (
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
                .eq("role", current_role)
                .eq("is_active", current.get("is_active"))
                .execute()
            )
            if not saved.data:
                raise RuntimeError("Role changed during update")

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

    clear_role_conversation(context)

    clear_permission_cache(
        target_id
    )

    context.admin_data.pop(
        "role_target_id",
        None,
    )

    context.admin_data.pop(
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

    return ConversationHandler.END


# ============================================================
# Manage role
# ============================================================

async def role_manage(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await has_permission(
        query.from_user.id,
        PERMISSION_MANAGE_ADMINS,
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية لإدارة المشرفين.",
            show_alert=True,
        )
        return

    parts = query.data.split(
        ":",
        1,
    )

    if len(parts) != 2:
        await query.answer(
            "❌ بيانات غير صحيحة.",
            show_alert=True,
        )
        return

    admin_id = parts[1]

    response = (
        supabase
        .table("admins")
        .select(
            "id, telegram_id, role, is_active"
        )
        .eq(
            "id",
            admin_id,
        )
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

    current_role = admin.get(
        "role"
    )

    if not admin.get("is_active"):
        await query.answer("❌ انتهت بيانات المشرف. أعد فتح القائمة.", show_alert=True)
        return

    await query.answer()

    # Owner can be viewed but never modified.
    if current_role == "owner":
        await query.edit_message_text(
            "👤 إدارة المشرف\n\n"
            f"👤 المستخدم: {identity}\n"
            "🏷️ الرتبة: 👑 Owner\n\n"
            "🔒 لا يمكن تعديل أو إزالة رتبة Owner.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ رجوع",
                        callback_data="admin_roles",
                    )
                ],
            ]),
        )
        return

    await query.edit_message_text(
        "👤 إدارة المشرف\n\n"
        f"👤 المستخدم: {identity}\n"
        f"🏷️ الرتبة: "
        f"{ROLE_NAMES.get(current_role, current_role)}\n\n"
        "اختر العملية:",
        reply_markup=InlineKeyboardMarkup([row for row in [
            [
                InlineKeyboardButton(
                    "🛡️ تحويل إلى Admin",
                    callback_data=(
                        f"change_role:"
                        f"{admin['telegram_id']}:admin:{current_role}:{query.from_user.id}"
                    ),
                )
            ] if current_role != "admin" else [],
            [
                InlineKeyboardButton(
                    "🔧 تحويل إلى Moderator",
                    callback_data=(
                        f"change_role:"
                        f"{admin['telegram_id']}:moderator:{current_role}:{query.from_user.id}"
                    ),
                )
            ] if current_role != "moderator" else [],
            [
                InlineKeyboardButton(
                    "❌ إزالة الرتبة",
                    callback_data=(
                        f"remove_role:"
                        f"{admin['telegram_id']}:{current_role}:{query.from_user.id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="admin_roles",
                )
            ],
        ] if row]),
    )


# ============================================================
# Change role
# ============================================================

async def change_role(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await has_permission(
        query.from_user.id,
        PERMISSION_MANAGE_ADMINS,
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية لإدارة المشرفين.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    if len(parts) != 5 or not parts[1].isdigit():
        await query.answer(
            "❌ بيانات الرتبة غير صحيحة.",
            show_alert=True,
        )
        return

    if not await require_callback_owner(query):
        return

    target_id = parts[1]
    role = parts[2]
    expected_role = parts[3]

    if role not in {
        "admin",
        "moderator",
    }:
        await query.answer(
            "❌ لا يمكن تعيين هذه الرتبة.",
            show_alert=True,
        )
        return

    try:
        existing = (
            supabase
            .table("admins")
            .select(
                "id, telegram_id, role, is_active"
            )
            .eq(
                "telegram_id",
                target_id,
            )
            .limit(1)
            .execute()
        )

        rows = existing.data or []

        if not rows:
            await query.answer(
                "❌ المشرف غير موجود.",
                show_alert=True,
            )
            return

        admin = rows[0]

        if admin.get("role") == "owner":
            await query.answer(
                "⛔ لا يمكن تعديل رتبة Owner.",
                show_alert=True,
            )
            return

        if not admin.get("is_active") or admin.get("role") != expected_role or role == expected_role:
            await query.answer("❌ هذا الاختيار قديم أو الرتبة مطبقة بالفعل. أعد فتح القائمة.", show_alert=True)
            return

        saved = (
            supabase
            .table("admins")
            .update({
                "role": role,
                "is_active": True,
            })
            .eq(
                "id",
                admin["id"],
            )
            .eq("telegram_id", target_id)
            .eq("role", expected_role)
            .eq("is_active", True)
            .execute()
        )
        if not saved.data:
            await query.answer("❌ تغيرت بيانات المشرف. أعد فتح القائمة.", show_alert=True)
            return

        clear_permission_cache(
            admin["telegram_id"]
        )

    except Exception as exc:
        print(
            "ROLE CHANGE ERROR:",
            type(exc).__name__,
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


# ============================================================
# Remove role
# ============================================================

async def remove_role(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    if not await has_permission(
        query.from_user.id,
        PERMISSION_MANAGE_ADMINS,
        refresh=True,
    ):
        await query.answer(
            "⛔ ليس لديك صلاحية لإدارة المشرفين.",
            show_alert=True,
        )
        return

    parts = query.data.split(":")

    if len(parts) != 4 or not parts[1].isdigit():
        await query.answer(
            "❌ بيانات غير صحيحة.",
            show_alert=True,
        )
        return

    if not await require_callback_owner(query):
        return

    target_id = parts[1]
    expected_role = parts[2]

    try:
        existing = (
            supabase
            .table("admins")
            .select(
                "id, telegram_id, role, is_active"
            )
            .eq(
                "telegram_id",
                target_id,
            )
            .limit(1)
            .execute()
        )

        rows = existing.data or []

        if not rows:
            await query.answer(
                "❌ المشرف غير موجود.",
                show_alert=True,
            )
            return

        admin = rows[0]

        if admin.get("role") == "owner":
            await query.answer(
                "⛔ لا يمكن إزالة رتبة Owner.",
                show_alert=True,
            )
            return

        if not admin.get("is_active") or admin.get("role") != expected_role:
            await query.answer("❌ هذا الاختيار قديم. أعد فتح القائمة.", show_alert=True)
            return

        saved = (
            supabase
            .table("admins")
            .update({
                "is_active": False,
            })
            .eq(
                "id",
                admin["id"],
            )
            .eq("telegram_id", target_id)
            .eq("role", expected_role)
            .eq("is_active", True)
            .execute()
        )
        if not saved.data:
            await query.answer("❌ تغيرت بيانات المشرف. أعد فتح القائمة.", show_alert=True)
            return

        clear_permission_cache(
            admin["telegram_id"]
        )

    except Exception as exc:
        print(
            "ROLE REMOVE ERROR:",
            type(exc).__name__,
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


# ============================================================
# Cancel role operation
# ============================================================

async def cancel_role(update, context):
    user = update.effective_user
    if user is None or context.admin_data.get("role_owner_id") != user.id:
        return None
    allowed = await has_permission(user.id, PERMISSION_MANAGE_ADMINS, refresh=True)
    clear_role_conversation(context)
    if update.message:
        await update.message.reply_text(
            "❌ تم إلغاء العملية." if allowed else "⛔ ليس لديك صلاحية."
        )
    return ConversationHandler.END


# ============================================================
# Role conversation handler
# ============================================================

async def back_from_role_operation(update, context):
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return None
    if context.admin_data.get("role_owner_id") != user.id:
        await query.answer("⛔ هذه العملية ليست لك.", show_alert=True)
        return None
    prefix = (query.data or "").split(":", 1)[0]
    if not await has_permission(user.id, PERMISSION_MANAGE_ADMINS, refresh=True):
        clear_role_conversation(context)
        await query.answer("⛔ ليس لديك صلاحية.", show_alert=True)
        return ConversationHandler.END

    from bot.handlers.admin import admin_back
    navigation = {
        "admin_roles": admin_roles,
        "admin_tools": admin_tools,
        "admin_back": admin_back,
    }
    clear_role_conversation(context)
    await navigation[prefix](update, context)
    return ConversationHandler.END


def role_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                role_add_start,
                pattern=r"^role_add:",
            )
        ],
        states={
            ROLE_SELECTION: [CallbackQueryHandler(set_role, pattern=r"^set_role:")],
            ROLE_USERNAME: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    role_receive_username,
                )
            ]
        },
        fallbacks=[
            CallbackQueryHandler(back_from_role_operation, pattern='^(?:admin_roles$|admin_tools$|admin_back$)'),
            CommandHandler(
                "cancel",
                cancel_role,
            )
        ],
        allow_reentry=True,
    )
