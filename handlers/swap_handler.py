# handlers/swap_handler.py (Versi Mention yang Telah Diperbaiki)

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

from config import GROUP_CHAT_ID, ALLOWED_TOPIC_ID
from core.database import (
    get_bulan_dibuka, get_user_jadwal_for_month, get_user_by_telegram_username,
    create_tukar_request, get_tukar_request_by_id, execute_swap,
    update_tukar_request_status, format_tanggal_indonesia
)

swap_data = {}

def register_swap_handlers(bot: telebot.TeleBot):

    def process_mention_step(message):
        user_id = message.from_user.id
        thread_id = message.message_thread_id
        
        if not message.entities or not any(e.type == 'mention' for e in message.entities):
            bot.reply_to(message, "Mention tidak valid. Ulangi dari /tukar_jadwal.", message_thread_id=thread_id)
            if user_id in swap_data: del swap_data[user_id]
            return
            
        mention_entity = next((e for e in message.entities if e.type == 'mention'), None)
        username_b_mention = message.text[mention_entity.offset : mention_entity.offset + mention_entity.length]
        
        user_b = get_user_by_telegram_username(username_b_mention)
        if not user_b:
            bot.reply_to(message, f"User {username_b_mention} tidak ditemukan. Pastikan mereka pernah menyimpan jadwal agar @username-nya tercatat. Ulangi dari /tukar_jadwal.", message_thread_id=thread_id)
            if user_id in swap_data: del swap_data[user_id]
            return
        
        user_b_id = user_b['user_id']
        user_b_name = user_b['username'] # Nama depan untuk tampilan
        user_b_username = user_b['telegram_username']

        if user_b_id == user_id:
            bot.reply_to(message, "Anda tidak bisa bertukar jadwal dengan diri sendiri. Ulangi dari /tukar_jadwal.", message_thread_id=thread_id)
            if user_id in swap_data: del swap_data[user_id]
            return

        swap_data[user_id]['user_b_id'] = user_b_id
        swap_data[user_id]['user_b_name'] = user_b_name
        swap_data[user_id]['user_b_username'] = user_b_username

        bulan_aktif = get_bulan_dibuka()
        jadwal_user_b = get_user_jadwal_for_month(user_b_id, bulan_aktif['tahun'], bulan_aktif['bulan'])
        if not jadwal_user_b:
            bot.reply_to(message, f"@{user_b_username} tidak memiliki jadwal di bulan ini untuk ditukar.", message_thread_id=thread_id)
            if user_id in swap_data: del swap_data[user_id]
            return

        markup = InlineKeyboardMarkup()
        for jadwal in jadwal_user_b:
            tgl_obj = datetime.strptime(jadwal['tanggal'], '%Y-%m-%d').date()
            label = format_tanggal_indonesia(tgl_obj)
            callback_data = f"swap_selectB_{jadwal['tanggal']}"
            markup.add(InlineKeyboardButton(label, callback_data=callback_data))
        
        bot.send_message(message.chat.id, f"Silakan pilih tanggal dari jadwal @{user_b_username} yang ingin Anda ambil:", reply_markup=markup, message_thread_id=thread_id)

    @bot.message_handler(commands=['tukar_jadwal'])
    def handle_tukar_jadwal(message):
        # ... (fungsi ini tidak berubah dari versi forward) ...
        user_id = message.from_user.id
        thread_id = message.message_thread_id
        bulan_aktif = get_bulan_dibuka()
        if not bulan_aktif:
            bot.reply_to(message, "Tidak ada jadwal yang aktif untuk ditukar.", message_thread_id=thread_id)
            return
        jadwal_user = get_user_jadwal_for_month(user_id, bulan_aktif['tahun'], bulan_aktif['bulan'])
        if not jadwal_user:
            bot.reply_to(message, "Anda tidak memiliki jadwal standby di bulan ini untuk ditukar.", message_thread_id=thread_id)
            return
        markup = InlineKeyboardMarkup()
        for jadwal in jadwal_user:
            tgl_obj = datetime.strptime(jadwal['tanggal'], '%Y-%m-%d').date()
            label = format_tanggal_indonesia(tgl_obj)
            callback_data = f"swap_selectA_{jadwal['tanggal']}"
            markup.add(InlineKeyboardButton(label, callback_data=callback_data))
        bot.reply_to(message, "Silakan pilih tanggal JADWAL ANDA yang ingin ditukar:", reply_markup=markup, message_thread_id=thread_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('swap_'))
    def handle_swap_callbacks(call):
        # ... (logika callback kembali ke versi mention) ...
        parts = call.data.split('_'); action = parts[1]; user_id = call.from_user.id; thread_id = call.message.message_thread_id
        if action == 'selectA':
            tanggal_a = parts[2]
            swap_data[user_id] = {'tanggal_a': tanggal_a}
            msg = bot.send_message(call.message.chat.id, "Baik. Sekarang, balas pesan ini dengan me-mention satu orang (contoh: @username).", reply_markup=telebot.types.ForceReply(selective=True), message_thread_id=thread_id)
            bot.register_next_step_handler(msg, process_mention_step)
            bot.answer_callback_query(call.id)
            bot.delete_message(call.message.chat.id, call.message.message_id)
        elif action == 'selectB':
            tanggal_b = parts[2]
            if user_id not in swap_data: return
            data = swap_data[user_id]
            data['tanggal_b'] = tanggal_b
            tgl_a_obj = datetime.strptime(data['tanggal_a'], '%Y-%m-%d').date()
            tgl_b_obj = datetime.strptime(data['tanggal_b'], '%Y-%m-%d').date()
            pesan = (f"Konfirmasi Pertukaran Jadwal:\n\nJadwal Anda: *{format_tanggal_indonesia(tgl_a_obj)}*\nAkan ditukar dengan jadwal @{data['user_b_username']}:\nJadwal @{data['user_b_username']}: *{format_tanggal_indonesia(tgl_b_obj)}*\n\nApakah Anda yakin?")
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("✅ Ya, Kirim", callback_data="swap_confirm"), InlineKeyboardButton("❌ Batal", callback_data="swap_cancel"))
            bot.edit_message_text(pesan, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
            bot.answer_callback_query(call.id)
        elif action == 'confirm':
            if user_id not in swap_data: return
            data = swap_data[user_id]
            request_id = create_tukar_request(user_id, call.from_user.first_name, data['user_b_id'], data['tanggal_a'], data['tanggal_b'])
            tgl_a_obj = datetime.strptime(data['tanggal_a'], '%Y-%m-%d').date()
            tgl_b_obj = datetime.strptime(data['tanggal_b'], '%Y-%m-%d').date()
            user_b_mention = f"[@{data['user_b_username']}](tg://user?id={data['user_b_id']})"
            pesan_request = (f"🔔 Permintaan Tukar Jadwal\n\nHai {user_b_mention}, pengguna *{call.from_user.first_name}* ingin bertukar jadwal dengan Anda:\n\n*{call.from_user.first_name}* memberikan jadwalnya pada *{format_tanggal_indonesia(tgl_a_obj)}*,\ndan ingin mengambil jadwal Anda pada *{format_tanggal_indonesia(tgl_b_obj)}*.\n\nApakah Anda setuju?")
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("✅ Setuju", callback_data=f"swap_approve_{request_id}"), InlineKeyboardButton("❌ Tolak", callback_data=f"swap_reject_{request_id}"))
            bot.send_message(GROUP_CHAT_ID, pesan_request, reply_markup=markup, parse_mode='Markdown', message_thread_id=ALLOWED_TOPIC_ID)
            bot.edit_message_text("✅ Permintaan Anda telah dikirim.", call.message.chat.id, call.message.message_id)
            if user_id in swap_data: del swap_data[user_id]
        elif action == 'cancel':
            bot.edit_message_text("Dibatalkan.", call.message.chat.id, call.message.message_id)
            if user_id in swap_data: del swap_data[user_id]
        elif action == 'approve' or action == 'reject':
            request_id = int(parts[2])
            req = get_tukar_request_by_id(request_id)
            if not req or req['status'] != 'PENDING':
                bot.edit_message_text("Permintaan ini sudah tidak valid.", call.message.chat.id, call.message.message_id)
                return
            if user_id != req['user_b_id']:
                bot.answer_callback_query(call.id, "Ini bukan permintaan untuk Anda.", show_alert=True)
                return
            tgl_a_obj = datetime.strptime(req['tanggal_a'], '%Y-%m-%d').date()
            tgl_b_obj = datetime.strptime(req['tanggal_b'], '%Y-%m-%d').date()
            user_b_mention = f"[{call.from_user.first_name}](tg://user?id={call.from_user.id})"
            user_a_mention = f"[{req['user_a_username']}](tg://user?id={req['user_a_id']})"
            if action == 'approve':
                success = execute_swap(request_id)
                if success:
                    pesan_final = (f"✅ Pertukaran Jadwal Disetujui!\n\n{user_a_mention} sekarang bertugas pada *{format_tanggal_indonesia(tgl_b_obj)}*.\n{user_b_mention} sekarang bertugas pada *{format_tanggal_indonesia(tgl_a_obj)}*.")
                else: pesan_final = "❌ Gagal memproses pertukaran."
            else: # reject
                update_tukar_request_status(request_id, 'REJECTED')
                pesan_final = f"❌ Permintaan tukar jadwal dari {user_a_mention} ditolak oleh {user_b_mention}."
            try: bot.edit_message_text(pesan_final, call.message.chat.id, call.message.message_id, parse_mode='Markdown')
            except: bot.send_message(call.message.chat.id, pesan_final, parse_mode='Markdown', message_thread_id=thread_id)