import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery

import db as database
import keyboards as kb
from config import BOT_TOKEN, ADMIN_ID, SERVICE_NAME, SERVICE_DURATION_MIN
from reminders import start_scheduler

logging.basicConfig(level=logging.INFO)

router = Router()

# ---------------- FSM состояния ----------------

class BookingFlow(StatesGroup):
    choosing_date = State()
    choosing_time = State()
    entering_name = State()
    entering_phone = State()
    confirming = State()

class AdminFlow(StatesGroup):
    entering_day_off = State()
    entering_target_date = State()
    entering_broadcast = State()

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# ---------------- Старт и меню ----------------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    database.upsert_client(message.from_user.id, message.from_user.username)
    await message.answer(
        f"Привет! Это бот для записи на «{SERVICE_NAME}» 💅\n\n"
        f"Выбери, что хочешь сделать:",
        reply_markup=kb.main_menu_kb()
    )

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("Админ-панель:", reply_markup=kb.admin_menu_kb())

@router.message(F.text == "⬅️ Обычное меню")
async def back_to_user_menu(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("Обычное меню:", reply_markup=kb.main_menu_kb())

# ---------------- Информация об услуге ----------------

@router.message(F.text == "ℹ️ Услуга и цена")
async def service_info(message: Message):
    await message.answer(
        f"💅 Услуга: {SERVICE_NAME}\n"
        f"⏱ Длительность: {SERVICE_DURATION_MIN} мин\n\n"
        f"Отредактируй этот текст (и цену) в файле main.py, функция service_info."
    )

# ---------------- Запись: выбор даты ----------------

@router.message(F.text == "📅 Записаться")
async def start_booking(message: Message, state: FSMContext):
    await state.set_state(BookingFlow.choosing_date)
    await message.answer(
        "Выбери удобную дату:",
        reply_markup=kb.dates_kb(prefix="date")
    )

@router.callback_query(F.data == "back_to_dates")
async def back_to_dates(call: CallbackQuery, state: FSMContext):
    await state.set_state(BookingFlow.choosing_date)
    await call.message.edit_text("Выбери удобную дату:", reply_markup=kb.dates_kb(prefix="date"))
    await call.answer()

@router.callback_query(BookingFlow.choosing_date, F.data.startswith("date:"))
async def choose_date(call: CallbackQuery, state: FSMContext):
    date_str = call.data.split(":", 1)[1]
    free_slots = database.get_free_slots(date_str)
    if not free_slots:
        await call.answer("На эту дату свободных слотов нет, выбери другую 🙏", show_alert=True)
        return
    await state.update_data(date=date_str)
    await state.set_state(BookingFlow.choosing_time)
    await call.message.edit_text(
        f"Дата: {date_str}\nВыбери время:",
        reply_markup=kb.times_kb(date_str)
    )
    await call.answer()

@router.callback_query(BookingFlow.choosing_time, F.data.startswith("time:"))
async def choose_time(call: CallbackQuery, state: FSMContext):
    _, date_str, time_str = call.data.split(":")
    await state.update_data(time=time_str)

    client = database.get_client(call.from_user.id)
    if client and client["name"] and client["phone"]:
        await state.update_data(name=client["name"], phone=client["phone"])
        await state.set_state(BookingFlow.confirming)
        await call.message.edit_text(
            f"Проверь данные записи:\n\n"
            f"📅 Дата: {date_str}\n"
            f"⏰ Время: {time_str}\n"
            f"👤 Имя: {client['name']}\n"
            f"📞 Телефон: {client['phone']}\n\n"
            f"Всё верно?",
            reply_markup=kb.confirm_kb()
        )
    else:
        await state.set_state(BookingFlow.entering_name)
        await call.message.edit_text(f"Дата: {date_str}, время: {time_str}.\n\nКак тебя зовут?")
    await call.answer()

@router.message(BookingFlow.entering_name)
async def enter_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(BookingFlow.entering_phone)
    await message.answer("Оставь номер телефона для связи (например, +7XXXXXXXXXX):")

@router.message(BookingFlow.entering_phone)
async def enter_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    data = await state.get_data()
    await state.set_state(BookingFlow.confirming)
    await message.answer(
        f"Проверь данные записи:\n\n"
        f"📅 Дата: {data['date']}\n"
        f"⏰ Время: {data['time']}\n"
        f"👤 Имя: {data['name']}\n"
        f"📞 Телефон: {data['phone']}\n\n"
        f"Всё верно?",
        reply_markup=kb.confirm_kb()
    )

@router.callback_query(BookingFlow.confirming, F.data == "confirm_booking")
async def confirm_booking(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()

    free_slots = database.get_free_slots(data["date"])
    if data["time"] not in free_slots:
        await call.message.edit_text("Ой, это время только что заняли 😔 Выбери другое.")
        await state.set_state(BookingFlow.choosing_date)
        await call.message.answer("Выбери дату:", reply_markup=kb.dates_kb())
        await call.answer()
        return

    database.upsert_client(call.from_user.id, call.from_user.username, data["name"], data["phone"])
    booking_id = database.create_booking(call.from_user.id, data["date"], data["time"])

    await call.message.edit_text(
        f"✅ Готово! Ты записан(а) на {data['date']} в {data['time']}.\n"
        f"Напомню о визите заранее 🙌"
    )
    await state.clear()
    await call.answer()

    if ADMIN_ID:
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🔔 Новая запись #{booking_id}\n"
                f"👤 {data['name']} ({data['phone']})\n"
                f"📅 {data['date']} ⏰ {data['time']}"
            )
        except Exception as e:
            logging.warning(f"Не смог уведомить админа: {e}")

@router.callback_query(F.data == "cancel_flow")
async def cancel_flow(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Запись отменена. Возвращайся, когда будешь готов(а) 🙂")
    await call.answer()

# ---------------- Мои записи ----------------

@router.message(F.text == "🗓 Мои записи")
async def my_bookings(message: Message):
    bookings = database.get_client_bookings(message.from_user.id)
    if not bookings:
        await message.answer("У тебя пока нет активных записей.")
        return
    await message.answer("Твои записи:", reply_markup=kb.my_bookings_kb(bookings))

@router.callback_query(F.data.startswith("cancel_my:"))
async def cancel_my_booking(call: CallbackQuery, bot: Bot):
    booking_id = int(call.data.split(":")[1])
    booking = database.get_booking(booking_id)
    ok = database.cancel_booking(booking_id, user_id=call.from_user.id)
    if ok:
        await call.message.edit_text("Запись отменена.")
        if ADMIN_ID and booking:
            await bot.send_message(
                ADMIN_ID,
                f"❌ Клиент отменил запись #{booking_id} ({booking['date']} {booking['time']})"
            )
    else:
        await call.answer("Не удалось отменить запись", show_alert=True)
    await call.answer()

# ================= АДМИН-ФУНКЦИИ =================

@router.message(F.text == "📋 Записи на сегодня")
async def admin_today(message: Message):
    if not is_admin(message.from_user.id):
        return
    today = datetime.now().strftime("%Y-%m-%d")
    await send_bookings_for_date(message, today)

@router.message(F.text == "🔎 Записи на дату")
async def admin_ask_date(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminFlow.entering_target_date)
    await message.answer("Введи дату в формате ГГГГ-ММ-ДД (например, 2026-08-01):")

@router.message(AdminFlow.entering_target_date)
async def admin_show_date(message: Message, state: FSMContext):
    await state.clear()
    date_str = message.text.strip()
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await message.answer("Неверный формат. Пример: 2026-08-01")
        return
    await send_bookings_for_date(message, date_str)

async def send_bookings_for_date(message: Message, date_str: str):
    bookings = database.get_bookings_by_date(date_str)
    if not bookings:
        await message.answer(f"На {date_str} записей нет.")
        return
    text = f"Записи на {date_str}:\n\n"
    for b in bookings:
        uname = f"@{b['username']}" if b["username"] else "—"
        text += f"⏰ {b['time']} — {b['name']} ({b['phone']}, {uname}) [id{b['id']}]\n"
    await message.answer(text)

@router.message(F.text == "👥 Клиенты")
async def admin_clients(message: Message):
    if not is_admin(message.from_user.id):
        return
    clients = database.get_all_clients()
    if not clients:
        await message.answer("Клиентов пока нет.")
        return
    text = "База клиентов:\n\n"
    for c in clients:
        uname = f"@{c['username']}" if c["username"] else "—"
        name = c["name"] or "без имени"
        phone = c["phone"] or "—"
        text += f"👤 {name}, {phone}, {uname} — визитов: {c['visits_count']}\n"
    for chunk_start in range(0, len(text), 3500):
        await message.answer(text[chunk_start:chunk_start + 3500])

@router.message(F.text == "🚫 Отметить выходной")
async def admin_ask_day_off(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    days_off = database.get_days_off()
    current = ", ".join(days_off) if days_off else "нет"
    await state.set_state(AdminFlow.entering_day_off)
    await message.answer(
        f"Текущие выходные дни: {current}\n\n"
        f"Введи дату ГГГГ-ММ-ДД, чтобы добавить/убрать её из выходных "
        f"(если дата уже выходная — она будет снята):"
    )

@router.message(AdminFlow.entering_day_off)
async def admin_toggle_day_off(message: Message, state: FSMContext):
    await state.clear()
    date_str = message.text.strip()
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await message.answer("Неверный формат. Пример: 2026-08-01")
        return
    if date_str in database.get_days_off():
        database.remove_day_off(date_str)
        await message.answer(f"{date_str} снова рабочий день.")
    else:
        database.add_day_off(date_str)
        await message.answer(f"{date_str} отмечен как выходной.")

@router.message(F.text == "📢 Рассылка")
async def admin_ask_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminFlow.entering_broadcast)
    await message.answer("Напиши текст, который разослать всем клиентам:")

@router.message(AdminFlow.entering_broadcast)
async def admin_do_broadcast(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    clients = database.get_all_clients()
    sent, failed = 0, 0
    for c in clients:
        try:
            await bot.send_message(c["user_id"], message.text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await message.answer(f"Рассылка завершена. Доставлено: {sent}, ошибок: {failed}.")

# ---------------- Запуск ----------------

async def main():
    database.init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    start_scheduler(bot)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())