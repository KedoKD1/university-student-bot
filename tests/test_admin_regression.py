"""Regression checks through PTB's real Application dispatcher, without network calls."""
import copy
import unittest
import warnings
from types import SimpleNamespace
from unittest.mock import patch

from telegram.ext import Application, ApplicationHandlerStop, CallbackQueryHandler, ConversationHandler
from telegram.warnings import PTBUserWarning

from tests.admin_support import Database, MODULES, context, permissions, registered_handlers, update
from tests.test_admin_routing import produced_callbacks
from bot.utils.permission_guard import permission_guard


OWNERS = {
    "admin_subjects": {"admin_subject_owner_id": 102},
    "admin_files": {"admin_files_owner_id": 102},
    "admin_summaries": {"admin_summary_owner_id": 102},
    "admin_drawings": {"admin_drawing_owner_id": 102},
    "admin_schedules": {"schedule_admin_id": 102},
    "admin_grades": {"admin_grade_owner_id": 102},
    "admin_exam_dates": {"admin_exam_owner_id": 102},
    "bundle_descriptions": {"bundle_desc_owner_id": 102},
    "admin_tools": {"role_owner_id": 102},
    "admin_notifications": {"admin_notification": {"owner_id": 102}},
    "admin_settings": {"admin_setting": {"owner_id": 102}},
}


class AdminDispatcherRegressionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database()
        permissions.clear_permission_cache()
        self.addCleanup(permissions.clear_permission_cache)
        for module in [permissions, *MODULES.values()]:
            replacement = patch.object(module, "supabase", self.db)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.all_permissions = [value for key, value in vars(permissions).items() if key.startswith("PERMISSION_")]
        self.db.grant("admin", *self.all_permissions)
        self.db.grant("moderator", *self.all_permissions)
        self.ctx = context()
        self.errors = []
        self.selected_globals = []
        self.selected_children = []

        async def collect_error(incoming, ctx):
            self.errors.append(ctx.error)

        original = CallbackQueryHandler.handle_update

        async def record_dispatch(handler, incoming, app, check, ctx):
            names = self.selected_globals if id(handler) in self.global_ids else self.selected_children
            names.append(handler.callback.__name__)
            return await original(handler, incoming, app, check, ctx)

        recorder = patch.object(CallbackQueryHandler, "handle_update", record_dispatch)
        recorder.start()
        self.addCleanup(recorder.stop)
        self.app = self.make_application()
        self.app.add_error_handler(collect_error)

    def make_application(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", PTBUserWarning)
            registrations, configured_context = registered_handlers(with_context_types=True)
            app = Application.builder().context_types(configured_context).bot(self.ctx.bot).updater(None).build()
        self.global_ids = {id(handler) for group, handler in registrations
                           if group == 0 and isinstance(handler, CallbackQueryHandler)}
        for group, handler in registrations:
            if group in (-2, 0):
                app.add_handler(handler, group)
        # No startup or real bot requests are needed for process_update with the offline bot.
        app._initialized = True
        self.conversations = {handler.entry_points[0].callback.__module__.split(".")[-1]: handler
                              for handler in app.handlers[0] if isinstance(handler, ConversationHandler)}
        return app

    def admin_state(self, user_id=102, chat_id=700):
        incoming = update(user_id, self.ctx, text="state", chat_id=chat_id)
        return self.app.context_types.context.from_update(incoming, self.app).admin_data

    def activate(self, module, user_id=102):
        conv = self.conversations[module]
        state = next(iter(conv.states))
        conv._conversations[(700, user_id)] = state
        owners = copy.deepcopy(OWNERS[module])
        for key, value in owners.items():
            if isinstance(value, dict):
                value["owner_id"] = user_id
            else:
                owners[key] = user_id
        self.admin_state(user_id).update(owners)
        return conv, state

    async def dispatch(self, user_id=102, **kwargs):
        self.selected_globals.clear()
        self.selected_children.clear()
        await self.app.process_update(update(user_id, self.ctx, **kwargs))
        self.assertFalse(self.errors, self.errors)

    async def test_every_new_back_pattern_consumes_the_update_before_global_handlers(self):
        samples = sorted({data.replace("101", "102") for _, data in produced_callbacks()})
        for module, conv in self.conversations.items():
            fallback = next(handler for handler in conv.fallbacks if isinstance(handler, CallbackQueryHandler)
                            and handler.callback.__name__.startswith("back_from_"))
            matched = [data for data in samples if fallback.pattern.match(data)]
            self.assertTrue(matched, module)
            for data in matched:
                with self.subTest(conversation=module, callback=data):
                    self.admin_state(102).clear()
                    self.activate(module)
                    await self.dispatch(data=data)
                    self.assertEqual(self.selected_children[-1:], [fallback.callback.__name__])
                    self.assertEqual(self.selected_globals, [])
                    self.assertNotIn((700, 102), conv._conversations)
                    self.assertFalse(self.db.writes)

    async def test_named_navigation_callbacks_use_the_global_route_without_an_active_conversation(self):
        cases = [
            ("admin_subjects", "admin_back", "admin_back"),
            ("admin_tools", "admin_tools", "admin_tools"),
            ("admin_schedules", "admin_schedules_back:102", "admin_schedules_back"),
            ("admin_schedules", "admin_schedule_back:102", "admin_schedule_back"),
            ("admin_drawings", "admin_drawings_owner:102", "admin_drawings_owner"),
            ("admin_drawings", "admin_drawing_back:102", "admin_drawing_back"),
            ("admin_grades", "admin_grades_back:102", "admin_grades_back"),
            ("admin_grades", "admin_grade_list_back:102", "admin_grade_list_back"),
            ("admin_exam_dates", "admin_exam_list:7", "admin_exam_stage"),
        ]
        for module, data, expected in cases:
            with self.subTest(callback=data):
                self.admin_state(102).clear()
                self.admin_state(102).update(copy.deepcopy(OWNERS[module]))
                await self.dispatch(data=data)
                self.assertEqual(self.selected_globals, [expected])
                self.assertFalse(self.db.writes)

    async def test_feature_owners_can_exit_without_view_admin_for_admin_and_moderator(self):
        grants = [name for name in self.all_permissions if name != permissions.PERMISSION_VIEW_ADMIN]
        self.db.grant("admin", *grants)
        self.db.grant("moderator", *grants)
        for user_id in (102, 103):
            for module in self.conversations:
                routes = ["admin_back", "admin_tools"] if module in ("admin_tools", "bundle_descriptions") else ["admin_back"]
                for data in routes:
                    with self.subTest(user=user_id, conversation=module, callback=data):
                        self.admin_state(user_id).clear()
                        conv, _ = self.activate(module, user_id)
                        await self.dispatch(user_id, data=data)
                        self.assertNotIn((700, user_id), conv._conversations)
                        self.assertEqual(self.selected_globals, [])
                        self.assertIn("⛔", str(self.ctx.bot.answer_callback_query.await_args))
                        self.assertFalse(self.db.writes)

    async def test_revoked_feature_can_still_leave_through_admin_back(self):
        self.db.grant("admin", permissions.PERMISSION_VIEW_ADMIN)
        for module in self.conversations:
            with self.subTest(conversation=module):
                self.admin_state(102).clear()
                conv, _ = self.activate(module)
                await self.dispatch(data="admin_back")
                self.assertNotIn((700, 102), conv._conversations)
                self.assertEqual(self.selected_globals, [])
                self.assertFalse(self.db.writes)

    async def test_deferred_navigation_still_denies_students_and_revoked_menu_access(self):
        for user_id in (105, 102):
            self.db.grant("admin")
            for data in ("admin_back", "admin_tools"):
                with self.subTest(user=user_id, callback=data):
                    self.ctx.bot.edit_message_text.reset_mock()
                    await self.dispatch(user_id, data=data)
                    self.ctx.bot.edit_message_text.assert_not_awaited()
                    self.assertIn("⛔", str(self.ctx.bot.answer_callback_query.await_args))
                    self.assertFalse(self.db.writes)
        for data in ("admin_back", "admin_tools"):
            incoming = SimpleNamespace(callback_query=SimpleNamespace(data=data, from_user=None))
            with self.assertRaises(ApplicationHandlerStop):
                await permission_guard(incoming, self.ctx)

    async def test_tools_menu_reuses_one_fresh_db_snapshot(self):
        for user_id, expected in ((101, 1), (102, 2), (103, 2)):
            with self.subTest(user=user_id):
                self.db.reads.clear()
                await self.dispatch(user_id, data="admin_tools")
                self.assertEqual(sum(table in ("admins", "role_permissions") for table in self.db.reads), expected)
        self.db.grant("admin")
        self.ctx.bot.edit_message_text.reset_mock()
        await self.dispatch(data="admin_tools")
        self.ctx.bot.edit_message_text.assert_not_awaited()

    async def test_read_only_grade_and_exam_navigation_reuses_the_fresh_snapshot(self):
        for data in ("admin_grade_stage:7:102", "admin_grade_list:7:102",
                     "admin_grade_list_back:102", "admin_exam_list:7"):
            with self.subTest(callback=data):
                self.admin_state(102)["admin_grade_owner_id"] = 102
                self.db.reads.clear()
                await self.dispatch(data=data)
                # One guard check and one handler check; rendering needs no extra reload.
                self.assertEqual(sum(table in ("admins", "role_permissions") for table in self.db.reads), 4)
                self.assertFalse(self.db.writes)

    async def test_cancellation_and_foreign_controls_cannot_fall_through_to_global_handlers(self):
        for module in self.conversations:
            with self.subTest(conversation=module):
                conv, _ = self.activate(module)
                if module == "admin_notifications":
                    await self.dispatch(data="notify_cancel:102")
                elif module == "admin_settings":
                    await self.dispatch(data="setting_cancel:102")
                else:
                    await self.dispatch(text="/cancel")
                self.assertNotIn((700, 102), conv._conversations)
                self.assertEqual(self.selected_globals, [])
        for module, data in [
            ("admin_drawings", "admin_drawings_owner:102"),
            ("admin_drawings", "admin_drawing_back:102"),
            ("admin_schedules", "admin_schedules_back:102"),
            ("admin_schedules", "admin_schedule_back:102"),
            ("admin_grades", "admin_grades_back:102"),
            ("admin_grades", "admin_grade_list_back:102"),
        ]:
            with self.subTest(foreign=data):
                self.admin_state(104).clear()
                conv, state = self.activate(module, 104)
                before = copy.deepcopy(self.admin_state(104))
                await self.dispatch(104, data=data)
                self.assertEqual(conv._conversations[(700, 104)], state)
                self.assertEqual(self.admin_state(104), before)
                self.assertEqual(self.selected_globals, [])
                conv._conversations.pop((700, 104))
        self.assertIsNot(self.admin_state(102), self.admin_state(104))
        self.assertFalse(self.db.writes)

    async def test_real_application_keeps_two_admins_subject_sessions_separate(self):
        for user_id in (102, 104):
            await self.dispatch(user_id, data=f"add_subject:7:{user_id}")
        await self.dispatch(102, text="First admin")
        await self.dispatch(104, text="Second admin")
        self.assertEqual(self.admin_state(102)["admin_subject_name"], "First admin")
        self.assertEqual(self.admin_state(104)["admin_subject_name"], "Second admin")
        first = copy.deepcopy(self.admin_state(102))
        conv = self.conversations["admin_subjects"]
        await self.dispatch(104, text="/cancel")
        self.assertNotIn((700, 104), conv._conversations)
        self.assertEqual(conv._conversations[(700, 102)], MODULES["admin_subjects"].ADD_DESCRIPTION)
        self.assertEqual(self.admin_state(102), first)
        await self.dispatch(102, data="admin_back")
        self.assertNotIn((700, 102), conv._conversations)


if __name__ == "__main__":
    unittest.main()
