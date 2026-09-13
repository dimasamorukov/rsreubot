import asyncio
from parser import fetch_schedule_from_site, format_schedule_for_message, DAYS_RU
from config import get_faculty_id, get_group_id
from datetime import datetime


async def test():
    # Замени на свою группу и факультет
    faculty_name = "ФРТ"
    group_name = "5110"
    
    faculty_id = get_faculty_id(faculty_name)
    group_id = get_group_id(group_name)
    
    print(f"Факультет: {faculty_name} → ID {faculty_id}")
    print(f"Группа: {group_name} → ID {group_id}")
    print("-" * 40)
    
    if not faculty_id or not group_id:
        print("❌ Не найден ID. Проверь config.py")
        return
    
    pairs = await fetch_schedule_from_site(faculty_id, group_id, date_offset=0)
    
    if pairs is None:
        print("❌ Парсер вернул None — ошибка запроса или разбора")
        return
    
    if len(pairs) == 0:
        print("⚠️ Парсер отработал, но пар не нашёл.")
        print("   Возможно: сегодня выходной, расписание пустое, или не тот день.")
        return
    
    print(f"✅ Парсер работает! Найдено пар: {len(pairs)}")
    print("-" * 40)
    
    for i, p in enumerate(pairs, 1):
        print(f"Пара {i}:")
        print(f"  Время: {p['time']}")
        print(f"  Тип: {p['type']}")
        print(f"  Предмет: {p['subject']}")
        print(f"  Преподаватель: {p['teacher']}")
        print(f"  Аудитория: {p['room']}")
        print(f"  Подгруппа: {p['subgroup']}")
        print()
    
    print("-" * 40)
    print("Форматированный текст для Telegram:")
    print()
    today = datetime.now()
    day_name = DAYS_RU[today.weekday()]
    date_str = today.strftime("%d.%m.%Y")
    print(format_schedule_for_message(pairs, day_name, date_str))


asyncio.run(test())