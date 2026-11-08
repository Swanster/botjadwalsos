"""Agen ringan untuk isi jadwal via teks natural dan bantuan penggunaan bot.

Bot ini sengaja tidak menjadi agent umum: hanya dua kemampuan terbatas:
1. Menambah tanggal jadwal dari kalimat sederhana, dengan konfirmasi user.
2. Menjawab pertanyaan cara pakai bot (bukan detail internal program).
"""
from __future__ import annotations

import calendar
import re
import time
from datetime import datetime

import core.database as db

NAMA_BULAN = {
    1: "Januari", 2: "Februari", 3: "Maret", 4: "April", 5: "Mei", 6: "Juni",
    7: "Juli", 8: "Agustus", 9: "September", 10: "Oktober", 11: "November", 12: "Desember",
}
MONTH_LOOKUP = {name.lower(): num for num, name in NAMA_BULAN.items()}
MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "jun": 6,
    "jul": 7, "agu": 8, "ags": 8, "sep": 9, "okt": 10, "nov": 11, "des": 12,
}
FILL_VERBS = ("input", "isi", "tambah", "masuk", "masukkan", "daftar", "catat")
REPLACE_VERBS = ("ganti", "ubah", "replace", "set", "timpa")
SCHEDULE_WORDS = ("jadwal", "sos", "standby", "shift", "piket")
HELP_WORDS = ("cara", "bagaimana", "help", "panduan", "guide", "tutorial", "langkah")
USAGE_WORDS = ("jadwal", "isi", "tukar", "batal", "cuti", "bot", "program", "pakai", "gunakan", "menu")

_pending_fills: dict[int, dict] = {}
PENDING_TTL_SECONDS = 900


def is_help_question(question: str) -> bool:
    q = (question or "").lower()
    return any(word in q for word in HELP_WORDS) and (
        any(word in q for word in USAGE_WORDS) or "bot" in q or "program" in q
    )


def get_help_text() -> str:
    return (
        "ℹ️ *Panduan Cepat Bot Jadwal SOS*\n\n"
        "*Perintah utama:*\n"
        "- `/menu` - buka tombol menu\n"
        "- `/start` - isi/edit jadwal bulan aktif\n"
        "- `/jadwal_saya` - lihat jadwal pribadi\n"
        "- `/lihat_jadwal` - rekap jadwal tim\n"
        "- `/cuti` - tandai tanggal tidak tersedia\n"
        "- `/lihat_cuti` - daftar cuti tim\n"
        "- `/tukar_jadwal` - ajukan pertukaran jadwal\n"
        "- `/batal_jadwal` - batalkan jadwal yang sudah ada\n"
        "- `/batal_cuti` - batalkan cuti\n"
        "- `/tanya <pertanyaan>` - tanya bot (jadwal/umum/panduan)\n\n"
        "- `/tambah_jadwal 4, 5, 10` - menambah tanggal ke jadwal Anda\n"
        "- `/ganti_jadwal 4, 5, 10` - mengganti seluruh jadwal bulan aktif\n"
        "Bot akan cek tanggal, lalu meminta konfirmasi sebelum menyimpan.\n\n"
        "*Aturan penting:*\n"
        "- Hanya bulan yang dibuka admin yang bisa diisi.\n"
        "- Tukar jadwal harus tipe hari yang sama (weekday/weekend).\n"
        "- `/tanya` tidak melayani topik vulgar, politik, SARA, atau detail internal program."
    )


def is_fill_request(text: str) -> bool:
    q = (text or "").lower()
    has_fill = any(verb in q for verb in FILL_VERBS + REPLACE_VERBS)
    has_schedule = any(word in q for word in SCHEDULE_WORDS)
    has_date = bool(re.search(r"\d", q)) and (
        "tanggal" in q or "tgl" in q or bool(re.search(r"\d+[,\s/\-]\d+", q))
    )
    return has_fill and has_schedule and has_date


def _parse_month_number(text: str) -> int | None:
    explicit = _extract_explicit_dates(text)
    if explicit:
        months = {item[1] for item in explicit}
        if len(months) == 1:
            return next(iter(months))
    low = (text or "").lower()
    for name, num in MONTH_LOOKUP.items():
        if name in low:
            return num
    for token in re.findall(r"\b[a-z]{3,4}\b", low):
        if token in MONTH_ABBR:
            return MONTH_ABBR[token]
    m = re.search(r"(?i)\bbulan\s+(\d{1,2})\b", low)
    if m:
        num = int(m.group(1))
        if 1 <= num <= 12:
            return num
    return None


def _parse_year(text: str) -> int | None:
    explicit = _extract_explicit_dates(text)
    if explicit:
        years = {item[2] for item in explicit if item[2] is not None}
        if len(years) == 1:
            return next(iter(years))
    m = re.search(r"\b(20\d{2})\b", text or "")
    return int(m.group(1)) if m else None


def _extract_explicit_dates(text: str) -> list[tuple[int, int, int | None]]:
    """Ambil tanggal eksplisit dd/mm/yyyy, dd-mm-yyyy, atau dd/mm."""
    result = []
    for match in re.finditer(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", text or ""):
        day = int(match.group(1))
        month = int(match.group(2))
        if not (1 <= day <= 31 and 1 <= month <= 12):
            continue
        year_raw = match.group(3)
        year = None
        if year_raw:
            year = int(year_raw)
            if year < 100:
                year += 2000
        result.append((day, month, year))
    return result


def _extract_days(text: str) -> list[int]:
    explicit = _extract_explicit_dates(text)
    if explicit:
        days = []
        for day, _month, _year in explicit:
            if day not in days:
                days.append(day)
        return days
    # Buang tahun dan frasa "bulan N" agar tidak dianggap hari.
    cleaned = re.sub(r"\b20\d{2}\b", " ", text or "")
    cleaned = re.sub(r"(?i)\bbulan\s+\d{1,2}\b", " ", cleaned)
    days = []
    for raw in re.findall(r"\b\d{1,2}\b", cleaned):
        value = int(raw)
        if 1 <= value <= 31 and value not in days:
            days.append(value)
    return days


def _resolve_open_month(text: str, open_months: list) -> tuple[int, int] | None:
    month_num = _parse_month_number(text)
    year_num = _parse_year(text)
    candidates = list(open_months)
    if month_num is not None:
        candidates = [b for b in candidates if b["bulan"] == month_num]
    if year_num is not None:
        candidates = [b for b in candidates if b["tahun"] == year_num]
    if not candidates:
        return None
    chosen = candidates[0]
    return chosen["tahun"], chosen["bulan"]


def is_replace_request(text: str) -> bool:
    q = (text or "").lower()
    return any(verb in q for verb in REPLACE_VERBS)


def build_fill_plan(text: str, user_id: int, first_name: str, username: str, mode: str = "add"):
    """Kembalikan dict rencana pengisian, atau string error yang siap dikirim."""
    days = _extract_days(text)
    if not days:
        return "Saya tidak menemukan tanggal yang valid. Contoh: `/tanya tolong input jadwal saya tanggal 4, 5, dan 10`."

    open_months = db.get_bulan_dibuka_list()
    if not open_months:
        return "Saat ini tidak ada periode jadwal yang sedang dibuka. Hubungi admin."

    resolved = _resolve_open_month(text, open_months)
    if resolved is None:
        month_num = _parse_month_number(text)
        if month_num is not None:
            return f"Bulan {NAMA_BULAN[month_num]} tidak sedang dibuka. Hubungi admin."
        return "Tidak ada periode jadwal yang cocok. Hubungi admin."
    year, month = resolved

    max_day = calendar.monthrange(year, month)[1]
    invalid_days = [day for day in days if day > max_day]
    if invalid_days:
        return f"Tanggal {', '.join(str(d) for d in invalid_days)} tidak valid untuk {NAMA_BULAN[month]} {year}."

    group_name = db.get_user_group(user_id)
    if not group_name:
        return "❌ Akun Anda belum terdaftar di grup mana pun. Silakan hubungi admin."

    existing_rows = db.get_user_jadwal_for_month(user_id, year, month)
    existing = {row["tanggal"] if isinstance(row, dict) else row[0] for row in existing_rows}
    # existing_rows dari sqlite Row juga mendukung key 'tanggal'; fallback di atas.

    available_new = []
    skipped = []
    unavailable = []
    for day in sorted(set(days)):
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        if mode == "replace":
            if db.date_is_taken(date_str, user_id):
                unavailable.append(date_str)
            else:
                available_new.append(date_str)
        elif date_str in existing:
            skipped.append(date_str)
        elif db.date_is_taken(date_str, user_id):
            unavailable.append(date_str)
        else:
            available_new.append(date_str)

    if not available_new and not skipped:
        return "Semua tanggal yang diminta tidak tersedia (penuh)."

    if available_new:
        if mode == "replace":
            projected_count = len(set(available_new))
        else:
            projected_count = len(existing | set(available_new))
        cap = db.get_monthly_cap_for_group(group_name)
        aksi = "Jadwal baru" if mode == "replace" else "Penambahan"
        if projected_count > cap:
            return (
                f"❌ {aksi} ini membuat total jadwal Anda {projected_count} hari, "
                f"melebihi batas bulanan divisi Anda ({cap} hari)."
            )

    return {
        "user_id": user_id,
        "first_name": first_name or "User",
        "username": username or "",
        "mode": mode,
        "year": year,
        "month": month,
        "available_new": available_new,
        "skipped": skipped,
        "unavailable": unavailable,
        "existing": sorted(existing),
    }


def is_cancel_request(text: str) -> bool:
    q = (text or "").lower()
    has_cancel = any(verb in q for verb in ("batal", "hapus", "cancel"))
    has_schedule = any(word in q for word in SCHEDULE_WORDS + ("cuti", "absen"))
    has_date = bool(re.search(r"\d", q)) and ("tanggal" in q or "tgl" in q or bool(re.search(r"\d+[,/\s-]\d+", q)))
    return has_cancel and has_schedule and has_date


def is_leave_request(text: str) -> bool:
    q = (text or "").lower()
    has_leave = any(word in q for word in ("cuti", "absen", "tidak tersedia"))
    has_date = bool(re.search(r"\d", q)) and ("tanggal" in q or "tgl" in q or bool(re.search(r"\d+[,/\s-]\d+", q)))
    return has_leave and has_date


def _build_cancel_plan(text: str, user_id: int, first_name: str, username: str) -> dict | str:
    days = _extract_days(text)
    if not days:
        return "Saya tidak menemukan tanggal yang valid. Contoh: `/tanya batal jadwal saya tanggal 4, 5`."

    open_months = db.get_bulan_dibuka_list()
    if not open_months:
        return "Saat ini tidak ada periode jadwal yang sedang dibuka. Hubungi admin."

    resolved = _resolve_open_month(text, open_months)
    if resolved is None:
        month_num = _parse_month_number(text)
        if month_num is not None:
            return f"Bulan {NAMA_BULAN[month_num]} tidak sedang dibuka. Hubungi admin."
        return "Tidak ada periode jadwal yang cocok. Hubungi admin."
    year, month = resolved

    max_day = calendar.monthrange(year, month)[1]
    invalid_days = [day for day in days if day > max_day]
    if invalid_days:
        return f"Tanggal {', '.join(str(d) for d in invalid_days)} tidak valid untuk {NAMA_BULAN[month]} {year}."

    group_name = db.get_user_group(user_id)
    if not group_name:
        return "❌ Akun Anda belum terdaftar di grup mana pun. Silakan hubungi admin."

    existing = {row["tanggal"] if isinstance(row, dict) else row[0] for row in db.get_user_jadwal_for_month(user_id, year, month)}
    selected = []
    for day in sorted(set(days)):
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        if date_str in existing and date_str not in selected:
            selected.append(date_str)

    not_found = [f"{year:04d}-{month:02d}-{day:02d}" for day in sorted(set(days)) if f"{year:04d}-{month:02d}-{day:02d}" not in existing]
    if not selected:
        return "Tidak ada jadwal yang dipilih untuk dibatalkan."

    return {
        "user_id": user_id,
        "first_name": first_name or "User",
        "username": username or "",
        "mode": "cancel_jadwal",
        "year": year,
        "month": month,
        "dates": selected,
        "available_new": selected,
        "skipped": [],
        "unavailable": not_found,
        "existing": sorted(existing),
    }


def _build_leave_plan(text: str, user_id: int, first_name: str, username: str) -> dict | str:
    days = _extract_days(text)
    if not days:
        return "Saya tidak menemukan tanggal yang valid. Contoh: `/tanya cuti tanggal 4, 5`."

    open_months = db.get_bulan_dibuka_list()
    if not open_months:
        today = db.today_wita()
        open_months = [{"tahun": today.year, "bulan": today.month}]

    resolved = _resolve_open_month(text, open_months)
    if resolved is None:
        month_num = _parse_month_number(text)
        if month_num is not None:
            return f"Bulan {NAMA_BULAN[month_num]} tidak sedang dibuka. Hubungi admin."
        return "Tidak ada periode jadwal yang cocok. Hubungi admin."
    year, month = resolved

    max_day = calendar.monthrange(year, month)[1]
    invalid_days = [day for day in days if day > max_day]
    if invalid_days:
        return f"Tanggal {', '.join(str(d) for d in invalid_days)} tidak valid untuk {NAMA_BULAN[month]} {year}."

    group_name = db.get_user_group(user_id)
    if not group_name:
        return "❌ Akun Anda belum terdaftar di grup mana pun. Silakan hubungi admin."

    start_of_month = f"{year:04d}-{month:02d}-01"
    end_of_month = f"{year:04d}-{month:02d}-{max_day:02d}"
    existing = db.get_user_absensi_in_range(user_id, start_of_month, end_of_month)

    to_add = []
    skipped = []
    for day in sorted(set(days)):
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        if date_str in existing:
            skipped.append(date_str)
        else:
            to_add.append(date_str)

    if not to_add and not skipped:
        return "Semua tanggal yang diminta tidak tersedia (penuh)."

    combined = sorted(existing | set(to_add))
    return {
        "user_id": user_id,
        "first_name": first_name or "User",
        "username": username or "",
        "mode": "leave",
        "year": year,
        "month": month,
        "dates": combined,
        "available_new": to_add,
        "skipped": skipped,
        "unavailable": [],
        "existing": sorted(existing),
    }


def build_action_plan(text: str, user_id: int, first_name: str, username: str, mode: str = "add"):
    if mode in ("add", "replace"):
        return build_fill_plan(text, user_id, first_name, username, mode)
    if mode == "cancel_jadwal":
        return _build_cancel_plan(text, user_id, first_name, username)
    if mode == "leave":
        return _build_leave_plan(text, user_id, first_name, username)
    if mode == "cancel_cuti":
        # Reuse leave parser but remove selected dates from existing cuti.
        base = _build_leave_plan(text, user_id, first_name, username)
        if isinstance(base, str):
            return base
        base["mode"] = "cancel_cuti"
        base["dates"] = [d for d in base.get("available_new", []) if d in base.get("existing", [])]
        base["available_new"] = base["dates"]
        return base
    return "Mode aksi tidak dikenal."
def store_pending(user_id: int, plan: dict) -> None:
    stored = dict(plan)
    stored["created_at"] = time.time()
    _pending_fills[user_id] = stored


def get_pending(user_id: int) -> dict | None:
    entry = _pending_fills.get(user_id)
    if not entry:
        return None
    if time.time() - float(entry.get("created_at", 0)) > PENDING_TTL_SECONDS:
        _pending_fills.pop(user_id, None)
        return None
    return entry


def clear_pending(user_id: int) -> None:
    _pending_fills.pop(user_id, None)


def format_plan(plan: dict) -> str:
    year = plan["year"]
    month = plan["month"]
    mode = plan.get("mode", "add")
    if mode == "replace":
        title = f"📋 *Rencana ganti jadwal* — {NAMA_BULAN[month]} {year}"
    elif mode == "cancel_jadwal":
        title = f"📋 *Rencana batal jadwal* — {NAMA_BULAN[month]} {year}"
    elif mode in ("leave", "cancel_cuti"):
        title = f"📋 *Rencana cuti* — {NAMA_BULAN[month]} {year}"
    else:
        title = f"📋 *Rencana isi jadwal* — {NAMA_BULAN[month]} {year}"
    lines = [title, ""]
    if mode == "replace":
        lines.append("⚠️ Jadwal lama di bulan ini akan diganti.")
        lines.append("")
    for date_str in plan.get("available_new", []):
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        lines.append(f"✅ Akan diset: {dt.day} {NAMA_BULAN[dt.month]} {dt.year} ({['Senin','Selasa','Rabu','Kamis','Jumat','Sabtu','Minggu'][dt.weekday()]})")
    for date_str in plan.get("skipped", []):
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        lines.append(f"ℹ️ Sudah ada, tetap: {dt.day} {NAMA_BULAN[dt.month]} {dt.year}")
    for date_str in plan.get("unavailable", []):
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        lines.append(f"❌ Penuh, tidak bisa: {dt.day} {NAMA_BULAN[dt.month]} {dt.year}")
    lines.append("")
    if plan.get("available_new"):
        lines.append("Lanjutkan penyimpanan?")
    else:
        lines.append("Tidak ada tanggal baru untuk disimpan.")
    return "\n".join(lines)
