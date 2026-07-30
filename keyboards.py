from datetime import datetime, timedelta
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from config import DAYS_AHEAD_FOR_BOOKING
import db as database

WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS_RU = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


def main_menu_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📅 Записаться"))
    builder.row(KeyboardButton(text="🗓 Мои записи"), KeyboardButton(text="ℹ️ Услуга и цена"))
    return builder.as_markup(resize_keyboard=True)


def admin_menu_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📋 Записи на сегодня"))
    builder.row(KeyboardButton(text="🔎 Записи на дату"))
    builder.row(KeyboardButton(text="👥 Клиенты"))
    builder.row(KeyboardButton(text="🚫 Отметить выходной"))
    builder.row(KeyboardButton(text="📢 Рассылка"))
    builder.row(KeyboardButton(text="⬅️ Обычное меню"))
    return builder.as_markup(resize_keyboard=True)


def dates_kb(prefix="date") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    today = datetime.now()
    for i in range(DAYS_AHEAD_FOR_BOOKING):
        d = today + timedelta(days=i)
        if database.is_day_off(d):
            continue
        date_str = d.strftime("%Y-%m-%d")
        label = f"{WEEKDAYS_RU[d.weekday()]} {d.day} {MONTHS_RU[d.month-1]}"
        builder.button(text=label, callback_data=f"{prefix}:{date_str}")
    builder.adjust(2)
    return builder.as_markup()


def times_kb(date_str: str, prefix="time") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    free_slots = database.get_free_slots(date_str)
    for t in free_slots:
        builder.button(text=t, callback_data=f"{prefix}:{date_str}:{t}")
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="⬅️ Назад к датам", callback_data="back_to_dates"))
    return builder.as_markup()


def confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="confirm_booking")
    builder.button(text="❌ Отмена", callback_data="cancel_flow")
    builder.adjust(2)
    return builder.as_markup()


def my_bookings_kb(bookings) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for b in bookings:
        builder.button(
            text=f"❌ Отменить {b['date']} {b['time']}",
            callback_data=f"cancel_my:{b['id']}"
        )
    builder.adjust(1)
    return builder.as_markup()
