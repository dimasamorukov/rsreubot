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
from config import get_week_type_for_date, get_current_week_type
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


# ============ МЕНЮ ============

@router.message(F.text == "📅 Расписание")
async def schedule_menu(message: types.Message):
    await message.answer("📅 Выбери период:", reply_markup=get_schedule_menu_kb())


@router.message(F.text == "✅ Посещение")
async def attendance_menu(message: types.Message):
    await message.answer("✅ Отметь посещение:", reply_markup=get_attendance_menu_kb())


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


# ============ ОБНОВЛЕНИЕ РАСПИСАНИЯ (ТОЛЬКО РГРТУ) ============

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

    # ⛔ ЗАЩИТА ОТ ЧУЖИХ ОТМЕТОК
    # Проверяем, что пара принадлежит группе пользователя
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала зарегистрируйтесь: /start", show_alert=True)
        return

    conn_sql = __import__("sqlite3")  # или просто sqlite3 в импортах
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
    # Сравниваем с данными пользователя
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

    # Записываем отметку. Функция вернёт True если пара из группы пользователя, False иначе.
    ok = set_attendance(callback.from_user.id, schedule_id, status, target_date)

    if not ok:
        # Пара чужая — не записываем, показываем alert
        await callback.answer("⛔ Эта пара не из вашей группы", show_alert=True)
        return

    # Всё ок — подтверждаем и продолжаем как раньше
    await callback.answer(f"{status_names.get(status, status)} ({day_word})")

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


# ============ ПРОЧЕЕ ============

@router.message(F.text.contains("Помощь"))
async def show_help(message: types.Message):
    await message.answer(
        "ℹ️ **Помощь**\n\n"
        "📅 Расписание — пары на сегодня/завтра\n"
        "📚 ДЗ — домашние задания\n"
        "📝 Задолженности — твои долги\n"
        "✅ Посещение — отметить пары\n\n"
        "Если что-то не работает — @hiloetc"
    )


@router.message(Command("my_role"))
async def my_role(message: types.Message):
    user = get_user(message.from_user.id)
    if user:
        await message.answer(
            f"user_id: <code>{user[0]}</code>\nФИО: {user[4]}\nРоль: <code>{user[5]}</code>",
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

INFO_TEXT = """📌 <b>Добро пожаловать в учебный бот!</b>

🚀 <b>С чего начать:</b>
Напиши /start и пройди регистрацию: ВУЗ → факультет → группа → ФИО

👨‍🎓 <b>ДЛЯ СТУДЕНТОВ</b>

🗓 <b>Расписание</b>
Кнопка «📅 Расписание» → Сегодня / Завтра / 2 недели.
Видно: номер пары, время, предмет, тип занятия, преподаватель, аудитория. Учитывается числитель и знаменатель.

✅ <b>Посещение</b>
Кнопка «✅ Посещение» → Сегодня / Завтра.
Отметь: ✅ Буду ❌ Не приду 🤒 Заболел ⏰ Задержусь.

✍️ Каждый день в 14:00 бот присылает «Отметь явку на завтра» — одно сообщение со всеми парами и кнопками.

📕 <b>Домашние задания</b>
Кнопка «📚 ДЗ» — список заданий с дедлайном и файлами.
Отметь: ✅ Сделал / ❌ Не сделал.

📝 <b>Задолженности</b>
Кнопка «📝 Задолженности» — веди свой список долгов. Добавляй и удаляй через inline-кнопки.

👤 <b>Профиль</b>
Кнопка «👤 Профиль» — твои данные и настройки уведомлений.
Можно отдельно выключить напоминания о парах и рассылку явки.

🔔 <b>Напоминания</b>
За 30 минут до пары бот пришлёт: предмет, аудиторию, время, преподавателя.

👑 <b>ДЛЯ СТАРОСТ</b>

👑 <b>Панель старосты</b> — все инструменты управления группой.

➕ <b>Пара</b> — мастер добавления: неделя → день → номер → время → предмет → тип → преподаватель → аудитория.

➕ <b>ДЗ</b> — мастер добавления: предмет → задание → срок → файл.

👥 <b>Список группы</b> — все зарегистрированные студенты. Можно удалить (с перерегистрацией).

📊 <b>Посещаемость</b> — сегодня и завтра, компактно по парам.

📜 <b>Логи посещаемости</b> — за 7 дней:
📅 13.09.2026 (Сб)
  Иванов И.И.: 1 пара — ✅, 2 пара — ❌, 3 пара — ⏰

📢 <b>Рассылка по группе</b> — команда /group_broadcast.

🗑 <b>Удаление ДЗ</b> — прямо из карточки задания.

🏛 <b>ПРО ВУЗЫ</b>
РГРТУ — расписание тянется с сайта автоматически (каждый час и в 00:00 МСК).
РГУ — расписание заполняет староста вручную через мастер.
Данные двух вузов полностью разделены.

ℹ️ <b>ПРОЧЕЕ</b>
Кнопка «ℹ️ Помощь» — краткая инструкция.
Если что-то не работает — пиши: @hiloetc
Бот обновляется сам. Ничего делать не нужно."""


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(INFO_TEXT, parse_mode="HTML")


@router.message(F.text == "ℹ️ Инфо")
async def info_button(message: types.Message):
    await message.answer(INFO_TEXT, parse_mode="HTML")