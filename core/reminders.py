"""Pengingat proaktif jadwal kosong."""
from __future__ import annotations

import os
from datetime import date

from config import ALLOWED_TOPIC_ID, GROUP_CHAT_ID
from core.database import today_wita
from core.schedule_query import empty_days


_SENT_REMINDER_DAYS: set[date] = set()


def find_empty_dates(days: int = 14) -> list[date]:
    today = today_wita()
    return empty_days(today, days)


def build_empty_schedule_warning() -> str:
    dates = find_empty_dates(14)
    if not dates:
        return ""
    lines = ["🔔 *Peringatan Jadwal Kosong*", "", "Tanggal berikut belum ada yang SOS:"]
    for d in dates[:12]:
        lines.append(f"- {d.strftime('%Y-%m-%d')}")
    if len(dates) > 12:
        lines.append(f"- ...dan {len(dates) - 12} tanggal lainnya")
    return "\n".join(lines)


def schedule_daily_reminder(bot) -> None:
    if os.getenv("REMINDER_ENABLED", "1").lower() in ("0", "false", "no", "off"):
        return
    today = today_wita()
    if today in _SENT_REMINDER_DAYS:
        return
    message = build_empty_schedule_warning()
    if not message:
        _SENT_REMINDER_DAYS.add(today)
        return
    bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=message,
        parse_mode="Markdown",
        message_thread_id=ALLOWED_TOPIC_ID,
    )
    _SENT_REMINDER_DAYS.add(today)
