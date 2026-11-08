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
from handlers.access import deny_private_callback, private_denied, deny_unregistered
import core.database as db
from core.database import (
    get_bulan_dibuka, get_bulan_dibuka_list, get_konfigurasi, get_jadwal_for_month,
    get_user_absensi_in_range, set_user_absensi, update_user_jadwal_for_month,
    format_tanggal_indonesia, get_user_jadwal_for_month, get_jadwal_for_specific_date,
    get_user_group, get_all_users_in_group, get_all_absensi_in_range,
    delete_user_jadwal_on_dates,
    get_weekend_monthly_limit_key,
    validate_weekday_weekend_balance, validate_weekend_monthly_limits,
    is_weekend_fallback_active_for_user, today_wita
)
SAVE_ERROR_MESSAGES = {
    'delivery_exact_one': 'Infra Delivery harus memiliki tepat 1 jadwal pada bulan ini.',
    'monthly_limit': 'Jumlah jadwal melebihi batas bulanan divisi Anda.',
    'date_conflict': 'Tanggal yang dipilih sudah penuh (Batasan Harian tercapai). Silakan pilih tanggal lain.',
    'weekend_limit': 'Batas jadwal Sabtu/Minggu per bulan terlampaui.',
    'weekday_balance': 'Batas keseimbangan weekday/weekend terlampaui.',
    'database_locked': db.LOCK_RETRY_MESSAGE,
}

from core.google_sheets import sync_jadwal_to_sheets, sync_absensi_to_sheets
from core.schedule_recap import generate_rekap_text as build_rekap_text
from core.ai_query import answer as ai_answer, ASK_HELP_MSG
from core.schedule_agent import is_fill_request, build_fill_plan, store_pending, format_plan, is_help_question, get_help_text, is_replace_request
from core.telegram_text import escape_markdown

# Variabel global
user_selections, user_cuti_selections = {}, {}
user_batal_selections, user_batal_cuti_selections = {}, {}
SESSION_TIMEOUT = 900 # detik (15 menit)
NAMA_BULAN = {1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'}
HARI_MAP_ID = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}
EMOJI_HARI = {'Senin':'🌞','Selasa':'📘','Rab':'📗','Kamis':'📙','Jumat':'📕','Sabtu':'🎉','Minggu':'🛌'}

def is_allowed(message, bot=None):
    """Cek apakah message berasal dari chat yang diizinkan dan user terdaftar.

    Chat pribadi: hanya admin (ADMIN_ID). Anggota tim memakai grup/topik.
    Grup: user harus ada di user_groups; bila belum, bot mengirim penjelasan.
    """
    if private_denied(message.chat.type, message.from_user.id):
        return False
    if message.chat.type == 'private': 
        return True
    if message.chat.type in ['group', 'supergroup']:
        # Jika ALLOWED_TOPIC_ID tidak di-set (None), izinkan semua group
        # Jika di-set, hanya izinkan topic yang sesuai
        if ALLOWED_TOPIC_ID is not None and message.message_thread_id != ALLOWED_TOPIC_ID:
            return False
        return not deny_unregistered(bot, message.chat.id, message.from_user.id, message.message_thread_id)
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

def is_month_open(tahun, bulan):
    """True bila (tahun, bulan) ada di daftar periode yang dibuka admin."""
    return any(b['tahun'] == tahun and b['bulan'] == bulan for b in get_bulan_dibuka_list())


def is_weekend_monthly_locked(tanggal_str: str, pilihan_sementara) -> bool:
    weekend_key = get_weekend_monthly_limit_key(tanggal_str)
    if not weekend_key or tanggal_str in pilihan_sementara:
        return False
    for pilihan in pilihan_sementara:
        if get_weekend_monthly_limit_key(pilihan) == weekend_key:
            return True
    return False

def get_weekday_balance_message(weekend_full=False, weekday_limit=2) -> str:
    limit = weekday_limit + (1 if weekend_full else 0)
    return f"❌ Anda sudah memilih maksimal {limit} jadwal weekday bulan ini."

def is_weekday_balance_locked(tanggal_str: str, pilihan_sementara, weekend_full=False, weekday_limit=2) -> bool:
    if get_weekend_monthly_limit_key(tanggal_str) or tanggal_str in pilihan_sementara:
        return False
    simulated_choices = set(pilihan_sementara)
    simulated_choices.add(tanggal_str)
    is_valid, _ = validate_weekday_weekend_balance(
        simulated_choices, weekday_limit=weekday_limit, weekend_full=weekend_full
    )
    return not is_valid

def create_reason_button(label: str, reason: str, tanggal_str: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, callback_data=f"reason_{reason}_{tanggal_str}")

def _month_seed_choices(mode, user_id, year, month):
    """Pilihan awal untuk satu bulan: jadwal tersimpan (jadwal) atau cuti tersimpan (cuti)."""
    if mode == 'jadwal':
        return {row['tanggal'] for row in get_user_jadwal_for_month(user_id, year, month)}
    start = f"{year}-{month:02d}-01"
    end = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]}"
    return set(get_user_absensi_in_range(user_id, start, end))


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
        # Invariant per bulan: sekali dihitung, bukan per tanggal.
        weekday_allowance = db.get_weekday_allowance_for_group(user_group)
        weekend_full = is_weekend_fallback_active_for_user(user_id, year, month)
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

                    # Gerbang tampilan sejalan backend: satu-per-tanggal dan
                    # jatah weekday turunan Maksimal Hari/Bulan grup.
                    is_penuh = db.date_is_taken(current_date_str, user_id)
                    is_weekend_terkunci = is_weekend_monthly_locked(current_date_str, pilihan_sementara)
                    is_weekday_balance_terkunci = is_weekday_balance_locked(
                        current_date_str, pilihan_sementara,
                        weekend_full=weekend_full, weekday_limit=weekday_allowance,
                    )

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
        markup.row(
            InlineKeyboardButton("Tambah Jadwal", callback_data="menu_tambah_jadwal"),
            InlineKeyboardButton("Ganti Jadwal", callback_data="menu_ganti_jadwal")
        )
        markup.row(InlineKeyboardButton("Panduan", callback_data="menu_panduan"))
        bot.send_message(chat_id, "Silakan pilih menu:", reply_markup=markup, message_thread_id=thread_id)

    def _send_month_picker(chat_id, thread_id, callback_prefix, prompt):
        markup = InlineKeyboardMarkup()
        for b in get_bulan_dibuka_list():
            markup.add(InlineKeyboardButton(
                f"{NAMA_BULAN[b['bulan']]} {b['tahun']}",
                callback_data=f"{callback_prefix}_{b['tahun']}_{b['bulan']}",
            ))
        bot.send_message(chat_id, prompt, reply_markup=markup, message_thread_id=thread_id)

    def pick_open_month(chat_id, thread_id, action, callback):
        """Panggil callback(tahun, bulan); minta user memilih bila bulan terbuka > 1."""
        bulan_terbuka_list = get_bulan_dibuka_list()
        if not bulan_terbuka_list:
            bot.send_message(chat_id, "Saat ini tidak ada periode jadwal yang sedang dibuka.", message_thread_id=thread_id)
            return
        if len(bulan_terbuka_list) == 1:
            b = bulan_terbuka_list[0]
            callback(b['tahun'], b['bulan'])
            return
        _send_month_picker(chat_id, thread_id, f"pick_{action}", "Pilih bulan jadwal:")

    def show_open_month_choices(chat_id, thread_id=None):
        bulan_terbuka_list = get_bulan_dibuka_list()
        if not bulan_terbuka_list:
            bot.send_message(chat_id, "Saat ini tidak ada periode jadwal yang sedang dibuka untuk diisi.", message_thread_id=thread_id)
            return None
        if len(bulan_terbuka_list) == 1:
            return bulan_terbuka_list[0]
        _send_month_picker(chat_id, thread_id, "openmonth", "Pilih bulan jadwal yang ingin diisi:")
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
            bot.send_message(chat_id, "❌ Akun Anda belum terdaftar di grup manapun (INFRA_DELIVERY/INFRA_OPERATION/APPS/MONITORING). Silakan hubungi Admin untuk didaftarkan.", message_thread_id=thread_id)
            return

        jadwal_bulan_ini = get_jadwal_for_month(tahun, bulan)
        user_jadwal_lama = {row['tanggal'] for row in jadwal_bulan_ini if row['user_id'] == user_id}
        user_selections[user_id] = {
            'choices': user_jadwal_lama,
            'tahun': tahun,
            'bulan': bulan,
            'timestamp': time.time()
        }
        
        markup = create_calendar('jadwal', user_id, tahun, bulan)

        bot.send_message(chat_id, "Silakan pilih tanggal standby Anda untuk bulan ini.", reply_markup=markup, message_thread_id=thread_id)

    def send_jadwal_saya(chat_id, user, thread_id=None, tahun=None, bulan=None):
        user_id = user.id
        if tahun is None or bulan is None:
            pick_open_month(chat_id, thread_id, 'jadwal_saya',
                            lambda t, b: send_jadwal_saya(chat_id, user, thread_id, t, b))
            return
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
        today = today_wita()
        markup = InlineKeyboardMarkup()

        # Always show current month
        markup.add(InlineKeyboardButton(
            f"🗓️ {NAMA_BULAN[today.month]} {today.year}",
            callback_data=f"view_rekap_{today.year}_{today.month}"))

        # Show next month if already opened
        bulan_terbuka_list = get_bulan_dibuka_list()
        for b in bulan_terbuka_list:
            if b['tahun'] != today.year or b['bulan'] != today.month:
                markup.add(InlineKeyboardButton(
                    f"✏️ {NAMA_BULAN[b['bulan']]} {b['tahun']} (Dibuka)",
                    callback_data=f"view_rekap_{b['tahun']}_{b['bulan']}"))

        bot.send_message(chat_id, "Pilih bulan untuk melihat jadwal:", reply_markup=markup, message_thread_id=thread_id)

    def start_cuti_flow(chat_id, user, thread_id=None, tahun=None, bulan=None):
        user_id = user.id
        if tahun is None or bulan is None:
            if get_bulan_dibuka_list():
                pick_open_month(chat_id, thread_id, 'cuti',
                                lambda t, b: start_cuti_flow(chat_id, user, thread_id, t, b))
                return
            hari_ini = today_wita()
            tahun, bulan = hari_ini.year, hari_ini.month
        start_of_month = f"{tahun}-{bulan:02d}-01"; end_of_month = f"{tahun}-{bulan:02d}-{calendar.monthrange(tahun, bulan)[1]}"
        absensi_tersimpan = get_user_absensi_in_range(user_id, start_of_month, end_of_month)
        
        user_cuti_selections[user_id] = {
            'choices': set(absensi_tersimpan),
            'tahun': tahun,
            'bulan': bulan,
            'timestamp': time.time()
        }
        
        markup = create_calendar('cuti', user_id, tahun, bulan)
        bot.send_message(chat_id, "Silakan pilih tanggal di mana Anda tidak tersedia.", reply_markup=markup, message_thread_id=thread_id)

    def send_lihat_cuti(chat_id, thread_id=None, tahun=None, bulan=None):
        if tahun is None or bulan is None:
            pick_open_month(chat_id, thread_id, 'lihat_cuti',
                            lambda t, b: send_lihat_cuti(chat_id, thread_id, t, b))
            return

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
                pesan += f"  - @{escape_markdown(username)}\n"
            pesan += "\n"

        bot.send_message(chat_id, pesan, parse_mode='Markdown', message_thread_id=thread_id)

    def start_batal_jadwal_flow(chat_id, user, thread_id=None, tahun=None, bulan=None):
        user_id = user.id
        if tahun is None or bulan is None:
            pick_open_month(chat_id, thread_id, 'batal_jadwal',
                            lambda t, b: start_batal_jadwal_flow(chat_id, user, thread_id, t, b))
            return

        # Inisialisasi sesi pembatalan
        user_batal_selections[user_id] = {'choices': set(), 'tahun': tahun, 'bulan': bulan, 'timestamp': time.time()}
        
        markup = create_calendar('batal_jadwal', user_id, tahun, bulan)
        bot.send_message(chat_id, "Pilih jadwal yang ingin Anda batalkan:", reply_markup=markup, message_thread_id=thread_id)


    def start_batal_cuti_flow(chat_id, user, thread_id=None, tahun=None, bulan=None):
        user_id = user.id
        if tahun is None or bulan is None:
            if get_bulan_dibuka_list():
                pick_open_month(chat_id, thread_id, 'batal_cuti',
                                lambda t, b: start_batal_cuti_flow(chat_id, user, thread_id, t, b))
                return
            hari_ini = today_wita()
            tahun, bulan = hari_ini.year, hari_ini.month

        # Inisialisasi sesi pembatalan cuti
        user_batal_cuti_selections[user_id] = {'choices': set(), 'tahun': tahun, 'bulan': bulan, 'timestamp': time.time()}

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
            "*/tanya <pertanyaan>* - Tanya bot (AI): jadwal atau pertanyaan umum aman.\n"
            "*/tambah_jadwal 4, 5, 10* - Menambah tanggal ke jadwal Anda.\n"
            "*/ganti_jadwal 4, 5, 10* - Mengganti jadwal bulan aktif.\n"
            "*/tukar_jadwal* - Mengajukan pertukaran jadwal.\n"
            "*/batal_jadwal* - Membatalkan jadwal standby yang sudah ada.\n"
            "*/batal_cuti* - Membatalkan data cuti yang sudah ada.\n"
            "*/guide* atau */panduan* - Menampilkan panduan ini.\n\n"
            "📌 *Catatan aturan jadwal:*\n"
            "- Infra Delivery wajib memilih tepat 1 jadwal per bulan saat menyimpan melalui /start.\n"
            "- Infra Operation mengikuti maksimal hari/bulan yang diatur Admin (default 5).\n"
            "- APPS dan MONITORING mengikuti maksimal hari/bulan pada Settings.\n"
            "- Setiap orang maksimal 1 Sabtu dan 1 Minggu setiap bulan.\n"
            "- Tukar jadwal harus tipe hari yang sama.\n"
            "- /tanya tidak melayani topik vulgar, politik, SARA, atau detail internal program."
        )
        bot.send_message(chat_id, help_text, parse_mode='Markdown', message_thread_id=thread_id)

    @bot.message_handler(commands=['menu'])
    def handle_menu(message):
        if not is_allowed(message, bot): return
        send_main_menu(message.chat.id, message.message_thread_id)

    @bot.message_handler(commands=['start'])
    def handle_start(message):
        if not is_allowed(message, bot): return
        start_jadwal_flow(message.chat.id, message.from_user, message.message_thread_id)

    @bot.message_handler(commands=['jadwal_saya'])
    def handle_jadwal_saya(message):
        if not is_allowed(message, bot): return
        send_jadwal_saya(message.chat.id, message.from_user, message.message_thread_id)

    @bot.message_handler(commands=['lihat_jadwal'])
    def handle_lihat_jadwal(message):
        if not is_allowed(message, bot): return
        send_lihat_jadwal(message.chat.id, message.message_thread_id)

    def _process_fill_command(message, mode):
        if not is_allowed(message, bot):
            return
        args = message.text.split(' ', 1)[1] if ' ' in message.text else ''
        usage = "/tambah_jadwal 4, 5, 10" if mode == "add" else "/ganti_jadwal 4, 5, 10"
        if not args.strip():
            bot.send_message(message.chat.id, f"Gunakan: {usage}", message_thread_id=message.message_thread_id)
            return
        plan = build_fill_plan(args, message.from_user.id, message.from_user.first_name, message.from_user.username, mode)
        if isinstance(plan, str):
            bot.send_message(message.chat.id, plan, message_thread_id=message.message_thread_id)
            return
        store_pending(message.from_user.id, plan)
        markup = InlineKeyboardMarkup()
        if plan.get("available_new"):
            markup.row(
                InlineKeyboardButton("✅ Ya, simpan", callback_data="agent_fill_confirm"),
                InlineKeyboardButton("❌ Batal", callback_data="agent_fill_cancel"),
            )
        bot.send_message(
            message.chat.id,
            format_plan(plan),
            parse_mode='Markdown',
            reply_markup=markup if plan.get("available_new") else None,
            message_thread_id=message.message_thread_id,
        )

    @bot.message_handler(commands=['tambah_jadwal', 'input_jadwal', 'isi_jadwal'])
    def handle_tambah_jadwal(message):
        _process_fill_command(message, "add")

    @bot.message_handler(commands=['ganti_jadwal', 'ubah_jadwal'])
    def handle_ganti_jadwal(message):
        _process_fill_command(message, "replace")
    @bot.message_handler(commands=['tanya', 'ask'])
    def handle_tanya(message):
        if not is_allowed(message, bot): return
        pertanyaan = message.text.split(' ', 1)[1] if ' ' in message.text else ''
        if not pertanyaan.strip():
            bot.send_message(message.chat.id, ASK_HELP_MSG, message_thread_id=message.message_thread_id)
            return
        if is_help_question(pertanyaan):
            bot.send_message(message.chat.id, get_help_text(), parse_mode='Markdown', message_thread_id=message.message_thread_id)
            return
        if is_fill_request(pertanyaan):
            mode = "replace" if is_replace_request(pertanyaan) else "add"
            plan = build_fill_plan(pertanyaan, message.from_user.id, message.from_user.first_name, message.from_user.username, mode)
            if isinstance(plan, str):
                bot.send_message(message.chat.id, plan, message_thread_id=message.message_thread_id)
                return
            store_pending(message.from_user.id, plan)
            markup = InlineKeyboardMarkup()
            if plan.get("available_new"):
                markup.row(
                    InlineKeyboardButton("✅ Ya, simpan", callback_data="agent_fill_confirm"),
                    InlineKeyboardButton("❌ Batal", callback_data="agent_fill_cancel"),
                )
            bot.send_message(
                message.chat.id,
                format_plan(plan),
                parse_mode='Markdown',
                reply_markup=markup if plan.get("available_new") else None,
                message_thread_id=message.message_thread_id,
            )
            return
        bot.send_message(message.chat.id, ai_answer(pertanyaan), message_thread_id=message.message_thread_id)

    @bot.message_handler(commands=['cuti'])
    def handle_cuti(message):
        if not is_allowed(message, bot): return
        start_cuti_flow(message.chat.id, message.from_user, message.message_thread_id)
        
    @bot.message_handler(commands=['lihat_cuti'])
    def handle_lihat_cuti(message):
        """Menampilkan daftar pengguna yang sedang cuti di bulan yang sedang dibuka."""
        if not is_allowed(message, bot):
            return
        send_lihat_cuti(message.chat.id, message.message_thread_id)

    @bot.message_handler(commands=['batal_jadwal'])
    def handle_batal_jadwal(message):
        """Membatalkan semua jadwal standby pengguna di bulan aktif."""
        if not is_allowed(message, bot):
            return
        start_batal_jadwal_flow(message.chat.id, message.from_user, message.message_thread_id)

    @bot.message_handler(commands=['batal_cuti'])
    def handle_batal_cuti(message):
        if not is_allowed(message, bot): return
        start_batal_cuti_flow(message.chat.id, message.from_user, message.message_thread_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('menu_'))
    def handle_menu_callbacks(call):
        if deny_private_callback(bot, call):
            return
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
        elif action == 'tambah_jadwal':
            bot.send_message(call.message.chat.id, "Gunakan `/tambah_jadwal 4, 5, 10` untuk menambah tanggal ke jadwal Anda.", parse_mode='Markdown', message_thread_id=thread_id)
        elif action == 'ganti_jadwal':
            bot.send_message(call.message.chat.id, "Gunakan `/ganti_jadwal 4, 5, 10` untuk mengganti seluruh jadwal bulan aktif.", parse_mode='Markdown', message_thread_id=thread_id)
        elif action == 'panduan':
            send_guide(call.message.chat.id, thread_id)

        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('reason_'))
    def handle_calendar_reason_callbacks(call):
        if deny_private_callback(bot, call):
            return
        parts = call.data.split('_', 2)
        reason = parts[1] if len(parts) > 1 else ''
        tanggal_str = parts[2] if len(parts) > 2 else ''

        if reason == 'absen':
            message_text = "Tanggal ini terkunci karena Anda menandai cuti/tidak tersedia."
        elif reason == 'full':
            message_text = "Tanggal ini sudah penuh (Batasan Harian tercapai)."
        elif reason == 'weekend':
            message_text = get_weekend_limit_message(tanggal_str)
        elif reason == 'weekdaybalance':
            try:
                dt_reason = datetime.strptime(tanggal_str, '%Y-%m-%d')
                weekend_full_reason = is_weekend_fallback_active_for_user(call.from_user.id, dt_reason.year, dt_reason.month)
            except ValueError:
                weekend_full_reason = False
            weekday_allowance_reason = db.get_weekday_allowance_for_group(get_user_group(call.from_user.id))
            message_text = get_weekday_balance_message(weekend_full_reason, weekday_limit=weekday_allowance_reason)
        else:
            message_text = "Tanggal ini tidak bisa dipilih."

        bot.answer_callback_query(call.id, message_text, show_alert=True)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('openmonth_'))
    def handle_open_month_callbacks(call):
        if deny_private_callback(bot, call):
            return
        parts = call.data.split('_')
        if len(parts) != 3:
            bot.answer_callback_query(call.id, "Pilihan bulan tidak valid.", show_alert=True)
            return

        tahun, bulan = int(parts[1]), int(parts[2])
        start_jadwal_flow(call.message.chat.id, call.from_user, call.message.message_thread_id, tahun, bulan)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('pick_') and not call.data.startswith('pick_tukar_'))
    def handle_pick_month(call):
        if deny_private_callback(bot, call):
            return
        parts = call.data.split('_')
        if len(parts) < 4:
            bot.answer_callback_query(call.id, "Pilihan bulan tidak valid.", show_alert=True)
            return
        action = '_'.join(parts[1:-2])
        tahun, bulan = int(parts[-2]), int(parts[-1])
        user = call.from_user
        chat_id = call.message.chat.id
        thread_id = call.message.message_thread_id
        routes = {
            'jadwal': lambda: start_jadwal_flow(chat_id, user, thread_id, tahun, bulan),
            'jadwal_saya': lambda: send_jadwal_saya(chat_id, user, thread_id, tahun, bulan),
            'batal_jadwal': lambda: start_batal_jadwal_flow(chat_id, user, thread_id, tahun, bulan),
            'lihat_cuti': lambda: send_lihat_cuti(chat_id, thread_id, tahun, bulan),
            'cuti': lambda: start_cuti_flow(chat_id, user, thread_id, tahun, bulan),
            'batal_cuti': lambda: start_batal_cuti_flow(chat_id, user, thread_id, tahun, bulan),
        }
        route = routes.get(action)
        if route is None:
            bot.answer_callback_query(call.id, "Pilihan bulan tidak valid.", show_alert=True)
            return
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except Exception:
            pass
        route()
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.split('_')[0] in ['jadwal', 'cuti', 'view', 'batal'])
    def handle_all_callbacks(call):
        if deny_private_callback(bot, call):
            return
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
                            pesan += f"*{nama_hari}*, {current_date.day}: {', '.join(escape_markdown(p['username']) for p in petugas)}\n"
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

                    dt_obj_toggle = datetime.strptime(date_str, '%Y-%m-%d')
                    weekend_full = is_weekend_fallback_active_for_user(user_id, dt_obj_toggle.year, dt_obj_toggle.month)

                    user_group = get_user_group(user_id)
                    weekday_allowance = db.get_weekday_allowance_for_group(user_group)

                    if is_weekday_balance_locked(date_str, selections, weekend_full=weekend_full, weekday_limit=weekday_allowance):
                        bot.answer_callback_query(
                            call.id,
                            get_weekday_balance_message(weekend_full=weekend_full, weekday_limit=weekday_allowance),
                            show_alert=True,
                        )
                        return

                    # Aturan satu-per-tanggal (sejalan date_conflict di save):
                    # Kapasitas tanggal (Batasan Harian): tolak bila slot sudah penuh.
                    if db.date_is_taken(date_str, user_id):
                        bot.answer_callback_query(call.id, "❌ Tanggal ini sudah penuh. Silakan pilih tanggal lain.", show_alert=True)
                        return

                    max_hari = db.get_monthly_cap_for_group(user_group)
                    pilihan_bulan_ini = {
                        s for s in selections
                        if datetime.strptime(s, '%Y-%m-%d').year == dt_obj_toggle.year
                        and datetime.strptime(s, '%Y-%m-%d').month == dt_obj_toggle.month
                    }
                    if len(pilihan_bulan_ini) >= max_hari:
                        bot.answer_callback_query(call.id, f"❌ Kuota maksimal {max_hari} hari/bulan untuk tim Anda telah tercapai.", show_alert=True)
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
                sesi = selection_dict[user_id]
                if (sesi.get('tahun'), sesi.get('bulan')) != (year, month):
                    sesi['tahun'], sesi['bulan'] = year, month
                    sesi['choices'] = _month_seed_choices(mode, user_id, year, month)
                markup = create_calendar(mode, user_id, year, month)
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)

            elif action == 'save':
                year, month = int(parts[2]), int(parts[3])
                if not is_month_open(year, month):
                    bot.answer_callback_query(
                        call.id,
                        f"Periode jadwal {NAMA_BULAN[month]} {year} sedang tidak dibuka. Hubungi admin.",
                        show_alert=True,
                    )
                    if user_id in selection_dict:
                        del selection_dict[user_id]
                    return
                pilihan_final = list(selection_dict.get(user_id, {}).get('choices', []))
                if mode == 'jadwal':
                    result = update_user_jadwal_for_month(user_id, call.from_user.first_name, call.from_user.username, pilihan_final, year, month)
                    if not result.ok:
                        error_message = result.message or SAVE_ERROR_MESSAGES.get(result.error_code, 'Gagal menyimpan jadwal. Mohon periksa pilihan Anda.')
                        bot.answer_callback_query(call.id, error_message, show_alert=True)
                        return
                    pesan = f"✅ Jadwal Anda untuk bulan {NAMA_BULAN[month]} {year} telah disimpan."
                    user_group = get_user_group(user_id)
                    try:
                        for tanggal in pilihan_final:
                            sync_jadwal_to_sheets(tanggal=tanggal, hari=get_hari_from_date(tanggal), username=call.from_user.username or call.from_user.first_name, group=user_group or 'UNKNOWN')
                    except Exception as exc:
                        # Sheets tidak boleh membatalkan konfirmasi simpan yang sudah commit.
                        print(f"Sinkronisasi Sheets jadwal dilewati: {exc}")
                else: # cuti
                    set_user_absensi(user_id, pilihan_final, year, month) # Modifikasi kecil agar lebih aman
                    pesan = f"✅ Data cuti Anda untuk bulan {NAMA_BULAN[month]} {year} telah diperbarui."
                    
                    # Sync ke Google Sheets untuk setiap tanggal cuti
                    try:
                        for tanggal in pilihan_final:
                            sync_absensi_to_sheets(
                                tanggal=tanggal,
                                username=call.from_user.username or call.from_user.first_name,
                                user_id=user_id
                            )
                    except Exception as exc:
                        print(f"Sinkronisasi Sheets cuti dilewati: {exc}")
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
                sesi = selection_dict[user_id]
                if (sesi.get('tahun'), sesi.get('bulan')) != (year, month):
                    sesi['tahun'], sesi['bulan'] = year, month
                    sesi['choices'] = set()
                markup = create_calendar(f"batal_{sub_mode}", user_id, year, month)
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)

            elif action == 'save':
                year, month = int(parts[3]), int(parts[4])
                if not is_month_open(year, month):
                    bot.answer_callback_query(
                        call.id,
                        f"Periode jadwal {NAMA_BULAN[month]} {year} sedang tidak dibuka.",
                        show_alert=True,
                    )
                    if user_id in selection_dict:
                        del selection_dict[user_id]
                    return
                pilihan_batal = list(selection_dict.get(user_id, {}).get('choices', []))
                
                if not pilihan_batal:
                    bot.answer_callback_query(call.id, "Tidak ada tanggal yang dipilih untuk dibatalkan.", show_alert=True)
                    return
                
                pesan_konfirmasi = ""
                if sub_mode == 'jadwal':
                    result = delete_user_jadwal_on_dates(user_id, pilihan_batal)
                    if not result.ok:
                        if result.error_code == 'database_locked':
                            pesan_err = result.message or 'Sistem sedang sibuk. Silakan coba beberapa saat lagi.'
                        elif result.error_code == 'stale_schedule':
                            pesan_err = 'Satu atau lebih jadwal yang dipilih sudah tidak tersedia.'
                        else:
                            pesan_err = result.message or 'Gagal membatalkan jadwal.'
                        bot.answer_callback_query(call.id, f"❌ {pesan_err}", show_alert=True)
                        return
                    pesan_konfirmasi = f"✅ Berhasil membatalkan {result.rows_affected} jadwal."
                elif sub_mode == 'cuti':
                    start_of_month = f"{year}-{month:02d}-01"; end_of_month = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]}"
                    cuti_sebelumnya = get_user_absensi_in_range(user_id, start_of_month, end_of_month)
                    cuti_tersisa = cuti_sebelumnya - set(pilihan_batal)
                    set_user_absensi(user_id, list(cuti_tersisa), year, month)
                    pesan_konfirmasi = f"✅ Berhasil membatalkan {len(pilihan_batal)} tanggal cuti."

                if user_id in selection_dict: del selection_dict[user_id]
                try: bot.delete_message(call.message.chat.id, call.message.message_id)
                except ApiTelegramException: pass
                bot.send_message(call.message.chat.id, pesan_konfirmasi, message_thread_id=thread_id)
        bot.answer_callback_query(call.id)
    
def register_help_handler(bot: telebot.TeleBot):
        @bot.message_handler(commands=['help', 'guide', 'panduan'])
        def handle_help(message):
            if not is_allowed(message, bot): return
            help_text = (
                "ℹ️ *Panduan Bot Jadwal Standby*\n\n"
                "Perintah yang bisa digunakan di grup:\n\n"
                "*/menu* - Membuka tombol menu bot.\n"
                "*/start* - Mengisi/mengedit jadwal Anda.\n"
                "*/lihat_jadwal* - Menampilkan rekap jadwal tim.\n"
                "*/jadwal_saya* - Menampilkan daftar jadwal pribadi Anda.\n"
                "*/cuti* - Menandai tanggal Anda tidak bersedia (cuti).\n"
                "*/lihat_cuti* - Menampilkan daftar cuti tim di bulan aktif.\n"
                "*/tanya <pertanyaan>* - Tanya bot (AI): jadwal atau pertanyaan umum aman.\n"
                "*/tambah_jadwal 4, 5, 10* - Menambah tanggal ke jadwal Anda.\n"
                "*/ganti_jadwal 4, 5, 10* - Mengganti jadwal bulan aktif.\n"
                "*/tukar_jadwal* - Mengajukan pertukaran jadwal.\n"
                "*/batal_jadwal* - Membatalkan jadwal standby yang sudah ada.\n"
                "*/batal_cuti* - Membatalkan data cuti yang sudah ada.\n"
                "*/guide* atau */panduan* - Menampilkan panduan ini.\n\n"
                "📌 *Catatan aturan jadwal:*\n"
                "- Infra Delivery wajib memilih tepat 1 jadwal per bulan saat menyimpan melalui /start.\n"
                "- Infra Operation mengikuti maksimal hari/bulan yang diatur Admin (default 5).\n"
                "- APPS dan MONITORING mengikuti maksimal hari/bulan pada Settings.\n"
                "- Setiap orang maksimal 1 Sabtu dan 1 Minggu setiap bulan.\n"
                "- Tukar jadwal harus tipe hari yang sama.\n"
                "- /tanya tidak melayani topik vulgar, politik, SARA, atau detail internal program."
            )
            bot.send_message(message.chat.id, help_text, parse_mode='Markdown', message_thread_id=message.message_thread_id)
