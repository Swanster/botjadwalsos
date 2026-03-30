# core/scheduler.py (Versi Final dengan Laporan & Pengingat Cuti)

import time
import pytz
from datetime import datetime, timedelta
from functools import wraps
from collections import defaultdict
from apscheduler.schedulers.background import BackgroundScheduler

from config import GROUP_CHAT_ID, ALLOWED_TOPIC_ID
from core.database import (
    get_jadwal_for_specific_date, get_all_absensi_in_range, get_jadwal_by_group,
    get_all_users_in_group, format_tanggal_indonesia,
    get_all_registered_users, get_users_with_schedule_in_range,
    is_date_full, get_daily_limit
)

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
    jadwal_infra = get_jadwal_by_group(next_week_start.year, next_week_start.month, 'INFRA')
    jadwal_ce = get_jadwal_by_group(next_week_start.year, next_week_start.month, 'CE')
    jadwal_apps = get_jadwal_by_group(next_week_start.year, next_week_start.month, 'APPS')
    jadwal_monitoring = get_jadwal_by_group(next_week_start.year, next_week_start.month, 'MONITORING')

    # Hitung slot terisi per hari untuk setiap grup
    slot_terisi_infra = defaultdict(int)
    for j in jadwal_infra: slot_terisi_infra[j['tanggal']] += 1

    slot_terisi_ce = defaultdict(int)
    for j in jadwal_ce: slot_terisi_ce[j['tanggal']] += 1

    slot_terisi_apps = defaultdict(int)
    for j in jadwal_apps: slot_terisi_apps[j['tanggal']] += 1

    slot_terisi_monitoring = defaultdict(int)
    for j in jadwal_monitoring: slot_terisi_monitoring[j['tanggal']] += 1

    # Cari tanggal yang kuotanya kurang
    tanggal_kurang_infra = []
    tanggal_kurang_ce = []
    tanggal_kurang_apps = []
    tanggal_kurang_monitoring = []
    for i in range(7):
        current_date = next_week_start + timedelta(days=i)
        current_date_str = current_date.strftime('%Y-%m-%d')
        
        # Cek jika tanggal berada di bulan yang sama dengan awal minggu
        if current_date.month == next_week_start.month:
            # Cek batasan harian (prioritas utama)
            max_per_hari_infra = get_daily_limit(current_date_str, 2)
            max_per_hari_ce = get_daily_limit(current_date_str, 1)
            max_per_hari_apps = get_daily_limit(current_date_str, 1)
            max_per_hari_monitoring = get_daily_limit(current_date_str, 1)
                
            if slot_terisi_infra.get(current_date_str, 0) < max_per_hari_infra:
                tanggal_kurang_infra.append(current_date_str)
            if slot_terisi_ce.get(current_date_str, 0) < max_per_hari_ce:
                tanggal_kurang_ce.append(current_date_str)
            if slot_terisi_apps.get(current_date_str, 0) < max_per_hari_apps:
                tanggal_kurang_apps.append(current_date_str)
            if slot_terisi_monitoring.get(current_date_str, 0) < max_per_hari_monitoring:
                tanggal_kurang_monitoring.append(current_date_str)

    # Kirim peringatan ke anggota grup INFRA jika perlu
    if tanggal_kurang_infra:
        users_infra = get_all_users_in_group('INFRA')
        pesan_infra = "🔔 *Peringatan Jadwal INFRA*\n\nJadwal standby Anda untuk beberapa tanggal di minggu depan masih belum terisi penuh (kuota: 2 orang/hari). Tanggal yang masih kosong:\n\n"
        for tgl in tanggal_kurang_infra:
            tgl_obj = datetime.strptime(tgl, '%Y-%m-%d').date()
            pesan_infra += f"- {format_tanggal_indonesia(tgl_obj)}\n"
        pesan_infra += "\nMohon segera lengkapi jadwal Anda dengan menggunakan perintah `/start` di grup."
        
        for user in users_infra:
            try:
                bot.send_message(user['user_id'], pesan_infra, parse_mode='Markdown')
            except Exception as e:
                print(f"Gagal mengirim DM peringatan ke user INFRA {user['telegram_username']}: {e}")

    # Kirim peringatan ke anggota grup CE jika perlu
    if tanggal_kurang_ce:
        users_ce = get_all_users_in_group('CE')
        pesan_ce = "🔔 *Peringatan Jadwal CE*\n\nJadwal standby Anda untuk beberapa tanggal di minggu depan masih belum terisi penuh (kuota: 1 orang/hari). Tanggal yang masih kosong:\n\n"
        for tgl in tanggal_kurang_ce:
            tgl_obj = datetime.strptime(tgl, '%Y-%m-%d').date()
            pesan_ce += f"- {format_tanggal_indonesia(tgl_obj)}\n"
        pesan_ce += "\nMohon segera lengkapi jadwal Anda dengan menggunakan perintah `/start` di grup."

        for user in users_ce:
            try:
                bot.send_message(user['user_id'], pesan_ce, parse_mode='Markdown')
            except Exception as e:
                print(f"Gagal mengirim DM peringatan ke user CE {user['telegram_username']}: {e}")

    # Kirim peringatan ke anggota grup APPS jika perlu
    if tanggal_kurang_apps:
        users_apps = get_all_users_in_group('APPS')
        pesan_apps = "🔔 *Peringatan Jadwal APPS*\n\nJadwal standby Anda untuk beberapa tanggal di minggu depan masih belum terisi penuh (kuota: 1 orang/hari). Tanggal yang masih kosong:\n\n"
        for tgl in tanggal_kurang_apps:
            tgl_obj = datetime.strptime(tgl, '%Y-%m-%d').date()
            pesan_apps += f"- {format_tanggal_indonesia(tgl_obj)}\n"
        pesan_apps += "\nMohon segera lengkapi jadwal Anda dengan menggunakan perintah `/start` di grup."

        for user in users_apps:
            try:
                bot.send_message(user['user_id'], pesan_apps, parse_mode='Markdown')
            except Exception as e:
                print(f"Gagal mengirim DM peringatan ke user APPS {user['telegram_username']}: {e}")

    # Kirim peringatan ke anggota grup MONITORING jika perlu
    if tanggal_kurang_monitoring:
        users_monitoring = get_all_users_in_group('MONITORING')
        pesan_monitoring = "🔔 *Peringatan Jadwal MONITORING*\n\nJadwal standby Anda untuk beberapa tanggal di minggu depan masih belum terisi penuh (kuota: 1 orang/hari). Tanggal yang masih kosong:\n\n"
        for tgl in tanggal_kurang_monitoring:
            tgl_obj = datetime.strptime(tgl, '%Y-%m-%d').date()
            pesan_monitoring += f"- {format_tanggal_indonesia(tgl_obj)}\n"
        pesan_monitoring += "\nMohon segera lengkapi jadwal Anda dengan menggunakan perintah `/start` di grup."

        for user in users_monitoring:
            try:
                bot.send_message(user['user_id'], pesan_monitoring, parse_mode='Markdown')
            except Exception as e:
                print(f"Gagal mengirim DM peringatan ke user MONITORING {user['telegram_username']}: {e}")
    
    if not tanggal_kurang_infra and not tanggal_kurang_ce and not tanggal_kurang_apps and not tanggal_kurang_monitoring:
        print("Scheduler: Jadwal minggu depan untuk semua grup sudah penuh.")
    
    print("Scheduler: Pengecekan peringatan jadwal mingguan selesai.")
    
@retry_on_failure(retries=3, delay=60)
def kirim_peringatan_jadwal_mingguan_kosong(bot):
    """
    Setiap Sabtu, me-mention pengguna yang sama sekali belum mengisi
    jadwal untuk minggu depan.
    """
    print("Scheduler: Mengecek pengguna yang belum input jadwal untuk minggu depan...")
    tz = pytz.timezone("Asia/Makassar")
    today = datetime.now(tz).date()

    # Tentukan periode minggu depan (Senin hingga Minggu)
    next_week_start = today + timedelta(days=(7 - today.weekday()))
    next_week_end = next_week_start + timedelta(days=6)
    
    start_str = next_week_start.strftime('%Y-%m-%d')
    end_str = next_week_end.strftime('%Y-%m-%d')

    # Dapatkan semua pengguna terdaftar dan yang sudah mengisi jadwal
    all_users = get_all_registered_users()
    users_sudah_isi = get_users_with_schedule_in_range(start_str, end_str)

    # Cari siapa saja yang belum mengisi
    users_belum_isi = []
    for user in all_users:
        if user['user_id'] not in users_sudah_isi:
            users_belum_isi.append(user)
    
    if not users_belum_isi:
        print("Scheduler: Semua pengguna sudah mengisi jadwal minggu depan. Peringatan dilewati.")
        return

    # Buat pesan dengan mention
    pesan = (f"🔔 *Peringatan Pengisian Jadwal*\n\n"
             f"Mohon perhatiannya untuk segera mengisi jadwal standby minggu depan "
             f"({next_week_start.day} - {next_week_end.day} {format_tanggal_indonesia(next_week_end).split(' ')[1]}).\n\n"
             f"Anggota yang belum mengisi:\n")

    mentions = []
    for user in users_belum_isi:
        # Gunakan telegram_username jika ada, jika tidak, buat mention dari user_id
        if user['telegram_username']:
            mentions.append(f"• @{user['telegram_username']}")
        else:
            # Fallback jika tidak ada username, mention dengan nama "pengguna"
            mentions.append(f"• [pengguna](tg://user?id={user['user_id']})")
            
    pesan += '\n'.join(mentions)
    pesan += "\n\nSilakan gunakan perintah `/start` untuk mengisi."
    
    bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=pesan,
        parse_mode='Markdown',
        message_thread_id=ALLOWED_TOPIC_ID
    )
    print("Scheduler: Peringatan mingguan (mention) berhasil dikirim.")


# --- FITUR BARU 2: Peringatan H-3 Slot Kosong ---
@retry_on_failure(retries=3, delay=60)
def kirim_peringatan_h_minus_3(bot):
    """
    Setiap hari, mengecek jadwal untuk 3 hari ke depan (H-3).
    Jika slot belum penuh, kirim peringatan.
    """
    print("Scheduler: Mengecek slot kosong untuk H-3...")
    tz = pytz.timezone("Asia/Makassar")
    
    # Tentukan tanggal target (3 hari dari sekarang)
    target_date = (datetime.now(tz) + timedelta(days=3)).date()
    target_date_str = target_date.strftime('%Y-%m-%d')

    # Dapatkan jadwal yang sudah terisi pada hari H-3
    jadwal_infra = get_jadwal_by_group(target_date.year, target_date.month, 'INFRA')
    jadwal_ce = get_jadwal_by_group(target_date.year, target_date.month, 'CE')
    jadwal_apps = get_jadwal_by_group(target_date.year, target_date.month, 'APPS')
    jadwal_monitoring = get_jadwal_by_group(target_date.year, target_date.month, 'MONITORING')
    
    # Hitung jumlah terisi khusus untuk tanggal target
    terisi_infra = sum(1 for j in jadwal_infra if j['tanggal'] == target_date_str)
    terisi_ce = sum(1 for j in jadwal_ce if j['tanggal'] == target_date_str)
    terisi_apps = sum(1 for j in jadwal_apps if j['tanggal'] == target_date_str)
    terisi_monitoring = sum(1 for j in jadwal_monitoring if j['tanggal'] == target_date_str)

    # Cek batasan harian
    max_per_hari_infra = get_daily_limit(target_date_str, 2)
    max_per_hari_ce = get_daily_limit(target_date_str, 1)
    max_per_hari_apps = get_daily_limit(target_date_str, 1)
    max_per_hari_monitoring = get_daily_limit(target_date_str, 1)

    pesan_peringatan = ""
    if terisi_infra < max_per_hari_infra:
        pesan_peringatan += f"• 🚨 Slot *INFRA* masih kurang ({terisi_infra}/{max_per_hari_infra} terisi).\n"
    if terisi_ce < max_per_hari_ce:
        pesan_peringatan += f"• 🚨 Slot *CE* masih kurang ({terisi_ce}/{max_per_hari_ce} terisi).\n"
    if terisi_apps < max_per_hari_apps:
        pesan_peringatan += f"• 🚨 Slot *APPS* masih kurang ({terisi_apps}/{max_per_hari_apps} terisi).\n"
    if terisi_monitoring < max_per_hari_monitoring:
        pesan_peringatan += f"• 🚨 Slot *MONITORING* masih kurang ({terisi_monitoring}/{max_per_hari_monitoring} terisi).\n"
        
    if not pesan_peringatan:
        print(f"Scheduler: Slot untuk H-3 ({target_date_str}) sudah penuh. Peringatan dilewati.")
        return

    # Buat pesan akhir
    pesan = (f"📢 *Peringatan Jadwal H-3*\n\n"
             f"Jadwal standby untuk hari *{format_tanggal_indonesia(target_date)}* masih belum penuh:\n\n"
             f"{pesan_peringatan}\n"
             f"Mohon anggota yang bersangkutan untuk segera mengisi kekosongan melalui perintah `/start` atau melakukan pertukaran jadwal.")
             
    bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=pesan,
        parse_mode='Markdown',
        message_thread_id=ALLOWED_TOPIC_ID
    )
    print(f"Scheduler: Peringatan H-3 untuk tanggal {target_date_str} berhasil dikirim.")

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

    # Job 4 (BARU): Peringatan H-3 slot kosong - Setiap hari jam 08:00
    scheduler.add_job(
        lambda: kirim_peringatan_h_minus_3(bot), trigger='cron',
        hour=8, minute=0, id='daily_h3_warning', replace_existing=True
    )
    
    scheduler.start()
    print("Scheduler untuk semua pekerjaan (harian, mingguan, peringatan) telah dimulai.")
    return scheduler