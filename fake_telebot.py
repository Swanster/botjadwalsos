"""Fake TeleBot untuk test handler: merekam pesan dan bisa memicu callback."""
from types import SimpleNamespace


class FakeBot:
    def __init__(self):
        self.handlers = {}
        self.callbacks = []
        self.sent = []
        self.replies = []
        self.edits = []
        self.answers = []
        self.deleted = []
        self.next_step = None

    def message_handler(self, **kwargs):
        def decorator(handler):
            for command in kwargs.get("commands", []):
                self.handlers[command] = handler
            return handler

        return decorator

    def callback_query_handler(self, func=None, **kwargs):
        def decorator(handler):
            self.callbacks.append((func, handler))
            return handler

        return decorator

    def register_next_step_handler(self, message, handler):
        self.next_step = handler

    def send_message(self, chat_id, text, **kwargs):
        self.sent.append({"chat_id": chat_id, "text": text, "markup": kwargs.get("reply_markup")})
        return SimpleNamespace(chat=SimpleNamespace(id=chat_id), message_id=len(self.sent))

    def reply_to(self, message, text, **kwargs):
        self.replies.append(text)

    def edit_message_reply_markup(self, chat_id, message_id, reply_markup=None, **kwargs):
        self.edits.append(reply_markup)

    def edit_message_text(self, text, chat_id, message_id, **kwargs):
        self.edits.append(text)

    def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))

    def answer_callback_query(self, callback_id, text=None, show_alert=False):
        self.answers.append(text)

    def fire(self, data, user_id, chat_id=-100, message_id=1, chat_type="supergroup"):
        call = SimpleNamespace(
            data=data,
            id="cb",
            from_user=SimpleNamespace(id=user_id, first_name="U", username="u"),
            message=SimpleNamespace(
                chat=SimpleNamespace(id=chat_id, type=chat_type),
                message_thread_id=None,
                message_id=message_id,
                reply_markup=None,
            ),
        )
        for predicate, handler in self.callbacks:
            if predicate is None or predicate(call):
                handler(call)
                return True
        return False


def button_data(markup):
    """Ratakan InlineKeyboardMarkup jadi daftar (label, callback_data)."""
    return [(button.text, button.callback_data) for row in markup.keyboard for button in row]


def message(user_id, text="", chat_id=-100, thread_id=None, chat_type="supergroup"):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=user_id, first_name="U", username="u"),
        chat=SimpleNamespace(id=chat_id, type=chat_type),
        message_thread_id=thread_id,
        message_id=1,
        document=None,
        entities=None,
    )
