import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

FACULTY_IDS = {
    "ФРТ": "1",
    "ФЭ": "2",
    "ФАИТУ": "3",
    "ФВТ": "4",
    "ИЭФ": "5",
    # добавь остальные факультеты, если есть
}
def get_faculty_id(faculty_name: str) -> str:
    """Возвращает ID факультета для парсера или None, если не найден"""
    return FACULTY_IDS.get(faculty_name)

GROUP_IDS = {
    "610": "2206",
    "610М": "2207",
    "611": "2208",
    "612": "2209",
    "613": "2210",
    "614": "2211",
    "615": "2212",
    "616": "2213",
    "617": "2214",
    "618": "2215",
    "618М": "2216",
    "619": "2217",
    "4818М": "2218",
    "5011": "2219",
    "6011": "2220",
    "6018": "2221",
    "6110": "2222",
    "5110": "2223",
    "310М": "2224",
    "318М": "2225",
    "410М": "2226",
    "418М": "2227",
    "510": "2228",
    "510М": "2229",
    "511": "2230",
    "512": "2231",
    "514": "2232",
    "515": "2233",
    "516": "2234",
    "518": "2235",
    "518М": "2236",
    "519": "2237",
    "3018М": "2238",
    "4011": "2239",
    "5110": "2240",
    "211": "2241",
    "213": "2242",
    "219": "2243",
    "410": "2244",
    "411": "2245",
    "412": "2246",
    "414": "2247",
    "415": "2248",
    "416": "2249",
    "417": "2250",
    "418": "2251",
    "419": "2252",
    "3011": "2253",
    "4110": "2254",   
}

def get_group_id(group_name: str) -> str:
    """Возвращает ID группы для парсера или None, если не найден"""
    return GROUP_IDS.get(group_name)
# Список ID админов из .env (через запятую)
ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip()
]

if not BOT_TOKEN:
    raise ValueError("Токен не найден! Проверь файл .env")

# ============ НАСТРОЙКИ УЧЕБНОГО СЕМЕСТРА ============

# ============ НАСТРОЙКИ УЧЕБНОГО СЕМЕСТРА ============

# Дата начала семестра. В этот день — ПЕРВАЯ неделя.
# Формат: "YYYY-MM-DD"
# По данным API: 14.09.2026 — числитель, 07.09.2026 — знаменатель
SEMESTER_START = "2026-09-07"

# Какая неделя идёт первой — "числитель" или "знаменатель"
FIRST_WEEK_TYPE = "знаменатель"


from datetime import datetime, timedelta


def get_current_week_type() -> str:
    """
    Возвращает 'числитель' или 'знаменатель' для текущей недели.
    Считает от SEMESTER_START.
    """
    start = datetime.strptime(SEMESTER_START, "%Y-%m-%d").date()
    today = datetime.now().date()
    
    # Разница в неделях от начала семестра
    days_diff = (today - start).days
    weeks_diff = days_diff // 7
    
    # Чётная неделя → первый тип, нечётная → второй
    if weeks_diff % 2 == 0:
        return FIRST_WEEK_TYPE
    else:
        return "знаменатель" if FIRST_WEEK_TYPE == "числитель" else "числитель"


def get_week_type_for_date(target_date) -> str:
    """
    Возвращает 'числитель' или 'знаменатель' для конкретной даты.
    target_date — объект datetime.date
    """
    start = datetime.strptime(SEMESTER_START, "%Y-%m-%d").date()
    
    days_diff = (target_date - start).days
    weeks_diff = days_diff // 7
    
    if weeks_diff % 2 == 0:
        return FIRST_WEEK_TYPE
    else:
        return "знаменатель" if FIRST_WEEK_TYPE == "числитель" else "числитель"
