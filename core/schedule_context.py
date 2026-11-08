"""Konteks jadwal yang lebih kaya untuk LLM /tanya."""
from __future__ import annotations

from datetime import timedelta

from core.database import (
    format_tanggal_indonesia,
    get_all_absensi_in_range,
    get_bulan_dibuka_list,
    today_wita,
)
from core.schedule_query import HARI_MAP_ID, empty_days, week_schedule


def build_rich_context(today=None) -> str:
    if today is None:
        today = today_wita()
    lines = [f"Hari ini: {format_tanggal_indonesia(today)} ({HARI_MAP_ID[today.weekday()]})."]
    lines.append("Minggu ini:")
    lines.append(week_schedule(today))
    lines.append("Tanggal ISO: " + ", ".join((today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(14)))
    empty = empty_days(today, 14)
    if empty:
        lines.append("Hari kosong 14 hari ke depan:")
        lines.append("\n".join(f"- {HARI_MAP_ID[d.weekday()]}, {format_tanggal_indonesia(d)}" for d in empty))
    else:
        lines.append("Hari kosong 14 hari ke depan: tidak ada.")
    opened = get_bulan_dibuka_list() or []
    if opened:
        lines.append("Bulan aktif: " + ", ".join(f"{(r or {}).get('bulan')}/{(r or {}).get('tahun')}" for r in opened))
    else:
        lines.append("Bulan aktif: tidak ada.")
    cuti = get_all_absensi_in_range(today.strftime("%Y-%m-%d"), (today + timedelta(days=13)).strftime("%Y-%m-%d")) or []
    if cuti:
        lines.append("Cuti aktif 14 hari ke depan:")
        for r in cuti:
            lines.append(f"- {r['tanggal']}: {r['username']}")
    else:
        lines.append("Cuti aktif 14 hari ke depan: tidak ada.")
    return "\n".join(lines)
