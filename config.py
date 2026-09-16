import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

FACULTY_IDS = {
    "ФРТ": "1",
    "ФЭ": "2",
    "ФАИТУ": "3",
    "ФВТ": "4",
    "ИЭФ": "5",
}


def get_faculty_id(faculty_name: str) -> str:
    return FACULTY_IDS.get(faculty_name)


GROUP_IDS = {
    "610": "2206", "610М": "2207", "611": "2208", "612": "2209",
    "613": "2210", "614": "2211", "615": "2212", "616": "2213",
    "617": "2214", "618": "2215", "618М": "2216", "619": "2217",
    "4818М": "2218", "5011": "2219", "6011": "2220", "6018": "2221",
    "6110": "2222", "5110": "2223", "310М": "2224", "318М": "2225",
    "410М": "2226", "418М": "2227", "510": "2228", "510М": "2229",
    "511": "2230", "512": "2231", "514": "2232", "515": "2233",
    "516": "2234", "518": "2235", "518М": "2236", "519": "2237",
    "3018М": "2238", "4011": "2239", "211": "2241", "213": "2242",
    "219": "2243", "410": "2244", "411": "2245", "412": "2246",
    "414": "2247", "415": "2248", "416": "2249", "417": "2250",
    "418": "2251", "419": "2252", "3011": "2253", "4110": "2254",
}


def get_group_id(group_name: str) -> str:
    return GROUP_IDS.get(group_name)


ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip()
]

if not BOT_TOKEN:
    raise ValueError("Токен не найден! Проверь файл .env")


# ============ ВУЗЫ И ФАКУЛЬТЕТЫ ============

UNIVERSITIES = ["РГРТУ", "РГУ"]

FACULTIES_RGRTU = ["ФРТ", "ФВТ", "ФАИТУ", "ИЭФ", "ФЭ"]

FACULTIES_RGU = [
    "ФЭСУ", "ИФМиКН", "ИЕН", "ИИЯ",
    "ФФКС", "ИИФПН", "ФРФНК", "ИППСР", "ЮИ",
]

# ============ СЕМЕСТР ============

SEMESTER_START = "2026-09-07"
FIRST_WEEK_TYPE = "знаменатель"

# ============ НАПОМИНАНИЯ ============

REMIND_MINUTES = 10

# ============ XP / ГЕЙМИФИКАЦИЯ ============

XP_PER_LEVEL = 10

XP_RULES = {
    "will":   1.0,
    "sick":   0.5,
    "late":   0.5,
    "absent": 0.0,
}

# ============ АЛЕРТ ПРОГУЛЬЩИКА ============

ABSENT_STREAK_THRESHOLD = 3   # сколько пропусков подряд = алерт старосте

# ============ ИГРЫ ============

HANGMAN_WORDS = [
    "АЛГЕБРА", "ФИЗИКА", "ХИМИЯ", "ГЕОМЕТРИЯ", "ИНФОРМАТИКА",
    "ИСТОРИЯ", "ФИЛОСОФИЯ", "ЭКОНОМИКА", "ПРОГРАММИРОВАНИЕ",
    "АЛГОРИТМ", "СТУДЕНТ", "СЕМИНАР", "ЛЕКЦИЯ", "ЭКЗАМЕН",
    "ЗАЧЕТ", "ДИПЛОМ", "КАФЕДРА", "ПРЕПОДАВАТЕЛЬ", "УНИВЕРСИТЕТ",
]

CITIES_DB = [
    "Москва", "Питер", "Новосибирск", "Екатеринбург", "Казань",
    "Нижний Новгород", "Челябинск", "Самара", "Омск", "Ростов",
    "Уфа", "Красноярск", "Воронеж", "Пермь", "Волгоград",
    "Краснодар", "Саратов", "Тюмень", "Тольятти", "Ижевск",
    "Барнаул", "Ульяновск", "Иркутск", "Хабаровск", "Ярославль",
    "Владивосток", "Махачкала", "Томск", "Оренбург", "Кемерово",
]

# ============ БЭКАПЫ ============

BACKUP_DIR = "/tmp"

# ============ ПРОМОКОДЫ ============

DEFAULT_PROMO_XP = 5
DEFAULT_PROMO_USES = 10


from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")


def get_current_week_type(university: str = "РГРТУ") -> str:
    start = datetime.strptime(SEMESTER_START, "%Y-%m-%d").date()
    today = datetime.now(MSK).date()
    days_diff = (today - start).days
    weeks_diff = days_diff // 7
    if weeks_diff % 2 == 0:
        return FIRST_WEEK_TYPE
    else:
        return "знаменатель" if FIRST_WEEK_TYPE == "числитель" else "числитель"


def get_week_type_for_date(target_date, university: str = "РГРТУ") -> str:
    start = datetime.strptime(SEMESTER_START, "%Y-%m-%d").date()
    days_diff = (target_date - start).days
    weeks_diff = days_diff // 7
    if weeks_diff % 2 == 0:
        return FIRST_WEEK_TYPE
    else:
        return "знаменатель" if FIRST_WEEK_TYPE == "числитель" else "числитель"