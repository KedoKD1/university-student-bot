"""Offline maintenance regressions through native PTB dispatch and API mocks."""
import copy
import unittest
import warnings
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram import Chat, ChatMemberLeft, ChatMemberMember, ChatMemberUpdated, Update, User
from telegram.error import BadRequest, ChatMigrated, Forbidden, TimedOut
from telegram.ext import Application, ChatMemberHandler, ConversationHandler
from telegram.warnings import PTBUserWarning

from tests.admin_support import Database, MODULES, context, permissions, registered_handlers, update
from bot.handlers import user_tracking
from bot.utils import chat_access, subscription


class MaintenanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database()
        self.db.rows['settings'] = [{'key': 'required_channel_id', 'value': '-1001'}]
        self.grants = [value for name, value in vars(permissions).items() if name.startswith('PERMISSION_')]
        self.db.grant('admin', *self.grants)
        self.db.grant('moderator', *self.grants)
        permissions.clear_permission_cache()
        self.addCleanup(permissions.clear_permission_cache)
        for module in [permissions, subscription, chat_access, user_tracking, *MODULES.values()]:
            replacement = patch.object(module, 'supabase', self.db)
            replacement.start()
            self.addCleanup(replacement.stop)
        fallback = patch.object(subscription, 'REQUIRED_CHANNEL_ID', None)
        fallback.start()
        self.addCleanup(fallback.stop)
        self.ctx = context()
        self.channel = SimpleNamespace(id=-1001, type='channel', title='LabBase', username='labbase', invite_link=None)
        self.own = SimpleNamespace(status='administrator', can_post_messages=True, can_send_messages=True)
        self.member = SimpleNamespace(status='member')
        self.ctx.bot.get_chat = AsyncMock(return_value=self.channel)
        self.ctx.bot.get_chat_member = AsyncMock(side_effect=lambda chat_id, user_id: self.own if user_id == 0 else self.member)
        self.ctx.bot.send_document = AsyncMock()
        self.errors = []
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', PTBUserWarning)
            registrations, types = registered_handlers(with_context_types=True)
            self.app = Application.builder().context_types(types).bot(self.ctx.bot).updater(None).build()
        for group, handler in registrations:
            if group in (-5, -4, -2, 0):
                self.app.add_handler(handler, group)
        self.app._initialized = True
        self.conversations = {h.entry_points[0].callback.__module__.split('.')[-1]: h for h in self.app.handlers[0]
                              if isinstance(h, ConversationHandler)}

        async def error(incoming, ctx):
            self.errors.append(ctx.error)

        self.app.add_error_handler(error)

    def state(self, chat_id=700, user_id=102):
        ctx = self.app.context_types.context.from_update(update(user_id, self.ctx, text='state', chat_id=chat_id), self.app)
        return ctx.admin_data

    async def dispatch(self, user_id=102, chat_id=700, **kwargs):
        await self.app.process_update(update(user_id, self.ctx, chat_id=chat_id, **kwargs))
        self.assertEqual(self.errors, [])

    def buttons(self):
        calls = self.ctx.bot.edit_message_text.await_args_list + self.ctx.bot.send_message.await_args_list
        return [b for call in calls if call.kwargs.get('reply_markup')
                for row in call.kwargs['reply_markup'].inline_keyboard for b in row]

    async def test_membership_statuses_fail_closed(self):
        for status, inside, expected in [('creator', None, True), ('administrator', None, True),
                                        ('member', None, True), ('restricted', True, True),
                                        ('restricted', False, False), ('left', None, False),
                                        ('kicked', None, False), ('unavailable', None, False)]:
            with self.subTest(status=status, inside=inside):
                self.member = SimpleNamespace(status=status, is_member=inside)
                self.assertEqual((await subscription.membership(self.ctx, 105, force=True))[0], expected)

    async def test_api_failures_never_turn_into_membership(self):
        await subscription.membership(self.ctx, 105)
        for failure in [Forbidden('private'), BadRequest('chat not found'), TimedOut(), RuntimeError('sensitive detail')]:
            with self.subTest(failure=type(failure).__name__):
                self.ctx.bot.get_chat_member.side_effect = failure
                result = await subscription.membership(self.ctx, 105, force=True)
                self.assertEqual((result[0], result[2]), (False, True))

    async def test_missing_invalid_and_failed_settings_do_not_disable_subscription(self):
        for value in [None, '', 'wrong', '123']:
            self.db.rows['settings'] = [{'key': 'required_channel_id', 'value': value}]
            self.assertEqual(await subscription.membership(self.ctx, 105, force=True), (False, None, True))
        self.db.failure = ('settings', 'select')
        with patch.object(subscription, 'REQUIRED_CHANNEL_ID', '-1001'):
            self.assertEqual(await subscription.membership(self.ctx, 105, force=True), (False, None, True))
        self.ctx.bot.get_chat.assert_not_awaited()

    async def test_environment_fallback_and_private_verified_links(self):
        self.db.rows['settings'] = []
        self.channel.username = None
        self.channel.invite_link = 'https://t.me/+verified_invite'
        with patch.object(subscription, 'REQUIRED_CHANNEL_ID', '-1001'):
            self.assertEqual((await subscription.membership(self.ctx, 105))[1], self.channel.invite_link)
            self.channel.invite_link = 'https://example.org/phishing'
            self.assertIsNone((await subscription.membership(self.ctx, 105, force=True))[1])
            self.channel.invite_link = None
            self.assertIsNone((await subscription.membership(self.ctx, 105, force=True))[1])

    async def test_bot_must_be_admin_of_a_channel_to_verify_other_members(self):
        self.own.status = 'member'
        self.assertEqual((await subscription.membership(self.ctx, 105))[::2], (False, True))
        self.own.status = 'administrator'
        self.channel.type = 'supergroup'
        self.assertEqual((await subscription.membership(self.ctx, 105, force=True))[::2], (False, True))

    async def test_membership_cache_and_verify_force_refresh(self):
        for _ in range(5):
            self.assertTrue((await subscription.membership(self.ctx, 105))[0])
        self.assertEqual(self.ctx.bot.get_chat.await_count, 1)
        self.assertEqual(self.ctx.bot.get_chat_member.await_count, 2)
        self.member.status = 'left'
        self.assertFalse((await subscription.membership(self.ctx, 105, force=True))[0])
        self.assertEqual(self.ctx.bot.get_chat_member.await_count, 4)

    async def test_membership_updates_evict_cached_access_for_only_the_affected_user(self):
        await subscription.membership(self.ctx, 105)
        await subscription.membership(self.ctx, 106)
        event = ChatMemberUpdated(Chat(-1001, 'channel', title='LabBase'), User(102, 'Actor', False),
                                  datetime.now(timezone.utc), ChatMemberMember(User(105, 'Student', False)),
                                  ChatMemberLeft(User(105, 'Student', False)))
        await subscription.subscription_membership_changed(Update(80, chat_member=event), self.ctx)
        self.assertNotIn((-1001, 105), self.ctx.bot_data['subscription']['members'])
        self.assertIn((-1001, 106), self.ctx.bot_data['subscription']['members'])
        self.member.status = 'left'
        self.assertFalse((await subscription.membership(self.ctx, 105))[0])
        bot_user = User(0, 'Bot', True)
        bot_event = ChatMemberUpdated(event.chat, event.from_user, event.date,
                                      ChatMemberMember(bot_user), ChatMemberLeft(bot_user))
        await user_tracking.track_user(Update(81, my_chat_member=bot_event), self.ctx)
        self.assertNotIn('subscription', self.ctx.bot_data)

    async def test_all_student_routes_and_text_are_blocked_when_unsubscribed(self):
        self.member.status = 'left'
        for incoming in [{'text': '/start'}, {'text': '/start@offline_test_bot'}, {'text': 'search text'},
                         {'text': '   '}, *[{'data': data} for data in (
                             'main:stages:105', 'stage:7:105', 'subject:17:105', 'file:1:105',
                             'content:summaries:17:105', 'main:settings:notifications:105',
                             'student_schedule_stage:7:105', 'exam_stage:7:105', 'main:grades:105',
                             'main:search:105', 'back_main:105', 'old_unknown_callback:105')]]:
            await self.dispatch(105, **incoming)
        self.assertFalse(set(self.db.reads) & {'subjects', 'files', 'summaries', 'drawings', 'user_settings'})
        self.ctx.bot.send_document.assert_not_awaited()
        self.assertTrue(any(b.callback_data == 'verify_subscription:105' for b in self.buttons()))
        self.assertTrue(any(b.url == 'https://t.me/labbase' for b in self.buttons()))

    async def test_subscribed_student_enters_existing_main_menu(self):
        await self.dispatch(105, text='/start')
        self.assertTrue(any(b.callback_data == 'main:stages:105' for b in self.buttons()))

    async def test_unsubscribed_users_are_still_tracked_before_content_is_denied(self):
        self.member.status = 'left'
        await self.dispatch(105, text='/start')
        self.assertEqual([row['telegram_id'] for row in self.db.rows['telegram_users']], [105])
        self.assertFalse(any(b.callback_data == 'main:stages:105' for b in self.buttons()))

    async def test_verification_reentry_and_foreign_button_owner(self):
        self.member.status = 'left'
        await self.dispatch(105, text='/start')
        self.member.status = 'member'
        await self.dispatch(105, data='verify_subscription:105')
        self.assertTrue(any(b.callback_data == 'main:stages:105' for b in self.buttons()))
        calls = self.ctx.bot.get_chat_member.await_count
        await self.dispatch(106, data='verify_subscription:105')
        self.assertEqual(self.ctx.bot.get_chat_member.await_count, calls)

    async def test_owner_admin_moderator_bypass_does_not_grant_admin_permissions(self):
        self.member.status = 'left'
        for user_id in (101, 102, 103):
            await self.dispatch(user_id, text='/start')
            self.assertTrue(any(b.callback_data == f'main:stages:{user_id}' for b in self.buttons()))
        self.ctx.bot.get_chat_member.assert_not_awaited()
        self.db.grant('admin')
        await self.dispatch(102, data='add_subject:7:102')
        await self.dispatch(105, text='/admin')
        await self.dispatch(105, data='add_subject:7:105')
        self.assertFalse(any(table == 'subjects' for table, _, _ in self.db.writes))

    async def test_saved_channel_setting_invalidates_cached_membership(self):
        await subscription.membership(self.ctx, 105)
        await MODULES['admin_settings'].setting_value(update(102, self.ctx, text='-1002'),
            SimpleNamespace(bot=self.ctx.bot, bot_data=self.ctx.bot_data,
                            admin_data={'admin_setting': {'owner_id': 102, 'key': 'required_channel_id'}}))
        self.assertNotIn('subscription', self.ctx.bot_data)
        self.assertEqual(self.db.rows['settings'][0]['value'], '-1002')

    async def test_cancel_from_every_notification_state_scoped_and_revoked(self):
        module = MODULES['admin_notifications']
        conversation = self.conversations['admin_notifications']
        for state in conversation.states:
            for revoked in (False, True):
                with self.subTest(state=state, revoked=revoked):
                    self.db.grant('admin', *self.grants)
                    await self.dispatch(data='admin_announcements')
                    await self.dispatch(chat_id=701, data='admin_announcements')
                    conversation._conversations[(700, 102)] = state
                    before = copy.deepcopy(self.state(701))
                    if revoked:
                        self.db.grant('admin')
                    await self.dispatch(data='notify_cancel:102')
                    self.assertNotIn((700, 102), conversation._conversations)
                    self.assertNotIn('admin_notification', self.state())
                    self.assertEqual(self.state(701), before)
        self.assertEqual(sum(h.callback == module.notification_cancel for h in conversation.fallbacks), 1)
        self.assertFalse(any(h.callback == module.notification_cancel for handlers in conversation.states.values() for h in handlers))

    async def test_foreign_notification_cancel_cannot_end_another_session(self):
        await self.dispatch(data='admin_announcements')
        await self.dispatch(104, data='admin_announcements')
        before = copy.deepcopy(self.state(user_id=104))
        await self.dispatch(104, data='notify_cancel:102')
        self.assertEqual(self.state(user_id=104), before)
        self.assertIn((700, 102), self.conversations['admin_notifications']._conversations)

    async def test_notification_all_user_steps_show_inline_cancel(self):
        await self.dispatch(data='admin_announcements')
        await self.dispatch(data='notify_audience:user:102')
        await self.dispatch(text='105')
        await self.dispatch(text='Title')
        await self.dispatch(text='Body')
        for call in self.ctx.bot.send_message.await_args_list[-3:]:
            self.assertIn('notify_cancel:102', [b.callback_data for row in call.kwargs['reply_markup'].inline_keyboard for b in row])

    async def test_full_notification_confirmation_delivery_and_cleanup(self):
        await self.dispatch(data='admin_announcements')
        await self.dispatch(data='notify_audience:all:102')
        await self.dispatch(text='Title')
        await self.dispatch(text='Content')
        with patch.object(MODULES['admin_notifications'].asyncio, 'sleep', new=AsyncMock()):
            await self.dispatch(data='notify_confirm:102')
        row = self.db.rows['notifications'][-1]
        self.assertEqual((row['status'], row['total_recipients'], row['successful_sends']), ('sent', 1, 1))
        self.assertNotIn('admin_notification', self.state())
        self.assertNotIn((700, 102), self.conversations['admin_notifications']._conversations)

    async def test_notification_revoked_message_steps_clean_owned_state(self):
        self.db.grant('admin')
        for name in ('notification_user_id', 'notification_title', 'notification_content'):
            self.ctx.admin_data['admin_notification'] = {'owner_id': 102}
            result = await getattr(MODULES['admin_notifications'], name)(update(102, self.ctx, text='Text'), self.ctx)
            self.assertEqual(result, ConversationHandler.END)
            self.assertNotIn('admin_notification', self.ctx.admin_data)

    async def test_description_text_inline_and_command_cancel_allow_successful_reentry(self):
        for inline in (True, False):
            await self.dispatch(data='bundle_desc_type:files:102')
            await self.dispatch(data='bundle_desc_stage:7:102')
            await self.dispatch(data='bundle_desc_subject:17:102')
            self.assertTrue(any(b.callback_data == 'bundle_desc_cancel:102' for b in self.buttons()))
            await self.dispatch(**({'data': 'bundle_desc_cancel:102'} if inline else {'text': '/cancel'}))
            self.assertNotIn((700, 102), self.conversations['bundle_descriptions']._conversations)
            self.assertFalse(any(key.startswith('bundle_desc_') for key in self.state()))
        await self.dispatch(data='bundle_desc_type:files:102')
        await self.dispatch(data='bundle_desc_stage:7:102')
        await self.dispatch(data='bundle_desc_subject:17:102')
        await self.dispatch(text='Reentered description')
        self.assertEqual(self.db.rows['content_bundle_descriptions'][-1]['description'], 'Reentered description')

    async def test_description_cancel_revocation_and_foreign_owner(self):
        conversation = self.conversations['bundle_descriptions']
        await self.dispatch(data='bundle_desc_type:files:102')
        before = copy.deepcopy(self.state())
        await self.dispatch(104, data='bundle_desc_cancel:102')
        self.assertEqual(self.state(), before)
        self.db.grant('admin')
        await self.dispatch(data='bundle_desc_cancel:102')
        self.assertNotIn((700, 102), conversation._conversations)
        self.assertFalse(any(key.startswith('bundle_desc_') for key in self.state()))

    async def test_role_menu_hides_current_role_and_protects_owner(self):
        tools = MODULES['admin_tools']
        for target, current in [(1, 'owner'), (2, 'admin'), (3, 'moderator')]:
            await tools.role_manage(update(102, self.ctx, data=f'role_manage:{target}'), self.ctx)
            keyboard = self.ctx.bot.edit_message_text.await_args.kwargs['reply_markup']
            callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
            self.assertFalse(any(data.startswith('change_role:') and data.split(':')[2] == current for data in callbacks))
            self.assertTrue(all(keyboard.inline_keyboard))
            if current == 'owner':
                self.assertEqual(callbacks, ['admin_roles'])

    async def test_role_callbacks_support_opaque_row_ids_and_telegram_size_limit(self):
        tools = MODULES['admin_tools']
        self.db.rows['admins'][3].update(id='00000000-0000-0000-0000-000000000004',
                                        telegram_id=4503599627370495)
        await tools.role_manage(update(102, self.ctx, data='role_manage:00000000-0000-0000-0000-000000000004'), self.ctx)
        buttons = [b for row in self.ctx.bot.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard for b in row]
        change = next(b.callback_data for b in buttons if b.callback_data.startswith('change_role:'))
        await tools.change_role(update(102, self.ctx, data=change), self.ctx)
        self.assertEqual(self.db.rows['admins'][3]['role'], 'moderator')
        self.db.rows['admins'][0]['telegram_id'] = 4503599627370494
        permissions.clear_permission_cache()
        await tools.role_manage(update(4503599627370494, self.ctx,
                                      data='role_manage:00000000-0000-0000-0000-000000000004'), self.ctx)
        markup = self.ctx.bot.edit_message_text.await_args.kwargs['reply_markup']
        self.assertTrue(all(len(b.callback_data.encode()) <= 64 for row in markup.inline_keyboard for b in row))

    async def test_role_change_and_removal_reject_stale_foreign_noop_and_legacy_buttons(self):
        tools = MODULES['admin_tools']
        for data in ['change_role:102:admin:admin:102', 'change_role:102:moderator:moderator:102',
                     'change_role:102:moderator:admin:104', 'change_role:101:admin:owner:102',
                     'change_role:2:moderator', 'remove_role:102:moderator:102', 'remove_role:101:owner:102',
                     'remove_role:102:admin:104', 'remove_role:2']:
            await getattr(tools, data.split(':')[0])(update(102, self.ctx, data=data), self.ctx)
        self.assertFalse(self.db.writes)
        await tools.change_role(update(102, self.ctx, data='change_role:104:moderator:admin:102'), self.ctx)
        self.assertEqual(self.db.rows['admins'][3]['role'], 'moderator')
        await tools.remove_role(update(102, self.ctx, data='remove_role:104:moderator:102'), self.ctx)
        self.assertFalse(self.db.rows['admins'][3]['is_active'])

    async def test_role_permission_revocation_and_pending_role_snapshot(self):
        tools = MODULES['admin_tools']
        self.db.rows['telegram_users'] = [{'telegram_id': 104, 'username': 'another_admin'}]
        await tools.role_add_start(update(102, self.ctx, data='role_add:102'), self.ctx)
        await tools.role_receive_username(update(102, self.ctx, text='another_admin'), self.ctx)
        callbacks = [b.callback_data for row in self.ctx.bot.send_message.await_args.kwargs['reply_markup'].inline_keyboard for b in row]
        self.assertNotIn('set_role:admin:104:102', callbacks)
        self.db.rows['admins'][3]['role'] = 'moderator'
        await tools.set_role(update(102, self.ctx, data='set_role:moderator:104:102'), self.ctx)
        self.assertFalse(self.db.writes)
        self.db.grant('admin')
        await tools.change_role(update(102, self.ctx, data='change_role:104:admin:moderator:102'), self.ctx)
        self.assertFalse(self.db.writes)

    async def test_statistics_exclude_deleted_rows_without_deduplicating_legitimate_media(self):
        for table in ('files', 'summaries', 'drawings'):
            self.db.rows[table] = [{'id': 1, 'is_active': True, 'deleted_at': None, 'telegram_file_id': 'same'},
                                   {'id': 2, 'is_active': True, 'deleted_at': None, 'telegram_file_id': 'same'},
                                   {'id': 3, 'is_active': True, 'deleted_at': 'old'},
                                   {'id': 4, 'is_active': False, 'deleted_at': None}]
            self.assertEqual(MODULES['admin_tools'].count_rows(table, active_only=True), 2)
            self.assertEqual(MODULES['admin_tools'].count_rows(table), 4)

    async def test_chat_lifecycle_removed_readded_and_stale_messages(self):
        self.db.rows['bot_chats'] = [{'chat_id': -1001, 'is_active': True}]
        chat = Chat(-1001, 'supergroup', title='Group')
        bot_user = User(0, 'Bot', True)
        actor = User(105, 'Actor', False)
        for removed in (True, False):
            event = ChatMemberUpdated(chat, actor, datetime.now(timezone.utc), ChatMemberMember(bot_user),
                                      ChatMemberLeft(bot_user) if removed else ChatMemberMember(bot_user))
            await self.app.process_update(Update(900, my_chat_member=event))
            self.assertEqual(self.errors, [])
            self.assertEqual(self.db.rows['bot_chats'][0]['is_active'], not removed)
            if removed:
                await self.dispatch(102, chat_id=-1001, data='admin_back')
                self.assertFalse(self.db.rows['bot_chats'][0]['is_active'])
        self.assertEqual(len(self.db.rows['bot_chats']), 1)
        self.assertTrue(any(isinstance(h, ChatMemberHandler) for h in self.app.handlers[-5]))

    async def test_channel_loss_of_post_permission_and_restoration(self):
        member = SimpleNamespace(status='administrator', user=User(0, 'Bot', True), can_post_messages=False)
        event = ChatMemberUpdated(Chat(-1001, 'channel', title='Channel'), User(105, 'Actor', False),
                                  datetime.now(timezone.utc), member, member)
        await user_tracking.track_user(Update(901, my_chat_member=event), self.ctx)
        self.assertFalse(self.db.rows['bot_chats'][0]['is_active'])
        member.can_post_messages = True
        await user_tracking.track_user(Update(902, my_chat_member=event), self.ctx)
        self.assertTrue(self.db.rows['bot_chats'][0]['is_active'])

    async def test_chat_access_permanent_transient_invalid_and_wrong_type(self):
        self.db.rows['bot_chats'] = [{'chat_id': -1001, 'is_active': True}, {'chat_id': 'bad', 'is_active': True}]
        self.ctx.bot.get_chat.side_effect = TimedOut()
        self.assertIsNone(await chat_access.accessible_chat(self.ctx.bot, -1001))
        self.assertTrue(self.db.rows['bot_chats'][0]['is_active'])
        self.ctx.bot.get_chat.side_effect = Forbidden('private')
        self.assertIsNone(await chat_access.accessible_chat(self.ctx.bot, -1001))
        self.assertFalse(self.db.rows['bot_chats'][0]['is_active'])
        self.assertIsNone(await chat_access.accessible_chat(self.ctx.bot, 'bad'))
        self.assertFalse(self.db.rows['bot_chats'][1]['is_active'])
        self.ctx.bot.get_chat.side_effect = None
        self.assertIsNone(await chat_access.accessible_chat(self.ctx.bot, -1001, 'group'))

    async def test_group_migration_event_and_api_migration_preserve_history(self):
        self.db.rows['bot_chats'] = [{'chat_id': -7, 'is_active': True}]
        self.channel.type = 'supergroup'
        self.ctx.bot.get_chat.side_effect = [ChatMigrated(-1001), self.channel]
        target = await chat_access.accessible_chat(self.ctx.bot, -7, 'group')
        self.assertEqual(target.id, -1001)
        self.assertFalse(self.db.rows['bot_chats'][0]['is_active'])
        self.assertTrue(self.db.rows['bot_chats'][1]['is_active'])
        self.ctx.bot.get_chat.side_effect = None
        await self.dispatch(105, chat_id=-7, text='migration', migrate_to_chat_id=-1001)
        self.assertEqual(len(self.db.rows['bot_chats']), 2)
        self.assertFalse(self.db.rows['bot_chats'][0]['is_active'])

    async def test_notification_chat_list_and_selection_recheck_access(self):
        self.db.rows['bot_chats'] = [{'chat_id': -1001, 'chat_type': 'channel', 'is_active': True},
                                    {'chat_id': -1002, 'chat_type': 'channel', 'is_active': False}]
        chats = await MODULES['admin_notifications']._get_chats('channel', self.ctx.bot)
        self.assertEqual([c['chat_id'] for c in chats], [-1001])
        self.ctx.admin_data['admin_notification'] = {'owner_id': 102}
        self.ctx.bot.get_chat.side_effect = Forbidden('private')
        result = await MODULES['admin_notifications'].notification_chat(
            update(102, self.ctx, data='notify_chat:channel:-1001:102'), self.ctx)
        self.assertEqual(result, MODULES['admin_notifications'].NOTIFICATION_AUDIENCE)
        self.assertNotIn('audience_value', self.ctx.admin_data['admin_notification'])
        self.assertFalse(self.db.rows['bot_chats'][0]['is_active'])

    async def test_notification_delivery_counts_and_inaccessible_destinations(self):
        notifications = MODULES['admin_notifications']
        self.db.rows['notifications'] = [{'id': 1}]
        self.db.rows['bot_chats'] = [{'chat_id': -1001, 'is_active': True}]
        self.ctx.bot.get_chat.side_effect = Forbidden('private')
        result = await notifications._send_notification(1, self.ctx.bot, 'channel', '-1001', 'Title', 'Content')
        self.assertEqual(result, (1, 0, 1, 'failed'))
        self.ctx.bot.send_message.assert_not_awaited()
        self.assertFalse(self.db.rows['bot_chats'][0]['is_active'])
        self.ctx.bot.get_chat.side_effect = None
        with patch.object(notifications.asyncio, 'sleep', new=AsyncMock()):
            result = await notifications._send_notification(1, self.ctx.bot, 'user', '105', 'Title', 'Content')
        self.assertEqual(result, (1, 1, 0, 'sent'))

    async def test_notification_send_failure_after_selection_marks_only_permanent_loss(self):
        notifications = MODULES['admin_notifications']
        self.db.rows['notifications'] = [{'id': 1}]
        self.db.rows['bot_chats'] = [{'chat_id': -1001, 'is_active': True}]
        for failure, active in [(TimedOut(), True), (BadRequest('message is too long'), True),
                                (Forbidden('bot was kicked'), False)]:
            self.db.rows['bot_chats'][0]['is_active'] = True
            self.ctx.bot.send_message.side_effect = failure
            with patch.object(notifications.asyncio, 'sleep', new=AsyncMock()):
                self.assertEqual(await notifications._send_notification(1, self.ctx.bot, 'channel', '-1001', 'T', 'C'),
                                 (1, 0, 1, 'failed'))
            self.assertEqual(self.db.rows['bot_chats'][0]['is_active'], active)

    async def test_notification_migration_during_send_retries_verified_new_group(self):
        notifications = MODULES['admin_notifications']
        self.db.rows['notifications'] = [{'id': 1}]
        self.db.rows['bot_chats'] = [{'chat_id': -7, 'is_active': True}]
        old = SimpleNamespace(id=-7, type='group', title='Old', username=None, permissions=None)
        self.channel.type = 'supergroup'
        self.ctx.bot.get_chat.side_effect = [old, self.channel]
        self.ctx.bot.send_message.side_effect = [ChatMigrated(-1001), None]
        with patch.object(notifications.asyncio, 'sleep', new=AsyncMock()):
            self.assertEqual(await notifications._send_notification(1, self.ctx.bot, 'group', '-7', 'T', 'C'),
                             (1, 1, 0, 'sent'))
        self.assertEqual([c.kwargs['chat_id'] for c in self.ctx.bot.send_message.await_args_list], [-7, -1001])
        self.assertFalse(self.db.rows['bot_chats'][0]['is_active'])
        self.assertTrue(self.db.rows['bot_chats'][1]['is_active'])


if __name__ == '__main__':
    unittest.main()
