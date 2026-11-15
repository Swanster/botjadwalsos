"""Ambil chat_id grup tempat bot ditambahkan.

Jalankan script ini, lalu kirim pesan apa saja di grup (mis. /start).
Script akan mencetak chat_id yang bisa disalin ke GROUP_CHAT_ID di .env.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

import telebot

token = os.environ.get("API_TOKEN")
if not token:
    raise SystemExit("API_TOKEN tidak ditemukan di .env")

bot = telebot.TeleBot(token)
print("Menunggu pesan di grup... kirim /start di grup target.")
print("Tekan Ctrl+C untuk berhenti.")

seen = set()


@bot.message_handler(func=lambda m: True)
def capture(message):
    chat = message.chat
    key = (chat.id, getattr(chat, "title", None))
    if key in seen:
        return
    seen.add(key)
    print(f"chat_id={chat.id}  type={chat.type}  title={getattr(chat, 'title', None)}  thread_id={message.message_thread_id}")


bot.infinity_polling(timeout=20, long_polling_timeout=20)
