# core/scheduler.py (Versi Final dengan Laporan & Pengingat Cuti)

import time
import calendar
import pytz
from datetime import datetime, timedelta
from functools import wraps
from collections import defaultdict
from apscheduler.schedulers.background import BackgroundScheduler

from config import GROUP_CHAT_ID, ALLOWED_TOPIC_ID
from core.database import (
    GROUP_NAMES, GROUP_LABELS,
    get_jadwal_for_specific_date, get_all_absensi_in_range, get_jadwal_by_group,
    get_all_users_in_group, format_tanggal_indonesia,
    get_all_registered_users, get_users_with_schedule_in_range,
    is_date_full, get_daily_limit, get_assignment_count_for_date,
    can_user_take_weekend_date, get_user_jadwal_for_month,
    get_weekend_monthly_limit_key, get_bulan_dibuka,
    get_group_quota, get_monthly_limit_for_group
)
from core.monthly_report import build_monthly_report, format_monthly_report_for_telegram
from core.schedule_recap import generate_rekap_text

# Decorator retry_on_failure (TETAP SAMA)
def retry_on_failure(retries=3, delay=10):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    print(f"Scheduler ERROR (Percobaan {i + 1}/{retries}): Fungsi {func.__name__} gagal. Error: {e}")
                    if i == retries - 1:
                        print(f"Scheduler GAGAL TOTAL: Fungsi {func.__name__} tetap gagal setelah {retries} percobaan.")
                        raise
                    print(f"Scheduler: Akan mencoba lagi dalam {delay} detik...")
                    time.sleep(delay)
        return wrapper
    return decorator


# ==========================================================
# FUNGSI PENGINGAT HARIAN (DIPERBARUI)
# ==========================================================
@retry_on_failure(retries=5, delay=30)
def kirim_pengingat_harian(bot):
    """
    Mengirim reminder harian yang kini mencakup siapa yang standby DAN siapa yang cuti.
    """
    print("Scheduler: Mengecek jadwal & cuti untuk reminder harian...")
    
    tz = pytz.timezone("Asia/Makassar")
    waktu_sekarang = datetime.now(tz)
    tanggal_hari_ini_str = waktu_sekarang.strftime('%Y-%m-%d')
    
    # 1. Dapatkan data petugas standby
    petugas_standby = get_jadwal_for_specific_date(tanggal_hari_ini_str)
    
    # 2. Dapatkan data yang cuti hari ini
    petugas_cuti = get_all_absensi_in_range(tanggal_hari_ini_str, tanggal_hari_ini_str)

    # Jika tidak ada yang standby dan tidak ada yang cuti, tidak perlu kirim reminder
    if not petugas_standby and not petugas_cuti:
        print(f"Scheduler: Tidak ada petugas standby maupun cuti untuk tanggal {tanggal_hari_ini_str}, reminder dilewati.")
        return

    hari_map = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}
    hari_ini_nama = hari_map[waktu_sekarang.weekday()]
    tanggal_ramah = format_tanggal_indonesia(waktu_sekarang)

    pesan = f"📢 *Update Harian - {hari_ini_nama}, {tanggal_ramah}*\n"
    pesan += "─" * 20 + "\n\n"

    # Bagian Petugas Standby
    pesan += "✅ *Petugas Standby Hari Ini:*\n"
    if petugas_standby:
        mentions = [f"[{p['username']}](tg://user?id={p['user_id']})" for p in petugas_standby]
        pesan += ' • ' + '\n • '.join(mentions) + "\n\n"
    else:
        pesan += "_Tidak ada yang standby hari ini._\n\n"

    # Bagian Petugas Cuti
    pesan += "⛔️ *Anggota yang Cuti/Tidak Tersedia:*\n"
    if petugas_cuti:
        nama_cuti = [p['username'] for p in petugas_cuti]
        pesan += ' • ' + '\n • '.join(nama_cuti) + "\n\n"
    else:
        pesan += "_Tidak ada yang cuti hari ini._\n\n"

    pesan += "Semangat menjalankan tugas! ✨"

    bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=pesan,
        parse_mode='Markdown',
        message_thread_id=ALLOWED_TOPIC_ID
    )
    print(f"Scheduler: Reminder harian (standby & cuti) untuk {tanggal_hari_ini_str} berhasil dikirim.")


# ==========================================================
# FUNGSI LAPORAN CUTI MINGGUAN (BARU)
# ==========================================================
@retry_on_failure(retries=3, delay=60)
def kirim_laporan_cuti_mingguan(bot):
    """
    Mengirim rekapitulasi semua anggota yang cuti dalam seminggu ke depan.
    """
    print("Scheduler: Membuat laporan cuti mingguan...")
    tz = pytz.timezone("Asia/Makassar")
    today = datetime.now(tz).date()
    
    # Tentukan periode: dari hari ini (Senin) sampai 6 hari ke depan (Minggu)
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    # Ambil semua data cuti dalam rentang seminggu
    data_cuti_seminggu = get_all_absensi_in_range(
        start_of_week.strftime('%Y-%m-%d'),
        end_of_week.strftime('%Y-%m-%d')
    )

    if not data_cuti_seminggu:
        print("Scheduler: Tidak ada data cuti untuk minggu ini, laporan dilewati.")
        return

    # Kelompokkan data cuti per tanggal
    cuti_per_hari = defaultdict(list)
    for cuti in data_cuti_seminggu:
        cuti_per_hari[cuti['tanggal']].append(cuti['username'])
    
    pesan = f"📋 *Laporan Cuti & Ketidaksediaan Minggu Ini*\n"
    pesan += f"_{format_tanggal_indonesia(start_of_week)} - {format_tanggal_indonesia(end_of_week)}_\n"
    pesan += "─" * 20 + "\n\n"
    
    hari_map = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}
    
    # Loop dari Senin sampai Minggu untuk membuat laporan yang terstruktur
    for i in range(7):
        current_date = start_of_week + timedelta(days=i)
        current_date_str = current_date.strftime('%Y-%m-%d')
        nama_hari = hari_map[current_date.weekday()]
        
        if current_date_str in cuti_per_hari:
            nama_petugas = ', '.join(cuti_per_hari[current_date_str])
            pesan += f"*{nama_hari}, {current_date.day}:* {nama_petugas}\n"
    
    bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=pesan,
        parse_mode='Markdown',
        message_thread_id=ALLOWED_TOPIC_ID
    )
    print(f"Scheduler: Laporan cuti mingguan berhasil dikirim.")

    
@retry_on_failure(retries=3, delay=60)
def kirim_peringatan_jadwal_mingguan(bot):
    """
    Mengirim peringatan via DM kepada pengguna di grup masing-masing
    jika jadwal untuk minggu depan belum terisi penuh sesuai kuota.
    """
    print("Scheduler: Mengecek jadwal kosong per grup untuk minggu depan...")
    tz = pytz.timezone("Asia/Makassar")
    today = datetime.now(tz).date()

    # Tentukan periode minggu depan (Senin hingga Minggu)
    next_week_start = today + timedelta(days=(7 - today.weekday()))
    next_week_end = next_week_start + timedelta(days=6)

    # Ambil jadwal yang sudah ada per grup
    jadwal_by_group = {
        group_name: get_jadwal_by_group(next_week_start.year, next_week_start.month, group_name)
        for group_name in GROUP_NAMES
    }

    # Hitung slot terisi per hari untuk setiap grup
    slot_terisi_by_group = {group_name: defaultdict(int) for group_name in GROUP_NAMES}
    for group_name, jadwal_list in jadwal_by_group.items():
        for j in jadwal_list:
            slot_terisi_by_group[group_name][j['tanggal']] += 1

    # Cari tanggal yang kuotanya kurang per grup
    tanggal_kurang_by_group = {group_name: [] for group_name in GROUP_NAMES}
    for i in range(7):
        current_date = next_week_start + timedelta(days=i)
        current_date_str = current_date.strftime('%Y-%m-%d')
        
        # Cek jika tanggal berada di bulan yang sama dengan awal minggu
        if current_date.month == next_week_start.month:
            for group_name in GROUP_NAMES:
                # Cek batasan harian grup
                quota_group = get_group_quota(group_name)
                max_per_hari = get_daily_limit(current_date_str, quota_group)
                if slot_terisi_by_group[group_name].get(current_date_str, 0) < max_per_hari:
                    tanggal_kurang_by_group[group_name].append(current_date_str)

    # Kirim peringatan ke anggota masing-masing grup jika perlu
    ada_kurang = False
    for group_name in GROUP_NAMES:
        tanggal_kurang = tanggal_kurang_by_group[group_name]
        if tanggal_kurang:
            ada_kurang = True
            users = get_all_users_in_group(group_name)
            label = GROUP_LABELS.get(group_name, group_name)
            quota_group = get_group_quota(group_name)
            pesan = f"🔔 *Peringatan Jadwal {label}*\n\nJadwal standby Anda untuk beberapa tanggal di minggu depan masih belum terisi penuh (kuota: {quota_group} orang/hari). Tanggal yang masih kosong:\n\n"
            for tgl in tanggal_kurang:
                tgl_obj = datetime.strptime(tgl, '%Y-%m-%d').date()
                pesan += f"- {format_tanggal_indonesia(tgl_obj)}\n"
            pesan += "\nMohon segera lengkapi jadwal Anda dengan menggunakan perintah `/start` di grup."
            
            for user in users:
                try:
                    bot.send_message(user['user_id'], pesan, parse_mode='Markdown')
                except Exception as e:
                    username_display = user.get('telegram_username') or user.get('username') or str(user.get('user_id'))
                    print(f"Gagal mengirim DM peringatan ke user {label} {username_display}: {e}")

    if not ada_kurang:
        print("Scheduler: Jadwal minggu depan untuk semua grup sudah penuh.")
    
    print("Scheduler: Pengecekan peringatan jadwal mingguan selesai.")
    
def _escape_markdown_text(value):
    """Escape basic Markdown chars for Telegram parse_mode=Markdown."""
    return str(value or '').replace('\\', '\\\\').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')


def _format_user_mention(user):
    if user['telegram_username']:
        safe_username = str(user['telegram_username']).lstrip('@')
        return f"@{safe_username}"
    safe_name = _escape_markdown_text(user['username']) or 'pengguna'
    return f"[{safe_name}](tg://user?id={user['user_id']})"


def _get_open_schedule_period():
    bulan_dibuka = get_bulan_dibuka()
    if bulan_dibuka:
        tahun = bulan_dibuka['tahun']
        bulan = bulan_dibuka['bulan']
        return tahun, bulan, f"{tahun}-{bulan:02d}-01", f"{tahun}-{bulan:02d}-{calendar.monthrange(tahun, bulan)[1]}"

    tz = pytz.timezone("Asia/Makassar")
    today = datetime.now(tz).date()
    next_week_start = today + timedelta(days=(7 - today.weekday()))
    next_week_end = next_week_start + timedelta(days=6)
    return next_week_start.year, next_week_start.month, next_week_start.strftime('%Y-%m-%d'), next_week_end.strftime('%Y-%m-%d')


def build_pesan_peringatan_pengisian_jadwal():
    """Build pesan peringatan pengisian jadwal tanpa mengirim Telegram."""
    tahun, bulan, start_str, end_str = _get_open_schedule_period()
    start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_str, '%Y-%m-%d').date()

    tanggal_kosong = []
    current_date = start_date
    while current_date <= end_date:
        tanggal = current_date.strftime('%Y-%m-%d')
        terisi = get_assignment_count_for_date(tanggal)
        limit = get_daily_limit(tanggal, 1)
        if terisi < limit:
            tanggal_kosong.append((current_date, terisi, limit))
        current_date += timedelta(days=1)

    kurang_isi_by_group = {}
    for group_name in GROUP_NAMES:
        entries = []
        for user in get_all_users_in_group(group_name):
            jadwal_bulan = get_user_jadwal_for_month(user['user_id'], tahun, bulan)
            total = len(jadwal_bulan)
            target = get_monthly_limit_for_group(group_name)
            if total < target:
                entries.append((total, target, user))
        kurang_isi_by_group[group_name] = sorted(entries, key=lambda item: (item[0], item[2]['username'].lower()))
    if not tanggal_kosong and not any(kurang_isi_by_group.values()):
        return None

    nama_bulan = format_tanggal_indonesia(start_date).split(' ')[1]
    pesan = (
        "🔔 *Peringatan Pengisian Jadwal SOS*\n\n"
        f"Periode: *{nama_bulan} {tahun}*\n"
        "Target: setiap anggota melengkapi jadwal sesuai batas bulanan divisi jika slot masih tersedia.\n\n"
    )

    if tanggal_kosong:
        pesan += "📅 *Tanggal yang masih belum terisi penuh:*\n"
        for tanggal_obj, terisi, limit in tanggal_kosong[:12]:
            pesan += f"• {format_tanggal_indonesia(tanggal_obj)} — {terisi}/{limit}\n"
        if len(tanggal_kosong) > 12:
            pesan += f"• ...dan {len(tanggal_kosong) - 12} tanggal lainnya\n"
        pesan += "\n"
    else:
        pesan += "✅ Semua tanggal pada periode ini sudah terisi penuh.\n\n"

    pesan += "👥 *Anggota yang jadwalnya belum lengkap:*\n"
    has_members = False
    for group_name, entries in kurang_isi_by_group.items():
        if not entries:
            continue
        has_members = True
        label = GROUP_LABELS.get(group_name, group_name)
        pesan += f"\n*{label}*\n"
        for total, target, user in entries:
            kurang = target - total
            pesan += f"• {_format_user_mention(user)} — baru *{total}x*, target *{target}x* (kurang *{kurang}x*)\n"

    if not has_members:
        pesan += "Semua anggota sudah memenuhi target jadwal.\n"
    if tanggal_kosong:
        pesan += (
            "\nSilakan anggota yang jadwalnya belum lengkap mengambil tanggal kosong di atas "
            "melalui `/start`."
        )
    else:
        pesan += (
            "\nSaat ini belum ada tanggal kosong di periode aktif. Jika ada slot dibuka lagi, "
            "anggota di atas menjadi prioritas untuk melengkapi jadwal."
        )
    return pesan


@retry_on_failure(retries=3, delay=60)
def kirim_peringatan_jadwal_mingguan_kosong(bot):
    """
    Mention anggota yang jadwalnya belum lengkap dan tampilkan tanggal kosong periode aktif.
    """
    print("Scheduler: Mengecek anggota yang belum melengkapi target jadwal...")
    pesan = build_pesan_peringatan_pengisian_jadwal()

    if not pesan:
        print("Scheduler: Tidak ada anggota/tanggal yang perlu diperingatkan.")
        return

    bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=pesan,
        parse_mode='Markdown',
        message_thread_id=ALLOWED_TOPIC_ID
    )
    print("Scheduler: Peringatan pengisian jadwal berhasil dikirim.")


@retry_on_failure(retries=3, delay=60)
def kirim_peringatan_slot_weekend_kosong(bot):
    """
    Mention anggota yang masih bisa mengisi slot Sabtu/Minggu minggu depan.
    """
    print("Scheduler: Mengecek slot weekend kosong untuk minggu depan...")
    tz = pytz.timezone("Asia/Makassar")
    today = datetime.now(tz).date()

    next_week_start = today + timedelta(days=(7 - today.weekday()))
    weekend_dates = [next_week_start + timedelta(days=5), next_week_start + timedelta(days=6)]
    all_users = get_all_registered_users()

    def format_mention(user):
        if user['telegram_username']:
            return f"@{user['telegram_username']}"
        return f"[pengguna](tg://user?id={user['user_id']})"

    def get_candidate_priority(user_id, target_date):
        jadwal_bulan = get_user_jadwal_for_month(user_id, target_date.year, target_date.month)
        total_jadwal = len(jadwal_bulan)
        total_weekend = 0
        for jadwal in jadwal_bulan:
            if get_weekend_monthly_limit_key(jadwal['tanggal']):
                total_weekend += 1
        return total_weekend, total_jadwal

    pesan_sections = []
    for target_date in weekend_dates:
        target_date_str = target_date.strftime('%Y-%m-%d')
        total_terisi = get_assignment_count_for_date(target_date_str)
        max_per_hari = get_daily_limit(target_date_str, 1)

        if total_terisi >= max_per_hari:
            continue

        slot_tersedia = max_per_hari - total_terisi
        petugas_hari_ini = get_jadwal_for_specific_date(target_date_str)
        user_sudah_isi_hari_ini = {petugas['user_id'] for petugas in petugas_hari_ini}

        candidates = []
        for user in all_users:
            if user['user_id'] in user_sudah_isi_hari_ini:
                continue
            if not can_user_take_weekend_date(user['user_id'], target_date_str):
                continue
            priority = get_candidate_priority(user['user_id'], target_date)
            candidates.append((priority, format_mention(user)))

        if candidates:
            candidates.sort(key=lambda item: (item[0][0], item[0][1], item[1].lower()))
            suggested_limit = max(slot_tersedia, 1)
            suggested_mentions = [mention for _, mention in candidates[:suggested_limit]]
            backup_mentions = [mention for _, mention in candidates[suggested_limit:suggested_limit + 3]]

            backup_text = ""
            if backup_mentions:
                backup_text = f"\nBackup eligible: {' '.join(backup_mentions)}"

            pesan_sections.append(
                f"*{format_tanggal_indonesia(target_date)}* masih kurang *{slot_tersedia} slot*.\n"
                f"Disarankan input: {' '.join(suggested_mentions)}"
                f"{backup_text}"
            )
        else:
            pesan_sections.append(
                f"*{format_tanggal_indonesia(target_date)}* masih kurang *{slot_tersedia} slot*, "
                f"tetapi tidak ada user yang masih eligible berdasarkan batas 1 Sabtu/1 Minggu per bulan."
            )

    if not pesan_sections:
        print("Scheduler: Slot weekend minggu depan sudah penuh. Peringatan dilewati.")
        return

    pesan = (
        "🔔 *Peringatan Slot Weekend Kosong*\n\n"
        f"Weekend minggu depan masih ada slot kosong:\n\n"
        + "\n\n".join(pesan_sections)
        + "\n\nSilakan gunakan perintah `/start` untuk mengisi."
    )

    bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=pesan,
        parse_mode='Markdown',
        message_thread_id=ALLOWED_TOPIC_ID
    )
    print("Scheduler: Peringatan slot weekend kosong berhasil dikirim.")


# --- FITUR BARU 2: Peringatan H-3 Slot Kosong ---
@retry_on_failure(retries=3, delay=60)
def kirim_peringatan_h_minus_3(bot):
    """
    Setiap hari, mengecek jadwal untuk 3 hari ke depan (H-3).
    Jika slot belum penuh, kirim peringatan dengan mention semua anggota.
    """
    print("Scheduler: Mengecek slot kosong untuk H-3...")
    tz = pytz.timezone("Asia/Makassar")

    # Tentukan tanggal target (3 hari dari sekarang)
    target_date = (datetime.now(tz) + timedelta(days=3)).date()
    target_date_str = target_date.strftime('%Y-%m-%d')

    # Cek total yang sudah terisi dan batas harian
    total_terisi = get_assignment_count_for_date(target_date_str)
    max_per_hari = get_daily_limit(target_date_str, 1)

    # Jika sudah penuh, tidak perlu kirim peringatan
    if total_terisi >= max_per_hari:
        print(f"Scheduler: Slot untuk H-3 ({target_date_str}) sudah penuh ({total_terisi}/{max_per_hari}). Peringatan dilewati.")
        return

    # Hitung slot yang masih tersedia
    slot_tersedia = max_per_hari - total_terisi

    # Mention semua pengguna terdaftar
    all_users = get_all_registered_users()
    mentions = []
    for user in all_users:
        if user['telegram_username']:
            mentions.append(f"@{user['telegram_username']}")
        else:
            mentions.append(f"[pengguna](tg://user?id={user['user_id']})")

    mention_block = " ".join(mentions)

    pesan = (f"📢 *Peringatan Jadwal H-3*\n\n"
             f"Jadwal standby untuk *{format_tanggal_indonesia(target_date)}* masih tersedia **{slot_tersedia} slot** lagi.\n\n"
             f"📊 Status: Terisi {total_terisi} dari {max_per_hari} slot\n\n"
             f"CC: {mention_block}\n\n"
             f"Mohon segera mengisi kekosongan melalui perintah `/start` atau melakukan pertukaran jadwal.")

    bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=pesan,
        parse_mode='Markdown',
        message_thread_id=ALLOWED_TOPIC_ID
    )
    print(f"Scheduler: Peringatan H-3 untuk tanggal {target_date_str} berhasil dikirim.")


@retry_on_failure(retries=3, delay=60)
def kirim_laporan_bulanan(bot):
    """Mengirim laporan jadwal bulanan ke grup pada hari terakhir bulan."""
    print("Scheduler: Membuat laporan jadwal bulanan...")
    tz = pytz.timezone("Asia/Makassar")
    today = datetime.now(tz).date()
    report = build_monthly_report(today.year, today.month)
    pesan = format_monthly_report_for_telegram(report)

    bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=pesan,
        parse_mode='Markdown',
        message_thread_id=ALLOWED_TOPIC_ID
    )
    print(f"Scheduler: Laporan bulanan {today.year}-{today.month:02d} berhasil dikirim.")


@retry_on_failure(retries=3, delay=60)
def kirim_jadwal_bulanan_awal_bulan(bot):
    """Mengirim rekap jadwal full bulan ke grup setiap tanggal 1."""
    print("Scheduler: Mengirim rekap jadwal awal bulan...")
    tz = pytz.timezone("Asia/Makassar")
    today = datetime.now(tz).date()
    pesan = generate_rekap_text(today.year, today.month)
    pesan += "\n\nJika Ingin tukar jadwal ketik menu `/tukar_jadwal`"

    bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=pesan,
        parse_mode='Markdown',
        message_thread_id=ALLOWED_TOPIC_ID
    )
    print(f"Scheduler: Rekap jadwal awal bulan {today.year}-{today.month:02d} berhasil dikirim.")

def init_scheduler(bot):
    """Menginisialisasi dan memulai semua scheduler."""
    scheduler = BackgroundScheduler(timezone=pytz.timezone("Asia/Makassar"))
    
    # Job 1: Reminder harian (standby & cuti) - Setiap hari jam 7:00
    scheduler.add_job(
        lambda: kirim_pengingat_harian(bot), trigger='cron',
        hour=7, minute=0, id='daily_reminder', replace_existing=True
    )
    
    # Job 2: Laporan cuti mingguan - Setiap Senin jam 7:05
    scheduler.add_job(
        lambda: kirim_laporan_cuti_mingguan(bot), trigger='cron',
        day_of_week='mon', hour=7, minute=5, id='weekly_cuti_report', replace_existing=True
    )

    # Job 3 (BARU): Peringatan mingguan belum input - Setiap Jumat jam 16:00
    scheduler.add_job(
        lambda: kirim_peringatan_jadwal_mingguan_kosong(bot), trigger='cron',
        day_of_week='fri', hour=16, minute=0, id='weekly_unfilled_warning', replace_existing=True
    )

    # Job 4: Peringatan slot weekend kosong - Setiap Jumat jam 16:05
    scheduler.add_job(
        lambda: kirim_peringatan_slot_weekend_kosong(bot), trigger='cron',
        day_of_week='fri', hour=16, minute=5, id='weekly_weekend_slot_warning', replace_existing=True
    )

    # Job 5 (BARU): Peringatan H-3 slot kosong - Setiap hari jam 08:00
    scheduler.add_job(
        lambda: kirim_peringatan_h_minus_3(bot), trigger='cron',
        hour=8, minute=0, id='daily_h3_warning', replace_existing=True
    )

    # Job 6: Laporan jadwal bulanan - Setiap hari terakhir bulan jam 17:00
    scheduler.add_job(
        lambda: kirim_laporan_bulanan(bot), trigger='cron',
        day='last', hour=17, minute=0, id='monthly_schedule_report', replace_existing=True
    )

    # Job 7: Rekap jadwal full bulan - Setiap tanggal 1 jam 07:10
    scheduler.add_job(
        lambda: kirim_jadwal_bulanan_awal_bulan(bot), trigger='cron',
        day=1, hour=7, minute=10, id='monthly_schedule_recap_first_day', replace_existing=True
    )
    
    scheduler.start()
    print("Scheduler untuk semua pekerjaan (harian, mingguan, bulanan, peringatan) telah dimulai.")
    return scheduler
