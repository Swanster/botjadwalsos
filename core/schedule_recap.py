import calendar
from collections import defaultdict
from datetime import date

from core.database import get_jadwal_for_month

NAMA_BULAN = {
    1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni',
    7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
}
HARI_MAP_ID = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}


def generate_rekap_text(tahun, bulan):
    jadwal_list = get_jadwal_for_month(tahun, bulan)
    if not jadwal_list:
        return f"Belum ada jadwal yang diinput untuk bulan {NAMA_BULAN[bulan]} {tahun}."

    jadwal_per_hari = defaultdict(list)
    for jadwal in jadwal_list:
        jadwal_per_hari[jadwal['tanggal']].append(jadwal['username'])

    pesan = f"📋 *Rekap Jadwal Standby Bulan {NAMA_BULAN[bulan]} {tahun}*\n\n"
    days_in_month = calendar.monthrange(tahun, bulan)[1]
    for day in range(1, days_in_month + 1):
        current_date = date(tahun, bulan, day)
        current_date_str = current_date.strftime('%Y-%m-%d')
        nama_hari = HARI_MAP_ID[current_date.weekday()]
        petugas = jadwal_per_hari.get(current_date_str)
        if petugas:
            pesan += f"*{current_date.day}* {nama_hari}: {', '.join(petugas)}\n"
        else:
            pesan += f"*{current_date.day}* {nama_hari}: _(kosong)_\n"

    return pesan
