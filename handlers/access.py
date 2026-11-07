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

UNREGISTERED_TEXT = (
    "👋 Bot ini khusus anggota tim yang sudah terdaftar.\n\n"
    "ID Telegram Anda belum terdaftar di sistem, jadi menu jadwal belum bisa dibuka.\n\n"
    "Setelah terdaftar, bot bisa membantu:\n"
    "• /lihat_jadwal — rekap jadwal SOS tim\n"
    "• /jadwal_saya — jadwal SOS pribadi\n"
    "• /cuti & /lihat_cuti — tandai dan lihat cuti\n"
    "• /tukar_jadwal — tukar jadwal dengan rekan\n"
    "• /tanya — tanya jadwal pakai bahasa biasa\n\n"
    "Silakan hubungi admin untuk mendaftarkan ID Telegram Anda, lalu coba lagi."
)


def is_admin(user_id):
    return user_id == config.ADMIN_ID


def is_registered(user_id):
    """True bila user_id ada di user_groups. Gagal baca DB = anggap belum terdaftar."""
    from core.database import get_user_group
    try:
        return get_user_group(user_id) is not None
    except Exception:
        return False


def private_denied(chat_type, user_id):
    """True bila pesan datang dari chat pribadi yang bukan admin."""
    return chat_type == 'private' and not is_admin(user_id)


def deny_unregistered(bot, chat_id, user_id, thread_id=None):
    """Kirim penjelasan ke user grup yang belum terdaftar. True bila ditolak."""
    if is_admin(user_id) or is_registered(user_id):
        return False
    if bot is not None:
        bot.send_message(chat_id, UNREGISTERED_TEXT, message_thread_id=thread_id)
    return True


def deny_private_callback(bot, call):
    """Tolak callback dari chat pribadi non-admin atau user yang belum terdaftar."""
    chat = getattr(call.message, 'chat', None)
    if private_denied(getattr(chat, 'type', None), call.from_user.id):
        bot.answer_callback_query(call.id, DENIED_PRIVATE_TEXT, show_alert=True)
        return True
    chat_id = getattr(chat, 'id', None)
    if chat_id is not None and deny_unregistered(
        bot, chat_id, call.from_user.id, getattr(call.message, 'message_thread_id', None)
    ):
        bot.answer_callback_query(call.id)
        return True
    return False
