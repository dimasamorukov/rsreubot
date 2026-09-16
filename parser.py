import aiohttp
from datetime import datetime, timedelta

API_BASE = "https://api.rsreu-schedule.ru"

DAYS_RU = {
    0: "Понедельник", 1: "Вторник", 2: "Среда",
    3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье"
}

DAY_EN = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

LESSON_TYPE_NAMES = {
    "Лек.": "Лекция",
    "Лаб.": "Лабораторная",
    "Упр.": "Практика",
    "Пр.": "Практика",
    "Сем.": "Семинар",
    "Курс.": "Курсовая",
}


async def fetch_schedule_from_api(group_name: str, date: str = None) -> dict:
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    url = f"{API_BASE}/api/v1/schedule/groups/{group_name}"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params={"date": date}, headers=headers, timeout=15) as response:
                if response.status != 200:
                    print(f"[parser] Ошибка API: {response.status}")
                    return None
                return await response.json()
    except Exception as e:
        print(f"[parser] Ошибка запроса: {e}")
        return None


def parse_schedule_for_day(data: dict, target_date: str, week_type: str) -> list:
    if not data or "schedule" not in data:
        return []

    week_type_en = "numerator" if week_type == "числитель" else "denominator"
    week_schedule = data["schedule"].get(week_type_en, {}) or {}

    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    day_en = DAY_EN[target_dt.weekday()]

    lessons = week_schedule.get(day_en, []) or []

    pairs = []
    for lesson in lessons:
        time_str = lesson.get("time", "")
        start_time, end_time = _split_time(time_str)

        lesson_type = _extract_lesson_type(lesson.get("lesson", ""))
        teacher, room = _extract_teacher_room(lesson)
        pair_number = _get_pair_number(start_time)

        pairs.append({
            "pair_number": pair_number,
            "subject": lesson.get("title", ""),
            "teacher": teacher,
            "room": room,
            "start_time": start_time,
            "end_time": end_time,
            "lesson_type": lesson_type,
        })

    pairs.sort(key=lambda p: p["pair_number"])
    return pairs


def _split_time(time_str: str) -> tuple:
    if not time_str or "-" not in time_str:
        return ("", "")
    parts = time_str.replace(".", ":").split("-")
    if len(parts) == 2:
        return (parts[0].strip(), parts[1].strip())
    return ("", "")


def _extract_lesson_type(lesson_text: str) -> str:
    if not lesson_text:
        return ""
    first_line = lesson_text.split("\n")[0]
    for prefix in ["Лек.", "Лаб.", "Упр.", "Пр.", "Сем.", "Курс."]:
        if first_line.startswith(prefix):
            return prefix
    return ""


def _extract_teacher_room(lesson: dict) -> tuple:
    teacher = ""
    room = ""
    ta_list = lesson.get("teacher_auditoriums", []) or []
    if ta_list:
        first = ta_list[0]
        t = first.get("teacher") or {}
        a = first.get("auditorium") or {}
        teacher = t.get("short_name") or t.get("full_name") or ""
        room = a.get("display_name") or a.get("number") or ""

    if not teacher or not room:
        lesson_text = lesson.get("lesson", "")
        lines = lesson_text.split("\n")
        if len(lines) >= 2:
            parts = lines[1].rsplit(" ", 2)
            if len(parts) >= 2:
                if not teacher:
                    teacher = " ".join(parts[:-1])
                if not room:
                    room = parts[-1]

    return (teacher, room)


def _get_pair_number(start_time: str) -> int:
    if not start_time:
        return 0
    PAIR_TIMES = [
        ("08:10", 1), ("09:55", 2), ("11:40", 3), ("13:35", 4),
        ("15:20", 5), ("17:05", 6), ("18:50", 7), ("20:25", 8),
    ]
    for time_str, num in PAIR_TIMES:
        if start_time.startswith(time_str[:4]):
            return num
    return 0


def format_schedule_for_message(pairs: list, day_name: str, week_type: str, date_str: str = "") -> str:
    if not pairs:
        return f"📅 На {day_name} ({week_type}) пар нет 🎉"

    week_icon = "🔵" if week_type == "числитель" else "🟢"
    text = f"📅 **Расписание на {day_name}"
    if date_str:
        text += f", {date_str}"
    text += "**\n"
    text += f"{week_icon} Неделя: **{week_type}**\n\n"

    for p in pairs:
        text += f"**{p['pair_number']} пара** ({p['start_time']}–{p['end_time']})\n"

        lesson_type = p.get('lesson_type') or ""
        lesson_type_full = LESSON_TYPE_NAMES.get(lesson_type, lesson_type)

        if lesson_type_full:
            text += f"📌 {lesson_type_full}\n"

        text += f"📖 {p['subject']}\n"

        if p['teacher']:
            text += f"👤 {p['teacher']}\n"
        if p['room']:
            text += f"🚪 {p['room']}\n"

        text += "➖➖➖➖➖\n"

    return text


def format_schedule_grouped(pairs: list, day_name: str, week_type: str,
                            date_str: str = "", user_subgroup: int = None) -> str:
    """
    Форматирует расписание с учётом подгрупп.
    user_subgroup: 0/None — показать все подгруппы с пометками;
                   1 или 2 — скрыть чужие подгруппы.
    """
    from collections import OrderedDict

    if not pairs:
        return f"📅 На {day_name} ({week_type}) пар нет 🎉"

    week_icon = "🔵" if week_type == "числитель" else "🟢"
    text = f"📅 **Расписание на {day_name}"
    if date_str:
        text += f", {date_str}"
    text += "**\n"
    text += f"{week_icon} Неделя: **{week_type}**\n\n"

    by_number = OrderedDict()
    for p in pairs:
        num = p.get("pair_number", 0)
        by_number.setdefault(num, []).append(p)

    for num, group in by_number.items():
        first = group[0]
        time_str = first.get('start_time') or ''
        end_str = first.get('end_time') or ''
        header = f"**{num} пара** ({time_str}"
        if end_str:
            header += f"–{end_str}"
        header += ")\n"
        text += header

        group.sort(key=lambda x: (x.get('subgroup', 0) or 0))

        printed_any = False
        for p in group:
            sg = p.get('subgroup', 0) or 0

            if user_subgroup and sg != 0 and sg != user_subgroup:
                continue

            printed_any = True
            prefix = "┣ "
            if sg == 1:
                prefix = "┣ **[1 пг]** "
            elif sg == 2:
                prefix = "┣ **[2 пг]** "

            lesson_full = p.get('lesson_type_full') or LESSON_TYPE_NAMES.get(
                p.get('lesson_type') or '', p.get('lesson_type') or ''
            )

            text += prefix
            if lesson_full:
                text += f"📌 {lesson_full}\n"
            else:
                text += "\n"

            text += f"┃ 📖 {p.get('subject', '')}\n"
            if p.get('teacher'):
                text += f"┃ 👤 {p['teacher']}\n"
            if p.get('room'):
                text += f"┃ 🚪 {p['room']}\n"

        if not printed_any:
            text = text[:-(len(header))]

        text += "➖➖➖➖➖\n"

    return text