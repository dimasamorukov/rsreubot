import sqlite3
import os
import shutil
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")

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
            notifications_enabled INTEGER DEFAULT 1,
            notify_pairs INTEGER DEFAULT 1,
            notify_attendance INTEGER DEFAULT 1,
            username TEXT,
            subgroup INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT NULL
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
            file_id TEXT,
            lesson_type TEXT,
            subgroup INTEGER DEFAULT 0,
            valid_until TEXT,
            lesson_type_full TEXT
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS starosta_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            fio TEXT,
            university TEXT,
            faculty TEXT,
            group_name TEXT,
            photo_group_id TEXT,
            photo_dean_id TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ============ НОВЫЕ ТАБЛИЦЫ ============

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_xp (
            user_id INTEGER PRIMARY KEY,
            xp REAL DEFAULT 0,
            level INTEGER DEFAULT 1,
            streak INTEGER DEFAULT 0,
            last_attendance_date TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            reward_xp INTEGER DEFAULT 5,
            uses_left INTEGER DEFAULT 10,
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS promo_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            user_id INTEGER,
            used_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(code, user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS games_stats (
            user_id INTEGER PRIMARY KEY,
            hangman_wins INTEGER DEFAULT 0,
            hangman_games INTEGER DEFAULT 0,
            bulls_wins INTEGER DEFAULT 0,
            bulls_games INTEGER DEFAULT 0,
            tictactoe_wins INTEGER DEFAULT 0,
            tictactoe_games INTEGER DEFAULT 0,
            mines_wins INTEGER DEFAULT 0,
            mines_games INTEGER DEFAULT 0
        )
    """)

    # миграции
    migrations = [
        "ALTER TABLE users ADD COLUMN notify_pairs INTEGER DEFAULT 1",
        "ALTER TABLE users ADD COLUMN notify_attendance INTEGER DEFAULT 1",
        "ALTER TABLE users ADD COLUMN username TEXT",
        "ALTER TABLE users ADD COLUMN subgroup INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN referred_by INTEGER DEFAULT NULL",
        "ALTER TABLE schedule ADD COLUMN lesson_type TEXT",
        "ALTER TABLE schedule ADD COLUMN subgroup INTEGER DEFAULT 0",
        "ALTER TABLE schedule ADD COLUMN valid_until TEXT",
        "ALTER TABLE schedule ADD COLUMN lesson_type_full TEXT",
    ]
    for m in migrations:
        try:
            cursor.execute(m)
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()


# ============ ПОЛЬЗОВАТЕЛИ ============

def register_user(user_id, university, faculty, group_name, full_name,
                  username=None, referred_by=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO users
        (user_id, university, faculty, group_name, full_name, username, referred_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, university, faculty, group_name, full_name, username, referred_by))
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, university, faculty, group_name, full_name, role,
               registered_at, notifications_enabled, notify_pairs,
               notify_attendance, username, subgroup
        FROM users WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def get_user_details(user_id):
    return get_user(user_id)


def get_user_subgroup(user_id):
    user = get_user(user_id)
    if not user or len(user) < 12:
        return 0
    return user[11] or 0


def set_user_subgroup(user_id, subgroup):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET subgroup = ? WHERE user_id = ?", (subgroup, user_id))
    conn.commit()
    conn.close()


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
    cursor.execute("DELETE FROM starosta_applications WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM user_xp WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM games_stats WHERE user_id = ?", (user_id,))
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


def get_users_for_pair_notifications(university, faculty, group_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, full_name FROM users
        WHERE university = ? AND faculty = ? AND group_name = ?
          AND (notify_pairs IS NULL OR notify_pairs = 1)
    """, (university, faculty, group_name))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_users_for_attendance_broadcast(university, faculty, group_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, full_name FROM users
        WHERE university = ? AND faculty = ? AND group_name = ?
          AND (notify_attendance IS NULL OR notify_attendance = 1)
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


def get_all_unique_groups():
    return get_all_groups()


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


def get_notify_pairs(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT notify_pairs FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row or row[0] is None:
        return True
    return bool(row[0])


def set_notify_pairs(user_id, enabled):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET notify_pairs = ? WHERE user_id = ?",
                   (1 if enabled else 0, user_id))
    conn.commit()
    conn.close()


def get_notify_attendance(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT notify_attendance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row or row[0] is None:
        return True
    return bool(row[0])


def set_notify_attendance(user_id, enabled):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET notify_attendance = ? WHERE user_id = ?",
                   (1 if enabled else 0, user_id))
    conn.commit()
    conn.close()


def update_username(user_id, username):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    conn.commit()
    conn.close()


def get_user_by_username(username):
    if not username:
        return None
    username_clean = username.lstrip("@").lower()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, university, faculty, group_name, full_name, role,
               registered_at, notifications_enabled, notify_pairs,
               notify_attendance, username, subgroup
        FROM users
        WHERE username IS NOT NULL AND LOWER(username) = ?
    """, (username_clean,))
    row = cursor.fetchone()
    conn.close()
    return row


# ============ РАСПИСАНИЕ ============

def add_schedule_pair(university, faculty, group_name, day, pair_num, subject,
                      teacher, room, start, end, file_id=None, week_type="числитель",
                      lesson_type=None, subgroup=0, valid_until=None,
                      lesson_type_full=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO schedule
        (university, faculty, group_name, day_of_week, week_type, pair_number,
         subject, teacher, room, start_time, end_time, file_id, lesson_type,
         subgroup, valid_until, lesson_type_full)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (university, faculty, group_name, day, week_type, pair_num,
          subject, teacher, room, start, end, file_id, lesson_type,
          subgroup, valid_until, lesson_type_full))
    conn.commit()
    conn.close()


def get_schedule(university, faculty, group_name, day, week_type=None,
                 subgroup=None, check_date=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    sql = """
        SELECT id, pair_number, subject, teacher, room, start_time, end_time,
               file_id, lesson_type, subgroup, valid_until, lesson_type_full
        FROM schedule
        WHERE university = ? AND faculty = ? AND group_name = ?
          AND day_of_week = ?
    """
    params = [university, faculty, group_name, day]

    if week_type:
        sql += " AND week_type = ?"
        params.append(week_type)

    if subgroup is not None:
        sql += " AND (subgroup = ? OR subgroup = 0)"
        params.append(subgroup)

    if check_date:
        sql += " AND (valid_until IS NULL OR valid_until = '' OR valid_until >= ?)"
        params.append(check_date)

    sql += " ORDER BY pair_number, subgroup"

    cursor.execute(sql, params)
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


def get_schedule_pair_by_key(university, faculty, group_name, day, week_type,
                             pair_num, subgroup=0):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, pair_number, subject, teacher, room, start_time, end_time, file_id
        FROM schedule
        WHERE university = ? AND faculty = ? AND group_name = ?
          AND day_of_week = ? AND week_type = ? AND pair_number = ?
          AND subgroup = ?
    """, (university, faculty, group_name, day, week_type, pair_num, subgroup))
    row = cursor.fetchone()
    conn.close()
    return row


def upsert_schedule_pair(university, faculty, group_name, day, pair_num, subject,
                         teacher, room, start, end, file_id=None, week_type="числитель",
                         lesson_type=None, subgroup=0, valid_until=None,
                         lesson_type_full=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM schedule
        WHERE university = ? AND faculty = ? AND group_name = ?
          AND day_of_week = ? AND week_type = ? AND pair_number = ?
          AND subgroup = ?
    """, (university, faculty, group_name, day, week_type, pair_num, subgroup))
    row = cursor.fetchone()
    if row:
        cursor.execute("""
            UPDATE schedule
            SET subject = ?, teacher = ?, room = ?, start_time = ?, end_time = ?,
                file_id = ?, lesson_type = ?, valid_until = ?, lesson_type_full = ?
            WHERE id = ?
        """, (subject, teacher, room, start, end, file_id, lesson_type,
              valid_until, lesson_type_full, row[0]))
    else:
        cursor.execute("""
            INSERT INTO schedule
            (university, faculty, group_name, day_of_week, week_type, pair_number,
             subject, teacher, room, start_time, end_time, file_id, lesson_type,
             subgroup, valid_until, lesson_type_full)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (university, faculty, group_name, day, week_type, pair_num,
              subject, teacher, room, start, end, file_id, lesson_type,
              subgroup, valid_until, lesson_type_full))
    conn.commit()
    conn.close()


def delete_orphan_schedule_pairs(university, faculty, group_name, valid_keys):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, day_of_week, week_type, pair_number, subgroup
        FROM schedule
        WHERE university = ? AND faculty = ? AND group_name = ?
    """, (university, faculty, group_name))
    existing = cursor.fetchall()
    deleted = 0
    if not valid_keys:
        conn.close()
        return 0
    first_key = next(iter(valid_keys))
    for row_id, day, wt, num, sg in existing:
        key = (day, wt, num, sg or 0)
        if len(first_key) == 3:
            if (day, wt, num) not in valid_keys:
                cursor.execute("DELETE FROM schedule WHERE id = ?", (row_id,))
                deleted += 1
        else:
            if key not in valid_keys:
                cursor.execute("DELETE FROM schedule WHERE id = ?", (row_id,))
                deleted += 1
    conn.commit()
    conn.close()
    return deleted


def delete_expired_schedule_pairs():
    today_iso = datetime.now(MSK).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM schedule
        WHERE valid_until IS NOT NULL AND valid_until != ''
          AND valid_until < ?
    """, (today_iso,))
    deleted = cursor.rowcount
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
    cutoff = (datetime.now(MSK) - timedelta(days=2)).strftime("%Y-%m-%d")
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
    """, (homework_id, user_id, status, datetime.now(MSK).isoformat()))
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


# ============ ПОСЕЩАЕМОСТЬ + XP ============

def set_attendance(user_id, schedule_id, status, date):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT university, faculty, group_name, subgroup
        FROM schedule WHERE id = ?
    """, (schedule_id,))
    sched = cursor.fetchone()

    cursor.execute("""
        SELECT university, faculty, group_name, subgroup
        FROM users WHERE user_id = ?
    """, (user_id,))
    usr = cursor.fetchone()

    if not sched or not usr:
        conn.close()
        return False

    s_uni, s_fac, s_grp, s_sub = sched
    u_uni, u_fac, u_grp, u_sub = usr

    if (s_uni, s_fac, s_grp) != (u_uni, u_fac, u_grp):
        conn.close()
        return False

    if s_sub not in (0, u_sub or 0):
        conn.close()
        return False

    cursor.execute("""
        INSERT OR REPLACE INTO attendance (user_id, schedule_id, status, date, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, schedule_id, status, date, datetime.now(MSK).isoformat()))
    conn.commit()
    conn.close()

    # ← начисляем XP
    _update_xp_for_attendance(user_id, status)

    return True


def _update_xp_for_attendance(user_id, status):
    """Пересчитывает XP по последнему статусу отметки."""
    from config import XP_RULES

    xp_delta = XP_RULES.get(status, 0.0)
    if xp_delta <= 0:
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT xp FROM user_xp WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("""
            INSERT INTO user_xp (user_id, xp, level, streak, last_attendance_date)
            VALUES (?, ?, 1, 1, ?)
        """, (user_id, xp_delta, datetime.now(MSK).strftime("%Y-%m-%d")))
    else:
        new_xp = row[0] + xp_delta
        new_level = 1 + int(new_xp // 10)
        cursor.execute("""
            UPDATE user_xp SET xp = ?, level = ? WHERE user_id = ?
        """, (new_xp, new_level, user_id))

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
        WHERE u.university = ? AND u.faculty = ? AND u.group_name = ?
          AND s.university = ? AND s.faculty = ? AND s.group_name = ?
          AND a.date = ?
        ORDER BY s.pair_number, u.full_name
    """, (
        university, faculty, group_name,
        university, faculty, group_name,
        date,
    ))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_attendance_logs_week(university, faculty, group_name, days=7):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    from_date = (datetime.now(MSK) - timedelta(days=days)).strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT a.date, u.full_name, s.pair_number, s.subject, a.status
        FROM attendance a
        JOIN users u ON a.user_id = u.user_id
        JOIN schedule s ON a.schedule_id = s.id
        WHERE u.university = ? AND u.faculty = ? AND u.group_name = ?
          AND s.university = ? AND s.faculty = ? AND s.group_name = ?
          AND a.date >= ?
        ORDER BY a.date DESC, s.pair_number, u.full_name
    """, (
        university, faculty, group_name,
        university, faculty, group_name,
        from_date,
    ))
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


# ============ АДМИН ============

def get_all_users(limit=None, offset=0):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    base = """
        SELECT user_id, university, faculty, group_name, full_name, role,
               registered_at, notifications_enabled, notify_pairs,
               notify_attendance, username
        FROM users
        ORDER BY registered_at DESC
    """
    if limit:
        cursor.execute(base + " LIMIT ? OFFSET ?", (limit, offset))
    else:
        cursor.execute(base)
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
    from config import get_week_type_for_date

    tomorrow = datetime.now(MSK) + timedelta(days=1)
    day_name = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"][tomorrow.weekday()]
    tomorrow_iso = tomorrow.strftime("%Y-%m-%d")
    week_type = get_week_type_for_date(tomorrow.date())

    groups = get_all_groups()
    result = []

    for university, faculty, group_name in groups:
        pairs = get_schedule(university, faculty, group_name, day_name, week_type,
                             check_date=tomorrow_iso)
        if pairs:
            result.append((university, faculty, group_name, day_name, pairs))

    return result


def get_user_answers_for_pairs(user_id, schedule_ids, date):
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
    from config import get_week_type_for_date

    user = get_user(user_id)
    if not user:
        return []

    university, faculty, group_name = user[1], user[2], user[3]
    subgroup = user[11] if len(user) > 11 else 0

    target = datetime.now(MSK) + timedelta(days=date_offset)
    day_name = ["Понедельник", "Вторник", "Среда", "Четверг",
                "Пятница", "Суббота", "Воскресенье"][target.weekday()]
    week_type = get_week_type_for_date(target.date(), university)
    target_iso = target.strftime("%Y-%m-%d")

    return get_schedule(university, faculty, group_name, day_name, week_type,
                        subgroup=subgroup, check_date=target_iso)


def get_pairs_for_delete(university, faculty, group_name, day_of_week):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, pair_number, subject, week_type, subgroup,
               start_time, teacher, room
        FROM schedule
        WHERE university = ? AND faculty = ? AND group_name = ?
          AND day_of_week = ?
        ORDER BY pair_number, week_type, subgroup
    """, (university, faculty, group_name, day_of_week))
    rows = cursor.fetchall()
    conn.close()
    return rows


def delete_schedule_pair_by_id(schedule_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM schedule WHERE id = ?", (schedule_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted > 0


def get_schedule_pair_info(schedule_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT university, faculty, group_name, day_of_week, pair_number,
               subject, week_type, subgroup, start_time, teacher, room
        FROM schedule WHERE id = ?
    """, (schedule_id,))
    row = cursor.fetchone()
    conn.close()
    return row


# ============ ПОДГРУППЫ (РГУ) ============

def get_users_for_attendance_broadcast_with_subgroup(university, faculty, group_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, full_name, subgroup
        FROM users
        WHERE university = ? AND faculty = ? AND group_name = ?
          AND (notify_attendance IS NULL OR notify_attendance = 1)
    """, (university, faculty, group_name))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_users_for_pair_notifications_with_subgroup(university, faculty, group_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, full_name, subgroup
        FROM users
        WHERE university = ? AND faculty = ? AND group_name = ?
          AND (notify_pairs IS NULL OR notify_pairs = 1)
    """, (university, faculty, group_name))
    rows = cursor.fetchall()
    conn.close()
    return rows


# ============ СВОБОДНЫЕ АУДИТОРИИ (РГРТУ) ============

def get_all_rooms_for_university(university="РГРТУ"):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT room
        FROM schedule
        WHERE university = ?
          AND room IS NOT NULL AND room != ''
    """, (university,))
    rows = cursor.fetchall()
    conn.close()

    rooms = set()
    for (room,) in rows:
        if room:
            rooms.add(room.strip())
    return rooms


def get_occupied_rooms(university, day_name, week_type, pair_number, date_iso):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT room
        FROM schedule
        WHERE university = ?
          AND day_of_week = ?
          AND week_type = ?
          AND pair_number = ?
          AND (valid_until IS NULL OR valid_until = '' OR valid_until >= ?)
          AND room IS NOT NULL AND room != ''
    """, (university, day_name, week_type, pair_number, date_iso))
    rows = cursor.fetchall()
    conn.close()

    occupied = set()
    for (room,) in rows:
        if room:
            occupied.add(room.strip())
    return occupied


# ============ ЗАЯВКИ НА СТАРОСТУ ============

def add_starosta_application(user_id, username, fio, university, faculty,
                             group_name, photo_group_id, photo_dean_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO starosta_applications
        (user_id, username, fio, university, faculty, group_name,
         photo_group_id, photo_dean_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
    """, (user_id, username, fio, university, faculty, group_name,
          photo_group_id, photo_dean_id))
    conn.commit()
    app_id = cursor.lastrowid
    conn.close()
    return app_id


def has_pending_application(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM starosta_applications
        WHERE user_id = ? AND status = 'pending'
        ORDER BY id DESC LIMIT 1
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_pending_applications():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, username, fio, university, faculty,
               group_name, photo_group_id, photo_dean_id, created_at
        FROM starosta_applications
        WHERE status = 'pending'
        ORDER BY id ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_application_by_id(app_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, username, fio, university, faculty,
               group_name, photo_group_id, photo_dean_id, status, created_at
        FROM starosta_applications
        WHERE id = ?
    """, (app_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def approve_application(app_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, fio, university, faculty, group_name, status
        FROM starosta_applications WHERE id = ?
    """, (app_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    user_id, fio, university, faculty, group_name, status = row
    if status != 'pending':
        conn.close()
        return None

    cursor.execute("""
        UPDATE users SET role = 'student'
        WHERE university = ? AND faculty = ? AND group_name = ?
          AND role = 'starosta' AND user_id != ?
    """, (university, faculty, group_name, user_id))

    cursor.execute("UPDATE users SET role = 'starosta' WHERE user_id = ?", (user_id,))

    cursor.execute("UPDATE starosta_applications SET status = 'approved' WHERE id = ?", (app_id,))

    conn.commit()
    conn.close()
    return (user_id, fio, university, faculty, group_name)


def reject_application(app_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, fio FROM starosta_applications WHERE id = ? AND status = 'pending'
    """, (app_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    cursor.execute("UPDATE starosta_applications SET status = 'rejected' WHERE id = ?", (app_id,))
    conn.commit()
    conn.close()
    return row


def get_all_starostas():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.user_id, a.username, a.fio,
               a.university, a.faculty, a.group_name, a.created_at
        FROM starosta_applications a
        WHERE a.status = 'approved'
        ORDER BY a.university, a.faculty, a.group_name
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


# ============ XP / РЕЙТИНГ ============

def get_user_xp(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT xp, level, streak FROM user_xp WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return (0.0, 1, 0)
    return row


def get_group_rating(university, faculty, group_name, limit=10):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.user_id, u.full_name, COALESCE(x.xp, 0), COALESCE(x.level, 1)
        FROM users u
        LEFT JOIN user_xp x ON u.user_id = x.user_id
        WHERE u.university = ? AND u.faculty = ? AND u.group_name = ?
        ORDER BY COALESCE(x.xp, 0) DESC
        LIMIT ?
    """, (university, faculty, group_name, limit))
    rows = cursor.fetchall()
    conn.close()
    return rows


def reset_user_xp(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE user_xp SET xp = 0, level = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def reset_group_xp(university, faculty, group_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE user_xp SET xp = 0, level = 1
        WHERE user_id IN (
            SELECT user_id FROM users
            WHERE university = ? AND faculty = ? AND group_name = ?
        )
    """, (university, faculty, group_name))
    conn.commit()
    conn.close()


# ============ ПРОМОКОДЫ ============

def create_promo_code(code, reward_xp=5, uses=10, created_by=0):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO promo_codes (code, reward_xp, uses_left, created_by)
            VALUES (?, ?, ?, ?)
        """, (code.upper(), reward_xp, uses, created_by))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def use_promo_code(user_id, code):
    code = code.upper().strip()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT reward_xp, uses_left FROM promo_codes WHERE code = ?", (code,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return ("not_found", None)

    reward_xp, uses_left = row
    if uses_left <= 0:
        conn.close()
        return ("expired", None)

    cursor.execute("SELECT id FROM promo_uses WHERE code = ? AND user_id = ?", (code, user_id))
    if cursor.fetchone():
        conn.close()
        return ("already_used", None)

    cursor.execute("INSERT INTO promo_uses (code, user_id) VALUES (?, ?)", (code, user_id))
    cursor.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code = ?", (code,))

    cursor.execute("SELECT xp FROM user_xp WHERE user_id = ?", (user_id,))
    xp_row = cursor.fetchone()
    if xp_row:
        new_xp = xp_row[0] + reward_xp
        new_level = 1 + int(new_xp // 10)
        cursor.execute("UPDATE user_xp SET xp = ?, level = ? WHERE user_id = ?",
                       (new_xp, new_level, user_id))
    else:
        cursor.execute("""
            INSERT INTO user_xp (user_id, xp, level) VALUES (?, ?, 1)
        """, (user_id, reward_xp))

    conn.commit()
    conn.close()
    return ("ok", reward_xp)


def get_all_promo_codes():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT code, reward_xp, uses_left, created_at FROM promo_codes
        ORDER BY created_at DESC LIMIT 50
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def delete_promo_code(code):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM promo_codes WHERE code = ?", (code.upper(),))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted > 0


# ============ РЕФЕРАЛЫ ============

def add_referral(referrer_id, referred_id):
    if referrer_id == referred_id:
        return False
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO referrals (referrer_id, referred_id)
            VALUES (?, ?)
        """, (referrer_id, referred_id))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def get_referral_count(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_referrer_for_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT referrer_id FROM referrals WHERE referred_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


# ============ СТАТИСТИКА ИГР ============

def update_game_stat(user_id, game, won):
    valid = {"hangman", "bulls", "tictactoe", "mines"}
    if game not in valid:
        return

    games_col = f"{game}_games"
    wins_col = f"{game}_wins"

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT user_id FROM games_stats WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO games_stats (user_id) VALUES (?)
        """, (user_id,))

    if won:
        cursor.execute(f"""
            UPDATE games_stats SET {games_col} = {games_col} + 1,
                                  {wins_col} = {wins_col} + 1
            WHERE user_id = ?
        """, (user_id,))
    else:
        cursor.execute(f"""
            UPDATE games_stats SET {games_col} = {games_col} + 1
            WHERE user_id = ?
        """, (user_id,))

    conn.commit()
    conn.close()


def get_game_stats(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT hangman_wins, hangman_games, bulls_wins, bulls_games,
               tictactoe_wins, tictactoe_games, mines_wins, mines_games
        FROM games_stats WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return (0, 0, 0, 0, 0, 0, 0, 0)
    return row


# ============ БЭКАПЫ ============

def backup_db():
    from config import BACKUP_DIR
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now(MSK).strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"backup_{timestamp}.db")
    shutil.copy(DB_NAME, backup_path)
    return backup_path


def restore_db(uploaded_path):
    if not os.path.exists(uploaded_path):
        return False

    try:
        test_conn = sqlite3.connect(uploaded_path)
        test_conn.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
        test_conn.close()
    except Exception:
        return False

    shutil.copy(uploaded_path, DB_NAME)
    return True


# ============ СТАТИСТИКА ПОСЕЩАЕМОСТИ ============

def get_user_attendance_stats(user_id, days=30):
    """
    Возвращает статистику посещаемости юзера за N дней:
    {
        "total": int,
        "will": int,
        "absent": int,
        "sick": int,
        "late": int,
        "percent": float,
    }
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    from_date = (datetime.now(MSK) - timedelta(days=days)).strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT status, COUNT(*)
        FROM attendance
        WHERE user_id = ? AND date >= ?
        GROUP BY status
    """, (user_id, from_date))

    rows = cursor.fetchall()
    conn.close()

    stats = {"total": 0, "will": 0, "absent": 0, "sick": 0, "late": 0}

    for status, count in rows:
        if status in stats:
            stats[status] = count
        stats["total"] += count

    if stats["total"] > 0:
        good = stats["will"] + stats["sick"] + stats["late"]
        stats["percent"] = round(good / stats["total"] * 100, 1)
    else:
        stats["percent"] = 0.0

    return stats


def get_absentees_streak(university, faculty, group_name, threshold=3):
    """
    Возвращает список юзеров с N+ пропусками ПОДРЯД (статус 'absent').
    [ (user_id, full_name, streak), ... ]
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_id, full_name FROM users
        WHERE university = ? AND faculty = ? AND group_name = ?
    """, (university, faculty, group_name))
    users = cursor.fetchall()

    result = []

    for user_id, full_name in users:
        cursor.execute("""
            SELECT status, date FROM attendance
            WHERE user_id = ?
            ORDER BY date DESC, id DESC
            LIMIT 20
        """, (user_id,))
        rows = cursor.fetchall()

        streak = 0
        for status, _ in rows:
            if status == "absent":
                streak += 1
            else:
                break

        if streak >= threshold:
            result.append((user_id, full_name, streak))

    conn.close()
    return result


def get_group_attendance_month(university, faculty, group_name, days=30):
    """
    Возвращает строки для CSV:
    [ (date, full_name, pair_num, subject, status), ... ]
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    from_date = (datetime.now(MSK) - timedelta(days=days)).strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT a.date, u.full_name, s.pair_number, s.subject, a.status
        FROM attendance a
        JOIN users u ON a.user_id = u.user_id
        JOIN schedule s ON a.schedule_id = s.id
        WHERE u.university = ? AND u.faculty = ? AND u.group_name = ?
          AND s.university = ? AND s.faculty = ? AND s.group_name = ?
          AND a.date >= ?
        ORDER BY a.date DESC, u.full_name, s.pair_number
    """, (
        university, faculty, group_name,
        university, faculty, group_name,
        from_date,
    ))

    rows = cursor.fetchall()
    conn.close()
    return rows