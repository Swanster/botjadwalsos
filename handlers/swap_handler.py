# handlers/swap_handler.py (Versi Mention yang Telah Diperbaiki)

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

from config import GROUP_CHAT_ID, ALLOWED_TOPIC_ID
from handlers.access import deny_private_callback, private_denied
from core.telegram_text import escape_markdown
from core.database import (
    get_bulan_dibuka_list, get_user_jadwal_for_month, get_user_by_telegram_username,
    create_tukar_request, get_tukar_request_by_id, execute_swap,
    update_tukar_request_status, format_tanggal_indonesia, validate_swap_date_type
)

NAMA_BULAN = {
    1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni',
    7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
}

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

        sesi = swap_data[user_id]
        jadwal_user_b = get_user_jadwal_for_month(user_b_id, sesi['tahun'], sesi['bulan'])
        if not jadwal_user_b:
            bot.reply_to(message, f"@{user_b_username} tidak memiliki jadwal di bulan itu untuk ditukar.", message_thread_id=thread_id)
            if user_id in swap_data: del swap_data[user_id]
            return

        markup = InlineKeyboardMarkup()
        for jadwal in jadwal_user_b:
            tgl_obj = datetime.strptime(jadwal['tanggal'], '%Y-%m-%d').date()
            label = format_tanggal_indonesia(tgl_obj)
            callback_data = f"swap_selectB_{jadwal['tanggal']}"
            markup.add(InlineKeyboardButton(label, callback_data=callback_data))
        
        bot.send_message(message.chat.id, f"Silakan pilih tanggal dari jadwal @{user_b_username} yang ingin Anda ambil:", reply_markup=markup, message_thread_id=thread_id)

    def start_tukar_flow(chat_id, user_id, thread_id, tahun, bulan):
        jadwal_user = get_user_jadwal_for_month(user_id, tahun, bulan)
        if not jadwal_user:
            bot.send_message(
                chat_id,
                f"Anda tidak memiliki jadwal standby di {NAMA_BULAN[bulan]} {tahun} untuk ditukar.",
                message_thread_id=thread_id,
            )
            return
        markup = InlineKeyboardMarkup()
        for jadwal in jadwal_user:
            tgl_obj = datetime.strptime(jadwal['tanggal'], '%Y-%m-%d').date()
            label = format_tanggal_indonesia(tgl_obj)
            callback_data = f"swap_selectA_{jadwal['tanggal']}"
            markup.add(InlineKeyboardButton(label, callback_data=callback_data))
        bot.send_message(chat_id, "Silakan pilih tanggal JADWAL ANDA yang ingin ditukar:", reply_markup=markup, message_thread_id=thread_id)

    @bot.message_handler(commands=['tukar_jadwal'])
    def handle_tukar_jadwal(message):
        if private_denied(message.chat.type, message.from_user.id):
            return
        user_id = message.from_user.id
        thread_id = message.message_thread_id
        bulan_terbuka_list = get_bulan_dibuka_list()
        if not bulan_terbuka_list:
            bot.reply_to(message, "Tidak ada jadwal yang aktif untuk ditukar.", message_thread_id=thread_id)
            return
        if len(bulan_terbuka_list) == 1:
            b = bulan_terbuka_list[0]
            start_tukar_flow(message.chat.id, user_id, thread_id, b['tahun'], b['bulan'])
            return
        markup = InlineKeyboardMarkup()
        for b in bulan_terbuka_list:
            markup.add(InlineKeyboardButton(
                f"{NAMA_BULAN[b['bulan']]} {b['tahun']}",
                callback_data=f"pick_tukar_{b['tahun']}_{b['bulan']}",
            ))
        bot.send_message(message.chat.id, "Pilih bulan jadwal yang ingin ditukar:", reply_markup=markup, message_thread_id=thread_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('pick_tukar_'))
    def handle_pick_tukar(call):
        if deny_private_callback(bot, call):
            return
        parts = call.data.split('_')
        tahun, bulan = int(parts[-2]), int(parts[-1])
        start_tukar_flow(call.message.chat.id, call.from_user.id, call.message.message_thread_id, tahun, bulan)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('swap_'))
    def handle_swap_callbacks(call):
        # ... (logika callback kembali ke versi mention) ...
        if deny_private_callback(bot, call):
            return
        parts = call.data.split('_'); action = parts[1]; user_id = call.from_user.id; thread_id = call.message.message_thread_id
        if action == 'selectA':
            tanggal_a = parts[2]
            tgl_obj = datetime.strptime(tanggal_a, '%Y-%m-%d').date()
            swap_data[user_id] = {'tanggal_a': tanggal_a, 'tahun': tgl_obj.year, 'bulan': tgl_obj.month}
            msg = bot.send_message(call.message.chat.id, "Baik. Sekarang, balas pesan ini dengan me-mention satu orang (contoh: @username).", reply_markup=telebot.types.ForceReply(selective=True), message_thread_id=thread_id)
            bot.register_next_step_handler(msg, process_mention_step)
            bot.answer_callback_query(call.id)
            bot.delete_message(call.message.chat.id, call.message.message_id)
        elif action == 'selectB':
            tanggal_b = parts[2]
            if user_id not in swap_data: return
            data = swap_data[user_id]
            data['tanggal_b'] = tanggal_b
            is_valid_swap_type, swap_type_error = validate_swap_date_type(data['tanggal_a'], data['tanggal_b'])
            if not is_valid_swap_type:
                bot.answer_callback_query(call.id, f"❌ {swap_type_error}", show_alert=True)
                return
            tgl_a_obj = datetime.strptime(data['tanggal_a'], '%Y-%m-%d').date()
            tgl_b_obj = datetime.strptime(data['tanggal_b'], '%Y-%m-%d').date()
            nama_b = escape_markdown(data['user_b_username'])
            pesan = (f"Konfirmasi Pertukaran Jadwal:\n\nJadwal Anda: *{format_tanggal_indonesia(tgl_a_obj)}*\nAkan ditukar dengan jadwal @{nama_b}:\nJadwal @{nama_b}: *{format_tanggal_indonesia(tgl_b_obj)}*\n\nApakah Anda yakin?")
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("✅ Ya, Kirim", callback_data="swap_confirm"), InlineKeyboardButton("❌ Batal", callback_data="swap_cancel"))
            bot.edit_message_text(pesan, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
            bot.answer_callback_query(call.id)
        elif action == 'confirm':
            if user_id not in swap_data: return
            data = swap_data[user_id]
            is_valid_swap_type, swap_type_error = validate_swap_date_type(data['tanggal_a'], data['tanggal_b'])
            if not is_valid_swap_type:
                bot.answer_callback_query(call.id, f"❌ {swap_type_error}", show_alert=True)
                if user_id in swap_data: del swap_data[user_id]
                return
            request_id = create_tukar_request(user_id, call.from_user.first_name, data['user_b_id'], data['tanggal_a'], data['tanggal_b'])
            tgl_a_obj = datetime.strptime(data['tanggal_a'], '%Y-%m-%d').date()
            tgl_b_obj = datetime.strptime(data['tanggal_b'], '%Y-%m-%d').date()
            user_b_mention = f"[@{escape_markdown(data['user_b_username'])}](tg://user?id={data['user_b_id']})"
            nama_a = escape_markdown(call.from_user.first_name)
            pesan_request = (f"🔔 Permintaan Tukar Jadwal\n\nHai {user_b_mention}, pengguna *{nama_a}* ingin bertukar jadwal dengan Anda:\n\n*{nama_a}* memberikan jadwalnya pada *{format_tanggal_indonesia(tgl_a_obj)}*,\ndan ingin mengambil jadwal Anda pada *{format_tanggal_indonesia(tgl_b_obj)}*.\n\nApakah Anda setuju?")
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
            user_b_mention = f"[{escape_markdown(call.from_user.first_name)}](tg://user?id={call.from_user.id})"
            user_a_mention = f"[{escape_markdown(req['user_a_username'])}](tg://user?id={req['user_a_id']})"
            if action == 'approve':
                result = execute_swap(request_id)
                if result.ok:
                    tgl_a_obj = datetime.strptime(req['tanggal_a'], '%Y-%m-%d').date()
                    tgl_b_obj = datetime.strptime(req['tanggal_b'], '%Y-%m-%d').date()
                    pesan_final = (f"✅ Pertukaran Jadwal Disetujui!\n\n{user_a_mention} sekarang bertugas pada *{format_tanggal_indonesia(tgl_b_obj)}*.\n{user_b_mention} sekarang bertugas pada *{format_tanggal_indonesia(tgl_a_obj)}*.")
                    try: bot.edit_message_text(pesan_final, call.message.chat.id, call.message.message_id, parse_mode='Markdown')
                    except: bot.send_message(call.message.chat.id, pesan_final, parse_mode='Markdown', message_thread_id=thread_id)
                else:
                    error_messages = {
                        'database_locked': result.message or 'Sistem sedang sibuk. Silakan coba beberapa saat lagi.',
                        'stale_request': 'Permintaan tukar jadwal sudah tidak valid atau jadwal telah berubah.',
                        'swap_conflict': result.message or 'Pertukaran tidak dapat diproses karena terjadi bentrok jadwal.',
                        'delivery_exact_one': result.message or 'Infra Delivery harus memiliki tepat 1 jadwal pada bulan ini.',
                        'monthly_limit': result.message or 'Pertukaran melebihi batas jadwal bulanan.',
                        'same_date': 'Tanggal yang ditukar tidak boleh sama.',
                        'invalid_dates': result.message or 'Format tanggal tidak valid.',
                        'invalid_date_type': result.message or 'Tipe hari tidak cocok.',
                        'weekend_limit': result.message or 'Pertukaran melanggar batas jadwal weekend.',
                        'weekday_balance': result.message or 'Pertukaran melanggar keseimbangan weekday/weekend.',
                    }
                    pesan_error = error_messages.get(result.error_code, result.message or 'Gagal memproses pertukaran jadwal.')
                    bot.answer_callback_query(call.id, f"❌ {pesan_error}", show_alert=True)
                return
            else: # reject
                update_tukar_request_status(request_id, 'REJECTED')
                pesan_final = f"❌ Permintaan tukar jadwal dari {user_a_mention} ditolak oleh {user_b_mention}."
                try: bot.edit_message_text(pesan_final, call.message.chat.id, call.message.message_id, parse_mode='Markdown')
                except: bot.send_message(call.message.chat.id, pesan_final, parse_mode='Markdown', message_thread_id=thread_id)
