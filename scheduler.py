from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re
import asyncio

from aiogram import Bot
from config import (
    get_current_week_type, get_week_type_for_date,
    REMIND_MINUTES, ABSENT_STREAK_THRESHOLD,
)

from database import (
    get_all_groups, get_schedule,
    get_users_for_pair_notifications,
    get_users_for_attendance_broadcast,
    get_users_for_pair_notifications_with_subgroup,
    get_users_for_attendance_broadcast_with_subgroup,
    get_homework, get_homework_status,
    get_schedule_pair_by_key, upsert_schedule_pair, delete_orphan_schedule_pairs,
    delete_expired_homework,
    get_schedule_for_tomorrow_all_groups,
    get_starosta,
    delete_expired_schedule_pairs,
    get_absentees_streak,
)

from keyboards import (
    get_tomorrow_attendance_all_kb,
)

from parser import fetch_schedule_from_api, parse_schedule_for_day, LESSON_TYPE_NAMES

scheduler = AsyncIOScheduler()

DAYS_RU = {
    0: "Понедельник", 1: "Вторник", 2: "Среда",
    3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье"
}

MSK = ZoneInfo("Europe/Moscow")


def extract_start_time(raw: str) -> str:
    if not raw:
        return ""
    match = re.search(r"(\d{1,2}):(\d{2})", raw)
    if not match:
        return ""
    h, m = int(match.group(1)), match.group(2)
    return f"{h:02d}:{m}"


def _unpack_pair(pair):
    return {
        "id": pair[0],
        "pair_number": pair[1],
        "subject": pair[2],
        "teacher": pair[3],
        "room": pair[4],
        "start_time": pair[5],
        "end_time": pair[6],
        "file_id": pair[7],
        "lesson_type": pair[8] if len(pair) > 8 else "",
        "subgroup": pair[9] if len(pair) > 9 else 0,
        "valid_until": pair[10] if len(pair) > 10 else None,
        "lesson_type_full": pair[11] if len(pair) > 11 else "",
    }


# ============ НАПОМИНАНИЯ О ПАРАХ ============

async def check_upcoming_pairs(bot: Bot):
    now = datetime.now(MSK)
    today = DAYS_RU[now.weekday()]
    today_iso = now.strftime("%Y-%m-%d")

    groups = get_all_groups()
    if not groups:
        return

    for university, faculty, group_name in groups:
        week_type = get_current_week_type(university)

        if university == "РГУ":
            users = get_users_for_pair_notifications_with_subgroup(university, faculty, group_name)
            by_sg = {}
            for user_id, full_name, sg in users:
                by_sg.setdefault(sg or 0, []).append((user_id, full_name))

            for sg, sg_users in by_sg.items():
                pairs = get_schedule(university, faculty, group_name, today, week_type,
                                     subgroup=sg, check_date=today_iso)
                await _send_pair_notifications(bot, pairs, sg_users,
                                               university, faculty, group_name)
        else:
            pairs = get_schedule(university, faculty, group_name, today, week_type,
                                 check_date=today_iso)
            users = get_users_for_pair_notifications(university, faculty, group_name)
            await _send_pair_notifications(bot, pairs, users,
                                           university, faculty, group_name)


async def _send_pair_notifications(bot, pairs, users, university, faculty, group_name):
    now = datetime.now(MSK)
    target_time = (now + timedelta(minutes=REMIND_MINUTES)).strftime("%H:%M")

    for pair in pairs:
        p = _unpack_pair(pair)
        start_short = extract_start_time(p["start_time"])
        if start_short != target_time:
            continue

        for user_id, full_name in users:
            try:
                text = (
                    f"🔔 <b>Через {REMIND_MINUTES} минут пара!</b>\n\n"
                    f"📖 {p['subject']}\n"
                    f"🚪 Аудитория: {p['room'] or '—'}\n"
                    f"⏰ Начало: {start_short}"
                )
                if p["lesson_type_full"]:
                    text += f"\n📌 {p['lesson_type_full']}"
                if p["teacher"]:
                    text += f"\n👤 {p['teacher']}"
                if p["subgroup"] in (1, 2):
                    text += f"\n👥 {p['subgroup']} подгруппа"
                await bot.send_message(user_id, text, parse_mode="HTML")
            except Exception as e:
                print(f"[scheduler] Не удалось отправить {user_id}: {e}")

        homework_list = get_homework(university, faculty, group_name)
        for hw_id, hw_subject, task, deadline, hw_file in homework_list:
            if hw_subject != p["subject"]:
                continue
            for user_id, full_name in users:
                status = get_homework_status(hw_id, user_id)
                if status == "done":
                    continue
                try:
                    await bot.send_message(
                        user_id,
                        f"⚠️ Не забудь про ДЗ по <b>{p['subject']}</b>:\n{task}",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    print(f"[scheduler] Ошибка ДЗ для {user_id}: {e}")


# ============ АВТООБНОВЛЕНИЕ РАСПИСАНИЯ (ТОЛЬКО РГРТУ) ============

async def auto_update_all_schedules(bot: Bot):
    print(f"[scheduler] 🔄 Автообновление расписания (РГРТУ): {datetime.now(MSK).strftime('%d.%m.%Y %H:%M')} МСК")

    groups = get_all_groups()
    groups_rgrtu = [g for g in groups if g[0] == "РГРТУ"]

    if not groups_rgrtu:
        print("[scheduler] Нет групп РГРТУ — пропускаю")
        return

    today = datetime.now(MSK)

    for university, faculty, group_name in groups_rgrtu:
        try:
            date_iso = today.strftime("%Y-%m-%d")
            data = await fetch_schedule_from_api(group_name, date_iso)

            if not data:
                print(f"[scheduler]   ❌ Не удалось получить расписание для {group_name}")
                continue

            saved = 0
            updated = 0
            valid_keys = set()

            for offset in range(14):
                target = today + timedelta(days=offset)
                day_name = DAYS_RU[target.weekday()]
                target_iso = target.strftime("%Y-%m-%d")
                target_week = get_week_type_for_date(target.date(), university)

                pairs = parse_schedule_for_day(data, target_iso, target_week)
                for p in pairs:
                    existing = get_schedule_pair_by_key(
                        university, faculty, group_name,
                        day_name, target_week, p["pair_number"], subgroup=0
                    )

                    upsert_schedule_pair(
                        university, faculty, group_name,
                        day_name, p["pair_number"], p["subject"],
                        p["teacher"], p["room"], p["start_time"], p["end_time"],
                        week_type=target_week,
                        lesson_type=p.get("lesson_type", ""),
                        subgroup=0,
                        valid_until=None,
                        lesson_type_full=LESSON_TYPE_NAMES.get(p.get("lesson_type", ""), "")
                    )
                    valid_keys.add((day_name, target_week, p["pair_number"], 0))

                    if existing:
                        updated += 1
                    else:
                        saved += 1

            deleted = delete_orphan_schedule_pairs(
                university, faculty, group_name, valid_keys
            )

            print(f"[scheduler]   ✅ {group_name}: новых {saved}, обновлено {updated}, удалено {deleted}")

        except Exception as e:
            print(f"[scheduler]   ❌ Ошибка для группы {group_name}: {e}")

    print("[scheduler] 🔄 Автообновление завершено")


# ============ АВТОУДАЛЕНИЕ ДЗ ============

async def cleanup_expired_homework(bot: Bot):
    print(f"[scheduler] 🧹 Очистка просроченных ДЗ: {datetime.now(MSK).strftime('%d.%m.%Y %H:%M')} МСК")
    expired = delete_expired_homework()
    if not expired:
        print("[scheduler] 🧹 Нет просроченных ДЗ")
        return
    for hw_id, subject, deadline in expired:
        print(f"[scheduler] 🧹 Удалено ДЗ: {subject} (срок {deadline})")
    print(f"[scheduler] 🧹 Удалено ДЗ: {len(expired)}")


# ============ АВТОУДАЛЕНИЕ ИСТЁКШИХ ПАР ============

async def cleanup_expired_schedule(bot: Bot):
    print(f"[scheduler] 🧹 Очистка истёкших пар: {datetime.now(MSK).strftime('%d.%m.%Y %H:%M')} МСК")
    deleted = delete_expired_schedule_pairs()
    print(f"[scheduler] 🧹 Удалено пар: {deleted}")


# ============ РАССЫЛКА ЯВКИ ============

async def send_tomorrow_attendance_requests(bot: Bot):
    now = datetime.now(MSK)
    print(f"[scheduler] 📋 Рассылка 'Отметь явку на завтра': {now.strftime('%d.%m.%Y %H:%M')} МСК")

    tomorrow = now + timedelta(days=1)
    day_name = DAYS_RU[tomorrow.weekday()]
    tomorrow_iso = tomorrow.strftime("%Y-%m-%d")
    date_str = tomorrow.strftime("%d.%m.%Y")

    groups = get_all_groups()
    if not groups:
        print("[scheduler] 📋 Нет групп — рассылка пропущена")
        return

    total_sent = 0
    total_failed = 0
    groups_skipped = 0

    for university, faculty, group_name in groups:
        starosta = get_starosta(university, faculty, group_name)
        if not starosta:
            print(f"[scheduler] 📋 Группа {group_name}: нет старосты → пропускаю")
            groups_skipped += 1
            continue

        week_type = get_week_type_for_date(tomorrow.date(), university)

        if university == "РГУ":
            users = get_users_for_attendance_broadcast_with_subgroup(university, faculty, group_name)
            by_sg = {}
            for user_id, full_name, sg in users:
                by_sg.setdefault(sg or 0, []).append((user_id, full_name))

            for sg, sg_users in by_sg.items():
                pairs = get_schedule(university, faculty, group_name,
                                     day_name, week_type,
                                     subgroup=sg, check_date=tomorrow_iso)
                if not pairs:
                    continue

                sent, failed = await _send_attendance_broadcast(
                    bot, pairs, sg_users, university, group_name,
                    day_name, date_str, sg
                )
                total_sent += sent
                total_failed += failed
        else:
            pairs = get_schedule(university, faculty, group_name,
                                 day_name, week_type, check_date=tomorrow_iso)
            if not pairs:
                continue

            users = get_users_for_attendance_broadcast(university, faculty, group_name)
            sent, failed = await _send_attendance_broadcast(
                bot, pairs, users, university, group_name,
                day_name, date_str, subgroup=None
            )
            total_sent += sent
            total_failed += failed

    print(f"[scheduler] 📋 Отправлено: {total_sent}, ошибок: {total_failed}, групп пропущено (нет старосты): {groups_skipped}")


async def _send_attendance_broadcast(bot, pairs, users, university, group_name,
                                     day_name, date_str, subgroup=None):
    text = (
        f"📋 <b>Отметь явку на завтра</b>\n\n"
        f"📅 <b>{day_name}, {date_str}</b>\n"
        f"🎓 Группа: <b>{group_name}</b>\n"
    )
    if subgroup in (1, 2):
        text += f"👥 Подгруппа: <b>{subgroup}</b>\n"
    text += "\n"

    for pair in pairs:
        p = _unpack_pair(pair)

        sg_label = ""
        if p["subgroup"] == 1:
            sg_label = " [1 пг]"
        elif p["subgroup"] == 2:
            sg_label = " [2 пг]"

        text += f"<b>{p['pair_number']} пара</b>{sg_label} | {p['subject']}\n"

        if p["lesson_type_full"]:
            text += f"📌 {p['lesson_type_full']}\n"

        text += f"🚪 {p['room'] or '—'} | ⏰ {p['start_time'] or '—'}\n"
        if p["teacher"]:
            text += f"👤 {p['teacher']}\n"
        text += "\n"

    text += "<i>Нажми кнопку под сообщением, чтобы отметить каждую пару.</i>"

    kb = get_tomorrow_attendance_all_kb(pairs)

    sent = 0
    failed = 0
    for user_id, full_name in users:
        try:
            await bot.send_message(user_id, text, parse_mode="HTML", reply_markup=kb)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            print(f"[scheduler] Не удалось отправить {user_id}: {e}")

    return sent, failed


# ============ ВРЕМЕННЫЙ ПУШ ДЛЯ ТЕСТА ============

async def manual_test_broadcast(bot: Bot):
    print("[scheduler] 🧪 РУЧНОЙ ЗАПУСК рассылки")
    await send_tomorrow_attendance_requests(bot)



# ============ АЛЕРТ СТАРОСТЕ О ПРОГУЛЬЩИКАХ ============

async def check_absentees_streaks(bot: Bot):
    """
    Раз в день проверяет юзеров с 3+ пропусками подряд.
    Отправляет алерт старосте группы.
    """
    now = datetime.now(MSK)
    print(f"[scheduler] ⚠️ Проверка прогульщиков: {now.strftime('%d.%m.%Y %H:%M')} МСК")

    groups = get_all_groups()
    alerts_sent = 0

    for university, faculty, group_name in groups:
        starosta = get_starosta(university, faculty, group_name)
        if not starosta:
            continue

        starosta_id, starosta_name = starosta

        absentees = get_absentees_streak(
            university, faculty, group_name,
            threshold=ABSENT_STREAK_THRESHOLD
        )

        if not absentees:
            continue

        text = (
            f"⚠️ <b>Прогульщики группы {group_name}</b>\n\n"
            f"Студенты с <b>{ABSENT_STREAK_THRESHOLD}+</b> пропусками подряд:\n\n"
        )

        for uid, full_name, streak in absentees:
            text += f"• <b>{full_name}</b> — {streak} пропусков\n"

        text += f"\n📅 {now.strftime('%d.%m.%Y')}"

        try:
            await bot.send_message(starosta_id, text, parse_mode="HTML")
            alerts_sent += 1
        except Exception as e:
            print(f"[scheduler] Не удалось отправить алерт старосте {starosta_id}: {e}")

    print(f"[scheduler] ⚠️ Отправлено алертов: {alerts_sent}")

# ============ ЗАПУСК ============

def start_scheduler(bot: Bot):
    scheduler.add_job(check_upcoming_pairs, "interval", minutes=1, args=[bot], id="check_pairs", replace_existing=True)
    scheduler.add_job(auto_update_all_schedules, "interval", hours=1, args=[bot], id="auto_update_schedules", replace_existing=True)
    scheduler.add_job(auto_update_all_schedules, "date", run_date=datetime.now(MSK) + timedelta(seconds=10), args=[bot], id="auto_update_initial", replace_existing=True)
    scheduler.add_job(cleanup_expired_homework, "interval", hours=24, args=[bot], id="cleanup_homework", replace_existing=True)
    scheduler.add_job(cleanup_expired_homework, "date", run_date=datetime.now(MSK) + timedelta(seconds=30), args=[bot], id="cleanup_homework_initial", replace_existing=True)
    scheduler.add_job(cleanup_expired_schedule, "cron", hour=3, minute=0, timezone=MSK, args=[bot], id="cleanup_schedule", replace_existing=True)
    scheduler.add_job(send_tomorrow_attendance_requests, "cron", hour=14, minute=0, timezone=MSK, args=[bot], id="tomorrow_attendance", replace_existing=True)
    scheduler.add_job(check_absentees_streaks, "cron", hour=18, minute=0, timezone=MSK, args=[bot], id="check_absentees", replace_existing=True)
    scheduler.add_job(auto_update_all_schedules, "cron", hour=0, minute=0, timezone=MSK, args=[bot], id="auto_update_midnight", replace_existing=True)

    print(f"⏰ Планировщик: напоминания за {REMIND_MINUTES} мин + автообновление РГРТУ + очистка ДЗ + очистка пар + рассылка на завтра + алерты прогульщиков")

    scheduler.start()