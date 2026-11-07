# handlers/access.py
"""Gerbang akses chat bot.

Chat pribadi hanya untuk admin (config.ADMIN_ID). Chat grup/topik tetap terbuka
untuk anggota, karena keanggotaan di grup sudah dibatasi oleh grup itu sendiri.

ADMIN_ID dibaca saat pemanggilan (bukan saat import) supaya bisa di-override test.
"""
import config

DENIED_PRIVATE_TEXT = (
    "🔒 Chat pribadi bot ini hanya untuk admin. "
    "Silakan gunakan grup/topik jadwal."
)


def is_admin(user_id):
    return user_id == config.ADMIN_ID


def private_denied(chat_type, user_id):
    """True bila pesan datang dari chat pribadi yang bukan admin."""
    return chat_type == 'private' and not is_admin(user_id)


def deny_private_callback(bot, call):
    """Tolak callback dari chat pribadi non-admin. True bila sudah ditolak."""
    chat = getattr(call.message, 'chat', None)
    if not private_denied(getattr(chat, 'type', None), call.from_user.id):
        return False
    bot.answer_callback_query(call.id, DENIED_PRIVATE_TEXT, show_alert=True)
    return True
