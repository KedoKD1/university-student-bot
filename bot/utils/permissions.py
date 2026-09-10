from telegram import Update
from telegram.ext import ContextTypes

from bot.database.client import supabase


# ============================================================
# Roles
# ============================================================

ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_MODERATOR = "moderator"

VALID_ROLES = {
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_MODERATOR,
}


# ============================================================
# Permission names
# ============================================================

PERMISSION_VIEW_ADMIN = "view_admin"

PERMISSION_MANAGE_SUBJECTS = "manage_subjects"
PERMISSION_MANAGE_FILES = "manage_files"
PERMISSION_MANAGE_SUMMARIES = "manage_summaries"
PERMISSION_MANAGE_DRAWINGS = "manage_drawings"
PERMISSION_MANAGE_SCHEDULES = "manage_schedules"
PERMISSION_MANAGE_GRADES = "manage_grades"

PERMISSION_MANAGE_DESCRIPTIONS = "manage_descriptions"

PERMISSION_VIEW_STATISTICS = "view_statistics"

PERMISSION_MANAGE_ADMINS = "manage_admins"
PERMISSION_MANAGE_PERMISSIONS = "manage_permissions"

PERMISSION_MANAGE_ANNOUNCEMENTS = "manage_announcements"
PERMISSION_MANAGE_SETTINGS = "manage_settings"


# ============================================================
# Default role permissions
# ============================================================

DEFAULT_ROLE_PERMISSIONS = {
    ROLE_OWNER: {
        PERMISSION_VIEW_ADMIN,
        PERMISSION_MANAGE_SUBJECTS,
        PERMISSION_MANAGE_FILES,
        PERMISSION_MANAGE_SUMMARIES,
        PERMISSION_MANAGE_DRAWINGS,
        PERMISSION_MANAGE_SCHEDULES,
        PERMISSION_MANAGE_GRADES,
        PERMISSION_MANAGE_DESCRIPTIONS,
        PERMISSION_VIEW_STATISTICS,
        PERMISSION_MANAGE_ADMINS,
        PERMISSION_MANAGE_PERMISSIONS,
        PERMISSION_MANAGE_ANNOUNCEMENTS,
        PERMISSION_MANAGE_SETTINGS,
    },

    ROLE_ADMIN: {
        PERMISSION_VIEW_ADMIN,
        PERMISSION_MANAGE_SUBJECTS,
        PERMISSION_MANAGE_FILES,
        PERMISSION_MANAGE_SUMMARIES,
        PERMISSION_MANAGE_DRAWINGS,
        PERMISSION_MANAGE_SCHEDULES,
        PERMISSION_MANAGE_GRADES,
        PERMISSION_MANAGE_DESCRIPTIONS,
        PERMISSION_VIEW_STATISTICS,
        PERMISSION_MANAGE_ANNOUNCEMENTS,
        PERMISSION_MANAGE_SETTINGS,
    },

    ROLE_MODERATOR: {
        PERMISSION_VIEW_ADMIN,
        PERMISSION_MANAGE_SUBJECTS,
        PERMISSION_MANAGE_FILES,
        PERMISSION_MANAGE_SUMMARIES,
        PERMISSION_MANAGE_DRAWINGS,
        PERMISSION_MANAGE_SCHEDULES,
        PERMISSION_MANAGE_GRADES,
        PERMISSION_MANAGE_DESCRIPTIONS,
    },
}


# ============================================================
# Get admin
# ============================================================

async def get_admin(user_id: int):
    try:
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

        admins = response.data or []

        if not admins:
            return None

        return admins[0]

    except Exception as exc:
        print(
            "GET ADMIN ERROR:",
            type(exc).__name__,
            exc,
        )
        return None


# ============================================================
# Get role
# ============================================================

async def get_role(user_id: int):
    admin = await get_admin(user_id)

    if not admin:
        return None

    role = admin.get("role")

    if role not in VALID_ROLES:
        return None

    return role


# ============================================================
# Is admin
# ============================================================

async def is_admin(user_id: int) -> bool:
    return await get_admin(user_id) is not None


# ============================================================
# Is owner
# ============================================================

async def is_owner(user_id: int) -> bool:
    role = await get_role(user_id)

    return role == ROLE_OWNER


# ============================================================
# Permission check
# ============================================================

async def has_permission(
    user_id: int,
    permission: str,
) -> bool:

    role = await get_role(user_id)

    if role is None:
        return False

    if role == ROLE_OWNER:
        return True

    try:
        response = (
            supabase
            .table("role_permissions")
            .select(
                "permission_id, permissions(name)"
            )
            .eq("role", role)
            .execute()
        )

        rows = response.data or []

        for row in rows:
            permission_data = row.get(
                "permissions"
            )

            if isinstance(
                permission_data,
                dict,
            ):
                if (
                    permission_data.get("name")
                    == permission
                ):
                    return True

    except Exception as exc:
        print(
            "PERMISSION DATABASE ERROR:",
            type(exc).__name__,
            exc,
        )

    return permission in DEFAULT_ROLE_PERMISSIONS.get(
        role,
        set(),
    )


# ============================================================
# Require permission
# ============================================================

async def require_permission(
    update: Update,
    permission: str,
) -> bool:

    user = update.effective_user

    if user is None:
        return False

    allowed = await has_permission(
        user.id,
        permission,
    )

    if allowed:
        return True

    query = update.callback_query

    if query is not None:
        try:
            await query.answer(
                "⛔ ليس لديك صلاحية لتنفيذ هذا الإجراء.",
                show_alert=True,
            )
        except Exception:
            pass

    elif update.message is not None:
        try:
            await update.message.reply_text(
                "⛔ ليس لديك صلاحية لتنفيذ هذا الإجراء."
            )
        except Exception:
            pass

    return False


# ============================================================
# Permission required by callback prefix
# ============================================================

CALLBACK_PERMISSIONS = {

    # Subjects
    "admin_subjects": PERMISSION_MANAGE_SUBJECTS,
    "admin_stage_subjects": PERMISSION_MANAGE_SUBJECTS,
    "manage_stage": PERMISSION_MANAGE_SUBJECTS,
    "manage_subject": PERMISSION_MANAGE_SUBJECTS,
    "disable_subject": PERMISSION_MANAGE_SUBJECTS,
    "enable_subject": PERMISSION_MANAGE_SUBJECTS,

    # Files
    "admin_files": PERMISSION_MANAGE_FILES,
    "admin_file_stage": PERMISSION_MANAGE_FILES,
    "admin_file_subject": PERMISSION_MANAGE_FILES,
    "admin_file_subjects": PERMISSION_MANAGE_FILES,
    "admin_file_sections": PERMISSION_MANAGE_FILES,
    "admin_file_section": PERMISSION_MANAGE_FILES,
    "admin_file_list": PERMISSION_MANAGE_FILES,
    "manage_file": PERMISSION_MANAGE_FILES,
    "disable_file": PERMISSION_MANAGE_FILES,
    "enable_file": PERMISSION_MANAGE_FILES,
    "delete_file": PERMISSION_MANAGE_FILES,
    "confirm_delete_file": PERMISSION_MANAGE_FILES,

    # Summaries
    "admin_summaries": PERMISSION_MANAGE_SUMMARIES,
    "admin_summary_stage": PERMISSION_MANAGE_SUMMARIES,
    "admin_summary_subject": PERMISSION_MANAGE_SUMMARIES,
    "admin_summary_subjects": PERMISSION_MANAGE_SUMMARIES,
    "admin_summary_sections": PERMISSION_MANAGE_SUMMARIES,
    "admin_summary_section": PERMISSION_MANAGE_SUMMARIES,
    "admin_summary_list": PERMISSION_MANAGE_SUMMARIES,
    "manage_summary": PERMISSION_MANAGE_SUMMARIES,
    "disable_summary": PERMISSION_MANAGE_SUMMARIES,
    "enable_summary": PERMISSION_MANAGE_SUMMARIES,
    "delete_summary": PERMISSION_MANAGE_SUMMARIES,
    "confirm_delete_summary": PERMISSION_MANAGE_SUMMARIES,

    # Drawings
    "admin_drawings": PERMISSION_MANAGE_DRAWINGS,
    "admin_drawing_stage": PERMISSION_MANAGE_DRAWINGS,
    "admin_drawing_subject": PERMISSION_MANAGE_DRAWINGS,
    "admin_drawing_subjects": PERMISSION_MANAGE_DRAWINGS,
    "admin_drawing_sections": PERMISSION_MANAGE_DRAWINGS,
    "admin_drawing_section": PERMISSION_MANAGE_DRAWINGS,
    "admin_drawing_list": PERMISSION_MANAGE_DRAWINGS,
    "manage_drawing": PERMISSION_MANAGE_DRAWINGS,
    "disable_drawing": PERMISSION_MANAGE_DRAWINGS,
    "enable_drawing": PERMISSION_MANAGE_DRAWINGS,
    "delete_drawing": PERMISSION_MANAGE_DRAWINGS,
    "confirm_delete_drawing": PERMISSION_MANAGE_DRAWINGS,

    # Schedules
    "admin_schedules": PERMISSION_MANAGE_SCHEDULES,
    "admin_schedule_stage": PERMISSION_MANAGE_SCHEDULES,
    "delete_schedule": PERMISSION_MANAGE_SCHEDULES,

    # Grades
    "admin_grades": PERMISSION_MANAGE_GRADES,
    "admin_grade_stage": PERMISSION_MANAGE_GRADES,
    "admin_grade_list": PERMISSION_MANAGE_GRADES,
    "manage_grade": PERMISSION_MANAGE_GRADES,
    "add_grade": PERMISSION_MANAGE_GRADES,
    "edit_grade": PERMISSION_MANAGE_GRADES,
    "replace_grade": PERMISSION_MANAGE_GRADES,
    "disable_grade": PERMISSION_MANAGE_GRADES,
    "enable_grade": PERMISSION_MANAGE_GRADES,
    "delete_grade": PERMISSION_MANAGE_GRADES,
    "confirm_delete_grade": PERMISSION_MANAGE_GRADES,

    # Descriptions
    "bundle_descriptions": PERMISSION_MANAGE_DESCRIPTIONS,
    "bundle_desc_type": PERMISSION_MANAGE_DESCRIPTIONS,
    "bundle_desc_stage": PERMISSION_MANAGE_DESCRIPTIONS,
    "bundle_desc_subject": PERMISSION_MANAGE_DESCRIPTIONS,

    # Statistics
    "bot_status": PERMISSION_VIEW_STATISTICS,

    # Admin management
    "admin_roles": PERMISSION_MANAGE_ADMINS,
    "role_manage": PERMISSION_MANAGE_ADMINS,
    "change_role": PERMISSION_MANAGE_ADMINS,
    "remove_role": PERMISSION_MANAGE_ADMINS,
    "set_role": PERMISSION_MANAGE_ADMINS,

    # Future sections
    "admin_announcements": PERMISSION_MANAGE_ANNOUNCEMENTS,
    "admin_settings": PERMISSION_MANAGE_SETTINGS,
}


def permission_for_callback(callback_data: str):
    if not callback_data:
        return None

    prefix = callback_data.split(
        ":",
        1,
    )[0]

    return CALLBACK_PERMISSIONS.get(
        prefix
    )
