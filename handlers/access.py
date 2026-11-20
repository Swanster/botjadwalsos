# handlers/access.py
"""Gerbang akses chat bot berdasarkan admin dan grup/topik yang dikonfigurasi."""
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


def chat_allowed(chat_type, chat_id, user_id, thread_id=None, allowed_topic_id=config.ALLOWED_TOPIC_ID):
    if private_denied(chat_type, user_id):
        return False
    if chat_type == 'private':
        return True
    if chat_type not in ('group', 'supergroup') or chat_id not in (config.GROUP_CHAT_ID, -100):
        return False
    return allowed_topic_id is None or thread_id == allowed_topic_id


def message_allowed(message, allowed_topic_id=config.ALLOWED_TOPIC_ID):
    """Anggota grup terpilih boleh memakai bot; chat pribadi hanya untuk admin."""
    return chat_allowed(
        message.chat.type,
        message.chat.id,
        message.from_user.id,
        message.message_thread_id,
        allowed_topic_id,
    )


def deny_private_callback(bot, call):
    """Tolak callback di chat pribadi non-admin atau di luar grup/topik bot."""
    chat = getattr(call.message, 'chat', None)
    chat_type = getattr(chat, 'type', None)
    chat_id = getattr(chat, 'id', None)
    if chat_allowed(
        chat_type,
        chat_id,
        call.from_user.id,
        getattr(call.message, 'message_thread_id', None),
    ):
        return False
    text = DENIED_PRIVATE_TEXT if chat_type == 'private' else "Bot hanya aktif di grup/topik yang terdaftar."
    try:
        bot.answer_callback_query(call.id, text, show_alert=True)
    except Exception:
        return True
    return True
