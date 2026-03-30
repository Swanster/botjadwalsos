# handlers/admin_handlers.py (Versi dengan /statistik)

import telebot
import io
import csv
from datetime import date, datetime
from collections import defaultdict

from config import ADMIN_ID, GROUP_CHAT_ID, ALLOWED_TOPIC_ID
from core.database import get_bulan_dibuka, buka_bulan_baru, format_tanggal_indonesia, get_jadwal_for_month, tutup_bulan_aktif, get_user_group, get_user_by_telegram_username, set_user_group

NAMA_BULAN = {
    1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni',
    7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
}
HARI_MAP_ID = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}
EMOJI_HARI = {'Senin':'🌞','Selasa':'📘','Rabu':'📗','Kamis':'📙','Jumat':'📕','Sabtu':'🎉','Minggu':'🛌'}

def register_admin_handlers(bot: telebot.TeleBot):
    
    @bot.message_handler(commands=['buka_jadwal_bulan'])
    def handle_buka_jadwal_bulan(message):
        # ... (fungsi ini tidak berubah)
        if message.from_user.id != ADMIN_ID:
            bot.reply_to(message, "❌ Perintah ini hanya untuk Admin.")
            return

        bulan_terbuka = get_bulan_dibuka()
        if bulan_terbuka:
            bot.reply_to(message, 
                f"⚠️ Gagal. Masih ada jadwal untuk bulan {NAMA_BULAN[bulan_terbuka['bulan']]} {bulan_terbuka['tahun']} yang sedang dibuka.")
            return

        parts = message.text.split()
        try:
            if len(parts) == 3:
                bulan = int(parts[1]); tahun = int(parts[2])
                if not (1 <= bulan <= 12 and tahun > 2020): raise ValueError("Bulan atau tahun tidak valid.")
            elif len(parts) == 1:
                hari_ini = date.today(); bulan = hari_ini.month; tahun = hari_ini.year
            else: raise ValueError("Format perintah salah.")
        except (ValueError, IndexError):
            bot.reply_to(message, "Format perintah salah.\nGunakan: `/buka_jadwal_bulan` (untuk bulan ini) atau `/buka_jadwal_bulan <bulan> <tahun>`")
            return

        id_bulan_baru = buka_bulan_baru(tahun, bulan)
        if id_bulan_baru is None:
            bot.reply_to(message, f"❌ Gagal. Jadwal untuk bulan {NAMA_BULAN[bulan]} {tahun} sepertinya sudah ada di database.")
            return

        nama_bulan_full = NAMA_BULAN[bulan]
        pesan_pengumuman = (f"📢 *Pengumuman Jadwal Bulanan*\n\nPeriode pengisian jadwal standby untuk bulan *{nama_bulan_full} {tahun}* telah dibuka!\n\nSilakan anggota tim untuk mulai mengisi jadwal dengan mengirim perintah /start.")
        try:
            bot.send_message(chat_id=GROUP_CHAT_ID, text=pesan_pengumuman, parse_mode='Markdown', message_thread_id=ALLOWED_TOPIC_ID)
            bot.reply_to(message, f"✅ Berhasil! Pengumuman untuk jadwal bulan {nama_bulan_full} {tahun} telah dikirim ke grup.")
        except Exception as e:
            bot.reply_to(message, f"Terjadi kesalahan saat mengirim pengumuman: {e}")
            
    # --- PERINTAH BARU UNTUK MENUTUP JADWAL ---
    @bot.message_handler(commands=['tutup_jadwal_bulan'])
    def handle_tutup_jadwal_bulan(message):
        if message.from_user.id != ADMIN_ID:
            bot.reply_to(message, "❌ Perintah ini hanya untuk Admin.")
            return
        
        bulan_terbuka = get_bulan_dibuka()
        if not bulan_terbuka:
            bot.reply_to(message, "Tidak ada jadwal bulan yang sedang dibuka saat ini.")
            return
            
        tahun, bulan = bulan_terbuka['tahun'], bulan_terbuka['bulan']
        
        # Panggil fungsi database untuk menutup bulan
        baris_diubah = tutup_bulan_aktif(tahun, bulan)
        
        if baris_diubah > 0:
            nama_bulan_full = NAMA_BULAN[bulan]
            bot.reply_to(message, f"✅ Berhasil. Jadwal untuk bulan *{nama_bulan_full} {tahun}* telah ditutup dan tidak bisa diisi lagi.", parse_mode='Markdown')
        else:
            bot.reply_to(message, "Gagal menutup jadwal. Mohon periksa log.")
            

    # --- FUNGSI BARU: /statistik ---
    @bot.message_handler(commands=['statistik'])
    def handle_statistik(message):
        if message.from_user.id != ADMIN_ID:
            bot.reply_to(message, "❌ Perintah ini hanya untuk Admin.")
            return
            
        today = date.today()
        tahun, bulan = today.year, today.month
        
        jadwal_bulan_ini = get_jadwal_for_month(tahun, bulan)
        
        if not jadwal_bulan_ini:
            bot.reply_to(message, f"Belum ada data jadwal untuk bulan {NAMA_BULAN[bulan]} {tahun} untuk ditampilkan.")
            return
            
        # Proses data untuk statistik
        rekap_user = defaultdict(int)
        rekap_hari = defaultdict(int)
        
        for jadwal in jadwal_bulan_ini:
            rekap_user[jadwal['username']] += 1
            tgl_obj = datetime.strptime(jadwal['tanggal'], '%Y-%m-%d').date()
            nama_hari = HARI_MAP_ID[tgl_obj.weekday()]
            rekap_hari[nama_hari] += 1
            
        # Urutkan rekap user dari yang paling banyak
        sorted_rekap_user = sorted(rekap_user.items(), key=lambda item: item[1], reverse=True)
        
        # Buat pesan balasan
        pesan = f"📈 *Statistik Jadwal Bulan {NAMA_BULAN[bulan]} {tahun}*\n\n"
        
        pesan += "👤 *Rekap per Pengguna:*\n"
        for nama, jumlah in sorted_rekap_user:
            pesan += f"- {nama}: *{jumlah}* kali\n"
            
        pesan += "\n🗓️ *Rekap per Hari:*\n"
        for hari in HARI_MAP_ID.values(): # Loop sesuai urutan Senin-Minggu
            emoji = EMOJI_HARI.get(hari, '•')
            jumlah = rekap_hari.get(hari, 0)
            pesan += f"{emoji} {hari}: *{jumlah}* kali terisi\n"

        bot.send_message(message.chat.id, pesan, parse_mode='Markdown', message_thread_id=message.message_thread_id)
        
    @bot.message_handler(commands=['upload_grup_csv'])
    def handle_upload_csv(message):
        if message.from_user.id != ADMIN_ID:
            bot.reply_to(message, "❌ Perintah ini hanya untuk Admin.")
            return
        
        # Minta admin untuk mengirim file
        msg = bot.reply_to(message, "Silakan kirim file `.csv` Anda.\n\n"
                                    "Format kolom harus: `user_id,username,telegram_username,group_name`\n"
                                    "Contoh: `123456,Budi,budisan,INFRA` atau `789012,Susi,susian,MONITORING`")
        bot.register_next_step_handler(msg, process_csv_file)

    def process_csv_file(message):
        # Cek apakah pesan berisi dokumen dan tipenya adalah csv
        if not message.document or not message.document.file_name.endswith('.csv'):
            bot.reply_to(message, "❌ File tidak valid. Harap kirim file dengan ekstensi `.csv`.")
            return

        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            # Decode file dari bytes ke string
            file_content = downloaded_file.decode('utf-8')
            csv_file = io.StringIO(file_content)
            
            # Baca CSV, lewati header
            reader = csv.reader(csv_file)
            next(reader, None) # Lewati baris header
            
            sukses_count = 0
            gagal_count = 0
            
            for row in reader:
                try:
                    # Pastikan format baris benar
                    user_id = int(row[0].strip())
                    username = row[1].strip()
                    telegram_username = row[2].strip().lstrip('@')
                    group_name = row[3].strip().upper()
                    
                    if group_name not in ['INFRA', 'CE', 'APPS', 'MONITORING']:
                        raise ValueError(f"Grup tidak valid: {group_name}")

                    # Simpan ke database
                    set_user_group(user_id, username, telegram_username, group_name)
                    sukses_count += 1
                except (ValueError, IndexError) as e:
                    print(f"Gagal memproses baris CSV: {row} - Error: {e}")
                    gagal_count += 1
            
            bot.reply_to(message, f"✅ Proses selesai.\n"
                                  f"Berhasil mengimpor: *{sukses_count}* pengguna.\n"
                                  f"Gagal: *{gagal_count}* baris.", parse_mode='Markdown')

        except Exception as e:
            bot.reply_to(message, f"Terjadi error saat memproses file: {e}")
