"""Admin temporary state scoped to the same chat/user pair as its conversations."""
from telegram.ext import CallbackContext


class AdminContext(CallbackContext):
    __slots__ = ("_admin_user_id",)

    def __init__(self, application, chat_id=None, user_id=None):
        super().__init__(application, chat_id=chat_id, user_id=user_id)
        self._admin_user_id = user_id

    @property
    def admin_data(self) -> dict:
        """Return this user's Admin fields in PTB's native per-chat storage.

        Feature keys already have separate prefixes. Their existing cleanup
        helpers therefore affect only that feature for this chat and user.
        Ordinary user_data remains unchanged for student flows.
        """
        chat_data = self.chat_data
        if chat_data is None or self._admin_user_id is None:
            raise RuntimeError("Admin state requires a chat and a user.")

        return chat_data.setdefault("admin_sessions", {}).setdefault(self._admin_user_id, {})
