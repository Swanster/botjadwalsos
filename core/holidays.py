"""Hari libur Indonesia (libur nasional + cuti bersama)."""
from __future__ import annotations

from datetime import date

# Data 2026 sesuai SKB 3 Menteri (17 libur nasional + 8 cuti bersama).
_HOLIDAYS_2026 = {
    "2026-01-01": "Tahun Baru 2026 Masehi",
    "2026-01-16": "Isra Mikraj Nabi Muhammad S.A.W.",
    "2026-02-16": "Cuti Bersama Tahun Baru Imlek 2577",
    "2026-02-17": "Tahun Baru Imlek 2577 Kongzili",
    "2026-03-18": "Cuti Bersama Hari Suci Nyepi",
    "2026-03-19": "Hari Suci Nyepi (Tahun Baru Saka 1948)",
    "2026-03-20": "Cuti Bersama Idul Fitri 1447 H",
    "2026-03-21": "Idul Fitri 1447 H",
    "2026-03-22": "Idul Fitri 1447 H",
    "2026-03-23": "Cuti Bersama Idul Fitri 1447 H",
    "2026-03-24": "Cuti Bersama Idul Fitri 1447 H",
    "2026-04-03": "Wafat Yesus Kristus",
    "2026-04-05": "Kebangkitan Yesus Kristus (Paskah)",
    "2026-05-01": "Hari Buruh Internasional",
    "2026-05-14": "Kenaikan Yesus Kristus",
    "2026-05-15": "Cuti Bersama Kenaikan Yesus Kristus",
    "2026-05-27": "Idul Adha 1447 H",
    "2026-05-28": "Cuti Bersama Idul Adha 1447 H",
    "2026-05-31": "Hari Raya Waisak 2570 BE",
    "2026-06-01": "Hari Lahir Pancasila",
    "2026-06-16": "1 Muharam Tahun Baru Islam 1448 H",
    "2026-08-17": "Proklamasi Kemerdekaan RI",
    "2026-08-25": "Maulid Nabi Muhammad S.A.W.",
    "2026-12-24": "Cuti Bersama Kelahiran Yesus Kristus",
    "2026-12-25": "Kelahiran Yesus Kristus (Natal)",
}

_HOLIDAY_MAP = {"2026": _HOLIDAYS_2026}


def holiday_name(date_str: str) -> str | None:
    year = date_str[:4]
    return _HOLIDAY_MAP.get(year, {}).get(date_str)


def holidays_in_month(year: int, month: int) -> list[tuple[date, str]]:
    prefix = f"{year:04d}-{month:02d}-"
    out = []
    for ds, name in _HOLIDAY_MAP.get(str(year), {}).items():
        if ds.startswith(prefix):
            d = date.fromisoformat(ds)
            out.append((d, name))
    out.sort()
    return out


def format_holidays_month(year: int, month: int) -> str:
    items = holidays_in_month(year, month)
    if not items:
        return f"Tidak ada hari libur nasional/cuti bersama pada {month:02d}/{year}."
    lines = [f"Libur Indonesia {month:02d}/{year}:"]
    for d, name in items:
        lines.append(f"- {d.strftime('%d %b %Y')}: {name}")
    return "\n".join(lines)
