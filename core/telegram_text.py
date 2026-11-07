# core/telegram_text.py
"""Utilitas teks untuk pesan Telegram ber-parse_mode='Markdown' (legacy)."""

# Backslash harus pertama: kalau tidak, escape berikutnya jadi ikut ter-escape dobel.
_MARKDOWN_ESCAPES = ('\\', '_', '*', '`', '[', ']')


def escape_markdown(value):
    """Escape teks dari pengguna supaya tidak memicu format/link Markdown.

    Nama Telegram bisa diubah anggota jadi `[Promo](https://situs-jahat)`, dan bot
    mem-post nama itu ke grup. Tanpa escape, tautan itu tampil sebagai link aktif
    yang dikirim oleh bot sendiri.
    """
    text = '' if value is None else str(value)
    for char in _MARKDOWN_ESCAPES:
        text = text.replace(char, '\\' + char)
    return text
