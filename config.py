import os
from dotenv import load_dotenv

load_dotenv()

# Токен бота, который выдаёт @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Твой Telegram ID (админ). Узнать можно у бота @userinfobot
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ==== Настройки услуги и расписания ====
SERVICE_NAME = "Маникюр"          # название услуги — поменяй под себя
SERVICE_DURATION_MIN = 90         # длительность услуги в минутах
SLOT_STEP_MIN = 90                # шаг между слотами (обычно = длительности услуги)

WORK_START_HOUR = 10              # начало рабочего дня
WORK_END_HOUR = 20                # конец рабочего дня (последняя запись начнётся раньше этого времени)

# Дни недели, в которые ты работаешь: 0=Пн, 1=Вт, ... 6=Вс
WORK_DAYS = [0, 1, 2, 3, 4, 5]     # по умолчанию выходной — воскресенье

DAYS_AHEAD_FOR_BOOKING = 14        # на сколько дней вперёд можно записаться

DB_PATH = "beauty_bot.db"
