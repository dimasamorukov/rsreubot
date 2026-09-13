from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re
import asyncio

from aiogram import Bot
from config import get_current_week_type, get_week_type_for_date
from database import (
    get_all_groups, get_schedule, get_users_with_notifications,
    get_homework, get_homework_status,
    get_schedule_pair_by_key, upsert_schedule_pair, delete_orphan_schedule_pairs,
    delete_expired_homework,
    get_schedule_for_tomorrow_all_groups,
    get_starosta,
)

from keyboards import (
    get_tomorrow_attendance_kb,
    get_tomorrow_attendance_all_kb,
)

from parser import fetch_schedule_from_api, parse_schedule_for_day

try:
    from sync import sync_tables
    SYNC_AVAILABLE = True
except ImportError:
    SYNC_AVAILABLE = False
    print("[scheduler] sync.py не найден — синхронизация с PostgreSQL отключена")

scheduler = AsyncIOScheduler()

DAYS_RU = {
    0: "Понедельник", 1: "Вторник", 2: "Среда",
    3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье"
}

MSK = ZoneInfo("Europe/Moscow")


def extract_start_time(raw: str) -> str:
    """Извлекает время начала из строки любого формата"""
    if not raw:
        return ""
    match = re.search(r"(\d{1,2}):(\d{2})", raw)
    if not match:
        return ""
    h, m = int(match.group(1)), match.group(2)
    return f"{h:02d}:{m}"


# ============ НАПОМИНАНИЯ О ПАРАХ ============

async def check_upcoming_pairs(bot: Bot):
    """Каждую минуту проверяет: нет ли пары, которая начнётся через 30 минут"""
    now = datetime.now(MSK)
    target_time = (now + timedelta(minutes=30)).strftime("%H:%M")
    today = DAYS_RU[now.weekday()]

    groups = get_all_groups()
    if not groups:
        return

    week_type = get_current_week_type()

    for university, faculty, group_name in groups:
        pairs = get_schedule(university, faculty, group_name, today, week_type)

        for pair_id, num, subject, teacher, room, start, end, file_id in pairs:
            start_short = extract_start_time(start)
            if start_short != target_time:
                continue

            users = get_users_with_notifications(university, faculty, group_name)

            for user_id, full_name in users:
                try:
                    text = (
                        f"🔔 <b>Через 30 минут пара!</b>\n\n"
                        f"📖 {subject}\n"
                        f"🚪 Аудитория: {room}\n"
                        f"⏰ Начало: {start_short}"
                    )
                    if teacher:
                        text += f"\n👤 {teacher}"
                    await bot.send_message(user_id, text, parse_mode="HTML")
                except Exception as e:
                    print(f"[scheduler] Не удалось отправить {user_id}: {e}")

            # Напоминание о ДЗ
            homework_list = get_homework(university, faculty, group_name)
            for hw_id, hw_subject, task, deadline, hw_file in homework_list:
                if hw_subject != subject:
                    continue
                for user_id, full_name in users:
                    status = get_homework_status(hw_id, user_id)
                    if status == "done":
                        continue
                    try:
                        await bot.send_message(
                            user_id,
                            f"⚠️ Не забудь про ДЗ по <b>{subject}</b>:\n{task}",
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        print(f"[scheduler] Ошибка ДЗ для {user_id}: {e}")


# ============ АВТООБНОВЛЕНИЕ РАСПИСАНИЯ (с сохранением посещаемости) ============

async def auto_update_all_schedules(bot: Bot):
    """
    Раз в час обновляет расписание ВСЕХ групп из базы.
    Использует upsert_schedule_pair — сохраняет schedule_id для неизменившихся пар,
    поэтому посещаемость НЕ СБРАСЫВАЕТСЯ.
    """
    print(f"[scheduler] 🔄 Автообновление расписания: {datetime.now(MSK).strftime('%d.%m.%Y %H:%M')} МСК")

    groups = get_all_groups()
    if not groups:
        print("[scheduler] Нет групп в базе — пропускаю")
        return

    today = datetime.now(MSK)

    for university, faculty, group_name in groups:
        try:
            date_iso = today.strftime("%Y-%m-%d")
            data = await fetch_schedule_from_api(group_name, date_iso)

            if not data:
                print(f"[scheduler]   ❌ Не удалось получить расписание для {group_name}")
                continue

            saved = 0      # новых пар
            updated = 0    # обновлённых
            valid_keys = set()

            for offset in range(14):
                target = today + timedelta(days=offset)
                day_name = DAYS_RU[target.weekday()]
                target_iso = target.strftime("%Y-%m-%d")
                target_week = get_week_type_for_date(target.date())

                pairs = parse_schedule_for_day(data, target_iso, target_week)
                for p in pairs:
                    existing = get_schedule_pair_by_key(
                        university, faculty, group_name,
                        day_name, target_week, p["pair_number"]
                    )

                    # Умное обновление — сохраняет id и посещаемость
                    upsert_schedule_pair(
                        university, faculty, group_name,
                        day_name, p["pair_number"], p["subject"],
                        p["teacher"], p["room"], p["start_time"], p["end_time"],
                        week_type=target_week
                    )
                    valid_keys.add((day_name, target_week, p["pair_number"]))

                    if existing:
                        updated += 1
                    else:
                        saved += 1

            # Удаляем только те пары, которых больше нет в расписании
            deleted = delete_orphan_schedule_pairs(
                university, faculty, group_name, valid_keys
            )

            print(f"[scheduler]   ✅ {group_name}: новых {saved}, обновлено {updated}, удалено {deleted}")

        except Exception as e:
            print(f"[scheduler]   ❌ Ошибка для группы {group_name}: {e}")

    print("[scheduler] 🔄 Автообновление завершено")


# ============ АВТОУДАЛЕНИЕ ПРОСРОЧЕННЫХ ДЗ ============

async def cleanup_expired_homework(bot: Bot):
    """Раз в сутки удаляет ДЗ, у которых срок истёк более 2 дней назад"""
    print(f"[scheduler] 🧹 Очистка просроченных ДЗ: {datetime.now(MSK).strftime('%d.%m.%Y %H:%M')} МСК")
    expired = delete_expired_homework()
    if not expired:
        print("[scheduler] 🧹 Нет просроченных ДЗ")
        return
    for hw_id, subject, deadline in expired:
        print(f"[scheduler] 🧹 Удалено ДЗ: {subject} (срок {deadline})")
    print(f"[scheduler] 🧹 Удалено ДЗ: {len(expired)}")


# ============ РАССЫЛКА «ОТМЕТЬ ЯВКУ НА ЗАВТРА» (14:00 МСК) ============

async def send_tomorrow_attendance_requests(bot: Bot):
    """
    Каждый день в 14:00 МСК рассылает всем студентам ОДНО сообщение
    с парами на завтра и inline-кнопками для отметки.

    Рассылка идёт ТОЛЬКО для групп, в которых есть староста.
    """
    now = datetime.now(MSK)
    print(f"[scheduler] 📋 Рассылка 'Отметь явку на завтра': {now.strftime('%d.%m.%Y %H:%M')} МСК")

    data = get_schedule_for_tomorrow_all_groups()

    if not data:
        print("[scheduler] 📋 Нет групп с парами на завтра")
        return

    total_sent = 0
    total_failed = 0
    groups_skipped = 0

    for university, faculty, group_name, day_name, pairs in data:
        # Проверка: есть ли староста в группе
        starosta = get_starosta(university, faculty, group_name)
        if not starosta:
            print(f"[scheduler] 📋 Группа {group_name}: нет старосты → пропускаю")
            groups_skipped += 1
            continue

        users = get_users_with_notifications(university, faculty, group_name)

        # Формируем текст сообщения
        date_str = (datetime.now(MSK) + timedelta(days=1)).strftime("%d.%m.%Y")

        text = (
            f"📋 <b>Отметь явку на завтра</b>\n\n"
            f"📅 <b>{day_name}, {date_str}</b>\n"
            f"🎓 Группа: <b>{group_name}</b>\n\n"
        )

        for pair in pairs:
            pair_id, pair_num, subject, teacher, room, start, end, file_id = pair
            text += f"<b>{pair_num} пара</b> | {subject}\n"
            text += f"🚪 {room or '—'} | ⏰ {start or '—'}\n"
            if teacher:
                text += f"👤 {teacher}\n"
            text += "\n"

        text += "<i>Нажми кнопку под сообщением, чтобы отметить каждую пару.</i>"

        # Формируем клавиатуру со всеми парами
        kb = get_tomorrow_attendance_all_kb(pairs)

        # Отправляем ОДНО сообщение каждому студенту
        for user_id, full_name in users:
            try:
                await bot.send_message(
                    user_id,
                    text,
                    parse_mode="HTML",
                    reply_markup=kb
                )
                total_sent += 1
                await asyncio.sleep(0.05)  # задержка между пользователями
            except Exception as e:
                total_failed += 1
                print(f"[scheduler] Не удалось отправить {user_id}: {e}")

    print(f"[scheduler] 📋 Отправлено: {total_sent}, ошибок: {total_failed}, групп пропущено (нет старосты): {groups_skipped}")


# ============ ЗАПУСК ПЛАНИРОВЩИКА ============

def start_scheduler(bot: Bot):
    # 1. Напоминания о парах — каждую минуту
    scheduler.add_job(
        check_upcoming_pairs,
        "interval",
        minutes=1,
        args=[bot],
        id="check_pairs",
        replace_existing=True
    )

    # 2. Автообновление расписания — каждый час
    scheduler.add_job(
        auto_update_all_schedules,
        "interval",
        hours=1,
        args=[bot],
        id="auto_update_schedules",
        replace_existing=True
    )

    # 3. Первое автообновление — через 10 секунд после старта
    scheduler.add_job(
        auto_update_all_schedules,
        "date",
        run_date=datetime.now(MSK) + timedelta(seconds=10),
        args=[bot],
        id="auto_update_initial",
        replace_existing=True
    )

    # 4. Автоудаление просроченных ДЗ — раз в сутки
    scheduler.add_job(
        cleanup_expired_homework,
        "interval",
        hours=24,
        args=[bot],
        id="cleanup_homework",
        replace_existing=True
    )

    # 5. Первый запуск очистки — через 30 секунд после старта
    scheduler.add_job(
        cleanup_expired_homework,
        "date",
        run_date=datetime.now(MSK) + timedelta(seconds=30),
        args=[bot],
        id="cleanup_homework_initial",
        replace_existing=True
    )

    # 6. Рассылка «Отметь явку на завтра» — каждый день в 14:00 МСК
    scheduler.add_job(
        send_tomorrow_attendance_requests,
        "cron",
        hour=14,
        minute=0,
        timezone=MSK,
        args=[bot],
        id="tomorrow_attendance",
        replace_existing=True
    )

    # 7. Синхронизация с PostgreSQL — каждый час (если sync.py есть)
    if SYNC_AVAILABLE:
        scheduler.add_job(
            sync_tables,
            "interval",
            hours=1,
            id="sync_db",
            replace_existing=True
        )
        print("⏰ Планировщик: напоминания + автообновление + очистка ДЗ + рассылка на завтра + синхронизация")
    else:
        print("⏰ Планировщик: напоминания + автообновление + очистка ДЗ + рассылка на завтра")

    scheduler.start()