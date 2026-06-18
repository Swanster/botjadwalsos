# handlers/user_handlers.py (Versi Final Gabungan: Aturan Weekend + Lihat Jadwal Fleksibel)

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.apihelper import ApiTelegramException
from collections import defaultdict
from datetime import datetime, date, timedelta
import calendar
import pytz
import time

from config import ALLOWED_TOPIC_ID
from core.database import (
    GROUP_NAMES,
    get_bulan_dibuka, get_bulan_dibuka_list, get_konfigurasi, get_jadwal_for_month,
    get_user_absensi_in_range, set_user_absensi, update_user_jadwal_for_month,
    format_tanggal_indonesia, get_user_jadwal_for_month, get_jadwal_for_specific_date,
    get_user_group, get_jadwal_by_group, get_all_users_in_group, get_all_absensi_in_range,
    delete_user_jadwal_on_dates, get_setting,
    is_date_full, get_daily_limit, get_weekend_monthly_limit_key,
    validate_weekday_weekend_balance, validate_weekend_monthly_limits
)
from core.google_sheets import sync_jadwal_to_sheets, sync_absensi_to_sheets
from core.schedule_recap import generate_rekap_text as build_rekap_text

# Variabel global
user_selections, user_cuti_selections = {}, {}
user_batal_selections, user_batal_cuti_selections = {}, {}
SESSION_TIMEOUT = 900 # detik (15 menit)
NAMA_BULAN = {1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'}
HARI_MAP_ID = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}
EMOJI_HARI = {'Senin':'🌞','Selasa':'📘','Rab':'📗','Kamis':'📙','Jumat':'📕','Sabtu':'🎉','Minggu':'🛌'}

def is_allowed(message):
    """Cek apakah message berasal dari chat yang diizinkan."""
    if message.chat.type == 'private': 
        return True
    if message.chat.type in ['group', 'supergroup']:
        # Jika ALLOWED_TOPIC_ID tidak di-set (None), izinkan semua group
        # Jika di-set, hanya izinkan topic yang sesuai
        if ALLOWED_TOPIC_ID is None:
            return True
        return message.message_thread_id == ALLOWED_TOPIC_ID
    return False

def get_hari_from_date(date_str: str) -> str:
    """Dapatkan nama hari dari string tanggal YYYY-MM-DD."""
    from datetime import datetime
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    return HARI_MAP_ID[date_obj.weekday()]

def get_weekend_limit_message(tanggal_str: str) -> str:
    weekend_key = get_weekend_monthly_limit_key(tanggal_str)
    if not weekend_key:
        return "❌ Batas weekend bulanan tercapai."
    nama_hari = HARI_MAP_ID[weekend_key[2]]
    return f"❌ Hanya bisa pilih 1 {nama_hari} setiap bulan."

def is_weekend_monthly_locked(tanggal_str: str, pilihan_sementara) -> bool:
    weekend_key = get_weekend_monthly_limit_key(tanggal_str)
    if not weekend_key or tanggal_str in pilihan_sementara:
        return False
    for pilihan in pilihan_sementara:
        if get_weekend_monthly_limit_key(pilihan) == weekend_key:
            return True
    return False

def get_weekday_balance_message() -> str:
    return "❌ Anda sudah memilih 2 jadwal weekday. Pilih minimal 1 jadwal weekend dulu sebelum menambah weekday lagi."

def is_weekday_balance_locked(tanggal_str: str, pilihan_sementara) -> bool:
    if get_weekend_monthly_limit_key(tanggal_str) or tanggal_str in pilihan_sementara:
        return False
    simulated_choices = set(pilihan_sementara)
    simulated_choices.add(tanggal_str)
    is_valid, _ = validate_weekday_weekend_balance(simulated_choices)
    return not is_valid

def create_reason_button(label: str, reason: str, tanggal_str: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, callback_data=f"reason_{reason}_{tanggal_str}")

def create_calendar(mode, user_id, year, month):
    markup = InlineKeyboardMarkup()
    # Bagian header kalender (nama bulan & nama hari)
    full_date_string = format_tanggal_indonesia(date(year, month, 1))
    nama_bulan_dan_tahun = full_date_string.split(' ', 1)[1]
    markup.row(InlineKeyboardButton(nama_bulan_dan_tahun, callback_data=f'ignore'))
    days_header_text = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
    days_header = [InlineKeyboardButton(day, callback_data=f'ignore') for day in days_header_text]
    markup.row(*days_header)

    # Inisialisasi variabel-variabel yang dibutuhkan
    pilihan_sementara = set()
    jadwal_user_bulan_ini = set()
    cuti_user_bulan_ini = set()
    start_of_month = f"{year}-{month:02d}-01"
    end_of_month = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]}"

    # Mengambil data sesuai dengan mode yang aktif
    if mode == 'jadwal':
        pilihan_sementara = user_selections.get(user_id, {}).get('choices', set())
        user_group = get_user_group(user_id)
        if not user_group:
            return "❌ Anda belum terdaftar di grup mana pun. Silakan hubungi admin."
        slot_terisi_by_group = {}
        for group_name in GROUP_NAMES:
            slot_terisi = defaultdict(int)
            for j in get_jadwal_by_group(year, month, group_name):
                slot_terisi[j['tanggal']] += 1
            slot_terisi_by_group[group_name] = slot_terisi
        absensi_user = get_user_absensi_in_range(user_id, start_of_month, end_of_month)
    elif mode == 'cuti':
        pilihan_sementara = user_cuti_selections.get(user_id, {}).get('choices', set())
    elif mode == 'batal_jadwal':
        pilihan_sementara = user_batal_selections.get(user_id, {}).get('choices', set())
        jadwal_user = get_user_jadwal_for_month(user_id, year, month)
        jadwal_user_bulan_ini = {j['tanggal'] for j in jadwal_user}
    elif mode == 'batal_cuti':
        pilihan_sementara = user_batal_cuti_selections.get(user_id, {}).get('choices', set())
        cuti_user_bulan_ini = get_user_absensi_in_range(user_id, start_of_month, end_of_month)

    # Membuat tombol-tombol tanggal
    my_calendar = calendar.Calendar(firstweekday=calendar.MONDAY)
    for week in my_calendar.monthdayscalendar(year, month):
        row_buttons = []
        for day in week:
            if day == 0:
                row_buttons.append(InlineKeyboardButton(" ", callback_data=f'ignore'))
                continue
            
            current_date_obj = date(year, month, day)
            current_date_str = current_date_obj.strftime('%Y-%m-%d')
            label = str(day)

            # Logika untuk mode pembatalan jadwal
            if mode == 'batal_jadwal':
                if current_date_str in jadwal_user_bulan_ini:
                    label_final = f"🗓️ {label}"
                    if current_date_str in pilihan_sementara:
                        label_final = f"❌ {label}" # Tandai untuk dihapus
                    row_buttons.append(InlineKeyboardButton(label_final, callback_data=f"{mode}_toggle_{current_date_str}"))
                else:
                    row_buttons.append(InlineKeyboardButton(" ", callback_data='ignore'))
            
            # Logika untuk mode pembatalan cuti
            elif mode == 'batal_cuti':
                if current_date_str in cuti_user_bulan_ini:
                    label_final = f"⛔️ {label}"
                    if current_date_str in pilihan_sementara:
                        label_final = f"❌ {label}"
                    row_buttons.append(InlineKeyboardButton(label_final, callback_data=f"{mode}_toggle_{current_date_str}"))
                else:
                    row_buttons.append(InlineKeyboardButton(" ", callback_data='ignore'))

            # Logika untuk mode pengisian jadwal & cuti (yang sudah ada sebelumnya)
            else:
                if mode == 'jadwal':
                    if current_date_str in absensi_user:
                        row_buttons.append(create_reason_button("⛔️", "absen", current_date_str)); continue
                    
                    # Cek batasan harian (prioritas utama)
                    max_per_hari = get_daily_limit(current_date_str, 1)  # Default 1 jika tidak ada setting
                    jumlah_terisi = slot_terisi_by_group.get(user_group, {}).get(current_date_str, 0)
                    
                    is_penuh = jumlah_terisi >= max_per_hari
                    is_weekend_terkunci = is_weekend_monthly_locked(current_date_str, pilihan_sementara)
                    is_weekday_balance_terkunci = is_weekday_balance_locked(current_date_str, pilihan_sementara)

                    if current_date_str in pilihan_sementara: label = f"✅{label}"
                    elif is_penuh: row_buttons.append(create_reason_button("❌", "full", current_date_str)); continue
                    elif is_weekend_terkunci: row_buttons.append(create_reason_button("-", "weekend", current_date_str)); continue
                    elif is_weekday_balance_terkunci: row_buttons.append(create_reason_button("-", "weekdaybalance", current_date_str)); continue
                
                elif mode == 'cuti' and current_date_str in pilihan_sementara:
                    label = f"✅{label}"
                
                row_buttons.append(InlineKeyboardButton(label, callback_data=f"{mode}_toggle_{current_date_str}"))

        markup.row(*row_buttons)

    # Tombol Navigasi dan Simpan/Konfirmasi
    prev_month_date = date(year, month, 1) - timedelta(days=1)
    next_month_date = date(year, month, 1) + timedelta(days=32)
    simpan_text = "Konfirmasi Batal" if 'batal' in mode else "Simpan"
    nav_buttons = [
        InlineKeyboardButton("<", callback_data=f"{mode}_nav_{prev_month_date.year}_{prev_month_date.month}"),
        InlineKeyboardButton(simpan_text, callback_data=f"{mode}_save_{year}_{month}"),
        InlineKeyboardButton(">", callback_data=f"{mode}_nav_{next_month_date.year}_{next_month_date.month}")
    ]
    markup.row(*nav_buttons)
    return markup

def generate_rekap_text(tahun, bulan):
    return build_rekap_text(tahun, bulan)

def register_user_handlers(bot: telebot.TeleBot):

    def send_main_menu(chat_id, thread_id=None):
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("Isi Jadwal", callback_data="menu_start"),
            InlineKeyboardButton("Jadwal Saya", callback_data="menu_jadwal_saya")
        )
        markup.row(
            InlineKeyboardButton("Lihat Jadwal", callback_data="menu_lihat_jadwal"),
            InlineKeyboardButton("Cuti", callback_data="menu_cuti")
        )
        markup.row(
            InlineKeyboardButton("Lihat Cuti", callback_data="menu_lihat_cuti"),
            InlineKeyboardButton("Tukar Jadwal", callback_data="menu_tukar_jadwal")
        )
        markup.row(
            InlineKeyboardButton("Batal Jadwal", callback_data="menu_batal_jadwal"),
            InlineKeyboardButton("Batal Cuti", callback_data="menu_batal_cuti")
        )
        markup.row(InlineKeyboardButton("Panduan", callback_data="menu_panduan"))
        bot.send_message(chat_id, "Silakan pilih menu:", reply_markup=markup, message_thread_id=thread_id)

    def show_open_month_choices(chat_id, thread_id=None):
        bulan_terbuka_list = get_bulan_dibuka_list()
        if not bulan_terbuka_list:
            bot.send_message(chat_id, "Saat ini tidak ada periode jadwal yang sedang dibuka untuk diisi.", message_thread_id=thread_id)
            return False
        if len(bulan_terbuka_list) == 1:
            return bulan_terbuka_list[0]

        markup = InlineKeyboardMarkup()
        for bulan_terbuka in bulan_terbuka_list:
            label = f"{NAMA_BULAN[bulan_terbuka['bulan']]} {bulan_terbuka['tahun']}"
            callback_data = f"openmonth_{bulan_terbuka['tahun']}_{bulan_terbuka['bulan']}"
            markup.add(InlineKeyboardButton(label, callback_data=callback_data))
        bot.send_message(chat_id, "Pilih bulan jadwal yang ingin diisi:", reply_markup=markup, message_thread_id=thread_id)
        return None

    def start_jadwal_flow(chat_id, user, thread_id=None, tahun=None, bulan=None):
        if tahun is None or bulan is None:
            bulan_terbuka = show_open_month_choices(chat_id, thread_id)
            if not bulan_terbuka:
                return
            tahun, bulan = bulan_terbuka['tahun'], bulan_terbuka['bulan']
        else:
            bulan_terbuka_list = get_bulan_dibuka_list()
            if not any(b['tahun'] == tahun and b['bulan'] == bulan for b in bulan_terbuka_list):
                bot.send_message(chat_id, f"Jadwal untuk {NAMA_BULAN[bulan]} {tahun} tidak sedang dibuka.", message_thread_id=thread_id)
                return

        user_id = user.id
        user_group = get_user_group(user_id)
        if not user_group:
            bot.send_message(chat_id, "❌ Akun Anda belum terdaftar di grup manapun (INFRA/APPS/MONITORING). Silakan hubungi Admin untuk didaftarkan.", message_thread_id=thread_id)
            return

        jadwal_bulan_ini = get_jadwal_for_month(tahun, bulan)
        user_jadwal_lama = {row['tanggal'] for row in jadwal_bulan_ini if row['user_id'] == user_id}
        user_selections[user_id] = {
            'choices': user_jadwal_lama,
            'timestamp': time.time()
        }
        
        markup = create_calendar('jadwal', user_id, tahun, bulan)

        bot.send_message(chat_id, "Silakan pilih tanggal standby Anda untuk bulan ini.", reply_markup=markup, message_thread_id=thread_id)

    def send_jadwal_saya(chat_id, user, thread_id=None):
        user_id = user.id
        bulan_aktif = get_bulan_dibuka()
        if bulan_aktif: tahun, bulan = bulan_aktif['tahun'], bulan_aktif['bulan']
        else:
            today = date.today(); tahun, bulan = today.year, today.month
        jadwal_user = get_user_jadwal_for_month(user_id, tahun, bulan)
        if not jadwal_user:
            bot.send_message(chat_id, f"Anda tidak memiliki jadwal standby di bulan {NAMA_BULAN[bulan]} {tahun}.", message_thread_id=thread_id)
            return
        pesan = f"📜 *Jadwal Standby Anda*\n_Bulan: {NAMA_BULAN[bulan]} {tahun}_\n\n"
        for jadwal in jadwal_user:
            tgl_obj = datetime.strptime(jadwal['tanggal'], '%Y-%m-%d').date()
            nama_hari = HARI_MAP_ID[tgl_obj.weekday()]
            pesan += f"- *{nama_hari}*, {format_tanggal_indonesia(tgl_obj)}\n"
        bot.send_message(chat_id, pesan, parse_mode='Markdown', message_thread_id=thread_id)

    def send_lihat_jadwal(chat_id, thread_id=None):
        bulan_dibuka = get_bulan_dibuka()
        today = date.today()
        if bulan_dibuka and (bulan_dibuka['tahun'] != today.year or bulan_dibuka['bulan'] != today.month):
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(f"🗓️ Lihat Jadwal Bulan Ini ({NAMA_BULAN[today.month]})", callback_data=f"view_rekap_{today.year}_{today.month}"))
            markup.add(InlineKeyboardButton(f"✏️ Lihat Jadwal Dibuka ({NAMA_BULAN[bulan_dibuka['bulan']]})", callback_data=f"view_rekap_{bulan_dibuka['tahun']}_{bulan_dibuka['bulan']}"))
            bot.send_message(chat_id, "Silakan pilih rekap jadwal yang ingin Anda lihat:", reply_markup=markup, message_thread_id=thread_id)
        else:
            target_tahun, target_bulan = (bulan_dibuka['tahun'], bulan_dibuka['bulan']) if bulan_dibuka else (today.year, today.month)
            rekap_text = generate_rekap_text(target_tahun, target_bulan)
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("🗓️ Hari Ini", callback_data="view_today"), InlineKeyboardButton("📅 Minggu Ini", callback_data="view_week"))
            bot.send_message(chat_id, rekap_text, parse_mode='Markdown', message_thread_id=thread_id, reply_markup=markup)

    def start_cuti_flow(chat_id, user, thread_id=None):
        today = date.today(); user_id = user.id
        start_of_month = f"{today.year}-{today.month:02d}-01"; end_of_month = f"{today.year}-{today.month:02d}-{calendar.monthrange(today.year, today.month)[1]}"
        absensi_tersimpan = get_user_absensi_in_range(user_id, start_of_month, end_of_month)
        
        # --- PERBAIKAN DI SINI: Gunakan struktur sesi yang benar ---
        user_cuti_selections[user_id] = {
            'choices': set(absensi_tersimpan),
            'timestamp': time.time()
        }
        
        markup = create_calendar('cuti', user_id, today.year, today.month)
        bot.send_message(chat_id, "Silakan pilih tanggal di mana Anda tidak tersedia.", reply_markup=markup, message_thread_id=thread_id)

    def send_lihat_cuti(chat_id, thread_id=None):
        bulan_terbuka = get_bulan_dibuka()
        if not bulan_terbuka:
            bot.send_message(chat_id, "Saat ini tidak ada periode jadwal yang sedang dibuka.", message_thread_id=thread_id)
            return

        tahun, bulan = bulan_terbuka['tahun'], bulan_terbuka['bulan']
        start_date = f"{tahun}-{bulan:02d}-01"
        end_date = f"{tahun}-{bulan:02d}-{calendar.monthrange(tahun, bulan)[1]}"

        data_absensi = get_all_absensi_in_range(start_date, end_date)

        if not data_absensi:
            pesan = f"🥳 Tidak ada data cuti yang tercatat untuk bulan *{NAMA_BULAN[bulan]} {tahun}*."
            bot.send_message(chat_id, pesan, parse_mode='Markdown', message_thread_id=thread_id)
            return

        # Kelompokkan data absensi berdasarkan tanggal
        absensi_per_tanggal = defaultdict(list)
        for absensi in data_absensi:
            tgl_obj = datetime.strptime(absensi['tanggal'], '%Y-%m-%d').date()
            absensi_per_tanggal[tgl_obj].append(absensi['username'])

        # Urutkan tanggal
        tanggal_terurut = sorted(absensi_per_tanggal.keys())

        # Format pesan balasan
        pesan = f"🗓️ *Daftar Cuti Bulan {NAMA_BULAN[bulan]} {tahun}*:\n\n"
        for tgl_obj in tanggal_terurut:
            usernames = absensi_per_tanggal[tgl_obj]
            pesan += f"*{format_tanggal_indonesia(tgl_obj)}*:\n"
            for username in usernames:
                pesan += f"  - @{username}\n"
            pesan += "\n"

        bot.send_message(chat_id, pesan, parse_mode='Markdown', message_thread_id=thread_id)

    def start_batal_jadwal_flow(chat_id, user, thread_id=None):
        user_id = user.id
        bulan_terbuka = get_bulan_dibuka()
        
        if not bulan_terbuka:
            bot.send_message(chat_id, "Saat ini tidak ada periode jadwal yang sedang dibuka untuk dibatalkan.", message_thread_id=thread_id)
            return

        tahun, bulan = bulan_terbuka['tahun'], bulan_terbuka['bulan']
    
        # Inisialisasi sesi pembatalan
        user_batal_selections[user_id] = {'choices': set(), 'timestamp': time.time()}
        
        markup = create_calendar('batal_jadwal', user_id, tahun, bulan)
        bot.send_message(chat_id, "Pilih jadwal yang ingin Anda batalkan:", reply_markup=markup, message_thread_id=thread_id)


    def start_batal_cuti_flow(chat_id, user, thread_id=None):
        user_id = user.id
        today = date.today()
        tahun, bulan = today.year, today.month
        
        # Inisialisasi sesi pembatalan cuti
        user_batal_cuti_selections[user_id] = {'choices': set(), 'timestamp': time.time()}

        markup = create_calendar('batal_cuti', user_id, tahun, bulan)
        bot.send_message(chat_id, "Pilih tanggal cuti yang ingin Anda batalkan:", reply_markup=markup, message_thread_id=thread_id)

    def send_guide(chat_id, thread_id=None):
        help_text = (
            "ℹ️ *Panduan Bot Jadwal Standby*\n\n"
            "Perintah yang bisa digunakan di grup:\n\n"
            "*/menu* - Membuka tombol menu bot.\n"
            "*/start* - Mengisi/mengedit jadwal Anda.\n"
            "*/lihat_jadwal* - Menampilkan rekap jadwal tim.\n"
            "*/jadwal_saya* - Menampilkan daftar jadwal pribadi Anda.\n"
            "*/cuti* - Menandai tanggal Anda tidak bersedia (cuti).\n"
            "*/lihat_cuti* - Menampilkan daftar cuti tim di bulan aktif.\n"
            "*/tukar_jadwal* - Mengajukan pertukaran jadwal.\n"
            "*/batal_jadwal* - Membatalkan jadwal standby yang sudah ada.\n"
            "*/batal_cuti* - Membatalkan data cuti yang sudah ada.\n"
            "*/guide* atau */panduan* - Menampilkan panduan ini.\n\n"
            "📌 *Catatan aturan jadwal:*\n"
            "- Maksimal 2 jadwal weekday sebelum memilih minimal 1 jadwal weekend.\n"
            "- Setiap orang maksimal 1 Sabtu dan 1 Minggu setiap bulan.\n"
            "- Tukar jadwal harus tipe hari yang sama: weekday dengan weekday, weekend dengan weekend."
        )
        bot.send_message(chat_id, help_text, parse_mode='Markdown', message_thread_id=thread_id)

    @bot.message_handler(commands=['menu'])
    def handle_menu(message):
        if not is_allowed(message): return
        send_main_menu(message.chat.id, message.message_thread_id)

    @bot.message_handler(commands=['start'])
    def handle_start(message):
        if not is_allowed(message): return
        start_jadwal_flow(message.chat.id, message.from_user, message.message_thread_id)

    @bot.message_handler(commands=['jadwal_saya'])
    def handle_jadwal_saya(message):
        if not is_allowed(message): return
        send_jadwal_saya(message.chat.id, message.from_user, message.message_thread_id)

    @bot.message_handler(commands=['lihat_jadwal'])
    def handle_lihat_jadwal(message):
        if not is_allowed(message): return
        send_lihat_jadwal(message.chat.id, message.message_thread_id)

    @bot.message_handler(commands=['cuti'])
    def handle_cuti(message):
        if not is_allowed(message): return
        start_cuti_flow(message.chat.id, message.from_user, message.message_thread_id)
        
    @bot.message_handler(commands=['lihat_cuti'])
    def handle_lihat_cuti(message):
        """Menampilkan daftar pengguna yang sedang cuti di bulan yang sedang dibuka."""
        if not is_allowed(message):
            return
        send_lihat_cuti(message.chat.id, message.message_thread_id)

    @bot.message_handler(commands=['batal_jadwal'])
    def handle_batal_jadwal(message):
        """Membatalkan semua jadwal standby pengguna di bulan aktif."""
        if not is_allowed(message):
            return
        start_batal_jadwal_flow(message.chat.id, message.from_user, message.message_thread_id)

    @bot.message_handler(commands=['batal_cuti'])
    def handle_batal_cuti(message):
        if not is_allowed(message): return
        start_batal_cuti_flow(message.chat.id, message.from_user, message.message_thread_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('menu_'))
    def handle_menu_callbacks(call):
        thread_id = call.message.message_thread_id
        action = call.data[5:]

        if action == 'start':
            start_jadwal_flow(call.message.chat.id, call.from_user, thread_id)
        elif action == 'jadwal_saya':
            send_jadwal_saya(call.message.chat.id, call.from_user, thread_id)
        elif action == 'lihat_jadwal':
            send_lihat_jadwal(call.message.chat.id, thread_id)
        elif action == 'cuti':
            start_cuti_flow(call.message.chat.id, call.from_user, thread_id)
        elif action == 'lihat_cuti':
            send_lihat_cuti(call.message.chat.id, thread_id)
        elif action == 'batal_jadwal':
            start_batal_jadwal_flow(call.message.chat.id, call.from_user, thread_id)
        elif action == 'batal_cuti':
            start_batal_cuti_flow(call.message.chat.id, call.from_user, thread_id)
        elif action == 'tukar_jadwal':
            bot.send_message(call.message.chat.id, "Untuk tukar jadwal, gunakan perintah `/tukar_jadwal` lalu pilih jadwal dan mention rekan yang ingin diajak tukar.", parse_mode='Markdown', message_thread_id=thread_id)
        elif action == 'panduan':
            send_guide(call.message.chat.id, thread_id)

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('reason_'))
    def handle_calendar_reason_callbacks(call):
        parts = call.data.split('_', 2)
        reason = parts[1] if len(parts) > 1 else ''
        tanggal_str = parts[2] if len(parts) > 2 else ''

        if reason == 'absen':
            message_text = "Tanggal ini terkunci karena Anda menandai cuti/tidak tersedia."
        elif reason == 'full':
            max_limit = get_daily_limit(tanggal_str, 1)
            message_text = f"Tanggal ini sudah penuh ({max_limit} orang)."
        elif reason == 'weekend':
            message_text = get_weekend_limit_message(tanggal_str)
        elif reason == 'weekdaybalance':
            message_text = get_weekday_balance_message()
        else:
            message_text = "Tanggal ini tidak bisa dipilih."

        bot.answer_callback_query(call.id, message_text, show_alert=True)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('openmonth_'))
    def handle_open_month_callbacks(call):
        parts = call.data.split('_')
        if len(parts) != 3:
            bot.answer_callback_query(call.id, "Pilihan bulan tidak valid.", show_alert=True)
            return

        tahun, bulan = int(parts[1]), int(parts[2])
        start_jadwal_flow(call.message.chat.id, call.from_user, call.message.message_thread_id, tahun, bulan)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.split('_')[0] in ['jadwal', 'cuti', 'view', 'batal'])
    def handle_all_callbacks(call):
        parts = call.data.split('_')
        mode = parts[0]
        user_id = call.from_user.id
        thread_id = call.message.message_thread_id
        
        full_mode = mode
        if mode == 'batal' and len(parts) > 1:
            full_mode = f"batal_{parts[1]}"

        # --- PERBAIKAN LOGIKA SESI ---
        interactive_modes = ['jadwal', 'cuti', 'batal_jadwal', 'batal_cuti']
        if full_mode in interactive_modes:
            session_map = {
                'jadwal': user_selections, 'cuti': user_cuti_selections,
                'batal_jadwal': user_batal_selections, 'batal_cuti': user_batal_cuti_selections
            }
            selection_dict = session_map.get(full_mode)
            if selection_dict is None:
                print(f"CRITICAL ERROR: Tidak ada kamus sesi untuk mode '{full_mode}'")
                return
            sesi_user = selection_dict.get(user_id)
            if not sesi_user or (time.time() - sesi_user.get('timestamp', 0)) > SESSION_TIMEOUT:
                if user_id in selection_dict: del selection_dict[user_id]
                bot.answer_callback_query(call.id)
                try: bot.delete_message(call.message.chat.id, call.message.message_id)
                except ApiTelegramException: pass
                bot.send_message(call.message.chat.id, "⚠️ Sesi Anda telah berakhir. Silakan mulai lagi.", message_thread_id=thread_id)
                return
            sesi_user['timestamp'] = time.time()

        action = parts[1] if len(parts) > 1 else ''
        
        # --- BAGIAN 2: Logika untuk Tombol 'Lihat Jadwal' ---
        if mode == 'view':
            if action == 'rekap':
                tahun, bulan = int(parts[2]), int(parts[3])
                rekap_text = generate_rekap_text(tahun, bulan)
                markup = InlineKeyboardMarkup()
                markup.row(InlineKeyboardButton("🗓️ Hari Ini", callback_data="view_today"), InlineKeyboardButton("📅 Minggu Ini", callback_data="view_week"))
                try:
                    bot.edit_message_text(rekap_text, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)
                except ApiTelegramException as e:
                    if "message is not modified" not in e.description: raise
            else:
                today = datetime.now(pytz.timezone("Asia/Makassar")).date()
                if action == 'today':
                    petugas = get_jadwal_for_specific_date(today.strftime('%Y-%m-%d'))
                    if not petugas:
                        info_text = f"Tidak ada yang bertugas hari ini, {format_tanggal_indonesia(today)}."
                    else:
                        nama_petugas = ', '.join([p['username'] for p in petugas])
                        info_text = f"Petugas hari ini ({format_tanggal_indonesia(today)}):\n\n- {nama_petugas}"
                    bot.answer_callback_query(call.id, info_text, show_alert=True)
                elif action == 'week':
                    start_of_week = today - timedelta(days=today.weekday())
                    end_of_week = start_of_week + timedelta(days=6)
                    pesan = f"🗓️ *Jadwal Minggu Ini ({start_of_week.day} - {end_of_week.day} {NAMA_BULAN[end_of_week.month]})*\n\n"
                    for i in range(7):
                        current_date = start_of_week + timedelta(days=i)
                        petugas = get_jadwal_for_specific_date(current_date.strftime('%Y-%m-%d'))
                        nama_hari = HARI_MAP_ID[current_date.weekday()]
                        if petugas:
                            pesan += f"*{nama_hari}*, {current_date.day}: {', '.join([p['username'] for p in petugas])}\n"
                        else:
                            pesan += f"*{nama_hari}*, {current_date.day}: _(kosong)_\n"
                    try:
                        bot.edit_message_text(pesan, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=call.message.reply_markup)
                    except ApiTelegramException as e:
                        if "message is not modified" not in e.description: raise
                    bot.answer_callback_query(call.id)

        # --- BAGIAN 3: Logika untuk Interaksi Kalender 'Jadwal' atau 'Cuti' ---
        elif mode == 'jadwal' or mode == 'cuti':
            selection_dict = user_selections if mode == 'jadwal' else user_cuti_selections
            if action == 'toggle':
                date_str = '_'.join(parts[2:])
                selections = selection_dict[user_id]['choices']
                if mode == 'jadwal' and date_str not in selections:
                    if is_weekend_monthly_locked(date_str, selections):
                        bot.answer_callback_query(call.id, get_weekend_limit_message(date_str), show_alert=True)
                        return

                    if is_weekday_balance_locked(date_str, selections):
                        bot.answer_callback_query(call.id, get_weekday_balance_message(), show_alert=True)
                        return

                    # --- LOGIKA BARU: Cek batasan harian ---
                    if is_date_full(date_str, 1):
                        max_limit = get_daily_limit(date_str, 1)
                        bot.answer_callback_query(call.id, f"❌ Tanggal ini sudah penuh ({max_limit} orang).", show_alert=True)
                        return

                    # --- LOGIKA LAMA: Batasan dinamis per grup dari database ---
                    user_group = get_user_group(user_id)
                    max_hari_keys = {
                        'INFRA': ('max_hari_infra', '10'),
                        'APPS': ('max_hari_apps', '31'),
                        'MONITORING': ('max_hari_monitoring', '31'),
                    }
                    max_hari_key, max_hari_default = max_hari_keys.get(user_group, ('max_hari_apps', '31'))
                    max_hari = int(get_setting(max_hari_key, max_hari_default))
                    # Hitung pilihan saat ini di bulan yang sama dengan tanggal yang akan ditambahkan
                    dt_obj_toggle = datetime.strptime(date_str, '%Y-%m-%d')
                    pilihan_bulan_ini = {s for s in selections if datetime.strptime(s, '%Y-%m-%d').month == dt_obj_toggle.month}
                    if len(pilihan_bulan_ini) >= max_hari:
                        bot.answer_callback_query(call.id, f"❌ Kuota maksimal {max_hari} hari/bulan untuk tim {user_group} telah tercapai.", show_alert=True)
                        return

                if date_str in selections: selections.remove(date_str)
                else: selections.add(date_str)
                dt_obj = datetime.strptime(date_str, '%Y-%m-%d')
                markup = create_calendar(mode, user_id, dt_obj.year, dt_obj.month)
                try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
                except ApiTelegramException as e:
                    if "message is not modified" not in e.description: raise

            elif action == 'nav':
                year, month = int(parts[2]), int(parts[3])
                markup = create_calendar(mode, user_id, year, month)
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)

            elif action == 'save':
                year, month = int(parts[2]), int(parts[3])
                pilihan_final = list(selection_dict.get(user_id, {}).get('choices', []))
                if mode == 'jadwal':
                    is_valid, error_message = validate_weekend_monthly_limits(pilihan_final)
                    if not is_valid:
                        bot.answer_callback_query(call.id, f"❌ {error_message}", show_alert=True)
                        return
                    is_valid, error_message = validate_weekday_weekend_balance(pilihan_final)
                    if not is_valid:
                        bot.answer_callback_query(call.id, f"❌ {error_message}", show_alert=True)
                        return
                    update_success = update_user_jadwal_for_month(user_id, call.from_user.first_name, call.from_user.username, pilihan_final, year, month)
                    if not update_success:
                        bot.answer_callback_query(call.id, "❌ Gagal menyimpan jadwal. Mohon periksa pilihan Anda.", show_alert=True)
                        return
                    pesan = f"✅ Jadwal Anda untuk bulan {NAMA_BULAN[month]} {year} telah disimpan."
                    
                    # Sync ke Google Sheets untuk setiap tanggal yang dipilih
                    user_group = get_user_group(user_id)
                    for tanggal in pilihan_final:
                        hari = get_hari_from_date(tanggal)
                        sync_jadwal_to_sheets(
                            tanggal=tanggal,
                            hari=hari,
                            username=call.from_user.username or call.from_user.first_name,
                            group=user_group or 'UNKNOWN'
                        )
                else: # cuti
                    set_user_absensi(user_id, pilihan_final, year, month) # Modifikasi kecil agar lebih aman
                    pesan = f"✅ Data cuti Anda untuk bulan {NAMA_BULAN[month]} {year} telah diperbarui."
                    
                    # Sync ke Google Sheets untuk setiap tanggal cuti
                    for tanggal in pilihan_final:
                        sync_absensi_to_sheets(
                            tanggal=tanggal,
                            username=call.from_user.username or call.from_user.first_name,
                            user_id=user_id
                        )
                if user_id in selection_dict: del selection_dict[user_id]
                try: bot.delete_message(call.message.chat.id, call.message.message_id)
                except ApiTelegramException: pass
                bot.send_message(call.message.chat.id, pesan, message_thread_id=thread_id)
                    
        elif mode == 'batal':
            sub_mode = parts[1] # 'jadwal' atau 'cuti'
            action = parts[2]
            selection_dict = user_batal_selections if sub_mode == 'jadwal' else user_batal_cuti_selections

            if action == 'toggle':
                date_str = '_'.join(parts[3:])
                selections = selection_dict[user_id]['choices']
                if date_str in selections: selections.remove(date_str)
                else: selections.add(date_str)
                
                dt_obj = datetime.strptime(date_str, '%Y-%m-%d')
                markup = create_calendar(f"batal_{sub_mode}", user_id, dt_obj.year, dt_obj.month)
                try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
                except ApiTelegramException as e:
                    if "message is not modified" not in e.description: raise
            
            elif action == 'nav':
                year, month = int(parts[3]), int(parts[4])
                markup = create_calendar(f"batal_{sub_mode}", user_id, year, month)
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)

            elif action == 'save':
                year, month = int(parts[3]), int(parts[4])
                pilihan_batal = list(selection_dict.get(user_id, {}).get('choices', []))
                
                if not pilihan_batal:
                    bot.answer_callback_query(call.id, "Tidak ada tanggal yang dipilih untuk dibatalkan.", show_alert=True)
                    return
                
                pesan_konfirmasi = ""
                if sub_mode == 'jadwal':
                    # Pastikan fungsi ini ada di database.py
                    rows_deleted = delete_user_jadwal_on_dates(user_id, pilihan_batal) 
                    pesan_konfirmasi = f"✅ Berhasil membatalkan {rows_deleted} jadwal."
                elif sub_mode == 'cuti':
                    start_of_month = f"{year}-{month:02d}-01"; end_of_month = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]}"
                    cuti_sebelumnya = get_user_absensi_in_range(user_id, start_of_month, end_of_month)
                    cuti_tersisa = cuti_sebelumnya - set(pilihan_batal)
                    set_user_absensi(user_id, list(cuti_tersisa))
                    pesan_konfirmasi = f"✅ Berhasil membatalkan {len(pilihan_batal)} tanggal cuti."

                if user_id in selection_dict: del selection_dict[user_id]
                try: bot.delete_message(call.message.chat.id, call.message.message_id)
                except ApiTelegramException: pass
                bot.send_message(call.message.chat.id, pesan_konfirmasi, message_thread_id=thread_id)

        bot.answer_callback_query(call.id)
    
def register_help_handler(bot: telebot.TeleBot):
        @bot.message_handler(commands=['help', 'guide', 'panduan'])
        def handle_help(message):
            if not is_allowed(message): return
            help_text = (
                "ℹ️ *Panduan Bot Jadwal Standby*\n\n"
                "Perintah yang bisa digunakan di grup:\n\n"
                "*/menu* - Membuka tombol menu bot.\n"
                "*/start* - Mengisi/mengedit jadwal Anda.\n"
                "*/lihat_jadwal* - Menampilkan rekap jadwal tim.\n"
                "*/jadwal_saya* - Menampilkan daftar jadwal pribadi Anda.\n"
                "*/cuti* - Menandai tanggal Anda tidak bersedia (cuti).\n"
                "*/lihat_cuti* - Menampilkan daftar cuti tim di bulan aktif.\n"
                "*/tukar_jadwal* - Mengajukan pertukaran jadwal.\n"
                "*/batal_jadwal* - Membatalkan jadwal standby yang sudah ada.\n"
                "*/batal_cuti* - Membatalkan data cuti yang sudah ada.\n"
                "*/guide* atau */panduan* - Menampilkan panduan ini.\n\n"
                "📌 *Catatan aturan jadwal:*\n"
                "- Maksimal 2 jadwal weekday sebelum memilih minimal 1 jadwal weekend.\n"
                "- Setiap orang maksimal 1 Sabtu dan 1 Minggu setiap bulan.\n"
                "- Tukar jadwal harus tipe hari yang sama: weekday dengan weekday, weekend dengan weekend."
            )
            bot.send_message(message.chat.id, help_text, parse_mode='Markdown', message_thread_id=message.message_thread_id)
