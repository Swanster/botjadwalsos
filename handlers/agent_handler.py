"""Handler Telegram untuk konfirmasi pengisian jadwal via agen ringan."""
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from core import database as db
from core import schedule_agent
from handlers.access import deny_private_callback


def register_agent_handlers(bot: telebot.TeleBot):
    @bot.callback_query_handler(func=lambda call: call.data in ("agent_fill_confirm", "agent_fill_cancel"))
    def handle_agent_fill_callbacks(call):
        if deny_private_callback(bot, call):
            return
        user_id = call.from_user.id
        plan = schedule_agent.get_pending(user_id)
        if not plan:
            bot.answer_callback_query(call.id, "Sesi pengisian sudah berakhir.", show_alert=True)
            return

        if call.data == "agent_fill_cancel":
            schedule_agent.clear_pending(user_id)
            try:
                bot.edit_message_text("❌ Pengisian jadwal dibatalkan.", call.message.chat.id, call.message.message_id)
            except Exception:
                bot.send_message(call.message.chat.id, "❌ Pengisian jadwal dibatalkan.", message_thread_id=call.message.message_thread_id)
            bot.answer_callback_query(call.id)
            return

        # confirm
        year = plan["year"]
        month = plan["month"]
        mode = plan.get("mode", "add")
        available_new = plan.get("available_new") or []
        dates = plan.get("dates") or available_new

        if mode == "cancel_jadwal":
            result = db.delete_user_jadwal_on_dates(user_id, dates)
            schedule_agent.clear_pending(user_id)
            if result.ok:
                text = f"✅ Berhasil membatalkan {result.rows_affected} jadwal."
            else:
                pesan = result.message or "Gagal membatalkan jadwal."
                text = f"❌ {pesan}"
        elif mode == "leave":
            existing = set(plan.get("existing") or [])
            combined = sorted(existing | set(dates))
            db.set_user_absensi(user_id, combined, year, month)
            schedule_agent.clear_pending(user_id)
            text = f"✅ Cuti berhasil disimpan untuk {schedule_agent.NAMA_BULAN[month]} {year}. Total cuti: {len(combined)} hari."
        elif mode == "cancel_cuti":
            existing = set(plan.get("existing") or [])
            remaining = sorted(existing - set(dates))
            db.set_user_absensi(user_id, remaining, year, month)
            schedule_agent.clear_pending(user_id)
            text = f"✅ Berhasil membatalkan {len(dates)} tanggal cuti."
        else:
            if mode == "replace":
                combined = sorted(set(available_new))
            else:
                existing = set(plan.get("existing") or [])
                combined = sorted(existing | set(available_new))
            result = db.update_user_jadwal_for_month(
                user_id,
                plan.get("first_name") or call.from_user.first_name,
                plan.get("username") or call.from_user.username,
                combined,
                year,
                month,
            )
            schedule_agent.clear_pending(user_id)
            if result.ok:
                text = (
                    f"✅ Jadwal berhasil disimpan untuk {schedule_agent.NAMA_BULAN[month]} {year}.\n"
                    f"Total jadwal Anda sekarang: {result.rows_affected} hari."
                )
            else:
                error_messages = {
                    "database_locked": result.message or "Sistem sedang sibuk. Coba lagi.",
                    "date_conflict": "Ada tanggal yang sudah penuh.",
                    "monthly_limit": result.message or "Melebihi batas bulanan.",
                    "invalid_dates": result.message or "Format tanggal tidak valid.",
                    "weekend_limit": result.message or "Melanggar batas weekend.",
                    "weekday_balance": result.message or "Melanggar keseimbangan weekday/weekend.",
                    "delivery_exact_one": result.message or "Infra Delivery harus tepat 1 jadwal.",
                }
                pesan = error_messages.get(result.error_code or "", result.message or "Gagal menyimpan jadwal.")
                text = f"❌ {pesan}"

        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id)
        except Exception:
            bot.send_message(call.message.chat.id, text, message_thread_id=call.message.message_thread_id)
        bot.answer_callback_query(call.id)
        return
