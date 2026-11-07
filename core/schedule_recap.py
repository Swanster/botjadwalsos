import calendar
from collections import defaultdict
from datetime import date

from core.database import get_jadwal_for_month
from core.telegram_text import escape_markdown

NAMA_BULAN = {
    1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni',
    7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
}
HARI_MAP_ID = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}
HARI_SINGKAT = {0: 'Sen', 1: 'Sel', 2: 'Rab', 3: 'Kam', 4: 'Jum', 5: 'Sab', 6: 'Min'}
SEPARATOR = '━━━━━━━━━━━━━━━━━━'


def generate_rekap_text(tahun, bulan):
    jadwal_list = get_jadwal_for_month(tahun, bulan)
    if not jadwal_list:
        return (
            "📋 *REKAP JADWAL STANDBY*\n"
            f"🗓️ *{NAMA_BULAN[bulan]} {tahun}*\n"
            f"{SEPARATOR}\n"
            f"_Belum ada jadwal yang diinput untuk bulan ini._"
        )

    jadwal_per_hari = defaultdict(list)
    for jadwal in jadwal_list:
        jadwal_per_hari[jadwal['tanggal']].append(jadwal['username'])

    days_in_month = calendar.monthrange(tahun, bulan)[1]
    terisi = len(jadwal_per_hari)
    kosong = days_in_month - terisi

    pesan = (
        "📋 *REKAP JADWAL STANDBY*\n"
        f"🗓️ *{NAMA_BULAN[bulan]} {tahun}*\n"
        f"{SEPARATOR}\n"
        f"📊 *{days_in_month}* hari · terisi *{terisi}* · kosong *{kosong}*\n"
    )

    my_calendar = calendar.Calendar(firstweekday=calendar.MONDAY)
    for pekan, week in enumerate(my_calendar.monthdayscalendar(tahun, bulan), start=1):
        hari_pekan = [day for day in week if day]
        if not hari_pekan:
            continue
        rentang = (
            f"{hari_pekan[0]}–{hari_pekan[-1]} {NAMA_BULAN[bulan][:3]}"
            if len(hari_pekan) > 1
            else f"{hari_pekan[0]} {NAMA_BULAN[bulan][:3]}"
        )
        pesan += f"\n*Pekan {pekan} · {rentang}*\n"
        for day in hari_pekan:
            current_date = date(tahun, bulan, day)
            current_date_str = current_date.strftime('%Y-%m-%d')
            label = f"*{day:02d} {HARI_SINGKAT[current_date.weekday()]}*"
            petugas = jadwal_per_hari.get(current_date_str)
            if petugas:
                nama = ', '.join(escape_markdown(p) for p in petugas)
                pesan += f"• {label} — {nama}\n"
            else:
                pesan += f"• {label} — _kosong_\n"

    return pesan.rstrip()