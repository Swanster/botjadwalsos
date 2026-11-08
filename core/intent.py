"""Router niat sederhana untuk bot jadwal SOS."""
from __future__ import annotations


def classify_intent(text: str) -> str:
    q = (text or "").lower().strip()
    if not q:
        return "unknown"

    help_words = ("cara", "bagaimana", "panduan", "guide", "tutorial", "langkah")
    usage_words = ("jadwal", "isi", "tukar", "batal", "cuti", "bot", "program", "pakai", "gunakan", "menu")
    schedule_words = ("jadwal", "sos", "standby", "shift", "piket")

    if any(word in q for word in help_words) and (
        any(word in q for word in usage_words) or "bot" in q or "program" in q
    ):
        return "help"

    if any(word in q for word in ("ganti", "ubah", "replace", "set", "timpa")) and any(
        word in q for word in schedule_words
    ):
        return "replace"

    if any(word in q for word in ("input", "isi", "tambah", "masuk", "masukkan", "daftar", "catat")) and any(
        word in q for word in schedule_words
    ):
        return "fill"

    if any(word in q for word in ("batal", "hapus", "cancel")) and any(
        word in q for word in ("jadwal", "cuti", "sos", "absen")
    ):
        return "cancel"

    if "cuti" in q or "absen" in q or "tidak tersedia" in q:
        return "leave"

    if any(word in q for word in ("tukar", "swap")) and any(word in q for word in schedule_words):
        return "swap"

    if any(word in q for word in ("siapa", "kapan", "besok", "hari ini", "kosong", "belum")) or any(
        word in q for word in schedule_words
    ):
        return "query"

    return "unknown"
