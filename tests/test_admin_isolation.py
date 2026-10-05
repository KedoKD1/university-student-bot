"""Cross-chat regressions using the registered PTB handlers and offline database."""
import ast
import copy
import unittest
import warnings
from unittest.mock import patch

from telegram import Document, PhotoSize
from telegram.ext import Application, ConversationHandler
from telegram.warnings import PTBUserWarning

from tests.admin_support import Database, MODULES, ROOT, context, permissions, registered_handlers, update
from bot.utils.admin_context import AdminContext


class AdminChatIsolationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database()
        self.db.rows["stages"].append({"id": 8, "stage_number": 2, "is_active": True})
        self.db.rows["subjects"].append({"id": 18, "stage_id": 8, "name": "Physics",
                                         "description": None, "sort_order": 1, "is_active": True})
        self.db.rows["telegram_users"] = [{"telegram_id": 9001, "username": "first_user"},
                                          {"telegram_id": 9002, "username": "second_user"}]
        self.grants = [value for key, value in vars(permissions).items() if key.startswith("PERMISSION_")]
        self.db.grant("admin", *self.grants)
        permissions.clear_permission_cache()
        self.addCleanup(permissions.clear_permission_cache)
        for module in [permissions, *MODULES.values()]:
            replacement = patch.object(module, "supabase", self.db)
            replacement.start()
            self.addCleanup(replacement.stop)
        send = patch.object(MODULES["admin_notifications"], "_send_notification", return_value=(1, 1, 0, "sent"))
        self.notification_send = send.start()
        self.addCleanup(send.stop)
        self.ctx = context()
        self.reset_application()

    def reset_application(self):
        self.errors = []
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", PTBUserWarning)
            registrations, configured_context = registered_handlers(with_context_types=True)
            self.app = Application.builder().context_types(configured_context).bot(self.ctx.bot).updater(None).build()
        for group, handler in registrations:
            if group in (-2, 0):
                self.app.add_handler(handler, group)
        self.app._initialized = True
        self.conversations = {handler.entry_points[0].callback.__module__.split(".")[-1]: handler
                              for handler in self.app.handlers[0] if isinstance(handler, ConversationHandler)}

        async def collect_error(incoming, ctx):
            self.errors.append(ctx.error)

        self.app.add_error_handler(collect_error)

    def state(self, chat_id, user_id=102):
        incoming = update(user_id, self.ctx, text="state", chat_id=chat_id)
        ctx = self.app.context_types.context.from_update(incoming, self.app)
        return ctx.admin_data

    async def dispatch(self, chat_id, user_id=102, **kwargs):
        await self.app.process_update(update(user_id, self.ctx, chat_id=chat_id, **kwargs))
        self.assertFalse(self.errors, self.errors)

    async def subject(self, chat_id, stage_id, name, user_id=102):
        await self.dispatch(chat_id, user_id, data=f"add_subject:{stage_id}:{user_id}")
        await self.finish_subject(chat_id, name, user_id)

    async def finish_subject(self, chat_id, name, user_id=102):
        await self.dispatch(chat_id, user_id, text=name)
        await self.dispatch(chat_id, user_id, text="-")
        await self.dispatch(chat_id, user_id, text="2")

    async def start_flow(self, module, chat_id, stage_id, user_id=102):
        subject_id = stage_id + 10
        if module in {"admin_files", "admin_grades"}:
            await self.dispatch(chat_id, user_id, data=module)
        entries = {
            "admin_subjects": f"add_subject:{stage_id}:{user_id}",
            "admin_files": f"add_file:{stage_id}:{subject_id}:practical:{user_id}",
            "admin_summaries": f"add_summary:{stage_id}:{subject_id}:practical:{user_id}",
            "admin_drawings": f"add_drawing:{stage_id}:{subject_id}:practical:{user_id}",
            "admin_schedules": f"add_schedule:{stage_id}:{user_id}",
            "admin_grades": f"add_grade:{stage_id}:{user_id}",
            "admin_exam_dates": f"add_exam:{stage_id}:{user_id}",
            "admin_notifications": "admin_announcements",
            "admin_settings": "admin_settings",
            "admin_tools": f"role_add:{user_id}",
            "bundle_descriptions": f"bundle_desc_type:{'files' if stage_id == 7 else 'summaries'}:{user_id}",
        }
        await self.dispatch(chat_id, user_id, data=entries[module])
        if module == "admin_notifications":
            await self.dispatch(chat_id, user_id, data=f"notify_audience:user:{user_id}")
            await self.dispatch(chat_id, user_id, text=str(8994 + stage_id))
        elif module == "admin_settings":
            key = "required_channel_id" if stage_id == 7 else "student_group_id"
            await self.dispatch(chat_id, user_id, data=f"setting_edit:{key}:{user_id}")
        elif module == "admin_tools":
            await self.dispatch(chat_id, user_id, text="first_user" if stage_id == 7 else "second_user")
        elif module == "bundle_descriptions":
            await self.dispatch(chat_id, user_id, data=f"bundle_desc_stage:{stage_id}:{user_id}")
            await self.dispatch(chat_id, user_id, data=f"bundle_desc_subject:{subject_id}:{user_id}")
        self.assertIn((chat_id, user_id), self.conversations[module]._conversations)

    def remaining_steps(self, module, stage_id, user_id=102):
        document = {"document": Document(f"file-{stage_id}", "unique", file_size=100)}
        photo = {"photo": [PhotoSize(f"image-{stage_id}", "unique", 20, 20, file_size=100)]}
        name = {"text": f"Content for stage {stage_id}"}
        description = {"text": "-"}
        order = {"text": "2"}
        return {
            "admin_subjects": [name, description, order],
            "admin_files": [name, description, order, document],
            "admin_summaries": [name, description, order, document],
            "admin_drawings": [name, description, order, photo],
            "admin_schedules": [photo],
            "admin_grades": [name, description, document],
            "admin_exam_dates": [{"data": f"add_exam_type:final:{user_id}"}, name,
                                 {"data": f"exam_subject:{stage_id + 10}:{user_id}"},
                                 {"text": "2026-11-15"}, description, description],
            "admin_notifications": [name, {"text": f"Body for stage {stage_id}"},
                                     {"data": f"notify_confirm:{user_id}"}],
            "admin_settings": [{"text": f"-10010000000{stage_id}"}],
            "admin_tools": [{"data": f"set_role:moderator:{8994 + stage_id}:{user_id}"}],
            "bundle_descriptions": [{"text": f"Description for stage {stage_id}"}],
        }[module]

    async def prepare_write(self, module, chat_id, stage_id, user_id=102):
        await self.start_flow(module, chat_id, stage_id, user_id)
        steps = self.remaining_steps(module, stage_id, user_id)
        for step in steps[:-1]:
            await self.dispatch(chat_id, user_id, **step)
        return steps[-1]

    def assert_saved_target(self, module, stage_id):
        targets = {
            "admin_subjects": ("subjects", "stage_id", stage_id),
            "admin_files": ("files", "subject_id", stage_id + 10),
            "admin_summaries": ("summaries", "subject_id", stage_id + 10),
            "admin_drawings": ("drawings", "subject_id", stage_id + 10),
            "admin_schedules": ("schedules", "stage_id", stage_id),
            "admin_grades": ("grade_files", "stage_id", stage_id),
            "admin_exam_dates": ("exam_dates", "stage_id", stage_id),
            "admin_notifications": ("notifications", "audience_value", 8994 + stage_id),
            "admin_settings": ("settings", "key", "required_channel_id" if stage_id == 7 else "student_group_id"),
            "admin_tools": ("admins", "telegram_id", 8994 + stage_id),
            "bundle_descriptions": ("content_bundle_descriptions", "subject_id", stage_id + 10),
        }
        table, key, expected = targets[module]
        self.assertEqual(str(self.db.rows[table][-1][key]), str(expected))

    async def test_same_admin_subject_completion_uses_only_its_origin_chat(self):
        await self.dispatch(700, data="add_subject:7:102")
        await self.dispatch(701, data="add_subject:8:102")
        await self.finish_subject(700, "Chat A subject")
        self.assertEqual(str(self.db.rows["subjects"][-1]["stage_id"]), "7")
        self.assertEqual(str(self.state(701)["admin_subject_stage_id"]), "8")
        await self.finish_subject(701, "Chat B subject")
        self.assertEqual(str(self.db.rows["subjects"][-1]["stage_id"]), "8")
        self.assertEqual(self.state(700), {})
        self.assertEqual(self.state(701), {})

    async def test_same_admin_subject_edits_cannot_overwrite_the_other_chats_row(self):
        await self.dispatch(700, data="edit_subject:17:7:102")
        await self.dispatch(701, data="edit_subject:18:8:102")
        before = copy.deepcopy(self.state(701))
        await self.finish_subject(700, "Edited in chat A")
        rows = {row["id"]: row for row in self.db.rows["subjects"]}
        self.assertEqual(rows[17]["name"], "Edited in chat A")
        self.assertEqual(rows[18]["name"], "Physics")
        self.assertEqual(self.state(701), before)
        await self.finish_subject(701, "Edited in chat B")
        self.assertEqual(rows[17]["name"], "Edited in chat A")
        self.assertEqual(rows[18]["name"], "Edited in chat B")

    async def test_cancel_in_chat_a_preserves_chat_b_and_its_completion(self):
        await self.dispatch(700, data="add_subject:7:102")
        await self.dispatch(701, data="add_subject:8:102")
        before = copy.deepcopy(self.state(701))
        await self.dispatch(700, text="/cancel")
        self.assertEqual(self.state(701), before)
        await self.finish_subject(701, "Survives cancel")
        self.assertEqual(str(self.db.rows["subjects"][-1]["stage_id"]), "8")

    async def test_back_in_chat_a_preserves_chat_b_and_its_completion(self):
        await self.dispatch(700, data="add_subject:7:102")
        await self.dispatch(701, data="add_subject:8:102")
        before = copy.deepcopy(self.state(701))
        await self.dispatch(700, data="admin_back")
        self.assertEqual(self.state(701), before)
        await self.finish_subject(701, "Survives back")
        self.assertEqual(str(self.db.rows["subjects"][-1]["stage_id"]), "8")

    async def test_same_admin_different_features_in_two_chats_complete_independently(self):
        await self.dispatch(700, data="add_subject:7:102")
        last = await self.prepare_write("admin_files", 701, 8)
        before = copy.deepcopy(self.state(701))
        await self.finish_subject(700, "Independent subject")
        self.assertEqual(self.state(701), before)
        self.assert_saved_target("admin_subjects", 7)
        await self.dispatch(701, **last)
        self.assert_saved_target("admin_files", 8)

    async def test_same_admin_two_chats_and_second_admin_share_no_operation_data(self):
        for chat_id, user_id, stage_id in ((700, 102, 7), (701, 102, 8), (700, 104, 8)):
            await self.dispatch(chat_id, user_id, data=f"add_subject:{stage_id}:{user_id}")
        other = copy.deepcopy(self.state(700, 104))
        await self.finish_subject(700, "Admin A chat 1")
        self.assertEqual(self.state(700, 104), other)
        await self.finish_subject(701, "Admin A chat 2")
        await self.finish_subject(700, "Admin B chat 1", 104)
        inserted = self.db.rows["subjects"][-3:]
        self.assertEqual([str(row["stage_id"]) for row in inserted], ["7", "8", "8"])
        self.assertEqual([row["name"] for row in inserted], ["Admin A chat 1", "Admin A chat 2", "Admin B chat 1"])

    async def test_every_feature_saves_its_own_target_and_preserves_the_other_chat(self):
        for module in self.conversations:
            with self.subTest(feature=module):
                self.reset_application()
                last_a = await self.prepare_write(module, 700, 7)
                before_a = copy.deepcopy(self.state(700))
                last_b = await self.prepare_write(module, 701, 8)
                self.assertEqual(self.state(700), before_a)
                before_b = copy.deepcopy(self.state(701))
                await self.dispatch(700, **last_a)
                self.assert_saved_target(module, 7)
                self.assertEqual(self.state(701), before_b)
                await self.dispatch(701, **last_b)
                self.assert_saved_target(module, 8)

    async def test_every_feature_cancel_and_back_preserve_the_other_chat(self):
        for module in self.conversations:
            for back in (False, True):
                with self.subTest(feature=module, back=back):
                    self.reset_application()
                    await self.start_flow(module, 700, 7)
                    await self.start_flow(module, 701, 8)
                    before = copy.deepcopy(self.state(701))
                    state_b = self.conversations[module]._conversations[(701, 102)]
                    if back:
                        await self.dispatch(700, data="admin_back")
                    elif module == "admin_notifications":
                        await self.dispatch(700, data="notify_cancel:102")
                    elif module == "admin_settings":
                        await self.dispatch(700, data="setting_cancel:102")
                    else:
                        await self.dispatch(700, text="/cancel")
                    self.assertNotIn((700, 102), self.conversations[module]._conversations)
                    self.assertEqual(self.conversations[module]._conversations[(701, 102)], state_b)
                    self.assertEqual(self.state(701), before)

    async def test_permission_revocation_blocks_each_write_without_clearing_other_chat(self):
        for module in self.conversations:
            with self.subTest(feature=module):
                self.reset_application()
                self.db.grant("admin", *self.grants)
                last_a = await self.prepare_write(module, 700, 7)
                last_b = await self.prepare_write(module, 701, 8)
                before = copy.deepcopy(self.state(701))
                writes = len(self.db.writes)
                sends = self.notification_send.await_count
                self.db.grant("admin")  # Deliberately leave cached grants populated.
                await self.dispatch(700, **last_a)
                self.assertEqual(len(self.db.writes), writes)
                self.assertEqual(self.notification_send.await_count, sends)
                self.assertEqual(self.state(701), before)
                self.db.grant("admin", *self.grants)
                await self.dispatch(701, **last_b)
                self.assert_saved_target(module, 8)

    async def test_database_failure_in_each_feature_preserves_other_chat(self):
        failures = {
            "admin_subjects": ("subjects", "insert"), "admin_files": ("files", "insert"),
            "admin_summaries": ("summaries", "insert"), "admin_drawings": ("drawings", "insert"),
            "admin_schedules": ("schedules", "insert"), "admin_grades": ("grade_files", "insert"),
            "admin_exam_dates": ("exam_dates", "insert"), "admin_notifications": ("notifications", "insert"),
            "admin_settings": ("settings", "insert"), "admin_tools": ("admins", "insert"),
            "bundle_descriptions": ("content_bundle_descriptions", "upsert"),
        }
        for module in self.conversations:
            with self.subTest(feature=module):
                self.reset_application()
                last_a = await self.prepare_write(module, 700, 7)
                last_b = await self.prepare_write(module, 701, 8)
                before = copy.deepcopy(self.state(701))
                self.db.failure = failures[module]
                writes = len(self.db.writes)
                await self.dispatch(700, **last_a)
                self.assertEqual(len(self.db.writes), writes)
                self.assertEqual(self.state(701), before)
                self.db.failure = None
                await self.dispatch(701, **last_b)
                self.assert_saved_target(module, 8)

    async def test_context_scopes_admin_data_and_preserves_native_user_data(self):
        self.assertIs(self.app.context_types.context, AdminContext)
        self.assertEqual(self.app.concurrent_updates, 1)
        first = AdminContext.from_update(update(102, self.ctx, text="A", chat_id=700), self.app)
        second = AdminContext.from_update(update(102, self.ctx, text="B", chat_id=701), self.app)
        other = AdminContext.from_update(update(104, self.ctx, text="C", chat_id=700), self.app)
        self.assertIsNot(first.admin_data, second.admin_data)
        self.assertIsNot(first.admin_data, other.admin_data)
        first.user_data["search_mode"] = True
        self.assertIs(first.user_data, second.user_data)
        self.assertTrue(second.user_data["search_mode"])
        first.admin_data["admin_subject_name"] = "A"
        self.assertEqual(second.admin_data, {})
        self.assertEqual(other.admin_data, {})
        self.assertNotIn("admin_subject_name", first.user_data)
        for chat_id, user_id in ((None, 102), (700, None)):
            with self.assertRaises(RuntimeError):
                AdminContext(self.app, chat_id=chat_id, user_id=user_id).admin_data

    async def test_all_admin_conversations_use_scoped_storage_and_disjoint_feature_keys(self):
        keys = {}
        for name in self.conversations:
            tree = ast.parse((ROOT / "bot" / "handlers" / f"{name}.py").read_text())
            self.assertFalse(any(isinstance(node, ast.Attribute) and node.attr == "user_data" for node in ast.walk(tree)), name)
            for node in ast.walk(tree):
                operation_keys = []
                if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == "admin_data" and isinstance(node.slice, ast.Constant):
                    operation_keys.append(node.slice.value)
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "admin_data" and node.args:
                    if isinstance(node.args[0], ast.Constant):
                        operation_keys.append(node.args[0].value)
                    elif node.func.attr == "update" and isinstance(node.args[0], ast.Dict):
                        operation_keys.extend(key.value for key in node.args[0].keys if isinstance(key, ast.Constant))
                for key in operation_keys:
                    self.assertEqual(keys.setdefault(key, name), name, key)
            self.assertTrue(self.conversations[name].per_user and self.conversations[name].per_chat)


if __name__ == "__main__":
    unittest.main()
