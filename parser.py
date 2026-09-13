import aiohttp
from datetime import datetime, timedelta

API_BASE = "https://api.rsreu-schedule.ru"

DAYS_RU = {
    0: "Понедельник", 1: "Вторник", 2: "Среда",
    3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье"
}

DAY_EN = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


async def fetch_schedule_from_api(group_name: str, date: str = None) -> dict:
    """
    Загружает расписание группы через API.
    group_name — номер группы (например, "5110")
    date — дата в формате YYYY-MM-DD (по умолчанию — сегодня)
    """
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
    """
    Извлекает расписание на конкретный день из ответа API.
    Возвращает список пар:
    [
        {
            "pair_number": 1,
            "subject": "Математика",
            "teacher": "доц. Бодрова И.В.",
            "room": "465 C",
            "start_time": "08:10",
            "end_time": "09:45",
            "lesson_type": "Лек."
        },
        ...
    ]
    """
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
        if p['lesson_type']:
            text += f"{p['lesson_type']} "
        text += f"{p['subject']}\n"
        if p['teacher']:
            text += f"👤 {p['teacher']}"
        if p['room']:
            text += f" | 🚪 {p['room']}"
        if p['teacher'] or p['room']:
            text += "\n"
        text += "➖➖➖➖➖\n"

    return text
