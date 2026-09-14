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
)
from keyboards import (
    get_homework_actions_kb, get_attendance_kb,
    get_debts_menu_kb, get_debts_delete_kb,
    get_homework_starosta_kb,
    get_homework_confirm_delete_kb,
    get_tomorrow_attendance_all_kb,
    get_schedule_menu_kb,
    get_attendance_menu_kb,
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


# ============ МЕНЮ «РАСПИСАНИЕ» И «ПОСЕЩЕНИЕ» ============

@router.message(F.text == "📅 Расписание")
async def schedule_menu(message: types.Message):
    await message.answer("📅 Выбери период:", reply_markup=get_schedule_menu_kb())


@router.message(F.text == "✅ Посещение")
async def attendance_menu(message: types.Message):
    await message.answer("✅ Отметь посещение:", reply_markup=get_attendance_menu_kb())


# ============ РАСПИСАНИЕ ============

@router.message(F.text == "📅 Сегодня")
async def show_schedule_today(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    today = datetime.now(MSK)
    day_name = DAYS_RU[today.weekday()]
    week_type = get_current_week_type()
    date_str = today.strftime("%d.%m.%Y")
    date_iso = today.strftime("%Y-%m-%d")

    pairs = get_schedule(user[1], user[2], user[3], day_name, week_type)

    if not pairs:
        data = await fetch_schedule_from_api(user[3], date_iso)
        if data:
            api_pairs = parse_schedule_for_day(data, date_iso, week_type)
            for p in api_pairs:
                upsert_schedule_pair(
                    user[1], user[2], user[3], day_name, p["pair_number"],
                    p["subject"], p["teacher"], p["room"],
                    p["start_time"], p["end_time"], week_type=week_type,
                    lesson_type=p.get("lesson_type", "")
                )
            pairs = get_schedule(user[1], user[2], user[3], day_name, week_type)

    if not pairs:
        await message.answer(f"📅 На {day_name} ({week_type}) пар нет 🎉")
        return

    text = format_schedule_for_message(
        [{"pair_number": p[1], "subject": p[2], "teacher": p[3],
          "room": p[4], "start_time": p[5], "end_time": p[6],
          "lesson_type": p[8] if len(p) > 8 else ""}
         for p in pairs],
        day_name, week_type, date_str
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(F.text == "📅 Завтра")
async def show_schedule_tomorrow(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    tomorrow = datetime.now(MSK) + timedelta(days=1)
    day_name = DAYS_RU[tomorrow.weekday()]
    week_type = get_week_type_for_date(tomorrow.date())
    date_str = tomorrow.strftime("%d.%m.%Y")
    date_iso = tomorrow.strftime("%Y-%m-%d")

    pairs = get_schedule(user[1], user[2], user[3], day_name, week_type)

    if not pairs:
        data = await fetch_schedule_from_api(user[3], date_iso)
        if data:
            api_pairs = parse_schedule_for_day(data, date_iso, week_type)
            for p in api_pairs:
                upsert_schedule_pair(
                    user[1], user[2], user[3], day_name, p["pair_number"],
                    p["subject"], p["teacher"], p["room"],
                    p["start_time"], p["end_time"], week_type=week_type,
                    lesson_type=p.get("lesson_type", "")
                )
            pairs = get_schedule(user[1], user[2], user[3], day_name, week_type)

    if not pairs:
        await message.answer(f"📅 На {day_name} ({week_type}) пар нет 🎉")
        return

    text = format_schedule_for_message(
        [{"pair_number": p[1], "subject": p[2], "teacher": p[3],
          "room": p[4], "start_time": p[5], "end_time": p[6],
          "lesson_type": p[8] if len(p) > 8 else ""}
         for p in pairs],
        day_name, week_type, date_str
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(F.text == "📅 2 недели")
async def show_schedule_two_weeks(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    await message.answer("📅 **Расписание на 2 недели вперёд:**")

    today = datetime.now(MSK)
    for offset in range(14):
        target = today + timedelta(days=offset)
        day_name = DAYS_RU[target.weekday()]
        week_type = get_week_type_for_date(target.date())
        date_str = target.strftime("%d.%m.%Y")
        date_iso = target.strftime("%Y-%m-%d")

        pairs = get_schedule(user[1], user[2], user[3], day_name, week_type)
        if not pairs:
            data = await fetch_schedule_from_api(user[3], date_iso)
            if data:
                api_pairs = parse_schedule_for_day(data, date_iso, week_type)
                for p in api_pairs:
                    upsert_schedule_pair(
                        user[1], user[2], user[3], day_name, p["pair_number"],
                        p["subject"], p["teacher"], p["room"],
                        p["start_time"], p["end_time"], week_type=week_type,
                        lesson_type=p.get("lesson_type", "")
                    )
                pairs = get_schedule(user[1], user[2], user[3], day_name, week_type)
        if not pairs:
            continue

        week_icon = "🔵" if week_type == "числитель" else "🟢"
        text = f"📅 **{day_name}, {date_str}** {week_icon} {week_type}\n\n"
        for p in pairs:
            text += f"**{p[1]} пара** ({p[5]})\n"

            lesson_type = p[8] if len(p) > 8 else ""
            if lesson_type:
                lesson_type_full = LESSON_TYPE_NAMES.get(lesson_type, lesson_type)
                text += f"📌 {lesson_type_full}\n"

            text += f"📖 {p[2]}\n"
            if p[3]:
                text += f"👤 {p[3]}\n"
            if p[4]:
                text += f"🚪 {p[4]}\n"
            text += "\n"
        await message.answer(text, parse_mode="Markdown")


# ============ ОБНОВЛЕНИЕ РАСПИСАНИЯ ============

@router.message(F.text == "🔄 Обновить расписание")
async def student_update_schedule(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
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
        target_week = get_week_type_for_date(target.date())

        pairs = parse_schedule_for_day(data, target_iso, target_week)
        for p in pairs:
            existing = get_schedule_pair_by_key(
                user[1], user[2], user[3],
                day_name, target_week, p["pair_number"]
            )

            upsert_schedule_pair(
                user[1], user[2], user[3], day_name, p["pair_number"],
                p["subject"], p["teacher"], p["room"],
                p["start_time"], p["end_time"], week_type=target_week,
                lesson_type=p.get("lesson_type", "")
            )
            valid_keys.add((day_name, target_week, p["pair_number"]))

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

    today = datetime.now(MSK)
    day_name = DAYS_RU[today.weekday()]
    date_str = today.strftime("%d.%m.%Y")
    week_type = get_current_week_type()

    pairs = get_schedule(user[1], user[2], user[3], day_name, week_type)

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
        lesson_type_full = LESSON_TYPE_NAMES.get(lesson_type, lesson_type)

        text = f"**{num} пара** | {subject}\n"
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

    tomorrow = datetime.now(MSK) + timedelta(days=1)
    day_name = DAYS_RU[tomorrow.weekday()]
    date_str = tomorrow.strftime("%d.%m.%Y")
    week_type = get_week_type_for_date(tomorrow.date())

    pairs = get_schedule(user[1], user[2], user[3], day_name, week_type)

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
        lesson_type_full = LESSON_TYPE_NAMES.get(lesson_type, lesson_type)

        text = f"**{num} пара** | {subject}\n"
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

    status_names = {
        "will":   "✅ Буду на паре",
        "absent": "❌ Не приду",
        "sick":   "🤒 Заболел",
        "late":   "⏰ Задержусь",
    }
    day_word = "сегодня" if date_offset == 0 else "завтра"

    target_date = (datetime.now(MSK) + timedelta(days=date_offset)).strftime("%Y-%m-%d")
    set_attendance(callback.from_user.id, schedule_id, status, target_date)

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
        "✅ Посещение — отметить пары\n"
        "🔄 Обновить расписание — подтянуть свежие данные\n\n"
        "Если что-то не работает — @hiloetc"
    )


@router.message(F.text == "🌐 Сайт РГРТУ")
async def site_rsreu(message: types.Message):
    await message.answer("🌐 **Сайт РГРТУ:**\nhttps://rsreu.ru")


@router.message(F.text == "🌐 Сайт CDO")
async def site_cdo(message: types.Message):
    await message.answer("🌐 **Сайт CDO:**\nhttps://cdo.rsreu.ru")


@router.message(F.text == "🌐 Сайт EDU")
async def site_edu(message: types.Message):
    await message.answer("🌐 **Сайт EDU:**\nhttps://edu.rsreu.ru")


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