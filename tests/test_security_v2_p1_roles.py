"""Role identity regressions using synthetic Telegram identities only."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram.error import Forbidden, TimedOut
from telegram.ext import ConversationHandler

from tests.admin_support import Database, Query, MODULES, context, permissions, update


class RoleIdentityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database()
        self.db.grant('admin', permissions.PERMISSION_MANAGE_ADMINS,
                      permissions.PERMISSION_VIEW_ADMIN)
        self.db.grant('moderator', permissions.PERMISSION_MANAGE_ADMINS)
        self.tools = MODULES['admin_tools']
        self.db.rows['telegram_users'] = [dict(
            telegram_id=9001, username='current_user', first_name='Synthetic', last_name='Target')]
        self.ctx = context()
        self.target = SimpleNamespace(id=9001, type='private', username='current_user',
                                      first_name='Synthetic', last_name='Target')
        self.ctx.bot.get_chat = AsyncMock(side_effect=lambda target_id: self.target)
        for module in (permissions, self.tools):
            replacement = patch.object(module, 'supabase', self.db)
            replacement.start()
            self.addCleanup(replacement.stop)
        permissions.clear_permission_cache()
        self.addCleanup(permissions.clear_permission_cache)

    async def select(self, text='9001', actor=102):
        await self.tools.role_add_start(update(actor, self.ctx, data=f'role_add:{actor}'), self.ctx)
        return await self.tools.role_receive_username(update(actor, self.ctx, text=text), self.ctx)

    async def save(self, actor=102):
        return await self.tools.set_role(
            update(actor, self.ctx, data=f'set_role:moderator:9001:{actor}'), self.ctx)

    def assert_no_grant(self):
        self.assertFalse(any(table == 'admins' for table, _, _ in self.db.writes))

    async def test_numeric_identity_is_verified_shown_and_rechecked_at_save(self):
        self.assertEqual(await self.select(), self.tools.ROLE_SELECTION)
        self.assertIn('9001', self.ctx.bot.send_message.await_args.kwargs['text'])
        self.ctx.bot.get_chat.assert_awaited_once_with(9001)
        self.assertEqual(await self.save(), ConversationHandler.END)
        self.assertEqual(self.ctx.bot.get_chat.await_count, 2)
        self.assertTrue(any(row['telegram_id'] == 9001 and row['role'] == 'moderator'
                            for row in self.db.rows['admins']))
        self.assertEqual(self.ctx.admin_data, {})

    async def test_current_unambiguous_username_resolves_to_verified_numeric_id(self):
        self.assertEqual(await self.select('@CURRENT_USER'), self.tools.ROLE_SELECTION)
        self.assertEqual(self.ctx.admin_data['role_target_id'], 9001)
        self.assertIn('9001', self.ctx.bot.send_message.await_args.kwargs['text'])
        await self.save()
        self.assertTrue(any(row['telegram_id'] == 9001 for row in self.db.rows['admins']))

    async def test_reused_username_with_one_historical_row_is_rejected(self):
        self.target.username = 'changed_elsewhere'
        result = await self.select('@current_user')
        self.assertNotEqual(result, self.tools.ROLE_SELECTION)
        await self.save()
        self.assert_no_grant()
        self.assertNotIn('role_target_id', self.ctx.admin_data)

    async def test_ambiguous_username_is_rejected_before_telegram_lookup(self):
        self.db.rows['telegram_users'].append(dict(telegram_id=9002, username='current_user'))
        self.assertNotEqual(await self.select('@current_user'), self.tools.ROLE_SELECTION)
        self.ctx.bot.get_chat.assert_not_awaited()
        await self.save()
        self.assert_no_grant()

    async def test_username_change_after_confirmation_cannot_redirect_assignment(self):
        await self.select('@current_user')
        self.target.username = 'different_current_name'
        self.assertEqual(await self.save(), ConversationHandler.END)
        self.assert_no_grant()
        self.assertEqual(self.ctx.admin_data, {})

    async def test_numeric_id_does_not_depend_on_mutable_display_name_or_username(self):
        await self.select('9001')
        self.target.username = 'renamed_user'
        self.target.first_name = 'Another display name'
        await self.save()
        self.assertTrue(any(row['telegram_id'] == 9001 for row in self.db.rows['admins']))

    async def test_wrong_id_group_and_unavailable_identity_fail_closed(self):
        for invalid in (SimpleNamespace(id=9002, type='private', username='current_user'),
                        SimpleNamespace(id=9001, type='channel', username='current_user'), None):
            with self.subTest(identity=invalid):
                self.target = invalid
                self.assertNotEqual(await self.select(), self.tools.ROLE_SELECTION)
                await self.save()
                self.assert_no_grant()

    async def test_failed_telegram_verification_at_entry_or_commit_never_grants(self):
        for at_commit in (False, True):
            for error in (Forbidden('Synthetic private detail'), TimedOut()):
                with self.subTest(at_commit=at_commit, error=type(error).__name__):
                    self.ctx.bot.get_chat.side_effect = lambda target_id: self.target
                    if at_commit:
                        await self.select()
                    self.ctx.bot.get_chat.side_effect = error
                    if at_commit:
                        await self.save()
                    else:
                        self.assertNotEqual(await self.select(), self.tools.ROLE_SELECTION)
                    self.assert_no_grant()
                    self.assertNotIn('role_target_id', self.ctx.admin_data)
                    rendered = str(self.ctx.bot.send_message.await_args_list)
                    rendered += str(self.ctx.bot.answer_callback_query.await_args_list)
                    self.assertNotIn('Synthetic private detail', rendered)

    async def test_revocation_during_identity_verification_blocks_commit(self):
        await self.select()

        async def verify_then_revoke(target_id):
            self.db.grant('admin')
            return self.target

        self.ctx.bot.get_chat.side_effect = verify_then_revoke
        await self.save()
        self.assert_no_grant()

    async def test_revoked_permission_cannot_select_or_commit(self):
        await self.select()
        self.db.grant('admin')
        await self.save()
        self.assert_no_grant()
        self.ctx.bot.get_chat.reset_mock()
        self.assertEqual(await self.select(), ConversationHandler.END)
        self.ctx.bot.get_chat.assert_not_awaited()

    async def test_owner_bypass_and_moderator_db_grant_are_preserved(self):
        for actor in (101, 103):
            with self.subTest(actor=actor):
                self.db.rows['admins'] = [r for r in self.db.rows['admins'] if r['telegram_id'] != 9001]
                self.assertEqual(await self.select(actor=actor), self.tools.ROLE_SELECTION)
                await self.save(actor)
                self.assertTrue(any(row['telegram_id'] == 9001 for row in self.db.rows['admins']))

    async def test_owner_target_cannot_be_changed_even_with_verified_identity(self):
        self.db.rows['admins'].append(dict(id=9, telegram_id=9001, role='owner', is_active=True))
        self.assertNotEqual(await self.select(), self.tools.ROLE_SELECTION)
        await self.save()
        self.assert_no_grant()

    async def test_foreign_callback_and_stale_target_cannot_grant(self):
        await self.select()
        await self.tools.set_role(update(104, self.ctx, data='set_role:admin:9001:102'), self.ctx)
        await self.tools.set_role(update(102, self.ctx, data='set_role:admin:9002:102'), self.ctx)
        self.assert_no_grant()

    async def test_database_failure_and_unregistered_numeric_target_fail_closed(self):
        self.db.failure = ('telegram_users', 'select')
        self.assertNotEqual(await self.select(), self.tools.ROLE_SELECTION)
        self.db.failure = None
        self.db.rows['telegram_users'] = []
        self.assertNotEqual(await self.select(), self.tools.ROLE_SELECTION)
        await self.save()
        self.assert_no_grant()

    async def test_existing_role_change_also_fails_closed_on_identity_verification(self):
        self.db.rows['admins'].append(dict(id=9, telegram_id=9001, role='moderator', is_active=True))
        self.ctx.bot.get_chat.side_effect = TimedOut()
        await self.tools.change_role(update(102, self.ctx, data='change_role:9001:admin:moderator:102'), self.ctx)
        self.assert_no_grant()

    async def test_existing_role_change_rechecks_actor_after_telegram_await(self):
        self.db.rows['admins'].append(dict(id=9, telegram_id=9001, role='moderator', is_active=True))

        async def verify_then_revoke(target_id):
            self.db.grant('admin')
            return self.target

        self.ctx.bot.get_chat.side_effect = verify_then_revoke
        await self.tools.change_role(update(102, self.ctx, data='change_role:9001:admin:moderator:102'), self.ctx)
        self.assert_no_grant()

    async def test_existing_role_confirmation_always_shows_immutable_id(self):
        self.db.rows['telegram_users'].append(dict(telegram_id=104, username='historical_name'))
        await self.tools.role_manage(update(102, self.ctx, data='role_manage:4'), self.ctx)
        self.assertIn('104', self.ctx.bot.edit_message_text.await_args.kwargs['text'])

    async def test_role_lookup_truncation_cannot_hide_ambiguous_username(self):
        self.db.rows['telegram_users'].append(dict(telegram_id=9002, username='current_user'))
        original = Query.execute

        def truncated(query):
            response = original(query)
            if query.table == 'telegram_users':
                response.data = response.data[:1]
            return response

        with patch.object(Query, 'execute', truncated):
            self.assertNotEqual(await self.select('@current_user'), self.tools.ROLE_SELECTION)
        self.ctx.bot.get_chat.assert_not_awaited()

    async def test_numeric_target_identity_change_at_commit_cannot_grant(self):
        await self.select()
        self.target.id = 9002
        await self.save()
        self.assert_no_grant()

    async def test_conditional_role_update_keeps_immutable_target_constraint(self):
        self.db.rows['admins'].append(dict(id=9, telegram_id=9001, role='admin', is_active=True))
        await self.select()
        original = Query.execute

        def replace_target_before_write(query):
            if query.table == 'admins' and query.action == 'update':
                self.db.rows['admins'][-1]['telegram_id'] = 9002
            return original(query)

        with patch.object(Query, 'execute', replace_target_before_write):
            await self.save()
        self.assertEqual(self.db.rows['admins'][-1]['role'], 'admin')


if __name__ == '__main__':
    unittest.main()
