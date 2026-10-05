import asyncio
import copy
import unittest
import warnings
from types import SimpleNamespace
from unittest.mock import patch

from telegram import Document, PhotoSize
from telegram.ext import ApplicationHandlerStop, ConversationHandler
from telegram.warnings import PTBUserWarning

from tests.admin_support import Database, MODULES, context, permissions, update
from bot.utils.permission_guard import permission_guard


class AdminSecurityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database()
        permissions.clear_permission_cache()
        for module in [permissions, *MODULES.values()]:
            replacement = patch.object(module, "supabase", self.db)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.addCleanup(permissions.clear_permission_cache)
        self.subjects = MODULES["admin_subjects"]
        self.db.grant("admin", permissions.PERMISSION_MANAGE_SUBJECTS)

    async def test_owner_admin_moderator_and_student_permissions_are_db_driven(self):
        p = permissions.PERMISSION_MANAGE_SUBJECTS
        for role, user_id in [("admin", 102), ("moderator", 103)]:
            for granted in (False, True):
                with self.subTest(role=role, granted=granted):
                    self.db.grant(role, *([p] if granted else []))
                    self.assertEqual(await permissions.has_permission(user_id, p, refresh=True), granted)
                    ctx = context()
                    result = await self.subjects.start_add_subject(update(user_id, ctx, data=f"add_subject:7:{user_id}"), ctx)
                    self.assertEqual(result, self.subjects.ADD_NAME if granted else None)
        self.assertTrue(await permissions.has_permission(101, p, refresh=True))
        self.assertFalse(await permissions.has_permission(105, p, refresh=True))
        self.db.rows["admins"][1]["is_active"] = False
        self.assertFalse(await permissions.has_permission(102, p, refresh=True))

    async def test_refresh_blocks_cached_permission_and_role_revocation(self):
        p = permissions.PERMISSION_MANAGE_SUBJECTS
        self.assertTrue(await permissions.has_permission(102, p))
        self.db.grant("admin")
        self.assertFalse(await permissions.has_permission(102, p, refresh=True))
        self.db.rows["admins"][0]["is_active"] = False
        self.assertFalse(await permissions.has_permission(101, p, refresh=True))

    async def test_subject_add_and_edit_complete_and_clear_all_operation_data(self):
        ctx = context({"unrelated": "preserved"})
        self.assertEqual(await self.subjects.start_add_subject(update(102, ctx, data="add_subject:7:102"), ctx), self.subjects.ADD_NAME)
        self.assertEqual(await self.subjects.receive_add_name(update(102, ctx, text="  مادة  جديدة "), ctx), self.subjects.ADD_DESCRIPTION)
        self.assertEqual(await self.subjects.receive_add_description(update(102, ctx, text="-"), ctx), self.subjects.ADD_ORDER)
        self.assertEqual(await self.subjects.receive_add_order(update(102, ctx, text="2"), ctx), ConversationHandler.END)
        added = self.db.rows["subjects"][-1]
        self.assertEqual(added["name"], "مادة جديدة")
        self.assertIsNone(added["description"])
        self.assertEqual(ctx.admin_data, {"unrelated": "preserved"})
        self.assertEqual(await self.subjects.start_edit_subject(update(102, ctx, data=f"edit_subject:{added['id']}:7:102"), ctx), self.subjects.EDIT_NAME)
        await self.subjects.receive_edit_name(update(102, ctx, text="اسم جديد"), ctx)
        await self.subjects.receive_edit_description(update(102, ctx, text="وصف"), ctx)
        self.assertEqual(await self.subjects.receive_edit_order(update(102, ctx, text="3"), ctx), ConversationHandler.END)
        self.assertEqual(added["name"], "اسم جديد")
        self.assertEqual(ctx.admin_data, {"unrelated": "preserved"})

    async def test_every_subject_step_blocks_revocation_and_foreign_owner(self):
        steps = [("receive_add_name", 0), ("receive_add_description", 1), ("receive_add_order", 2),
                 ("receive_edit_name", 3), ("receive_edit_description", 4), ("receive_edit_order", 5)]
        for name, state in steps:
            data = {"admin_subject_owner_id": 102, "admin_subject_stage_id": 7,
                    "admin_subject_id": 17, "admin_subject_name": "Name"}
            with self.subTest(step=name):
                ctx = context(copy.deepcopy(data))
                self.assertEqual(await getattr(self.subjects, name)(update(104, ctx, text="2"), ctx), state)
                self.assertEqual(ctx.admin_data, data)
                self.db.grant("admin")
                self.assertEqual(await getattr(self.subjects, name)(update(102, ctx, text="2"), ctx), ConversationHandler.END)
                self.assertEqual(ctx.admin_data, {})
                self.assertFalse(self.db.writes)
                self.db.grant("admin", permissions.PERMISSION_MANAGE_SUBJECTS)

    async def test_subject_missing_session_data_cannot_write(self):
        ctx = context({"admin_subject_stage_id": 7, "admin_subject_name": "Name"})
        self.assertEqual(await self.subjects.receive_add_order(update(102, ctx, text="1"), ctx), ConversationHandler.END)
        self.assertEqual(ctx.admin_data, {})
        self.assertFalse(self.db.writes)

    async def test_subject_cancellation_cannot_clear_foreign_session(self):
        ctx = context({"admin_subject_owner_id": 102, "admin_subject_stage_id": 7})
        before = copy.deepcopy(ctx.admin_data)
        self.assertIsNone(await self.subjects.cancel_subject_operation(update(104, ctx, text="/cancel"), ctx))
        self.assertEqual(ctx.admin_data, before)
        self.assertEqual(await self.subjects.cancel_subject_operation(update(102, ctx, text="/cancel"), ctx), ConversationHandler.END)
        self.assertEqual(ctx.admin_data, {})

    async def test_subject_database_failures_and_deleted_rows_clear_without_success(self):
        for failure in [("subjects", "select"), ("subjects", "insert")]:
            with self.subTest(failure=failure):
                ctx = context()
                await self.subjects.start_add_subject(update(102, ctx, data="add_subject:7:102"), ctx)
                self.db.failure = failure
                if failure[1] == "select":
                    result = await self.subjects.receive_add_name(update(102, ctx, text="new"), ctx)
                else:
                    ctx.admin_data["admin_subject_name"] = "new"
                    ctx.admin_data["admin_subject_description"] = None
                    result = await self.subjects.receive_add_order(update(102, ctx, text="1"), ctx)
                self.assertEqual(result, ConversationHandler.END)
                self.assertEqual(ctx.admin_data, {})
                self.assertNotIn("internal database detail", str(ctx.bot.send_message.await_args_list))
                self.db.failure = None
        ctx = context({"admin_subject_owner_id": 102, "admin_subject_stage_id": 7,
                       "admin_subject_id": 17, "admin_subject_name": "new", "admin_subject_description": None})
        self.db.rows["subjects"] = []
        await self.subjects.receive_edit_order(update(102, ctx, text="1"), ctx)
        self.assertEqual(ctx.admin_data, {})
        self.assertNotIn("✅", str(ctx.bot.send_message.await_args_list))

    async def test_subject_malformed_and_foreign_inline_entries_preserve_operation(self):
        ctx = context({"admin_subject_owner_id": 102, "admin_subject_stage_id": 7})
        before = copy.deepcopy(ctx.admin_data)
        for data in ("add_subject", "add_subject::102", "add_subject:7:wrong", "add_subject:7:104"):
            self.assertIsNone(await self.subjects.start_add_subject(update(102, ctx, data=data), ctx))
            self.assertEqual(ctx.admin_data, before)

    async def test_actual_conversation_dispatch_keeps_two_admins_separate(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", PTBUserWarning)
            conv = self.subjects.subject_conversation_handler()
        contexts = {user_id: context() for user_id in (102, 104)}
        app = SimpleNamespace(bot=contexts[102].bot)

        async def dispatch(user_id, **kwargs):
            ctx = contexts[user_id]
            incoming = update(user_id, ctx, **kwargs)
            check = conv.check_update(incoming)
            self.assertIsNotNone(check)
            await conv.handle_update(incoming, app, check, ctx)

        await asyncio.gather(*(dispatch(user_id, data=f"add_subject:7:{user_id}") for user_id in contexts))
        await asyncio.gather(dispatch(102, text="First"), dispatch(104, text="Second"))
        self.assertEqual(contexts[102].admin_data["admin_subject_name"], "First")
        self.assertEqual(contexts[104].admin_data["admin_subject_name"], "Second")
        await dispatch(104, text="/cancel")
        self.assertNotIn((700, 104), conv._conversations)
        self.assertEqual(conv._conversations[(700, 102)], self.subjects.ADD_DESCRIPTION)
        await dispatch(102, data="admin_subjects")
        self.assertNotIn((700, 102), conv._conversations)
        self.assertEqual(contexts[102].admin_data, {})

    async def test_other_conversations_reject_another_admins_inline_buttons(self):
        cases = [("admin_files", "start_add_file", "add_file:7:17:practical:102"),
                 ("admin_summaries", "start_edit_summary", "edit_summary:1:7:17:practical:102"),
                 ("admin_exam_dates", "add_exam_type", "add_exam_type:final:102"),
                 ("admin_tools", "role_add_start", "role_add:102"),
                 ("admin_tools", "set_role", "set_role:admin:105:102"),
                 ("bundle_descriptions", "choose_description_type", "bundle_desc_type:files:102"),
                 ("admin_notifications", "notification_confirm", "notify_confirm:102"),
                 ("admin_notifications", "notification_cancel", "notify_cancel:102"),
                 ("admin_settings", "setting_predefined_value", "setting_value:true:102"),
                 ("admin_settings", "settings_cancel", "setting_cancel:102")]
        for module, function, data in cases:
            with self.subTest(handler=function):
                ctx = context({"unrelated": "preserve", "admin_subject_owner_id": 104})
                before = copy.deepcopy(ctx.admin_data)
                self.assertIsNone(await getattr(MODULES[module], function)(update(104, ctx, data=data), ctx))
                self.assertEqual(ctx.admin_data, before)
                self.assertFalse(self.db.writes)

    async def test_exam_controls_require_a_current_owned_session(self):
        module = MODULES["admin_exam_dates"]
        cases = [
            ("add_exam_type", "add_exam_type:final:102"),
            ("add_exam_subject", "exam_subject:none:102"),
            ("edit_exam_type", "edit_exam_type:final:102"),
            ("edit_exam_subject", "edit_exam_subject:none:102"),
        ]
        for name, data in cases:
            for revoked in (False, True):
                with self.subTest(handler=name, revoked=revoked):
                    self.db.grant("admin", *([] if revoked else [permissions.PERMISSION_MANAGE_EXAMS]))
                    ctx = context({"exam_stage_id": 7, "exam_type": "final", "unrelated": "preserve"})
                    if revoked:
                        ctx.admin_data["admin_exam_owner_id"] = 102
                    result = await getattr(module, name)(update(102, ctx, data=data), ctx)
                    self.assertEqual(result, ConversationHandler.END)
                    self.assertEqual(ctx.admin_data, {"unrelated": "preserve"})
                    self.assertFalse(self.db.writes)

    async def test_role_lookup_selection_and_stale_target(self):
        tools = MODULES["admin_tools"]
        self.db.grant("admin", permissions.PERMISSION_MANAGE_ADMINS)
        self.db.rows["telegram_users"] = [{"telegram_id": 105, "username": "user_name"}]
        ctx = context()
        await tools.role_add_start(update(102, ctx, data="role_add:102"), ctx)
        self.assertEqual(await tools.role_receive_username(update(102, ctx, text="@user_name"), ctx), tools.ROLE_SELECTION)
        self.assertEqual(ctx.admin_data["role_target_id"], 105)
        await tools.set_role(update(102, ctx, data="set_role:admin:106:102"), ctx)
        self.assertFalse(self.db.writes)
        self.assertEqual(await tools.set_role(update(102, ctx, data="set_role:admin:105:102"), ctx), ConversationHandler.END)
        self.assertTrue(any(row["telegram_id"] == 105 for row in self.db.rows["admins"]))
        self.assertEqual(ctx.admin_data, {})

    async def test_role_lookup_rechecks_revoked_permission(self):
        tools = MODULES["admin_tools"]
        self.db.grant("admin", permissions.PERMISSION_MANAGE_ADMINS)
        ctx = context()
        await tools.role_add_start(update(102, ctx, data="role_add:102"), ctx)
        self.db.grant("admin")
        self.assertEqual(await tools.role_receive_username(update(102, ctx, text="@username"), ctx), ConversationHandler.END)
        self.assertNotIn("telegram_users", self.db.reads)
        self.assertEqual(ctx.admin_data, {})

    async def test_file_and_summary_entry_buttons_start_the_correct_operation(self):
        for module_name, kind, owner_key, permission in [
            ("admin_files", "file", "admin_files_owner_id", permissions.PERMISSION_MANAGE_FILES),
            ("admin_summaries", "summary", "admin_summary_owner_id", permissions.PERMISSION_MANAGE_SUMMARIES),
        ]:
            with self.subTest(module=module_name):
                self.db.grant("admin", permission)
                module = MODULES[module_name]
                ctx = context({owner_key: 102})
                keyboard = getattr(module, f"{kind}_list_keyboard")([], 7, 17, "practical", 102)
                callback = keyboard.inline_keyboard[0][0].callback_data
                result = await getattr(module, f"start_add_{kind}")(update(102, ctx, data=callback), ctx)
                self.assertEqual(result, getattr(module, f"ADD_{kind.upper()}_NAME"))
                self.assertEqual(ctx.admin_data[f"admin_{kind}_stage_id"], "7")

    async def test_summary_manage_keyboard_preserves_actual_stage(self):
        self.db.grant("admin", permissions.PERMISSION_MANAGE_SUMMARIES)
        self.db.rows["summaries"] = [{"id": 1, "subject_id": 17, "section_type": "practical",
                                     "name": "Summary", "is_active": True}]
        ctx = context({"admin_summary_owner_id": 102})
        await MODULES["admin_summaries"].manage_summary(update(102, ctx, data="manage_summary:1:17:practical"), ctx)
        buttons = ctx.bot.edit_message_text.await_args.kwargs["reply_markup"].inline_keyboard
        self.assertEqual(buttons[0][0].callback_data, "edit_summary:1:7:17:practical:102")

    async def test_exam_add_edit_and_delete_return_to_the_correct_list(self):
        exams = MODULES["admin_exam_dates"]
        self.db.grant("admin", permissions.PERMISSION_MANAGE_EXAMS)
        ctx = context()
        self.assertEqual(await exams.add_exam_start(update(102, ctx, data="add_exam:7:102"), ctx), exams.ADD_EXAM_TYPE)
        await exams.add_exam_type(update(102, ctx, data="add_exam_type:final:102"), ctx)
        await exams.add_exam_title(update(102, ctx, text="Final"), ctx)
        self.assertEqual(await exams.add_exam_subject(update(102, ctx, data="exam_subject:17:102"), ctx), exams.ADD_EXAM_DATE)
        await exams.add_exam_date(update(102, ctx, text="2026-10-15"), ctx)
        await exams.add_exam_time(update(102, ctx, text="09:30"), ctx)
        self.assertEqual(await exams.add_exam_notes(update(102, ctx, text="-"), ctx), ConversationHandler.END)
        row = self.db.rows["exam_dates"][0]
        self.assertEqual(row["subject_id"], 17)
        self.assertEqual(ctx.admin_data, {})
        await exams.edit_exam_start(update(102, ctx, data=f"edit_exam:{row['id']}:7:102"), ctx)
        self.assertEqual(await exams.edit_exam_type(update(102, ctx, data="edit_exam_type:midterm:102"), ctx), exams.EDIT_EXAM_TITLE)
        await exams.edit_exam_title(update(102, ctx, text="Midterm"), ctx)
        await exams.edit_exam_subject(update(102, ctx, data="edit_exam_subject:none:102"), ctx)
        await exams.edit_exam_date(update(102, ctx, text="2026-10-16"), ctx)
        await exams.edit_exam_time(update(102, ctx, text="-"), ctx)
        await exams.edit_exam_notes(update(102, ctx, text="-"), ctx)
        self.assertEqual(row["title"], "Midterm")
        await exams.confirm_delete_exam(update(102, ctx, data=f"confirm_delete_exam:{row['id']}:7"), ctx)
        self.assertFalse(row["is_active"])
        self.assertTrue(row["deleted_at"])
        self.assertIn("عدد المواعيد: 0", ctx.bot.edit_message_text.await_args.kwargs["text"])

    async def test_description_flow_requires_owner_and_cleans_up(self):
        module = MODULES["bundle_descriptions"]
        self.db.grant("admin", permissions.PERMISSION_MANAGE_DESCRIPTIONS)
        ctx = context()
        self.assertEqual(await module.choose_description_type(update(102, ctx, data="bundle_desc_type:files:102"), ctx), module.DESC_STAGE)
        self.assertEqual(await module.choose_description_stage(update(102, ctx, data="bundle_desc_stage:7:102"), ctx), module.DESC_SUBJECT)
        self.assertEqual(await module.choose_description_subject(update(102, ctx, data="bundle_desc_subject:17:102"), ctx), module.DESC_TEXT)
        self.assertEqual(await module.receive_description(update(102, ctx, text="description"), ctx), ConversationHandler.END)
        self.assertEqual(ctx.admin_data, {})
        ctx.admin_data.update(bundle_desc_type="files", bundle_desc_stage_id=7, bundle_desc_subject_id=17)
        before = len(self.db.writes)
        await module.receive_description(update(102, ctx, text="stale"), ctx)
        self.assertEqual(len(self.db.writes), before)
        self.assertEqual(ctx.admin_data, {})

    async def test_settings_edit_save_and_cancel_keep_owner(self):
        module = MODULES["admin_settings"]
        self.db.grant("admin", permissions.PERMISSION_MANAGE_SETTINGS)
        ctx = context()
        await module.admin_settings(update(102, ctx, data="admin_settings"), ctx)
        self.assertEqual(await module.setting_edit(update(102, ctx, data="setting_edit:maintenance_mode:102"), ctx), module.SETTINGS_VALUE)
        self.assertEqual(await module.setting_predefined_value(update(102, ctx, data="setting_value:true:102"), ctx), module.SETTINGS_MENU)
        self.assertEqual(self.db.rows["settings"][0]["value"], "true")
        self.assertEqual(ctx.admin_data["admin_setting"]["owner_id"], 102)
        await module.settings_cancel(update(102, ctx, data="setting_cancel:102"), ctx)
        self.assertEqual(ctx.admin_data, {})

    async def test_notification_confirm_dispatch_uses_owner_bound_control(self):
        module = MODULES["admin_notifications"]
        self.db.grant("admin", permissions.PERMISSION_MANAGE_ANNOUNCEMENTS)
        ctx = context()
        await module.admin_notifications(update(102, ctx, data="admin_announcements"), ctx)
        await module.notification_audience(update(102, ctx, data="notify_audience:all:102"), ctx)
        await module.notification_title(update(102, ctx, text="Title"), ctx)
        await module.notification_content(update(102, ctx, text="Content"), ctx)
        buttons = ctx.bot.send_message.await_args.kwargs["reply_markup"].inline_keyboard
        self.assertEqual(buttons[0][0].callback_data, "notify_confirm:102")
        with patch.object(module, "_send_notification", return_value=(1, 1, 0, "sent")) as send:
            result = await module.notification_confirm(update(102, ctx, data="notify_confirm:102"), ctx)
        self.assertEqual(result, ConversationHandler.END)
        send.assert_awaited_once()
        self.assertEqual(ctx.admin_data, {})

    async def test_revocation_blocks_every_other_conversation_write(self):
        ctx_data = {
            "admin_files_owner_id": 102, "admin_file_stage_id": 7, "admin_file_subject_id": 17,
            "admin_file_section_type": "practical", "admin_file_name": "file", "admin_file_order": 1,
            "admin_summary_owner_id": 102, "admin_summary_stage_id": 7, "admin_summary_subject_id": 17,
            "admin_summary_section_type": "practical", "admin_summary_id": 1, "admin_summary_name": "summary",
            "admin_drawing_owner_id": 102, "admin_drawing_stage_id": 7, "admin_drawing_subject_id": 17,
            "admin_drawing_section_type": "practical", "admin_drawing_id": 1, "admin_drawing_name": "drawing",
            "admin_grade_owner_id": 102, "admin_grade_stage_id": 7, "admin_grade_file_id": 1, "admin_grade_name": "grade",
            "schedule_admin_id": 102, "schedule_stage_id": 7,
            "admin_exam_owner_id": 102, "exam_stage_id": 7, "exam_type": "final", "exam_title": "Exam", "exam_date": "2026-10-15",
            "bundle_desc_owner_id": 102, "bundle_desc_type": "files", "bundle_desc_stage_id": 7, "bundle_desc_subject_id": 17,
            "role_owner_id": 102, "role_target_id": 105,
            "admin_setting": {"owner_id": 102, "key": "required_channel_id"},
            "admin_notification": {"owner_id": 102, "title": "Title", "content": "Content", "audience_type": "all_users"},
        }
        self.db.grant("admin")
        cases = [
            ("admin_files", "receive_add_file_upload", {"document": Document("offline", "unique")}),
            ("admin_summaries", "receive_edit_summary_order", {"text": "1"}),
            ("admin_drawings", "receive_edit_drawing_order", {"text": "1"}),
            ("admin_grades", "edit_grade_description", {"text": "Description"}),
            ("admin_schedules", "receive_schedule_image", {"photo": [PhotoSize("offline", "unique", 10, 10)]}),
            ("admin_exam_dates", "add_exam_notes", {"text": "-"}),
            ("bundle_descriptions", "receive_description", {"text": "Description"}),
            ("admin_tools", "set_role", {"data": "set_role:admin:105:102"}),
            ("admin_settings", "setting_value", {"text": "-100123456"}),
            ("admin_notifications", "notification_confirm", {"data": "notify_confirm:102"}),
        ]
        for module, name, incoming in cases:
            with self.subTest(handler=name):
                ctx = context(copy.deepcopy(ctx_data))
                await getattr(MODULES[module], name)(update(102, ctx, **incoming), ctx)
                self.assertFalse(self.db.writes)

    async def test_file_save_error_details_stay_out_of_telegram(self):
        self.db.grant("admin", permissions.PERMISSION_MANAGE_FILES)
        ctx = context({"admin_files_owner_id": 102, "admin_file_stage_id": 7, "admin_file_subject_id": 17,
                       "admin_file_section_type": "practical", "admin_file_name": "file", "admin_file_order": 1})
        self.db.failure = ("files", "insert")
        result = await MODULES["admin_files"].receive_add_file_upload(
            update(102, ctx, document=Document("offline", "unique")), ctx
        )
        self.assertEqual(result, ConversationHandler.END)
        self.assertNotIn("internal database detail", str(ctx.bot.send_message.await_args_list))
        self.assertNotIn("admin_file_name", ctx.admin_data)

    async def test_permission_guard_fails_closed(self):
        ctx = context()
        for incoming in [update(105, ctx, data="add_subject:7:105"),
                         SimpleNamespace(callback_query=SimpleNamespace(data="add_subject:7", from_user=None)),
                         SimpleNamespace(callback_query=SimpleNamespace(data=object()))]:
            with self.assertRaises(ApplicationHandlerStop):
                await permission_guard(incoming, ctx)
        with patch("bot.utils.permission_guard.has_permission", side_effect=RuntimeError("offline")), patch(
            "bot.utils.permission_guard.logger"
        ):
            with self.assertRaises(ApplicationHandlerStop):
                await permission_guard(update(102, ctx, data="add_subject:7:102"), ctx)
        await permission_guard(update(105, ctx, data="stage:7:105"), ctx)

    async def test_all_conversations_end_on_back_instead_of_leaving_stale_states(self):
        cases = [
            ("admin_subjects", "subject_conversation_handler", {"admin_subject_owner_id": 102}),
            ("admin_files", "file_conversation_handler", {"admin_files_owner_id": 102}),
            ("admin_summaries", "summary_conversation_handler", {"admin_summary_owner_id": 102}),
            ("admin_drawings", "drawing_conversation_handler", {"admin_drawing_owner_id": 102}),
            ("admin_schedules", "schedule_conversation_handler", {"schedule_admin_id": 102}),
            ("admin_grades", "grade_conversation_handler", {"admin_grade_owner_id": 102}),
            ("admin_exam_dates", "exam_conversation_handler", {"admin_exam_owner_id": 102}),
            ("bundle_descriptions", "bundle_description_conversation_handler", {"bundle_desc_owner_id": 102}),
            ("admin_tools", "role_conversation_handler", {"role_owner_id": 102}),
            ("admin_notifications", "notification_conversation_handler", {"admin_notification": {"owner_id": 102}}),
            ("admin_settings", "settings_conversation_handler", {"admin_setting": {"owner_id": 102}}),
        ]
        all_permissions = [value for key, value in vars(permissions).items() if key.startswith("PERMISSION_")]
        self.db.grant("admin", *all_permissions)
        for name, factory, data in cases:
            with self.subTest(conversation=name), warnings.catch_warnings():
                warnings.simplefilter("ignore", PTBUserWarning)
                conv = getattr(MODULES[name], factory)()
                conv._conversations[(700, 102)] = next(iter(conv.states))
                ctx = context(copy.deepcopy(data))
                incoming = update(102, ctx, data="admin_back")
                check = conv.check_update(incoming)
                self.assertIsNotNone(check)
                with patch("bot.handlers.admin.admin_back", return_value=None) as navigate:
                    await conv.handle_update(incoming, SimpleNamespace(bot=ctx.bot), check, ctx)
                navigate.assert_awaited_once()
                self.assertNotIn((700, 102), conv._conversations)

    async def test_foreign_back_buttons_do_not_cancel_an_active_conversation(self):
        cases = [
            ("admin_drawings", "drawing_conversation_handler", "admin_drawing_owner_id", "admin_drawing_back:102"),
            ("admin_schedules", "schedule_conversation_handler", "schedule_admin_id", "admin_schedule_back:102"),
            ("admin_grades", "grade_conversation_handler", "admin_grade_owner_id", "admin_grades_back:102"),
        ]
        for name, factory, key, callback in cases:
            with self.subTest(conversation=name), warnings.catch_warnings():
                warnings.simplefilter("ignore", PTBUserWarning)
                conv = getattr(MODULES[name], factory)()
                state = next(iter(conv.states))
                conv._conversations[(700, 104)] = state
                ctx = context({key: 104})
                incoming = update(104, ctx, data=callback)
                await conv.handle_update(incoming, SimpleNamespace(bot=ctx.bot), conv.check_update(incoming), ctx)
                self.assertEqual(conv._conversations[(700, 104)], state)
                self.assertEqual(ctx.admin_data, {key: 104})

    async def test_owner_role_cannot_be_changed_or_removed(self):
        tools = MODULES["admin_tools"]
        self.db.grant("admin", permissions.PERMISSION_MANAGE_ADMINS)
        ctx = context()
        await tools.change_role(update(102, ctx, data="change_role:1:admin"), ctx)
        await tools.remove_role(update(102, ctx, data="remove_role:1"), ctx)
        ctx.admin_data.update(role_owner_id=102, role_target_id=101)
        await tools.set_role(update(102, ctx, data="set_role:admin:101:102"), ctx)
        self.assertFalse(self.db.writes)
        self.assertEqual(self.db.rows["admins"][0]["role"], "owner")

    async def test_revoked_grade_and_schedule_steps_end_the_actual_conversation(self):
        self.db.grant("admin")
        cases = [
            ("admin_grades", "grade_conversation_handler", "admin_grade_owner_id", {"text": "Name"}),
            ("admin_schedules", "schedule_conversation_handler", "schedule_admin_id", {"photo": [PhotoSize("offline", "unique", 10, 10)]}),
        ]
        for name, factory, key, payload in cases:
            with self.subTest(conversation=name), warnings.catch_warnings():
                warnings.simplefilter("ignore", PTBUserWarning)
                conv = getattr(MODULES[name], factory)()
                conv._conversations[(700, 102)] = next(iter(conv.states))
                ctx = context({key: 102})
                incoming = update(102, ctx, **payload)
                await conv.handle_update(incoming, SimpleNamespace(bot=ctx.bot), conv.check_update(incoming), ctx)
                self.assertNotIn((700, 102), conv._conversations)
                self.assertEqual(ctx.admin_data, {})

    async def test_grade_list_navigation_works_after_success_clears_operation_owner(self):
        self.db.grant("admin", permissions.PERMISSION_MANAGE_GRADES)
        ctx = context()
        await MODULES["admin_grades"].admin_grade_list(update(102, ctx, data="admin_grade_list:7:102"), ctx)
        self.assertEqual(ctx.admin_data["admin_grade_owner_id"], 102)
        self.assertTrue(ctx.bot.edit_message_text.await_count)
        ctx = context()
        await MODULES["admin_grades"].admin_grade_list(update(104, ctx, data="admin_grade_list:7:102"), ctx)
        self.assertEqual(ctx.admin_data, {})

    async def test_deleted_summary_and_drawing_cannot_be_edited_from_stale_session(self):
        cases = [
            ("admin_summaries", "summary", "receive_edit_summary_order", "admin_summary_owner_id", permissions.PERMISSION_MANAGE_SUMMARIES),
            ("admin_drawings", "drawing", "receive_edit_drawing_order", "admin_drawing_owner_id", permissions.PERMISSION_MANAGE_DRAWINGS),
        ]
        for module, kind, name, key, permission in cases:
            with self.subTest(content=kind):
                self.db.grant("admin", permission)
                row = {"id": 1, "subject_id": 17, "name": "Original", "deleted_at": "2026-10-01"}
                table = "drawings" if kind == "drawing" else "summaries"
                self.db.rows[table] = [row]
                ctx = context({key: 102, f"admin_{kind}_stage_id": 7, f"admin_{kind}_subject_id": 17,
                               f"admin_{kind}_section_type": "practical", f"admin_{kind}_id": 1,
                               f"admin_{kind}_name": "Changed"})
                result = await getattr(MODULES[module], name)(update(102, ctx, text="1"), ctx)
                self.assertEqual(result, ConversationHandler.END)
                self.assertEqual(row["name"], "Original")
                self.assertNotIn("✅", str(ctx.bot.send_message.await_args_list))

    async def test_admin_command_refreshes_role_and_view_permission(self):
        admin = MODULES["admin"]
        ctx = context()
        self.db.grant("admin", permissions.PERMISSION_VIEW_ADMIN)
        await admin.admin_command(update(102, ctx, text="/admin"), ctx)
        self.assertIn("🛠️", ctx.bot.send_message.await_args.kwargs["text"])
        self.db.grant("admin")
        await admin.admin_command(update(102, ctx, text="/admin"), ctx)
        self.assertIn("⛔", ctx.bot.send_message.await_args.kwargs["text"])
        self.db.rows["admins"][1]["is_active"] = False
        await admin.admin_command(update(102, ctx, text="/admin"), ctx)
        self.assertIn("⛔", ctx.bot.send_message.await_args.kwargs["text"])
        await admin.admin_command(update(101, ctx, text="/admin"), ctx)
        self.assertIn("🛠️", ctx.bot.send_message.await_args.kwargs["text"])


if __name__ == "__main__":
    unittest.main()
