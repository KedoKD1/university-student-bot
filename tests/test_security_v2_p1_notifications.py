"""Private broadcast preference policy; no Telegram or database connections."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram.error import RetryAfter
from telegram.ext import ConversationHandler

from tests.admin_support import Database, Query, MODULES, context, permissions, update
from bot.handlers import content


class BroadcastPreferenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database()
        self.module = MODULES['admin_notifications']
        self.ctx = context()
        self.ctx.bot.send_document = AsyncMock()
        self.db.rows['notifications'] = [dict(id=1)]
        self.db.rows['telegram_users'] = [dict(telegram_id=value) for value in (105, 106, 107)]
        self.db.rows['user_settings'] = [dict(telegram_id=105, notifications_enabled=True),
                                         dict(telegram_id=106, notifications_enabled=False)]
        for module in (self.module, content, permissions):
            replacement = patch.object(module, 'supabase', self.db)
            replacement.start()
            self.addCleanup(replacement.stop)
        sleep = patch.object(self.module.asyncio, 'sleep', new=AsyncMock())
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)
        self.clock = 0
        clock = patch.object(self.module, 'monotonic', side_effect=lambda: self.clock, create=True)
        clock.start()
        self.addCleanup(clock.stop)
        permissions.clear_permission_cache()
        self.addCleanup(permissions.clear_permission_cache)

    async def send(self, audience='all_users', target=None):
        return await self.module._send_notification(1, self.ctx.bot, audience, target,
                                                     'Important synthetic notice', 'Synthetic content')

    def targets(self):
        return [call.kwargs['chat_id'] for call in self.ctx.bot.send_message.await_args_list]

    async def test_all_users_respects_opt_in_opt_out_and_missing_default_without_writes(self):
        result = await self.send()
        self.assertEqual(self.targets(), [105, 107])
        self.assertEqual(result[:3], (2, 2, 0))
        self.assertFalse(any(table == 'user_settings' for table, _, _ in self.db.writes))

    async def test_individual_unsolicited_important_notification_has_no_opt_out_bypass(self):
        await self.send('user', '106')
        self.ctx.bot.send_message.assert_not_awaited()
        await self.send('user', '107')
        self.assertEqual(self.targets(), [107])

    async def test_preference_database_failure_never_assumes_default_opt_in(self):
        self.db.failure = ('user_settings', 'select')
        result = await self.send()
        self.ctx.bot.send_message.assert_not_awaited()
        self.assertEqual(result[1], 0)
        self.assertEqual(result[3], 'failed')

    async def test_null_invalid_or_conflicting_preference_is_not_opt_in(self):
        for value in (None, 'false', 0):
            with self.subTest(value=value):
                self.db.rows['user_settings'] = [dict(telegram_id=105, notifications_enabled=value)]
                await self.send('user', '105')
                self.ctx.bot.send_message.assert_not_awaited()
        self.db.rows['user_settings'] = [dict(telegram_id=105, notifications_enabled=True),
                                         dict(telegram_id=105, notifications_enabled=False)]
        await self.send('user', '105')
        self.ctx.bot.send_message.assert_not_awaited()

    async def test_incomplete_preference_response_is_not_treated_as_missing_preferences(self):
        original = Query.execute

        def truncated(query):
            response = original(query)
            if query.table == 'user_settings':
                return SimpleNamespace(data=[], count=2)
            return response

        with patch.object(Query, 'execute', truncated):
            await self.send()
        self.ctx.bot.send_message.assert_not_awaited()

    async def test_unknown_preference_count_fails_closed(self):
        original = Query.execute

        def unverified(query):
            response = original(query)
            if query.table == 'user_settings':
                response.count = None
            return response

        with patch.object(Query, 'execute', unverified):
            await self.send()
        self.ctx.bot.send_message.assert_not_awaited()

    async def test_bulk_preferences_are_read_in_bounded_batches_not_per_recipient(self):
        self.db.rows['telegram_users'] = [dict(telegram_id=value) for value in range(1000, 1250)]
        self.db.rows['user_settings'] = [dict(telegram_id=value, notifications_enabled=False)
                                         for value in range(1000, 1250, 2)]
        result = await self.send()
        self.assertEqual(len(self.targets()), 125)
        self.assertTrue(all(value % 2 == 1 for value in self.targets()))
        self.assertLessEqual(self.db.reads.count('user_settings'), 3)
        self.assertEqual(result[:3], (125, 125, 0))

    async def test_new_opt_out_in_later_batch_is_respected_during_broadcast(self):
        self.db.rows['telegram_users'] = [dict(telegram_id=value) for value in range(1000, 1102)]
        self.db.rows['user_settings'] = []

        async def disable_later_target(**kwargs):
            if kwargs['chat_id'] == 1000:
                self.db.rows['user_settings'] = [dict(telegram_id=1101, notifications_enabled=False)]

        self.ctx.bot.send_message.side_effect = disable_later_target
        await self.send()
        self.assertNotIn(1101, self.targets())
        self.assertIn(1100, self.targets())

    async def test_expired_preference_snapshot_is_refreshed_inside_current_batch(self):
        async def disable_next_target(**kwargs):
            if kwargs['chat_id'] == 105:
                self.db.rows['user_settings'].append(dict(telegram_id=107, notifications_enabled=False))
                self.clock = 2

        self.ctx.bot.send_message.side_effect = disable_next_target
        await self.send()
        self.assertEqual(self.targets(), [105])

    async def test_preference_failure_mid_broadcast_stops_remaining_sends(self):
        async def fail_after_first(**kwargs):
            self.db.failure = ('user_settings', 'select')
            self.clock = 2

        self.ctx.bot.send_message.side_effect = fail_after_first
        result = await self.send()
        self.assertEqual(self.targets(), [105])
        self.assertEqual(result[1], 1)
        self.assertEqual(result[3], 'completed_with_errors')

    async def test_retry_after_rechecks_opt_out_before_retrying(self):
        self.ctx.bot.send_message.side_effect = RetryAfter(1)

        async def opt_out_while_waiting(delay):
            self.db.rows['user_settings'] = [dict(telegram_id=105, notifications_enabled=False)]

        self.sleep.side_effect = opt_out_while_waiting
        result = await self.send('user', '105')
        self.assertEqual(self.ctx.bot.send_message.await_count, 1)
        self.assertEqual(result[1], 0)

    async def test_opted_out_student_interactive_content_request_is_unaffected(self):
        self.db.rows['files'] = [dict(id=1, subject_id=17, name='Synthetic', is_active=True,
                                      deleted_at=None, telegram_file_id='offline_file', file_type='document')]
        await content.file_button(update(106, self.ctx, data='file:1:106'), self.ctx)
        self.ctx.bot.send_document.assert_awaited_once()
        self.assertNotIn('user_settings', self.db.reads)

    async def test_revoked_admin_cannot_start_broadcast_despite_opted_in_recipients(self):
        self.ctx.admin_data['admin_notification'] = dict(owner_id=102, audience_type='all_users',
                                                        audience_value=None, title='Synthetic', content='Synthetic')
        await self.module.notification_confirm(update(102, self.ctx, data='notify_confirm:102'), self.ctx)
        self.ctx.bot.send_message.assert_not_awaited()
        self.assertNotIn('user_settings', self.db.reads)

    async def test_shared_audiences_never_send_or_change_historical_chat_records(self):
        self.db.rows['bot_chats'] = [dict(chat_id=-1001, is_active=True)]
        for audience in ('group', 'channel'):
            with self.subTest(audience=audience):
                self.assertEqual(await self.send(audience, '-1001'), (0, 0, 0, 'failed'))
        self.ctx.bot.send_message.assert_not_awaited()
        self.assertEqual(self.db.rows['bot_chats'], [dict(chat_id=-1001, is_active=True)])

    async def test_shared_audience_and_old_destination_buttons_explain_policy(self):
        self.db.grant('admin', permissions.PERMISSION_MANAGE_ANNOUNCEMENTS)
        for audience in ('group', 'channel'):
            self.ctx.admin_data['admin_notification'] = dict(owner_id=102)
            for handler, callback in ((self.module.notification_audience, f'notify_audience:{audience}:102'),
                                      (self.module.notification_chat, f'notify_chat:{audience}:-1001:102')):
                with self.subTest(callback=callback):
                    result = await handler(update(102, self.ctx, data=callback), self.ctx)
                    self.assertEqual(result, self.module.NOTIFICATION_AUDIENCE)
                    self.assertNotIn('audience_type', self.ctx.admin_data['admin_notification'])
                    self.assertTrue(self.ctx.bot.answer_callback_query.await_args.kwargs['show_alert'])
                    self.assertIn('إيقاف الإشعارات', self.ctx.bot.answer_callback_query.await_args.kwargs['text'])

    async def test_stale_shared_confirmation_cannot_write_even_for_owner(self):
        for audience in ('group', 'channel'):
            self.ctx.admin_data.update(unrelated='preserve', admin_notification=dict(
                owner_id=101, audience_type=audience, audience_value='-1001',
                title='Synthetic', content='Synthetic'))
            result = await self.module.notification_confirm(update(101, self.ctx, data='notify_confirm:101'), self.ctx)
            self.assertEqual(result, ConversationHandler.END)
            self.assertNotIn('admin_notification', self.ctx.admin_data)
            self.assertEqual(self.ctx.admin_data['unrelated'], 'preserve')
        self.ctx.bot.send_message.assert_not_awaited()
        self.assertEqual(self.db.writes, [])

    async def test_stale_shared_text_step_ends_safely_without_a_callback_query(self):
        self.db.grant('admin', permissions.PERMISSION_MANAGE_ANNOUNCEMENTS)
        self.ctx.admin_data['admin_notification'] = dict(
            owner_id=102, audience_type='group', audience_value='-1001', title='Synthetic')
        result = await self.module.notification_content(update(102, self.ctx, text='Synthetic body'), self.ctx)
        self.assertEqual(result, ConversationHandler.END)
        self.assertNotIn('admin_notification', self.ctx.admin_data)
        self.assertEqual(self.db.writes, [])

    async def test_negative_or_invalid_private_destination_cannot_bypass_shared_policy(self):
        self.db.rows['telegram_users'].extend([dict(telegram_id=-1001), dict(telegram_id=0),
                                               dict(telegram_id='invalid')])
        await self.send()
        self.assertTrue(all(target > 0 for target in self.targets()))


if __name__ == '__main__':
    unittest.main()
