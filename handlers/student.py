from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from datetime import datetime, timedelta

from parser import (
    fetch_schedule_from_api,
    parse_schedule_for_day,
    format_schedule_for_message,
    format_schedule_grouped,
    LESSON_TYPE_NAMES,
)
from config import get_week_type_for_date, get_current_week_type, ADMIN_IDS, XP_PER_LEVEL
from database import (
    get_user, get_schedule, add_schedule_pair,
    get_homework, get_homework_status,
    set_homework_status, get_debts, add_debt, delete_debt, set_attendance,
    get_schedule_pair_by_key,
    upsert_schedule_pair,
    delete_orphan_schedule_pairs,
    delete_homework,
    get_homework_by_id,
    get_user_answers_for_pairs,
    get_pairs_for_user_on_date,
    get_user_subgroup,
    get_all_rooms_for_university,
    get_occupied_rooms,
    get_user_xp,
    get_group_rating,
    get_referral_count,
    use_promo_code,
    get_user_attendance_stats,
)
from keyboards import (
    get_homework_actions_kb,
    get_debts_menu_kb, get_debts_delete_kb,
    get_homework_starosta_kb,
    get_homework_confirm_delete_kb,
    get_tomorrow_attendance_all_kb,
    get_schedule_menu_kb,
    get_attendance_menu_kb,
    get_attendance_kb,
    get_rating_kb,
    get_promo_menu_kb,
    get_promo_cancel_kb,
    get_my_stats_kb,
)

from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")

router = Router()

DAYS_RU = {
    0: "Понедельник", 1: "Вторник", 2: "Среда",
    3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье"
}


class DebtStates(StatesGroup):
    waiting_new_debt = State()


class PromoStates(StatesGroup):
    waiting_promo = State()


# ============ МЕНЮ ============

@router.message(F.text == "📅 Расписание")
async def schedule_menu(message: types.Message):
    await message.answer("📅 Выбери период:", reply_markup=get_schedule_menu_kb())


@router.message(F.text == "✅ Посещение")
async def attendance_menu(message: types.Message):
    await message.answer("✅ Отметь посещение:", reply_markup=get_attendance_menu_kb())


# ============ /now ============

@router.message(Command("now"))
async def cmd_now(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    university = user[1]
    subgroup = user[11] if len(user) > 11 else 0

    today = datetime.now(MSK)
    day_name = DAYS_RU[today.weekday()]
    week_type = get_current_week_type(university)
    date_iso = today.strftime("%Y-%m-%d")

    pairs = get_schedule(university, user[2], user[3], day_name, week_type,
                         check_date=date_iso)

    if not pairs:
        await message.answer(
            f"📅 Сегодня пар нет 🎉\n"
            f"<i>{day_name}, {week_type}</i>",
            parse_mode="HTML"
        )
        return

    now_str = today.strftime("%H:%M")

    # ищем текущую или следующую пару
    current_pair = None
    next_pair = None

    for p in pairs:
        start = p[5] or ""
        end = p[6] or ""
        if not start:
            continue
        # нормализуем
        s = start.replace(".", ":")
        e = end.replace(".", ":")
        if s <= now_str <= e:
            current_pair = p
            break
        if s > now_str and next_pair is None:
            next_pair = p

    if current_pair:
        p = current_pair
        text = (
            f"🎯 <b>Сейчас идёт пара</b>\n\n"
            f"📖 {p[2]}\n"
            f"🚪 {p[4] or '—'}\n"
            f"⏰ {p[5]}–{p[6] or ''}\n"
        )
        if len(p) > 8 and p[8]:
            text += f"📌 {LESSON_TYPE_NAMES.get(p[8], p[8])}\n"
        if p[3]:
            text += f"👤 {p[3]}\n"
        await message.answer(text, parse_mode="HTML")
        return

    if next_pair:
        p = next_pair
        s = p[5] or ""
        try:
            h, m = map(int, s.replace(".", ":").split(":")[:2])
            start_dt = today.replace(hour=h, minute=m, second=0, microsecond=0)
            delta = (start_dt - today).seconds // 60
            when = f"через {delta} мин"
        except Exception:
            when = "скоро"

        text = (
            f"⏭ <b>Следующая пара</b> ({when})\n\n"
            f"📖 {p[2]}\n"
            f"🚪 {p[4] or '—'}\n"
            f"⏰ {p[5]}–{p[6] or ''}\n"
        )
        if len(p) > 8 and p[8]:
            text += f"📌 {LESSON_TYPE_NAMES.get(p[8], p[8])}\n"
        if p[3]:
            text += f"👤 {p[3]}\n"
        await message.answer(text, parse_mode="HTML")
        return

    await message.answer("✅ На сегодня пары закончились 🎉")


# ============ РАСПИСАНИЕ ============

def _pairs_to_dicts(pairs):
    result = []
    for p in pairs:
        result.append({
            "pair_number": p[1],
            "subject": p[2],
            "teacher": p[3],
            "room": p[4],
            "start_time": p[5],
            "end_time": p[6],
            "lesson_type": p[8] if len(p) > 8 else "",
            "subgroup": p[9] if len(p) > 9 else 0,
            "valid_until": p[10] if len(p) > 10 else None,
            "lesson_type_full": p[11] if len(p) > 11 else "",
        })
    return result


@router.message(F.text == "📅 Сегодня")
async def show_schedule_today(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    university = user[1]
    subgroup = user[11] if len(user) > 11 else 0

    today = datetime.now(MSK)
    day_name = DAYS_RU[today.weekday()]
    week_type = get_current_week_type(university)
    date_str = today.strftime("%d.%m.%Y")
    date_iso = today.strftime("%Y-%m-%d")

    pairs = get_schedule(university, user[2], user[3], day_name, week_type,
                         check_date=date_iso)

    if not pairs and university == "РГРТУ":
        data = await fetch_schedule_from_api(user[3], date_iso)
        if data:
            api_pairs = parse_schedule_for_day(data, date_iso, week_type)
            for p in api_pairs:
                upsert_schedule_pair(
                    university, user[2], user[3], day_name, p["pair_number"],
                    p["subject"], p["teacher"], p["room"],
                    p["start_time"], p["end_time"], week_type=week_type,
                    lesson_type=p.get("lesson_type", ""),
                    subgroup=0,
                    lesson_type_full=LESSON_TYPE_NAMES.get(p.get("lesson_type", ""), ""),
                )
            pairs = get_schedule(university, user[2], user[3], day_name, week_type,
                                 check_date=date_iso)

    if not pairs:
        if university == "РГУ":
            await message.answer(
                f"📅 На {day_name} ({week_type}) пар нет.\n"
                f"<i>Расписание РГУ заполняет староста.</i>",
                parse_mode="HTML"
            )
        else:
            await message.answer(f"📅 На {day_name} ({week_type}) пар нет 🎉")
        return

    text = format_schedule_grouped(
        _pairs_to_dicts(pairs),
        day_name, week_type, date_str,
        user_subgroup=subgroup
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(F.text == "📅 Завтра")
async def show_schedule_tomorrow(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    university = user[1]
    subgroup = user[11] if len(user) > 11 else 0

    tomorrow = datetime.now(MSK) + timedelta(days=1)
    day_name = DAYS_RU[tomorrow.weekday()]
    week_type = get_week_type_for_date(tomorrow.date(), university)
    date_str = tomorrow.strftime("%d.%m.%Y")
    date_iso = tomorrow.strftime("%Y-%m-%d")

    pairs = get_schedule(university, user[2], user[3], day_name, week_type,
                         check_date=date_iso)

    if not pairs and university == "РГРТУ":
        data = await fetch_schedule_from_api(user[3], date_iso)
        if data:
            api_pairs = parse_schedule_for_day(data, date_iso, week_type)
            for p in api_pairs:
                upsert_schedule_pair(
                    university, user[2], user[3], day_name, p["pair_number"],
                    p["subject"], p["teacher"], p["room"],
                    p["start_time"], p["end_time"], week_type=week_type,
                    lesson_type=p.get("lesson_type", ""),
                    subgroup=0,
                    lesson_type_full=LESSON_TYPE_NAMES.get(p.get("lesson_type", ""), ""),
                )
            pairs = get_schedule(university, user[2], user[3], day_name, week_type,
                                 check_date=date_iso)

    if not pairs:
        if university == "РГУ":
            await message.answer(
                f"📅 На {day_name} ({week_type}) пар нет.\n"
                f"<i>Расписание РГУ заполняет староста.</i>",
                parse_mode="HTML"
            )
        else:
            await message.answer(f"📅 На {day_name} ({week_type}) пар нет 🎉")
        return

    text = format_schedule_grouped(
        _pairs_to_dicts(pairs),
        day_name, week_type, date_str,
        user_subgroup=subgroup
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(F.text == "📅 2 недели")
async def show_schedule_two_weeks(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    university = user[1]
    subgroup = user[11] if len(user) > 11 else 0
    await message.answer("📅 **Расписание на 2 недели вперёд:**")

    today = datetime.now(MSK)
    for offset in range(14):
        target = today + timedelta(days=offset)
        day_name = DAYS_RU[target.weekday()]
        week_type = get_week_type_for_date(target.date(), university)
        date_str = target.strftime("%d.%m.%Y")
        date_iso = target.strftime("%Y-%m-%d")

        pairs = get_schedule(university, user[2], user[3], day_name, week_type,
                             check_date=date_iso)
        if not pairs and university == "РГРТУ":
            data = await fetch_schedule_from_api(user[3], date_iso)
            if data:
                api_pairs = parse_schedule_for_day(data, date_iso, week_type)
                for p in api_pairs:
                    upsert_schedule_pair(
                        university, user[2], user[3], day_name, p["pair_number"],
                        p["subject"], p["teacher"], p["room"],
                        p["start_time"], p["end_time"], week_type=week_type,
                        lesson_type=p.get("lesson_type", ""),
                        subgroup=0,
                        lesson_type_full=LESSON_TYPE_NAMES.get(p.get("lesson_type", ""), ""),
                    )
                pairs = get_schedule(university, user[2], user[3], day_name, week_type,
                                     check_date=date_iso)
        if not pairs:
            continue

        text = format_schedule_grouped(
            _pairs_to_dicts(pairs),
            day_name, week_type, date_str,
            user_subgroup=subgroup
        )
        await message.answer(text, parse_mode="Markdown")


# ============ ОБНОВЛЕНИЕ РАСПИСАНИЯ ============

@router.message(F.text == "🔄 Обновить расписание")
async def student_update_schedule(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    if user[1] != "РГРТУ":
        await message.answer(
            "ℹ️ Автообновление доступно только для <b>РГРТУ</b>.\n"
            "Расписание РГУ заполняет староста вручную.",
            parse_mode="HTML"
        )
        return

    await message.answer("🔄 Обновляю расписание вашей группы...")

    today = datetime.now(MSK)
    date_iso = today.strftime("%Y-%m-%d")

    data = await fetch_schedule_from_api(user[3], date_iso)
    if not data:
        await message.answer(
            "❌ Не удалось получить расписание с сайта.\n"
            "Попробуйте позже или обратитесь к старосте."
        )
        return

    saved = 0
    updated = 0
    valid_keys = set()

    for offset in range(14):
        target = today + timedelta(days=offset)
        day_name = DAYS_RU[target.weekday()]
        target_iso = target.strftime("%Y-%m-%d")
        target_week = get_week_type_for_date(target.date(), user[1])

        pairs = parse_schedule_for_day(data, target_iso, target_week)
        for p in pairs:
            existing = get_schedule_pair_by_key(
                user[1], user[2], user[3],
                day_name, target_week, p["pair_number"], subgroup=0
            )

            upsert_schedule_pair(
                user[1], user[2], user[3], day_name, p["pair_number"],
                p["subject"], p["teacher"], p["room"],
                p["start_time"], p["end_time"], week_type=target_week,
                lesson_type=p.get("lesson_type", ""),
                subgroup=0,
                valid_until=None,
                lesson_type_full=LESSON_TYPE_NAMES.get(p.get("lesson_type", ""), ""),
            )
            valid_keys.add((day_name, target_week, p["pair_number"], 0))

            if existing:
                updated += 1
            else:
                saved += 1

    deleted = delete_orphan_schedule_pairs(
        user[1], user[2], user[3], valid_keys
    )

    await message.answer(
        f"✅ Расписание обновлено!\n"
        f"📚 Новых пар: **{saved}**\n"
        f"♻️ Обновлено: **{updated}**\n"
        f"🗑 Удалено: **{deleted}**",
        parse_mode="Markdown"
    )


# ============ ПОСЕЩЕНИЕ ============

@router.message(F.text == "✅ Сегодня")
async def show_attendance_today(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    university = user[1]
    today = datetime.now(MSK)
    day_name = DAYS_RU[today.weekday()]
    date_str = today.strftime("%d.%m.%Y")
    date_iso = today.strftime("%Y-%m-%d")
    week_type = get_current_week_type(university)

    pairs = get_schedule(university, user[2], user[3], day_name, week_type,
                         check_date=date_iso)

    if not pairs:
        await message.answer(f"📅 На {day_name}, {date_str} ({week_type}) пар нет 🎉")
        return

    week_icon = "🔵" if week_type == "числитель" else "🟢"
    await message.answer(
        f"✅ **Отметь посещение на {day_name}, {date_str}**\n{week_icon} Неделя: **{week_type}**",
        parse_mode="Markdown"
    )

    for pair in pairs:
        pair_id = pair[0]
        num = pair[1]
        subject = pair[2]
        room = pair[4]
        start = pair[5]
        lesson_type = pair[8] if len(pair) > 8 else ""
        sg = pair[9] if len(pair) > 9 else 0
        lesson_type_full = LESSON_TYPE_NAMES.get(lesson_type, lesson_type)

        sg_label = ""
        if sg == 1:
            sg_label = " [1 пг]"
        elif sg == 2:
            sg_label = " [2 пг]"

        text = f"**{num} пара**{sg_label} | {subject}\n"
        if lesson_type_full:
            text += f"📌 {lesson_type_full}\n"
        text += (
            f"📅 {date_str} ({day_name})\n"
            f"{week_icon} {week_type}\n"
            f"🚪 {room} | ⏰ {start}"
        )
        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=get_attendance_kb(pair_id, date_offset=0)
        )


@router.message(F.text == "✅ Завтра")
async def show_attendance_tomorrow(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    university = user[1]
    tomorrow = datetime.now(MSK) + timedelta(days=1)
    day_name = DAYS_RU[tomorrow.weekday()]
    date_str = tomorrow.strftime("%d.%m.%Y")
    date_iso = tomorrow.strftime("%Y-%m-%d")
    week_type = get_week_type_for_date(tomorrow.date(), university)

    pairs = get_schedule(university, user[2], user[3], day_name, week_type,
                         check_date=date_iso)

    if not pairs:
        await message.answer(f"📅 На {day_name}, {date_str} (завтра, {week_type}) пар нет 🎉")
        return

    week_icon = "🔵" if week_type == "числитель" else "🟢"
    await message.answer(
        f"✅ **Отметь посещение на {day_name}, {date_str} (завтра)**\n{week_icon} Неделя: **{week_type}**",
        parse_mode="Markdown"
    )

    for pair in pairs:
        pair_id = pair[0]
        num = pair[1]
        subject = pair[2]
        room = pair[4]
        start = pair[5]
        lesson_type = pair[8] if len(pair) > 8 else ""
        sg = pair[9] if len(pair) > 9 else 0
        lesson_type_full = LESSON_TYPE_NAMES.get(lesson_type, lesson_type)

        sg_label = ""
        if sg == 1:
            sg_label = " [1 пг]"
        elif sg == 2:
            sg_label = " [2 пг]"

        text = f"**{num} пара**{sg_label} | {subject}\n"
        if lesson_type_full:
            text += f"📌 {lesson_type_full}\n"
        text += (
            f"📅 {date_str} ({day_name})\n"
            f"{week_icon} {week_type}\n"
            f"🚪 {room} | ⏰ {start}"
        )
        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=get_attendance_kb(pair_id, date_offset=1)
        )


@router.callback_query(F.data == "att_noop")
async def att_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith("att_"))
async def process_attendance(callback: CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 5:
        await callback.answer("Ошибка", show_alert=True)
        return

    status = parts[1]
    try:
        schedule_id = int(parts[2])
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return
    date_offset = int(parts[3])
    is_broadcast = parts[4] == "1"

    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала зарегистрируйтесь: /start", show_alert=True)
        return

    import sqlite3 as _sqlite3
    from database import DB_NAME as _DB_NAME
    conn = _sqlite3.connect(_DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT university, faculty, group_name
        FROM schedule WHERE id = ?
    """, (schedule_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        await callback.answer("❌ Пара не найдена", show_alert=True)
        return

    s_uni, s_fac, s_grp = row
    if (s_uni, s_fac, s_grp) != (user[1], user[2], user[3]):
        await callback.answer(
            "⛔ Эта пара не из вашей группы",
            show_alert=True
        )
        return

    status_names = {
        "will":   "✅ Буду на паре",
        "absent": "❌ Не приду",
        "sick":   "🤒 Заболел",
        "late":   "⏰ Задержусь",
    }
    day_word = "сегодня" if date_offset == 0 else "завтра"

    target_date = (datetime.now(MSK) + timedelta(days=date_offset)).strftime("%Y-%m-%d")

    ok = set_attendance(callback.from_user.id, schedule_id, status, target_date)

    if not ok:
        await callback.answer("⛔ Эта пара не из вашей группы", show_alert=True)
        return

    # бонус XP показываем
    from config import XP_RULES
    xp_delta = XP_RULES.get(status, 0.0)
    xp_text = f" | +{xp_delta} XP" if xp_delta > 0 else ""

    await callback.answer(f"{status_names.get(status, status)} ({day_word}){xp_text}")

    if is_broadcast:
        pairs = get_pairs_for_user_on_date(callback.from_user.id, date_offset)
        if not pairs:
            return
        schedule_ids = [p[0] for p in pairs]
        user_answers = get_user_answers_for_pairs(
            callback.from_user.id, schedule_ids, target_date
        )
        new_kb = get_tomorrow_attendance_all_kb(pairs, user_answers)
        try:
            await callback.message.edit_reply_markup(reply_markup=new_kb)
        except TelegramBadRequest:
            pass
    else:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass


# ============ ДОМАШКА ============

@router.message(F.text.contains("ДЗ"))
async def show_homework(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    homework = get_homework(user[1], user[2], user[3], limit=10)

    if not homework:
        await message.answer("Пока нет добавленных домашних заданий.")
        return

    await message.answer("📚 **Последние домашние задания:**")

    is_starosta = user[5] == 'starosta'

    for hw_id, subject, task, deadline, file_id in homework:
        status = get_homework_status(hw_id, message.from_user.id)
        status_text = ""
        if status == 'done':
            status_text = " | ✅ Сделал"
        elif status == 'not_done':
            status_text = " | ❌ Не сделал"

        text = f"**{subject}**{status_text}\n{task}\n"
        if deadline:
            text += f"⏰ Срок: {deadline}\n"

        kb = get_homework_starosta_kb(hw_id) if is_starosta else get_homework_actions_kb(hw_id)

        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=kb
        )


@router.callback_query(F.data.startswith("hw_done_"))
async def hw_done(callback: CallbackQuery):
    hw_id = int(callback.data.split("_")[2])
    set_homework_status(hw_id, callback.from_user.id, "done")
    await callback.answer("✅ Отмечено: Сделал")
    await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("hw_not_done_"))
async def hw_not_done(callback: CallbackQuery):
    hw_id = int(callback.data.split("_")[3])
    set_homework_status(hw_id, callback.from_user.id, "not_done")
    await callback.answer("❌ Отмечено: Не сделал")
    await callback.message.edit_reply_markup(reply_markup=None)


# ============ ЗАДОЛЖЕННОСТИ ============

@router.message(F.text.contains("Задолженности"))
async def show_debts(message: types.Message):
    user_id = message.from_user.id
    debts = get_debts(user_id)

    if not debts:
        text = "📝 **У тебя нет задолженностей. Молодец! 🎉**\n\nХочешь добавить новую?"
    else:
        text = "📝 **Твои задолженности:**\n\n"
        for i, (debt_id, subject, task) in enumerate(debts, 1):
            text += f"{i}. **{subject}**"
            if task:
                text += f" — {task}"
            text += "\n"
        text += "\n_Выбери действие:_"

    await message.answer(text, parse_mode="Markdown", reply_markup=get_debts_menu_kb())


@router.callback_query(F.data == "debt_add")
async def debt_add_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📝 **Новая задолженность**\n\n"
        "Введи в формате:\n`Предмет | Задание`\n\n"
        "Пример:\n`Математика | Задачи 1-5`",
        parse_mode="Markdown"
    )
    await state.set_state(DebtStates.waiting_new_debt)
    await callback.answer()


@router.message(DebtStates.waiting_new_debt)
async def debt_add_process(message: types.Message, state: FSMContext):
    parts = [p.strip() for p in message.text.split("|", 1)]
    if len(parts) < 2 or not parts[0]:
        await message.answer("❌ Неверный формат. Попробуй ещё раз:\n`Предмет | Задание`", parse_mode="Markdown")
        return

    subject, task = parts[0], parts[1]
    add_debt(message.from_user.id, subject, task)

    await state.clear()
    await message.answer(f"✅ Задолженность добавлена: **{subject}**", parse_mode="Markdown")

    debts = get_debts(message.from_user.id)
    text = "📝 **Твои задолженности:**\n\n"
    for i, (debt_id, subj, tsk) in enumerate(debts, 1):
        text += f"{i}. **{subj}**"
        if tsk:
            text += f" — {tsk}"
        text += "\n"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_debts_menu_kb())


@router.callback_query(F.data == "debt_delete_menu")
async def debt_delete_menu(callback: CallbackQuery):
    debts = get_debts(callback.from_user.id)
    if not debts:
        await callback.answer("Нет задолженностей для удаления")
        return
    await callback.message.edit_text(
        "🗑 **Выбери, что удалить:**",
        parse_mode="Markdown",
        reply_markup=get_debts_delete_kb(debts)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("debt_del_"))
async def debt_delete(callback: CallbackQuery):
    debt_id = int(callback.data.replace("debt_del_", ""))
    delete_debt(debt_id)

    debts = get_debts(callback.from_user.id)
    if not debts:
        await callback.message.edit_text(
            "📝 **У тебя нет задолженностей. Молодец! 🎉**",
            parse_mode="Markdown",
            reply_markup=get_debts_menu_kb()
        )
    else:
        text = "📝 **Твои задолженности:**\n\n"
        for i, (d_id, subject, task) in enumerate(debts, 1):
            text += f"{i}. **{subject}**"
            if task:
                text += f" — {task}"
            text += "\n"
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_debts_menu_kb())
    await callback.answer("Удалено")


@router.callback_query(F.data == "debt_back")
async def debt_back(callback: CallbackQuery):
    debts = get_debts(callback.from_user.id)
    if not debts:
        text = "📝 **У тебя нет задолженностей. Молодец! 🎉**"
    else:
        text = "📝 **Твои задолженности:**\n\n"
        for i, (debt_id, subject, task) in enumerate(debts, 1):
            text += f"{i}. **{subject}**"
            if task:
                text += f" — {task}"
            text += "\n"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_debts_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "debt_close")
async def debt_close(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Закрыто")


# ============ РЕЙТИНГ ГРУППЫ ============

@router.message(F.text == "🏆 Рейтинг группы")
async def show_rating(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    await _send_rating(message, user)


@router.callback_query(F.data == "rating_refresh")
async def rating_refresh(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("Нет данных", show_alert=True)
        return

    await _send_rating(callback.message, user, edit=True)
    await callback.answer("Обновлено")


@router.callback_query(F.data == "rating_close")
async def rating_close(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer("Закрыто")


async def _send_rating(message, user, edit=False):
    university, faculty, group_name = user[1], user[2], user[3]

    rows = get_group_rating(university, faculty, group_name, limit=10)

    if not rows:
        text = "🏆 **Рейтинг группы**\n\n_Пока никто не набрал XP._"
    else:
        text = f"🏆 **Рейтинг группы {group_name}**\n🏛 {university} | {faculty}\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, (uid, fio, xp, level) in enumerate(rows):
            icon = medals[i] if i < 3 else f"{i + 1}."
            short = _short_name(fio)
            text += f"{icon} {short} — **{int(xp)} XP** (ур. {level})\n"

    kb = get_rating_kb()

    if edit:
        try:
            await message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            return
        except Exception:
            pass

    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


def _short_name(full_name):
    parts = full_name.strip().split()
    if len(parts) >= 3:
        return f"{parts[0]} {parts[1][0]}.{parts[2][0]}."
    elif len(parts) == 2:
        return f"{parts[0]} {parts[1][0]}."
    return full_name


# ============ ПРОМОКОДЫ ============

@router.message(Command("promo"))
async def cmd_promo(message: types.Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    user_id = message.from_user.id
    ref_count = get_referral_count(user_id)
    bot_username = (await message.bot.me()).username
    invite_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    text = (
        f"🎁 <b>Промокоды и рефералы</b>\n\n"
        f"👥 Приглашено друзей: <b>{ref_count}</b>\n\n"
        f"🔗 Твоя ссылка:\n<code>{invite_link}</code>\n\n"
        f"За каждого друга — <b>+3 XP</b>!"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=get_promo_menu_kb())


@router.message(Command("invite"))
async def cmd_invite(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    user_id = message.from_user.id
    ref_count = get_referral_count(user_id)
    bot_username = (await message.bot.me()).username
    invite_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    await message.answer(
        f"👥 <b>Пригласи друга</b>\n\n"
        f"Твоя ссылка:\n<code>{invite_link}</code>\n\n"
        f"🎁 За каждого друга — <b>+3 XP</b>\n"
        f"👥 Уже приглашено: <b>{ref_count}</b>",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "promo_enter")
async def promo_enter(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "🎁 <b>Введи промокод:</b>\n\n"
        "<i>Отмена — /cancel</i>",
        parse_mode="HTML",
        reply_markup=get_promo_cancel_kb()
    )
    await state.set_state(PromoStates.waiting_promo)
    await callback.answer()


@router.message(PromoStates.waiting_promo, F.text)
async def promo_process(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()

    status, reward = use_promo_code(message.from_user.id, code)

    if status == "not_found":
        await message.answer("❌ Такого промокода не существует.")
    elif status == "expired":
        await message.answer("❌ Промокод больше не действует.")
    elif status == "already_used":
        await message.answer("⚠️ Ты уже активировал этот промокод.")
    elif status == "ok":
        await message.answer(
            f"✅ Промокод активирован!\n"
            f"🎁 Получено: <b>+{reward} XP</b>",
            parse_mode="HTML"
        )

    await state.clear()


@router.callback_query(F.data == "promo_close")
async def promo_close(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Закрыто")


# ============ ПРОЧЕЕ ============

@router.message(F.text.contains("Помощь"))
async def show_help(message: types.Message):
    await message.answer(
        "ℹ️ **Помощь**\n\n"
        "📅 Расписание — пары на сегодня/завтра\n"
        "🎯 /now — что сейчас идёт\n"
        "📚 ДЗ — домашние задания\n"
        "📝 Задолженности — твои долги\n"
        "✅ Посещение — отметить пары\n"
        "🏆 Рейтинг — топ группы по XP\n"
        "🎮 Игры — сыграть на перемене\n\n"
        "Если что-то не работает — @hiloetc"
    )


@router.message(Command("my_role"))
async def my_role(message: types.Message):
    user = get_user(message.from_user.id)
    if user:
        xp, level, streak = get_user_xp(message.from_user.id)
        await message.answer(
            f"user_id: <code>{user[0]}</code>\n"
            f"ФИО: {user[4]}\n"
            f"Роль: <code>{user[5]}</code>\n"
            f"XP: <b>{int(xp)}</b> | Уровень: <b>{level}</b> | Streak: <b>{streak}</b>",
            parse_mode="HTML"
        )
    else:
        await message.answer("Ты не зарегистрирован в боте.")


# ============ УДАЛЕНИЕ ДЗ СТАРОСТОЙ ============

@router.callback_query(F.data.startswith("hw_delete_yes_"))
async def hw_delete_yes(callback):
    user = get_user(callback.from_user.id)
    if not user or user[5] != 'starosta':
        await callback.answer("⛔ Только староста.", show_alert=True)
        return
    try:
        hw_id = int(callback.data.replace("hw_delete_yes_", ""))
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return
    hw = get_homework_by_id(hw_id)
    if not hw:
        await callback.answer("❌ ДЗ уже удалено.", show_alert=True)
        return
    subject = hw[1]
    delete_homework(hw_id)
    await callback.message.edit_text(f"✅ ДЗ по **{subject}** удалено.", parse_mode="Markdown")
    await callback.answer("Удалено")


@router.callback_query(F.data.startswith("hw_delete_no_"))
async def hw_delete_no(callback):
    await callback.message.edit_text("❌ Удаление отменено.")
    await callback.answer("Отменено")


@router.callback_query(F.data.startswith("hw_delete_"))
async def hw_delete_start(callback):
    user = get_user(callback.from_user.id)
    if not user or user[5] != 'starosta':
        await callback.answer("⛔ Только староста может удалять ДЗ.", show_alert=True)
        return
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("Ошибка", show_alert=True)
        return
    try:
        hw_id = int(parts[2])
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return
    hw = get_homework_by_id(hw_id)
    if not hw:
        await callback.answer("❌ ДЗ уже удалено.", show_alert=True)
        return
    await callback.message.edit_text(
        f"⚠️ **Удалить это ДЗ?**\n\n📖 {hw[1]}\n📝 {hw[2]}\n\n_Действие нельзя отменить._",
        parse_mode="Markdown",
        reply_markup=get_homework_confirm_delete_kb(hw_id)
    )
    await callback.answer()


# ============ ИНФО / HELP ============

INFO_TEXT = """📌 <b>Это учебный бот</b>

🚀 <b>С чего начать:</b> /start → регистрация (ВУЗ → факультет → группа → ФИО)

👨‍🎓 <b>ДЛЯ СТУДЕНТОВ</b>
📅 Расписание — пары на сегодня / завтра / 2 недели
🎯 /now — что сейчас идёт или будет дальше
✅ Посещение — отметить явку
📚 ДЗ — домашние задания
📝 Задолженности — твои долги
🏆 Рейтинг группы — топ по XP
🎮 Игры — сыграть на перемене
🎁 /promo — промокоды и рефералы

👑 <b>ДЛЯ СТАРОСТ</b>
👑 Панель старосты:
 • ➕ ДЗ, ➕ Пара
 • 👥 Список группы
 • 📊 Посещаемость, 📜 Логи
📢 /group_broadcast — рассылка по группе

👑 <b>Хочешь стать старостой?</b>
👤 Профиль → «👑 Получить старосту» → отправь текст заявки (и фото, если есть).
Пока идёт проверка — подать вторую заявку нельзя.

ℹ️ <b>Прочее</b>
/cancel — отменить текущее действие
По вопросам — @hiloetc"""


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    is_admin = message.from_user.id in ADMIN_IDS

    text = INFO_TEXT
    if is_admin:
        text += (
            "\n\n🛠 <b>АДМИН-КОМАНДЫ</b>\n"
            "/users — список пользователей\n"
            "/user &lt;id&gt; — инфо о пользователе\n"
            "/applications — заявки на старосту\n"
            "/starosta — список старост\n"
            "/make_starosta &lt;id&gt;\n"
            "/remove_starosta &lt;id&gt;\n"
            "/ban, /unban, /banlist\n"
            "/broadcast — рассылка всем\n"
            "/refresh_schedule\n"
            "/backup — скачать БД\n"
            "/create_promo &lt;код&gt; &lt;xp&gt; &lt;uses&gt;\n"
            "/promo_list — все промокоды"
        )

    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "ℹ️ Инфо")
async def info_button(message: types.Message):
    await message.answer(INFO_TEXT, parse_mode="HTML")


# ============ СВОБОДНЫЕ АУДИТОРИИ ============

def _is_lab_room(room):
    upper = str(room).strip().upper()
    return (
        " L" in upper
        or upper.endswith("L")
        or upper.startswith("L")
        or " Л" in upper
        or upper.endswith("Л")
        or upper.startswith("Л")
    )


def _is_stadium(room):
    upper = str(room).strip().upper()
    return "СТАДИОН" in upper


def _split_rooms_by_building(rooms):
    lab_rooms = []
    other_rooms = []

    for room in rooms:
        if _is_stadium(room):
            continue
        if _is_lab_room(room):
            lab_rooms.append(room)
        else:
            other_rooms.append(room)

    return other_rooms, lab_rooms


def _group_rooms_by_first_digit(rooms):
    import re
    groups = {}

    for room in rooms:
        m = re.match(r"^(\d)", room)
        if m:
            key = m.group(1)
        else:
            key = "0"
        groups.setdefault(key, []).append(room)

    def sort_key(r):
        m = re.match(r"(\d+)", r)
        if m:
            return (0, int(m.group(1)), r)
        return (1, 0, r)

    for key in groups:
        groups[key].sort(key=sort_key)

    return groups


def _format_rooms_grouped(rooms, prefix="• "):
    lines = []
    groups = _group_rooms_by_first_digit(rooms)

    for key in sorted(groups.keys()):
        group = groups[key]
        line = prefix + ", ".join(group)
        lines.append(line)

    return lines


@router.message(F.text == "🚪 Свободные аудитории")
async def show_free_rooms(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    if user[1] != "РГРТУ":
        await message.answer(
            "ℹ️ Функция доступна только для <b>РГРТУ</b>.",
            parse_mode="HTML"
        )
        return

    today = datetime.now(MSK)
    day_name = DAYS_RU[today.weekday()]
    week_type = get_current_week_type("РГРТУ")
    date_iso = today.strftime("%Y-%m-%d")
    date_str = today.strftime("%d.%m.%Y")

    all_rooms = get_all_rooms_for_university("РГРТУ")
    all_rooms = {r for r in all_rooms if not _is_stadium(r)}

    if not all_rooms:
        await message.answer(
            "⚠️ В базе пока нет данных об аудиториях.\n"
            "Попробуйте позже — расписание обновляется каждый час."
        )
        return

    PAIR_TIMES = {
        1: "08:10–09:45",
        2: "09:55–11:30",
        3: "11:40–13:15",
        4: "13:35–15:10",
        5: "15:20–16:55",
        6: "17:05–18:40",
        7: "18:50–20:15",
        8: "20:25–21:50",
    }

    week_icon = "🔵" if week_type == "числитель" else "🟢"

    header = (
        f"🚪 <b>Свободные аудитории на сегодня</b>\n"
        f"📅 {day_name}, {date_str}\n"
        f"{week_icon} Неделя: <b>{week_type}</b>\n"
    )

    lines = [header]
    any_pairs_found = False

    for pair_num in sorted(PAIR_TIMES.keys()):
        occupied = get_occupied_rooms(
            "РГРТУ", day_name, week_type, pair_num, date_iso
        )
        occupied = {r for r in occupied if not _is_stadium(r)}

        if not occupied:
            continue

        any_pairs_found = True

        free = sorted(all_rooms - occupied)
        other_rooms, lab_rooms = _split_rooms_by_building(free)

        lines.append(f"\n📚 <b>{pair_num} пара</b> ({PAIR_TIMES[pair_num]})")

        if other_rooms:
            for line in _format_rooms_grouped(other_rooms, prefix="• "):
                lines.append(line)

        if lab_rooms:
            lines.append("🧪 <b>L-корпус:</b> " + ", ".join(lab_rooms))

        if not other_rooms and not lab_rooms:
            lines.append("❌ Все аудитории заняты")

    if not any_pairs_found:
        await message.answer(
            f"📅 На {day_name} ({week_type}) пар нет — все аудитории свободны 🎉"
        )
        return

    text = "\n".join(lines)
    text += f"\n\n<i>Всего аудиторий в базе: {len(all_rooms)}</i>"

    MAX_LEN = 3800
    if len(text) > MAX_LEN:
        chunks = []
        current = ""
        for line in lines:
            if len(current) + len(line) + 1 > MAX_LEN:
                chunks.append(current)
                current = line
            else:
                current += "\n" + line if current else line
        if current:
            chunks.append(current)
        for chunk in chunks:
            await message.answer(chunk, parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")



        # ============ МОЯ ПОСЕЩАЕМОСТЬ ============

@router.message(F.text == "📉 Моя посещаемость")
async def my_stats(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    await _send_my_stats(message, user)


@router.callback_query(F.data == "mystats_refresh")
async def mystats_refresh(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("Нет данных", show_alert=True)
        return

    await _send_my_stats(callback.message, user, edit=True)
    await callback.answer("Обновлено")


@router.callback_query(F.data == "mystats_close")
async def mystats_close(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.answer("Закрыто")


async def _send_my_stats(message, user, edit=False):
    user_id = user[0]
    stats = get_user_attendance_stats(user_id, days=30)

    total = stats["total"]
    will = stats["will"]
    absent = stats["absent"]
    sick = stats["sick"]
    late = stats["late"]
    percent = stats["percent"]

    if total == 0:
        text = (
            "📉 <b>Моя посещаемость</b>\n\n"
            "За последние 30 дней нет отметок.\n\n"
            "Отмечай пары через «✅ Посещение»!"
        )
    else:
        bar_len = 20
        filled = int(percent / 100 * bar_len)
        bar = "▰" * filled + "▱" * (bar_len - filled)

        emoji = "🟢" if percent >= 80 else "🟡" if percent >= 60 else "🔴"

        text = (
            f"📉 <b>Моя посещаемость за 30 дней</b>\n\n"
            f"{emoji} <b>{percent}%</b>\n"
            f"{bar}\n\n"
            f"✅ Буду: <b>{will}</b>\n"
            f"❌ Не приду: <b>{absent}</b>\n"
            f"🤒 Заболел: <b>{sick}</b>\n"
            f"⏰ Задержусь: <b>{late}</b>\n\n"
            f"📊 Всего отметок: <b>{total}</b>"
        )

    kb = get_my_stats_kb()

    if edit:
        try:
            await message.edit_text(text, parse_mode="HTML", reply_markup=kb)
            return
        except Exception:
            pass

    await message.answer(text, parse_mode="HTML", reply_markup=kb)