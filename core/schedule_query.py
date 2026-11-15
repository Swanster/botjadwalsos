"""Pertanyaan jadwal SOS (natural language ringan) — ruang lingkup terbatas."""

import re
from datetime import date, timedelta

from core.database import format_tanggal_indonesia, get_jadwal_for_specific_date, get_all_absensi_in_range, today_wita
from core.holidays import format_holidays_month, holidays_in_month

SCOPE_MSG = (
    "Saya hanya bisa membantu jadwal SOS/standby tim. "
    "Contoh: \"siapa yang SOS besok?\" atau \"hari apa yang belum ada yang SOS?\""
)


HARI_MAP_ID = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}

SCHEDULE_KEYWORDS = ("sos", "jadwal", "standby", "piket", "shift", "cuti", "tukar", "bertugas", "jaga", "kosong", "libur", "holiday", "tanggal merah")


def is_schedule_question(question: str) -> bool:
    """Gate deterministik: hanya pertanyaan ber-topik jadwal yang boleh ke LLM."""
    q = (question or "").lower()
    return any(keyword in q for keyword in SCHEDULE_KEYWORDS)


def _names_on(date_str: str) -> list[str]:
    rows = get_jadwal_for_specific_date(date_str) or []
    names = []
    for r in rows:
        name = r.get("username") if isinstance(r, dict) else None
        if not name:
            name = r.get("telegram_username") if isinstance(r, dict) else None
        names.append(name or "?")
    return names


def who_on_date(date_obj: date) -> str:
    date_str = date_obj.strftime("%Y-%m-%d")
    names = _names_on(date_str)
    if not names:
        return f"Tidak ada yang SOS pada {format_tanggal_indonesia(date_obj)} ({HARI_MAP_ID[date_obj.weekday()]})."
    return f"SOS pada {format_tanggal_indonesia(date_obj)} ({HARI_MAP_ID[date_obj.weekday()]}): {', '.join(names)}."


def empty_days(start: date, days: int = 14) -> list[date]:
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        if not _names_on(d.strftime("%Y-%m-%d")):
            out.append(d)
    return out


def week_schedule(start: date) -> str:
    lines = []
    for i in range(7):
        d = start + timedelta(days=i)
        names = _names_on(d.strftime("%Y-%m-%d"))
        label = ", ".join(names) if names else "(kosong)"
        lines.append(f"- {HARI_MAP_ID[d.weekday()]}, {format_tanggal_indonesia(d)}: {label}")
    return "\n".join(lines)


def _cuti_on_date(date_obj: date) -> str:
    rows = get_all_absensi_in_range(date_obj.strftime("%Y-%m-%d"), date_obj.strftime("%Y-%m-%d")) or []
    names = [r.get("username") if isinstance(r, dict) else None for r in rows]
    names = [n for n in names if n]
    if not names:
        return f"Tidak ada yang cuti pada {format_tanggal_indonesia(date_obj)} ({HARI_MAP_ID[date_obj.weekday()]})."
    return f"Cuti pada {format_tanggal_indonesia(date_obj)} ({HARI_MAP_ID[date_obj.weekday()]}): {', '.join(names)}."


def _resolve_target_date(q: str, today: date) -> date | None:
    if "lusa" in q:
        return today + timedelta(days=2)
    if "besok" in q:
        return today + timedelta(days=1)
    if "kemarin" in q:
        return today - timedelta(days=1)
    if "hari ini" in q or "today" in q:
        return today
    m = re.search(r"tanggal\s+(\d{1,2})", q)
    if m:
        day = int(m.group(1))
        try:
            return date(today.year, today.month, day)
        except ValueError:
            return None
    return None


def answer_question(question: str, today: date | None = None) -> str:
    if today is None:
        today = today_wita()
    q = (question or "").lower().strip()

    # Guardrail ruang lingkup: tolak pertanyaan yang jelas di luar jadwal.
    off_topic = ("cuaca", "berita", "kode", "python", "harga", "film", "musik")
    if any(k in q for k in off_topic):
        return SCOPE_MSG

    target_date = _resolve_target_date(q, today)
    if target_date is not None and ("sos" in q or "standby" in q or "jadwal" in q or "bertugas" in q or "jaga" in q or "siapa" in q):
        return who_on_date(target_date)

    if "cuti" in q or "absen" in q:
        if target_date is not None:
            return _cuti_on_date(target_date)
        return _cuti_on_date(today)

    if "besok" in q:
        return who_on_date(today + timedelta(days=1))
    if "hari ini" in q or "today" in q:
        return who_on_date(today)
    if "lusa" in q:
        return who_on_date(today + timedelta(days=2))
    if "kemarin" in q:
        return who_on_date(today - timedelta(days=1))
    if "minggu ini" in q or "pekan ini" in q:
        start = today - timedelta(days=today.weekday())
        return "Jadwal SOS minggu ini:\n" + week_schedule(start)
    if any(k in q for k in ("kosong", "belum", "empty", "belum ada")):
        days = empty_days(today, 14)
        if not days:
            return "Tidak ada hari kosong dalam 14 hari ke depan."
        return "Hari yang belum ada yang SOS (14 hari ke depan):\n" + "\n".join(
            f"- {HARI_MAP_ID[d.weekday()]}, {format_tanggal_indonesia(d)}" for d in days
        )
    if "libur" in q or "holiday" in q or "tanggal merah" in q:
        y, m = today.year, today.month
        if "bulan depan" in q or "next month" in q:
            if m == 12:
                y, m = y + 1, 1
            else:
                m += 1
        return format_holidays_month(y, m)

    # Default: tawarkan bantuan ruang lingkup.
    return SCOPE_MSG