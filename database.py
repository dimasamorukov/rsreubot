import sqlite3
import os
from datetime import datetime, timedelta

DATA_DIR = "/app/data"
DB_NAME = os.path.join(DATA_DIR, "rsreu_bot.db")
os.makedirs(DATA_DIR, exist_ok=True)


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            university TEXT,
            faculty TEXT,
            group_name TEXT,
            full_name TEXT,
            role TEXT DEFAULT 'student',
            registered_at TEXT DEFAULT CURRENT_TIMESTAMP,
            notifications_enabled INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university TEXT,
            faculty TEXT,
            group_name TEXT,
            day_of_week TEXT,
            week_type TEXT,
            pair_number INTEGER,
            subject TEXT,
            teacher TEXT,
            room TEXT,
            start_time TEXT,
            end_time TEXT,
            file_id TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS homework (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university TEXT,
            faculty TEXT,
            group_name TEXT,
            subject TEXT,
            task TEXT,
            deadline TEXT,
            file_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS homework_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            homework_id INTEGER,
            user_id INTEGER,
            status TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(homework_id, user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS debts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            subject TEXT,
            task TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            schedule_id INTEGER,
            status TEXT,
            date TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, schedule_id, date)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS banned_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            reason TEXT,
            banned_at TEXT DEFAULT CURRENT_TIMESTAMP,
            banned_by INTEGER
        )
    """)

    conn.commit()
    conn.close()


# ============ ПОЛЬЗОВАТЕЛИ ============

def register_user(user_id, university, faculty, group_name, full_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO users (user_id, university, faculty, group_name, full_name)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, university, faculty, group_name, full_name))
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def delete_user_completely(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        conn.close()
        return False
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM attendance WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM homework_status WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM debts WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True


def get_group_users(university, faculty, group_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, full_name FROM users
        WHERE university = ? AND faculty = ? AND group_name = ?
    """, (university, faculty, group_name))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_users_with_notifications(university, faculty, group_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, full_name FROM users
        WHERE university = ? AND faculty = ? AND group_name = ?
          AND (notifications_enabled IS NULL OR notifications_enabled = 1)
    """, (university, faculty, group_name))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_all_groups():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT university, faculty, group_name
        FROM users
        WHERE group_name IS NOT NULL AND group_name != ''
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def update_user_field(user_id, field, value):
    allowed = {"university", "faculty", "group_name", "full_name"}
    if field not in allowed:
        raise ValueError(f"Поле {field} нельзя изменять")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()


def get_starosta(university, faculty, group_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, full_name FROM users
        WHERE university = ? AND faculty = ? AND group_name = ? AND role = 'starosta'
    """, (university, faculty, group_name))
    row = cursor.fetchone()
    conn.close()
    return row


def set_role(user_id, role):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))
    conn.commit()
    conn.close()


def remove_starosta(user_id):
    """
    Снимает роль старосты с пользователя.
    Возвращает (True, full_name, group_name) если снял, (False, None, None) если не староста.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT full_name, group_name, role FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return (False, None, None)
    full_name, group_name, role = row
    if role != 'starosta':
        conn.close()
        return (False, full_name, group_name)
    cursor.execute("UPDATE users SET role = 'student' WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return (True, full_name, group_name)


def get_notifications_enabled(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT notifications_enabled FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row or row[0] is None:
        return True
    return bool(row[0])


def set_notifications_enabled(user_id, enabled):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET notifications_enabled = ? WHERE user_id = ?",
        (1 if enabled else 0, user_id)
    )
    conn.commit()
    conn.close()


# ============ РАСПИСАНИЕ ============

def add_schedule_pair(university, faculty, group_name, day, pair_num, subject,
                      teacher, room, start, end, file_id=None, week_type="числитель"):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO schedule
        (university, faculty, group_name, day_of_week, week_type, pair_number,
         subject, teacher, room, start_time, end_time, file_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (university, faculty, group_name, day, week_type, pair_num,
          subject, teacher, room, start, end, file_id))
    conn.commit()
    conn.close()


def get_schedule(university, faculty, group_name, day, week_type=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if week_type:
        cursor.execute("""
            SELECT id, pair_number, subject, teacher, room, start_time, end_time, file_id
            FROM schedule
            WHERE university = ? AND faculty = ? AND group_name = ?
              AND day_of_week = ? AND week_type = ?
            ORDER BY pair_number
        """, (university, faculty, group_name, day, week_type))
    else:
        cursor.execute("""
            SELECT id, pair_number, subject, teacher, room, start_time, end_time, file_id
            FROM schedule
            WHERE university = ? AND faculty = ? AND group_name = ? AND day_of_week = ?
            ORDER BY pair_number
        """, (university, faculty, group_name, day))
    rows = cursor.fetchall()
    conn.close()
    return rows


def delete_schedule_for_day(university, faculty, group_name, day_of_week):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM schedule
        WHERE university = ? AND faculty = ? AND group_name = ? AND day_of_week = ?
    """, (university, faculty, group_name, day_of_week))
    conn.commit()
    conn.close()


def clear_schedule_for_group(university, faculty, group_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM schedule
        WHERE university = ? AND faculty = ? AND group_name = ?
    """, (university, faculty, group_name))
    conn.commit()
    conn.close()


def get_schedule_pair_by_key(university, faculty, group_name, day, week_type, pair_num):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, pair_number, subject, teacher, room, start_time, end_time, file_id
        FROM schedule
        WHERE university = ? AND faculty = ? AND group_name = ?
          AND day_of_week = ? AND week_type = ? AND pair_number = ?
    """, (university, faculty, group_name, day, week_type, pair_num))
    row = cursor.fetchone()
    conn.close()
    return row


def upsert_schedule_pair(university, faculty, group_name, day, pair_num, subject,
                         teacher, room, start, end, file_id=None, week_type="числитель"):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM schedule
        WHERE university = ? AND faculty = ? AND group_name = ?
          AND day_of_week = ? AND week_type = ? AND pair_number = ?
    """, (university, faculty, group_name, day, week_type, pair_num))
    row = cursor.fetchone()
    if row:
        cursor.execute("""
            UPDATE schedule
            SET subject = ?, teacher = ?, room = ?, start_time = ?, end_time = ?, file_id = ?
            WHERE id = ?
        """, (subject, teacher, room, start, end, file_id, row[0]))
    else:
        cursor.execute("""
            INSERT INTO schedule
            (university, faculty, group_name, day_of_week, week_type, pair_number,
             subject, teacher, room, start_time, end_time, file_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (university, faculty, group_name, day, week_type, pair_num,
              subject, teacher, room, start, end, file_id))
    conn.commit()
    conn.close()


def delete_orphan_schedule_pairs(university, faculty, group_name, valid_keys):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, day_of_week, week_type, pair_number
        FROM schedule
        WHERE university = ? AND faculty = ? AND group_name = ?
    """, (university, faculty, group_name))
    existing = cursor.fetchall()
    deleted = 0
    for row_id, day, wt, num in existing:
        if (day, wt, num) not in valid_keys:
            cursor.execute("DELETE FROM schedule WHERE id = ?", (row_id,))
            deleted += 1
    conn.commit()
    conn.close()
    return deleted


# ============ ДОМАШКА ============

def add_homework(university, faculty, group_name, subject, task, deadline=None, file_id=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO homework (university, faculty, group_name, subject, task, deadline, file_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (university, faculty, group_name, subject, task, deadline, file_id))
    conn.commit()
    hw_id = cursor.lastrowid
    conn.close()
    return hw_id


def get_homework(university, faculty, group_name, limit=10):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, subject, task, deadline, file_id
        FROM homework
        WHERE university = ? AND faculty = ? AND group_name = ?
        ORDER BY id DESC LIMIT ?
    """, (university, faculty, group_name, limit))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_homework_by_id(homework_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, subject, task, deadline, file_id
        FROM homework WHERE id = ?
    """, (homework_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def delete_homework(homework_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM homework WHERE id = ?", (homework_id,))
    cursor.execute("DELETE FROM homework_status WHERE homework_id = ?", (homework_id,))
    conn.commit()
    conn.close()


def delete_expired_homework():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT id, subject, deadline FROM homework
        WHERE deadline IS NOT NULL AND deadline != ''
          AND deadline < ?
    """, (cutoff,))
    expired = cursor.fetchall()
    if expired:
        ids = [row[0] for row in expired]
        placeholders = ",".join("?" * len(ids))
        cursor.execute(f"DELETE FROM homework WHERE id IN ({placeholders})", ids)
        cursor.execute(f"DELETE FROM homework_status WHERE homework_id IN ({placeholders})", ids)
    conn.commit()
    conn.close()
    return expired


def set_homework_status(homework_id, user_id, status):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO homework_status (homework_id, user_id, status, updated_at)
        VALUES (?, ?, ?, ?)
    """, (homework_id, user_id, status, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_homework_status(homework_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT status FROM homework_status
        WHERE homework_id = ? AND user_id = ?
    """, (homework_id, user_id))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


# ============ ЗАДОЛЖЕННОСТИ ============

def add_debt(user_id, subject, task):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO debts (user_id, subject, task) VALUES (?, ?, ?)", (user_id, subject, task))
    conn.commit()
    conn.close()


def get_debts(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, subject, task FROM debts WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def delete_debt(debt_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM debts WHERE id = ?", (debt_id,))
    conn.commit()
    conn.close()


# ============ ПОСЕЩАЕМОСТЬ ============

def set_attendance(user_id, schedule_id, status, date):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO attendance (user_id, schedule_id, status, date, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, schedule_id, status, date, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_attendance_for_day_grouped(university, faculty, group_name, date):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.pair_number, s.subject, s.start_time, u.full_name, a.status
        FROM attendance a
        JOIN users u ON a.user_id = u.user_id
        JOIN schedule s ON a.schedule_id = s.id
        WHERE u.university = ? AND u.faculty = ? AND u.group_name = ? AND a.date = ?
        ORDER BY s.pair_number, u.full_name
    """, (university, faculty, group_name, date))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_attendance_logs_week(university, faculty, group_name, days=7):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT a.date, u.full_name, s.pair_number, s.subject, a.status
        FROM attendance a
        JOIN users u ON a.user_id = u.user_id
        JOIN schedule s ON a.schedule_id = s.id
        WHERE u.university = ? AND u.faculty = ? AND u.group_name = ?
          AND a.date >= ?
        ORDER BY a.date DESC, s.pair_number, u.full_name
    """, (university, faculty, group_name, from_date))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_group_members(university, faculty, group_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, full_name, role
        FROM users
        WHERE university = ? AND faculty = ? AND group_name = ?
        ORDER BY role DESC, full_name
    """, (university, faculty, group_name))
    rows = cursor.fetchall()
    conn.close()
    return rows


# ============ БЛОКИРОВКА ============

def is_user_banned(user_id=None, username=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if user_id:
        cursor.execute("SELECT id FROM banned_users WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            conn.close()
            return True
    if username:
        username_clean = username.lstrip("@").lower()
        cursor.execute("""
            SELECT id FROM banned_users
            WHERE username IS NOT NULL AND LOWER(username) = ?
        """, (username_clean,))
        if cursor.fetchone():
            conn.close()
            return True
    conn.close()
    return False


def ban_user(user_id=None, username=None, reason="", banned_by=0):
    if not user_id and not username:
        raise ValueError("Нужен user_id или username")
    username_clean = username.lstrip("@").lower() if username else None
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO banned_users (user_id, username, reason, banned_by)
        VALUES (?, ?, ?, ?)
    """, (user_id, username_clean, reason, banned_by))
    conn.commit()
    conn.close()


def unban_user(user_id=None, username=None):
    if not user_id and not username:
        raise ValueError("Нужен user_id или username")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if user_id:
        cursor.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
    if username:
        username_clean = username.lstrip("@").lower()
        cursor.execute("DELETE FROM banned_users WHERE LOWER(username) = ?", (username_clean,))
    conn.commit()
    conn.close()


def get_banned_users():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, username, reason, banned_at
        FROM banned_users
        ORDER BY banned_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


# ============ АДМИН: ВСЕ ПОЛЬЗОВАТЕЛИ ============

def get_all_users(limit=None, offset=0):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if limit:
        cursor.execute("""
            SELECT user_id, university, faculty, group_name, full_name, role, registered_at, notifications_enabled
            FROM users
            ORDER BY registered_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
    else:
        cursor.execute("""
            SELECT user_id, university, faculty, group_name, full_name, role, registered_at, notifications_enabled
            FROM users
            ORDER BY registered_at DESC
        """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def count_users():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_user_details(user_id):
    return get_user(user_id)


# ============ РАССЫЛКА ============

def get_all_user_ids():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


def get_group_user_ids(university, faculty, group_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id FROM users
        WHERE university = ? AND faculty = ? AND group_name = ?
    """, (university, faculty, group_name))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_schedule_for_tomorrow_all_groups():
    """
    Возвращает список: (university, faculty, group_name, day_name, pairs)
    pairs = [(id, pair_number, subject, teacher, room, start_time, end_time, file_id), ...]
    Используется для рассылки «Отметь явку на завтра» в 14:00.
    """
    from datetime import datetime as _dt, timedelta as _td
    from config import get_week_type_for_date

    tomorrow = _dt.now() + _td(days=1)
    day_name = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"][tomorrow.weekday()]
    week_type = get_week_type_for_date(tomorrow.date())

    groups = get_all_groups()
    result = []

    for university, faculty, group_name in groups:
        pairs = get_schedule(university, faculty, group_name, day_name, week_type)
        if pairs:
            result.append((university, faculty, group_name, day_name, pairs))

    return result


def get_user_answers_for_pairs(user_id, schedule_ids, date):
    """Возвращает {schedule_id: status} для указанных пар и даты."""
    if not schedule_ids:
        return {}
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    placeholders = ",".join("?" * len(schedule_ids))
    cursor.execute(f"""
        SELECT schedule_id, status FROM attendance
        WHERE user_id = ? AND date = ? AND schedule_id IN ({placeholders})
    """, (user_id, date, *schedule_ids))
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}


def get_pairs_for_user_on_date(user_id, date_offset):
    """
    Возвращает пары для группы пользователя на дату (date_offset дней от сегодня).
    Используется в обработчике callback, чтобы пересобрать клавиатуру.
    """
    from config import get_week_type_for_date

    user = get_user(user_id)
    if not user:
        return []
    university, faculty, group_name = user[1], user[2], user[3]

    target = datetime.now() + timedelta(days=date_offset)
    day_name = ["Понедельник", "Вторник", "Среда", "Четверг",
                "Пятница", "Суббота", "Воскресенье"][target.weekday()]
    week_type = get_week_type_for_date(target.date())

    return get_schedule(university, faculty, group_name, day_name, week_type)