import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager

from config import DB_PATH, WORK_START_HOUR, WORK_END_HOUR, SLOT_STEP_MIN, WORK_DAYS


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                name TEXT,
                phone TEXT,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                date TEXT,
                time TEXT,
                status TEXT DEFAULT 'active',
                remind_24h_sent INTEGER DEFAULT 0,
                remind_2h_sent INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS days_off (
                date TEXT PRIMARY KEY
            )
        """)


# ---------- Клиенты ----------

def upsert_client(user_id: int, username: str, name: str = None, phone: str = None):
    with get_conn() as conn:
        existing = conn.execute("SELECT * FROM clients WHERE user_id=?", (user_id,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE clients SET username=?, "
                "name=COALESCE(?, name), phone=COALESCE(?, phone) WHERE user_id=?",
                (username, name, phone, user_id)
            )
        else:
            conn.execute(
                "INSERT INTO clients (user_id, username, name, phone, created_at) VALUES (?,?,?,?,?)",
                (user_id, username, name, phone, datetime.now().isoformat())
            )


def get_client(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM clients WHERE user_id=?", (user_id,)).fetchone()


def get_all_clients():
    with get_conn() as conn:
        return conn.execute("""
            SELECT c.*, COUNT(b.id) as visits_count
            FROM clients c
            LEFT JOIN bookings b ON b.client_id = c.user_id AND b.status='active'
            GROUP BY c.user_id
            ORDER BY c.created_at DESC
        """).fetchall()


# ---------- Выходные дни ----------

def add_day_off(date: str):
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO days_off (date) VALUES (?)", (date,))


def remove_day_off(date: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM days_off WHERE date=?", (date,))


def is_day_off(date_obj) -> bool:
    date_str = date_obj.strftime("%Y-%m-%d")
    if date_obj.weekday() not in WORK_DAYS:
        return True
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM days_off WHERE date=?", (date_str,)).fetchone()
        return row is not None


def get_days_off():
    with get_conn() as conn:
        return [r["date"] for r in conn.execute("SELECT date FROM days_off ORDER BY date").fetchall()]


# ---------- Слоты и записи ----------

def generate_day_slots():
    """Все теоретические слоты дня, например ['10:00', '11:30', ...]"""
    slots = []
    start = datetime.strptime(f"{WORK_START_HOUR}:00", "%H:%M")
    end = datetime.strptime(f"{WORK_END_HOUR}:00", "%H:%M")
    current = start
    while current < end:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=SLOT_STEP_MIN)
    return slots


def get_booked_times(date_str: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT time FROM bookings WHERE date=? AND status='active'", (date_str,)
        ).fetchall()
        return {r["time"] for r in rows}


def get_free_slots(date_str: str):
    booked = get_booked_times(date_str)
    all_slots = generate_day_slots()

    # если это сегодняшний день — убираем прошедшее время
    today = datetime.now().strftime("%Y-%m-%d")
    if date_str == today:
        now_time = datetime.now().strftime("%H:%M")
        all_slots = [s for s in all_slots if s > now_time]

    return [s for s in all_slots if s not in booked]


def create_booking(client_id: int, date_str: str, time_str: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO bookings (client_id, date, time, created_at) VALUES (?,?,?,?)",
            (client_id, date_str, time_str, datetime.now().isoformat())
        )
        return cur.lastrowid


def get_client_bookings(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM bookings WHERE client_id=? AND status='active' "
            "AND date >= ? ORDER BY date, time",
            (user_id, datetime.now().strftime("%Y-%m-%d"))
        ).fetchall()


def get_booking(booking_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()


def cancel_booking(booking_id: int, user_id: int = None) -> bool:
    with get_conn() as conn:
        if user_id is not None:
            cur = conn.execute(
                "UPDATE bookings SET status='cancelled' WHERE id=? AND client_id=?",
                (booking_id, user_id)
            )
        else:
            cur = conn.execute(
                "UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,)
            )
        return cur.rowcount > 0


def get_bookings_by_date(date_str: str):
    with get_conn() as conn:
        return conn.execute("""
            SELECT b.*, c.name, c.phone, c.username
            FROM bookings b JOIN clients c ON c.user_id = b.client_id
            WHERE b.date=? AND b.status='active'
            ORDER BY b.time
        """, (date_str,)).fetchall()


def get_bookings_needing_reminder(field: str, target_date: str, target_time: str):
    """field = 'remind_24h_sent' или 'remind_2h_sent'"""
    with get_conn() as conn:
        return conn.execute(f"""
            SELECT b.*, c.name, c.phone
            FROM bookings b JOIN clients c ON c.user_id = b.client_id
            WHERE b.status='active' AND b.{field}=0
            AND b.date=? AND b.time=?
        """, (target_date, target_time)).fetchall()


def mark_reminder_sent(booking_id: int, field: str):
    with get_conn() as conn:
        conn.execute(f"UPDATE bookings SET {field}=1 WHERE id=?", (booking_id,))
