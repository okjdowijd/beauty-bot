import logging
from datetime import datetime, timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import db as database
from config import SERVICE_NAME


async def check_reminders(bot: Bot):
    now = datetime.now()

    # напоминание за 24 часа
    target = now + timedelta(hours=24)
    target_date = target.strftime("%Y-%m-%d")
    target_time = target.strftime("%H:%M")
    bookings_24h = database.get_bookings_needing_reminder("remind_24h_sent", target_date, target_time)
    for b in bookings_24h:
        try:
            await bot.send_message(
                b["client_id"],
                f"🔔 Напоминание: завтра в {b['time']} у тебя запись на «{SERVICE_NAME}». Ждём! 💅"
            )
            database.mark_reminder_sent(b["id"], "remind_24h_sent")
        except Exception as e:
            logging.warning(f"Не удалось отправить напоминание (24ч) id{b['id']}: {e}")

    # напоминание за 2 часа
    target2 = now + timedelta(hours=2)
    target2_date = target2.strftime("%Y-%m-%d")
    target2_time = target2.strftime("%H:%M")
    bookings_2h = database.get_bookings_needing_reminder("remind_2h_sent", target2_date, target2_time)
    for b in bookings_2h:
        try:
            await bot.send_message(
                b["client_id"],
                f"⏰ Напоминание: сегодня в {b['time']} у тебя запись на «{SERVICE_NAME}». До встречи! 💅"
            )
            database.mark_reminder_sent(b["id"], "remind_2h_sent")
        except Exception as e:
            logging.warning(f"Не удалось отправить напоминание (2ч) id{b['id']}: {e}")


def start_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler()
    # проверяем каждую минуту, не пора ли кому-то напомнить
    scheduler.add_job(check_reminders, "interval", minutes=1, args=[bot])
    scheduler.start()
    return scheduler
