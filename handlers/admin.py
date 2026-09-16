from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, CallbackQuery
)
from datetime import datetime, timedelta
from collections import OrderedDict
import re
import os
import csv
import io

from parser import fetch_schedule_from_api, parse_schedule_for_day
from database import (
    get_user, add_homework, add_schedule_pair, get_all_groups,
    get_attendance_for_day_grouped,
    get_attendance_logs_week,
    delete_schedule_for_day, set_role, clear_schedule_for_group,
    get_group_members, delete_user_completely,
    get_schedule_pair_by_key,
    upsert_schedule_pair,
    delete_orphan_schedule_pairs,
    is_user_banned, ban_user, unban_user, get_banned_users,
    remove_starosta,
    get_pairs_for_delete,
    delete_schedule_pair_by_id,
    get_schedule_pair_info,
    get_pending_applications,
    get_application_by_id,
    approve_application,
    reject_application,
    get_all_starostas,
    # ===== новые =====
    backup_db,
    restore_db,
    create_promo_code,
    get_all_promo_codes,
    delete_promo_code,
    reset_user_xp,
    reset_group_xp,
    get_user_xp,
    get_group_attendance_month,
    DB_NAME,
)
from keyboards import (
    get_admin_panel_kb, get_main_menu,
    get_days_kb, get_confirm_kb,
    get_group_members_delete_kb, get_group_list_actions_kb,
    get_broadcast_confirm_kb, get_remove_starosta_confirm_kb,
    get_week_type_kb, get_days_kb_full,
    get_lesson_type_kb, get_subgroup_kb, get_period_end_kb,
    get_days_delete_kb,
    get_pairs_delete_kb,
    get_application_review_kb,
    get_applications_list_kb,
    get_admin_backup_kb,
    get_export_month_kb,
)
from config import (
    ADMIN_IDS, get_current_week_type, get_week_type_for_date,
    BACKUP_DIR, DEFAULT_PROMO_XP, DEFAULT_PROMO_USES,
)

from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")

router = Router()

DAYS_RU = {
    0: "Понедельник", 1: "Вторник", 2: "Среда",
    3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье"
}

STATUS_ICONS = {"will": "✅", "absent": "❌", "sick": "🤒", "late": "⏰"}


def _short_name(full_name):
    parts = full_name.strip().split()
    if len(parts) >= 3:
        return f"{parts[0]} {parts[1][0]}.{parts[2][0]}."
    elif len(parts) == 2:
        return f"{parts[0]} {parts[1][0]}."
    return full_name


def _is_admin(user_id):
    return user_id in ADMIN_IDS


def _escape_html(text):
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


# ============ МАСТЕР ДОБАВЛЕНИЯ ПАРЫ ============

class AddPair(StatesGroup):
    choosing_week_type = State()
    choosing_day = State()
    entering_number = State()
    entering_time = State()
    entering_subject = State()
    choosing_lesson_type = State()
    entering_teacher = State()
    entering_room = State()
    choosing_subgroup = State()
    choosing_period_end = State()
    entering_manual_date = State()
    confirming = State()


@router.message(F.text == "➕ Пара")
async def add_pair_start(message, state):
    user = get_user(message.from_user.id)
    if not user or user[5] != 'starosta':
        await message.answer("⛔ Только староста может добавлять пары.")
        return

    await state.clear()
    await message.answer(
        "📅 **Мастер добавления пары**\n\n"
        "**Шаг 1/9.** Выбери **тип недели**:",
        parse_mode="Markdown",
        reply_markup=get_week_type_kb()
    )
    await state.set_state(AddPair.choosing_week_type)


@router.callback_query(F.data.startswith("pw_"), AddPair.choosing_week_type)
async def pair_choose_week_type(callback, state):
    mapping = {"pw_num": "числитель", "pw_den": "знаменатель", "pw_any": None}
    week_type = mapping.get(callback.data)
    await state.update_data(week_type=week_type)

    label = week_type if week_type else "каждую неделю"
    await callback.message.edit_text(
        f"📅 Тип недели: **{label}**\n\n"
        f"**Шаг 2/9.** Выбери **день недели**:",
        parse_mode="Markdown",
        reply_markup=get_days_kb_full()
    )
    await state.set_state(AddPair.choosing_day)
    await callback.answer()


@router.callback_query(F.data.startswith("pd_"), AddPair.choosing_day)
async def pair_choose_day(callback, state):
    day = callback.data.replace("pd_", "")
    await state.update_data(day=day)
    await callback.message.edit_text(
        f"📅 День: **{day}**\n\n"
        f"**Шаг 3/9.** Введи **номер пары** числом (1–8):",
        parse_mode="Markdown"
    )
    await state.set_state(AddPair.entering_number)
    await callback.answer()


@router.message(AddPair.entering_number)
async def pair_enter_number(message, state):
    text = message.text.strip()
    if not text.isdigit() or not (1 <= int(text) <= 8):
        await message.answer("❌ Номер пары — число от 1 до 8.")
        return
    await state.update_data(pair_number=int(text))
    await message.answer(
        "⏰ **Шаг 4/9.** Введи **время начала пары** в формате `ЧЧ:ММ`\n"
        "Например: `09:55`",
        parse_mode="Markdown"
    )
    await state.set_state(AddPair.entering_time)


@router.message(AddPair.entering_time)
async def pair_enter_time(message, state):
    text = message.text.strip()
    if not re.match(r"^\d{1,2}:\d{2}$", text):
        await message.answer("❌ Формат: `ЧЧ:ММ`, например `09:55`", parse_mode="Markdown")
        return
    await state.update_data(start_time=text)
    await message.answer(
        "📖 **Шаг 5/9.** Введи **название предмета**:\n"
        "Например: `Математический анализ`",
        parse_mode="Markdown"
    )
    await state.set_state(AddPair.entering_subject)


@router.message(AddPair.entering_subject)
async def pair_enter_subject(message, state):
    await state.update_data(subject=message.text.strip())
    await message.answer(
        "📌 **Шаг 6/9.** Выбери **тип занятия**:",
        parse_mode="Markdown",
        reply_markup=get_lesson_type_kb()
    )
    await state.set_state(AddPair.choosing_lesson_type)


@router.callback_query(F.data.startswith("lt_"), AddPair.choosing_lesson_type)
async def pair_choose_lesson_type(callback, state):
    lesson_type_full = callback.data.replace("lt_", "")
    short_map = {
        "Лекция": "Лек.",
        "Лабораторная": "Лаб.",
        "Практика": "Пр.",
        "Семинар": "Сем.",
        "Курсовая": "Курс.",
    }
    await state.update_data(
        lesson_type=short_map.get(lesson_type_full, ""),
        lesson_type_full=lesson_type_full
    )
    await callback.message.edit_text(
        f"📌 Тип: **{lesson_type_full}**\n\n"
        f"**Шаг 7/9.** Введи **ФИО преподавателя** (или `-`):",
        parse_mode="Markdown"
    )
    await state.set_state(AddPair.entering_teacher)
    await callback.answer()


@router.message(AddPair.entering_teacher)
async def pair_enter_teacher(message, state):
    teacher = message.text.strip()
    if teacher == "-":
        teacher = ""
    await state.update_data(teacher=teacher)
    await message.answer(
        "🚪 **Шаг 8/9.** Введи **номер аудитории** (или `-`):",
        parse_mode="Markdown"
    )
    await state.set_state(AddPair.entering_room)


@router.message(AddPair.entering_room)
async def pair_enter_room(message, state):
    room = message.text.strip()
    if room == "-":
        room = ""
    await state.update_data(room=room)
    await message.answer(
        "👥 **Шаг 9/9.** Для какой **подгруппы** эта пара?",
        parse_mode="Markdown",
        reply_markup=get_subgroup_kb()
    )
    await state.set_state(AddPair.choosing_subgroup)


@router.callback_query(F.data.startswith("sg_"), AddPair.choosing_subgroup)
async def pair_choose_subgroup(callback, state):
    subgroup = int(callback.data.replace("sg_", ""))
    await state.update_data(subgroup=subgroup)

    label = "для всех" if subgroup == 0 else f"{subgroup} подгруппа"
    await callback.message.edit_text(
        f"👥 Подгруппа: **{label}**\n\n"
        f"📆 До какого **периода** действует эта пара?",
        parse_mode="Markdown",
        reply_markup=get_period_end_kb()
    )
    await state.set_state(AddPair.choosing_period_end)
    await callback.answer()


@router.callback_query(F.data.startswith("pe_"), AddPair.choosing_period_end)
async def pair_choose_period_end(callback, state):
    action = callback.data.replace("pe_", "")
    today = datetime.now(MSK)

    if action == "semester":
        year = today.year if today.month <= 8 else today.year + 1
        valid_until = f"{year}-12-31"
        await state.update_data(valid_until=valid_until)
        await _pair_show_confirm(callback.message, state, edit=True)
        await callback.answer()
        return

    if action == "month":
        if today.month == 12:
            valid_until = f"{today.year}-12-31"
        else:
            next_month = today.replace(day=1, month=today.month + 1)
            last_day = (next_month - timedelta(days=1)).day
            valid_until = f"{today.year}-{today.month:02d}-{last_day:02d}"
        await state.update_data(valid_until=valid_until)
        await _pair_show_confirm(callback.message, state, edit=True)
        await callback.answer()
        return

    if action == "manual":
        await callback.message.edit_text(
            "📆 Введи дату окончания в формате `ДД.ММ.ГГГГ`\n"
            "Например: `25.12.2026`",
            parse_mode="Markdown"
        )
        await state.set_state(AddPair.entering_manual_date)
        await callback.answer()
        return


@router.message(AddPair.entering_manual_date)
async def pair_enter_manual_date(message, state):
    text = message.text.strip()
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", text)
    if not m:
        await message.answer("❌ Формат: `ДД.ММ.ГГГГ`, например `25.12.2026`", parse_mode="Markdown")
        return
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        valid_until = f"{year:04d}-{month:02d}-{day:02d}"
        datetime.strptime(valid_until, "%Y-%m-%d")
    except ValueError:
        await message.answer("❌ Некорректная дата.")
        return
    await state.update_data(valid_until=valid_until)
    await _pair_show_confirm(message, state, edit=False)


async def _pair_show_confirm(message_or_msg, state, edit=False):
    data = await state.get_data()

    week_label = data.get('week_type') or "каждую неделю"
    sg = data.get('subgroup', 0)
    sg_label = "для всех" if sg == 0 else f"{sg} подгруппа"
    valid_until = data.get('valid_until') or "—"
    lesson_full = data.get('lesson_type_full') or "—"

    text = (
        f"**Проверь пару:**\n\n"
        f"📆 Неделя: **{week_label}**\n"
        f"📅 День: **{data['day']}**\n"
        f"🔢 Номер: **{data['pair_number']}**\n"
        f"⏰ Начало: **{data['start_time']}**\n"
        f"📖 Предмет: **{data['subject']}**\n"
        f"📌 Тип: **{lesson_full}**\n"
        f"👤 Преподаватель: **{data.get('teacher') or '—'}**\n"
        f"🚪 Аудитория: **{data.get('room') or '—'}**\n"
        f"👥 Подгруппа: **{sg_label}**\n"
        f"📆 Действует до: **{valid_until}**\n\n"
        f"Сохранить?"
    )

    kb = get_confirm_kb("pairconfirm")

    if edit:
        await message_or_msg.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await message_or_msg.answer(text, parse_mode="Markdown", reply_markup=kb)

    await state.set_state(AddPair.confirming)


@router.callback_query(F.data == "pairconfirm_yes", AddPair.confirming)
async def pair_confirm_yes(callback, state):
    data = await state.get_data()
    user = get_user(callback.from_user.id)

    week_type = data.get('week_type')
    weeks = [week_type] if week_type else ["числитель", "знаменатель"]

    for wt in weeks:
        add_schedule_pair(
            university=user[1], faculty=user[2], group_name=user[3],
            day=data['day'], pair_num=data['pair_number'],
            subject=data['subject'],
            teacher=data.get('teacher', ''),
            room=data.get('room', ''),
            start=data['start_time'], end="",
            week_type=wt,
            lesson_type=data.get('lesson_type', ''),
            subgroup=data.get('subgroup', 0),
            valid_until=data.get('valid_until'),
            lesson_type_full=data.get('lesson_type_full', ''),
        )

    week_label = week_type if week_type else "каждую неделю"
    sg = data.get('subgroup', 0)
    sg_label = "для всех" if sg == 0 else f"{sg} подгруппа"

    await callback.message.edit_text(
        f"✅ **Пара сохранена!**\n\n"
        f"📆 Неделя: **{week_label}**\n"
        f"📅 {data['day']}, {data['pair_number']} пара\n"
        f"📌 {data.get('lesson_type_full', '')}\n"
        f"📖 {data['subject']}\n"
        f"⏰ {data['start_time']}\n"
        f"👥 {sg_label}\n"
        f"📆 До: {data.get('valid_until') or '—'}",
        parse_mode="Markdown"
    )
    await callback.message.answer("Панель старосты:", reply_markup=get_admin_panel_kb(university=user[1]))
    await state.clear()
    await callback.answer("Сохранено")


@router.callback_query(F.data == "pairconfirm_no", AddPair.confirming)
async def pair_confirm_no(callback, state):
    await callback.message.edit_text("❌ Отменено.")
    await callback.message.answer("Панель старосты:", reply_markup=get_admin_panel_kb(university=user[1]))
    await state.clear()
    await callback.answer("Отменено")


# ============ ПАНЕЛЬ СТАРОСТЫ ============

@router.message(F.text == "👑 Панель старосты")
async def admin_panel(message):
    user = get_user(message.from_user.id)
    if not user or user[5] != 'starosta':
        await message.answer("⛔ У тебя нет прав старосты.")
        return
    await message.answer("👑 Панель старосты", reply_markup=get_admin_panel_kb(university=user[1]))


@router.message(F.text == "🔙 Назад")
async def back_to_menu(message):
    user = get_user(message.from_user.id)
    is_admin = user[5] == 'starosta' if user else False
    university = user[1] if user else None
    await message.answer(
        "🏠 Главное меню:",
        reply_markup=get_main_menu(is_admin, university=university)
    )


# ============ МАСТЕР ДОБАВЛЕНИЯ ДЗ ============

class AddHomework(StatesGroup):
    entering_subject = State()
    entering_task = State()
    entering_deadline = State()
    attaching_file = State()
    confirming = State()


@router.message(F.text == "➕ ДЗ")
async def add_hw_start(message, state):
    user = get_user(message.from_user.id)
    if not user or user[5] != 'starosta':
        await message.answer("⛔ Только староста может добавлять ДЗ.")
        return
    await message.answer("📚 **Мастер добавления ДЗ**\n\n**Шаг 1/4.** Введи **предмет**:", parse_mode="Markdown")
    await state.set_state(AddHomework.entering_subject)


@router.message(AddHomework.entering_subject)
async def hw_enter_subject(message, state):
    await state.update_data(subject=message.text.strip())
    await message.answer("**Шаг 2/4.** Введи **задание** (можно многострочно):", parse_mode="Markdown")
    await state.set_state(AddHomework.entering_task)


@router.message(AddHomework.entering_task)
async def hw_enter_task(message, state):
    await state.update_data(task=message.text.strip())
    await message.answer("**Шаг 3/4.** Введи **срок сдачи** в формате `ДД.ММ` (например `25.12`).\n\nЕсли срока нет — напиши `-`.", parse_mode="Markdown")
    await state.set_state(AddHomework.entering_deadline)


@router.message(AddHomework.entering_deadline)
async def hw_enter_deadline(message, state):
    text = message.text.strip()
    deadline = None
    if text and text != "-":
        match = re.match(r"^(\d{1,2})[.\-/](\d{1,2})$", text)
        if not match:
            await message.answer("❌ Неверный формат. Введи `ДД.ММ` (например `25.12`) или `-`.", parse_mode="Markdown")
            return
        day, month = int(match.group(1)), int(match.group(2))
        year = datetime.now(MSK).year
        if month < datetime.now(MSK).month:
            year += 1
        try:
            deadline = f"{year:04d}-{month:02d}-{day:02d}"
        except Exception:
            await message.answer("❌ Неверная дата.")
            return
    await state.update_data(deadline=deadline)
    await message.answer("**Шаг 4/4.** Прикрепи **файл** к ДЗ (или напиши `-`).", parse_mode="Markdown")
    await state.set_state(AddHomework.attaching_file)


@router.message(AddHomework.attaching_file, F.document)
async def hw_attach_file(message, state):
    file_id = message.document.file_id
    file_name = message.document.file_name or "файл"
    await state.update_data(file_id=file_id, file_name=file_name)
    await _hw_show_confirm(message, state)


@router.message(AddHomework.attaching_file, F.text)
async def hw_skip_file(message, state):
    if message.text.strip() != "-":
        await message.answer("❌ Отправь документ как вложение или напиши `-`.")
        return
    await state.update_data(file_id=None, file_name=None)
    await _hw_show_confirm(message, state)


async def _hw_show_confirm(message, state):
    data = await state.get_data()
    deadline_text = data.get("deadline") or "без срока"
    file_text = data.get("file_name") or "нет"
    text = (
        f"**Проверь ДЗ:**\n\n"
        f"📖 Предмет: **{data['subject']}**\n"
        f"📝 Задание: {data['task']}\n"
        f"⏰ Срок: **{deadline_text}**\n"
        f"📎 Файл: {file_text}\n\n"
        f"Сохранить?"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_confirm_kb("hwconfirm"))
    await state.set_state(AddHomework.confirming)


@router.callback_query(F.data == "hwconfirm_yes", AddHomework.confirming)
async def hw_confirm_yes(callback, state):
    data = await state.get_data()
    user = get_user(callback.from_user.id)
    add_homework(
        university=user[1], faculty=user[2], group_name=user[3],
        subject=data['subject'], task=data['task'],
        deadline=data.get('deadline'), file_id=data.get('file_id')
    )
    deadline_text = data.get("deadline") or "без срока"
    await callback.message.edit_text(
        f"✅ **ДЗ добавлено!**\n\n📖 {data['subject']}\n📝 {data['task']}\n⏰ Срок: **{deadline_text}**",
        parse_mode="Markdown"
    )
    await callback.message.answer("Панель старосты:", reply_markup=get_admin_panel_kb(university=user[1]))
    await state.clear()
    await callback.answer("Сохранено")


@router.callback_query(F.data == "hwconfirm_no", AddHomework.confirming)
async def hw_confirm_no(callback, state):
    await callback.message.edit_text("❌ Отменено.")
    await callback.message.answer("Панель старосты:", reply_markup=get_admin_panel_kb(university=user[1]))
    await state.clear()
    await callback.answer("Отменено")


# ============ ПОСЕЩАЕМОСТЬ ============

@router.message(F.text == "📊 Посещаемость")
async def show_group_attendance(message):
    user = get_user(message.from_user.id)
    if not user or user[5] != 'starosta':
        return
    for offset, label in [(0, "сегодня"), (1, "завтра")]:
        target = datetime.now(MSK) + timedelta(days=offset)
        target_date = target.strftime("%Y-%m-%d")
        date_display = target.strftime("%d.%m.%Y")
        rows = get_attendance_for_day_grouped(user[1], user[2], user[3], target_date)
        if not rows:
            await message.answer(f"📊 **Посещаемость на {label}** ({date_display})\n_Никто ещё не отметился._", parse_mode="Markdown")
            continue
        pairs_dict = OrderedDict()
        for pair_num, subject, start_time, full_name, status in rows:
            key = (pair_num, subject, start_time)
            if key not in pairs_dict:
                pairs_dict[key] = []
            pairs_dict[key].append((full_name, status))
        text = f"📊 **Посещаемость на {label}** ({date_display})\n\n"
        for (pair_num, subject, start_time), students in pairs_dict.items():
            text += f"**{pair_num} пара — {subject}** ({start_time})\n"
            for full_name, status in students:
                icon = STATUS_ICONS.get(status, "?")
                text += f"{icon} {_short_name(full_name)}\n"
            text += "\n"
        text += "✅ Буду  ❌ Не приду  🤒 Заболел  ⏰ Задержусь"
        await message.answer(text, parse_mode="Markdown")


@router.message(F.text == "📜 Логи посещаемости")
async def show_attendance_logs(message):
    user = get_user(message.from_user.id)
    if not user or user[5] != 'starosta':
        await message.answer("⛔ Только староста может смотреть логи.")
        return

    await message.answer("📜 Загружаю логи за последнюю неделю...")

    rows = get_attendance_logs_week(user[1], user[2], user[3], days=7)

    if not rows:
        await message.answer("📜 За последнюю неделю никто не отмечался.")
        return

    logs_by_date = OrderedDict()
    for date, full_name, pair_num, subject, status in rows:
        if date not in logs_by_date:
            logs_by_date[date] = OrderedDict()
        if full_name not in logs_by_date[date]:
            logs_by_date[date][full_name] = {}
        logs_by_date[date][full_name][pair_num] = status

    text = f"📜 <b>Логи посещаемости группы {user[3]}</b>\n"
    text += f"Период: последние 7 дней\n\n"

    status_icons = {
        "will": "✅", "absent": "❌", "sick": "🤒", "late": "⏰"
    }

    for date, students in logs_by_date.items():
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
            day_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][dt.weekday()]
            date_display = f"{dt.strftime('%d.%m.%Y')} ({day_ru})"
        except Exception:
            date_display = date

        text += f"📅 <b>{date_display}</b>\n"

        for full_name in sorted(students.keys()):
            short = _short_name(full_name)
            pairs_info = []
            for pair_num in sorted(students[full_name].keys()):
                status = students[full_name][pair_num]
                icon = status_icons.get(status, "?")
                pairs_info.append(f"{pair_num} пара — {icon}")
            text += f"  <b>{short}</b>: {', '.join(pairs_info)}\n"

        text += "\n"

    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await message.answer(text[i:i+4000], parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")


# ============ НАЗНАЧЕНИЕ СТАРОСТЫ ============

@router.message(Command("make_starosta"))
async def make_starosta(message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Только админ может назначать старост.")
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Формат: `/make_starosta <user_id>`", parse_mode="Markdown")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом.")
        return
    user = get_user(target_id)
    if not user:
        await message.answer(f"❌ Пользователь с ID {target_id} не зарегистрирован.")
        return
    set_role(target_id, "starosta")
    await message.answer(f"✅ {user[4]} (ID {target_id}) теперь староста.\nВУЗ: {user[1]}\nГруппа: {user[3]}")


# ============ СПИСОК ГРУППЫ ============

@router.message(F.text == "👥 Список группы")
async def show_group_list(message):
    user = get_user(message.from_user.id)
    if not user or user[5] != 'starosta':
        await message.answer("⛔ Только староста может смотреть список группы.")
        return
    members = get_group_members(user[1], user[2], user[3])
    if not members:
        await message.answer("👥 В группе пока никто не зарегистрировался.")
        return
    starostas = [m for m in members if m[2] == 'starosta']
    students = [m for m in members if m[2] != 'starosta']
    text = f"👥 **Список группы {user[3]}**\n🏛 {user[1]} | {user[2]}\n👤 Всего зарегистрировано: **{len(members)}**\n\n"
    if starostas:
        text += "**👑 Староста:**\n"
        for user_id, full_name, role in starostas:
            text += f"• {full_name} (`{user_id}`)\n"
        text += "\n"
    if students:
        text += f"**🎓 Студенты ({len(students)}):**\n"
        for i, (user_id, full_name, role) in enumerate(students, 1):
            text += f"{i}. {full_name}\n"
        text += "\n"
    text += "_Список показывает только тех, кто зарегистрировался в боте._"
    if students:
        await message.answer(text, parse_mode="Markdown", reply_markup=get_group_list_actions_kb())
    else:
        await message.answer(text, parse_mode="Markdown")


# ============ УДАЛЕНИЕ СТУДЕНТОВ ============

@router.callback_query(F.data == "group_list_delete_menu")
async def delete_member_menu(callback):
    user = get_user(callback.from_user.id)
    if not user or user[5] != 'starosta':
        await callback.answer("⛔ Только староста может удалять студентов.", show_alert=True)
        return
    members = get_group_members(user[1], user[2], user[3])
    students = [m for m in members if m[2] != 'starosta']
    if not students:
        await callback.answer("Нет студентов для удаления.", show_alert=True)
        return
    await callback.message.edit_text(
        "🗑 **Выбери студента для удаления**\n\n⚠️ Удалённый студент **не сможет** пользоваться ботом, пока не пройдёт регистрацию заново.\n\n_Старост удалять нельзя._",
        parse_mode="Markdown", reply_markup=get_group_members_delete_kb(members)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("del_member_"))
async def delete_member_confirm(callback, bot: Bot):
    if callback.data == "del_member_back":
        user = get_user(callback.from_user.id)
        if user and user[5] == 'starosta':
            members = get_group_members(user[1], user[2], user[3])
            starostas = [m for m in members if m[2] == 'starosta']
            students = [m for m in members if m[2] != 'starosta']
            text = f"👥 **Список группы {user[3]}**\n🏛 {user[1]} | {user[2]}\n👤 Всего зарегистрировано: **{len(members)}**\n\n"
            if starostas:
                text += "**👑 Староста:**\n"
                for user_id, full_name, role in starostas:
                    text += f"• {full_name} (`{user_id}`)\n"
                text += "\n"
            if students:
                text += f"**🎓 Студенты ({len(students)}):**\n"
                for i, (user_id, full_name, role) in enumerate(students, 1):
                    text += f"{i}. {full_name}\n"
                text += "\n"
            text += "_Список показывает только тех, кто зарегистрировался в боте._"
            if students:
                await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_group_list_actions_kb())
            else:
                await callback.message.edit_text(text, parse_mode="Markdown")
        await callback.answer()
        return
    admin_user = get_user(callback.from_user.id)
    if not admin_user or admin_user[5] != 'starosta':
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    target_id = int(callback.data.replace("del_member_", ""))
    target_user = get_user(target_id)
    if not target_user:
        await callback.answer("❌ Пользователь уже удалён.", show_alert=True)
        return
    if target_user[5] == 'starosta':
        await callback.answer("⛔ Нельзя удалить старосту.", show_alert=True)
        return
    target_name = target_user[4]
    target_group = target_user[3]
    deleted = delete_user_completely(target_id)
    if not deleted:
        await callback.answer("❌ Не удалось удалить.", show_alert=True)
        return
    try:
        await bot.send_message(target_id, f"⚠️ **Вы были удалены из группы {target_group}** старостой.\n\nЧтобы снова пользоваться ботом, пройдите регистрацию заново: /start", parse_mode="Markdown")
    except Exception as e:
        print(f"[admin] Не удалось уведомить {target_id}: {e}")
    await callback.answer(f"✅ {target_name} удалён из группы", show_alert=True)
    members = get_group_members(admin_user[1], admin_user[2], admin_user[3])
    students = [m for m in members if m[2] != 'starosta']
    if not students:
        await callback.message.edit_text(f"✅ Студент **{target_name}** удалён.\n\n👥 В группе больше нет студентов для удаления.", parse_mode="Markdown")
        return
    await callback.message.edit_text(f"✅ Студент **{target_name}** удалён.\n\n🗑 **Оставшиеся студенты:**\n_Нажми ❌, чтобы удалить ещё одного._", parse_mode="Markdown", reply_markup=get_group_members_delete_kb(members))


# ============ БЛОКИРОВКА ============

@router.message(Command("ban"))
async def ban_command(message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ может банить.")
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("📝 **Формат:**\n\n`/ban <user_id> [причина]`\n`/ban @username [причина]`", parse_mode="Markdown")
        return
    target = parts[1].strip()
    reason = parts[2] if len(parts) > 2 else ""
    if target.startswith("@"):
        username = target.lstrip("@").lower()
        if is_user_banned(username=username):
            await message.answer(f"⚠️ Пользователь `@{username}` уже забанен.", parse_mode="Markdown")
            return
        ban_user(username=username, reason=reason, banned_by=message.from_user.id)
        text = f"✅ Пользователь `@{username}` забанен."
        if reason:
            text += f"\n**Причина:** {reason}"
        await message.answer(text, parse_mode="Markdown")
    else:
        try:
            target_id = int(target)
        except ValueError:
            await message.answer("❌ Укажи числовой ID или @username.", parse_mode="Markdown")
            return
        if _is_admin(target_id):
            await message.answer("⛔ Нельзя забанить администратора.")
            return
        if is_user_banned(target_id):
            await message.answer(f"⚠️ Пользователь `{target_id}` уже забанен.", parse_mode="Markdown")
            return
        ban_user(user_id=target_id, reason=reason, banned_by=message.from_user.id)
        try:
            text = "⛔ **Вы были заблокированы администратором.**"
            if reason:
                text += f"\n\n**Причина:** {reason}"
            await message.bot.send_message(target_id, text, parse_mode="Markdown")
        except Exception as e:
            print(f"[admin] Не удалось уведомить {target_id}: {e}")
        text = f"✅ Пользователь `{target_id}` забанен."
        if reason:
            text += f"\n**Причина:** {reason}"
        await message.answer(text, parse_mode="Markdown")


@router.message(Command("unban"))
async def unban_command(message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ может разбанивать.")
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("📝 **Формат:**\n\n`/unban <user_id>`\n`/unban @username`", parse_mode="Markdown")
        return
    target = parts[1].strip()
    if target.startswith("@"):
        username = target.lstrip("@").lower()
        if not is_user_banned(username=username):
            await message.answer(f"⚠️ Пользователь `@{username}` не забанен.", parse_mode="Markdown")
            return
        unban_user(username=username)
        await message.answer(f"✅ Пользователь `@{username}` разбанен.", parse_mode="Markdown")
    else:
        try:
            target_id = int(target)
        except ValueError:
            await message.answer("❌ Укажи числовой ID или @username.", parse_mode="Markdown")
            return
        if not is_user_banned(target_id):
            await message.answer(f"⚠️ Пользователь `{target_id}` не забанен.", parse_mode="Markdown")
            return
        unban_user(user_id=target_id)
        try:
            await message.bot.send_message(target_id, "✅ **Вы разблокированы.**\n\nМожете снова пользоваться ботом: /start", parse_mode="Markdown")
        except Exception as e:
            print(f"[admin] Не удалось уведомить {target_id}: {e}")
        await message.answer(f"✅ Пользователь `{target_id}` разбанен.", parse_mode="Markdown")


# ============ /users, /user, /banlist ============

from database import get_all_users, count_users, get_user_details
from keyboards import (
    get_users_pagination_kb,
    get_user_info_kb,
    get_user_delete_confirm_kb,
)

USERS_PER_PAGE = 10


def _format_user_row(user):
    user_id = user[0]
    university = user[1]
    group_name = user[3]
    full_name = user[4]
    role = user[5]
    registered_at = user[6]
    username = user[10] if len(user) > 10 else None

    role_icon = "👑" if role == "starosta" else "🎓"
    full_name_safe = _escape_html(full_name)
    group_safe = _escape_html(group_name or "")
    uni_safe = _escape_html(university or "")

    if username:
        username_str = f"@{_escape_html(username)}"
    else:
        username_str = "<i>без username</i>"

    return (
        f"{role_icon} <b>{full_name_safe}</b>\n"
        f"   {username_str}\n"
        f"   🎓 {uni_safe} | {group_safe}\n"
        f"   🆔 <code>{user_id}</code> | {registered_at[:10]}"
    )


def _format_user_details(user):
    user_id = user[0]
    university = user[1]
    faculty = user[2]
    group_name = user[3]
    full_name = user[4]
    role = user[5]
    registered_at = user[6]
    notif = user[7]
    username = user[10] if len(user) > 10 else None

    role_text = "👑 Староста" if role == "starosta" else "🎓 Студент"
    notif_text = "🔔 Включены" if notif else "🔕 Отключены"
    if username:
        username_str = f"@{_escape_html(username)}"
    else:
        username_str = "<i>без username</i>"

    # XP
    xp, level, streak = get_user_xp(user_id)

    return (
        f"👤 <b>Информация о пользователе</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"<b>Username:</b> {username_str}\n"
        f"<b>ФИО:</b> {_escape_html(full_name)}\n"
        f"<b>Роль:</b> {role_text}\n\n"
        f"🏛 <b>ВУЗ:</b> {_escape_html(university)}\n"
        f"<b>Факультет:</b> {_escape_html(faculty)}\n"
        f"<b>Группа:</b> {_escape_html(group_name)}\n\n"
        f"🎖 <b>XP:</b> {int(xp)} | <b>Уровень:</b> {level} | <b>Streak:</b> {streak}\n\n"
        f"📅 <b>Зарегистрирован:</b> {registered_at[:19]}\n"
        f"🔔 <b>Уведомления:</b> {notif_text}"
    )


async def _send_users_page(message: types.Message, page: int):
    total = count_users()
    total_pages = (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE

    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1

    offset = page * USERS_PER_PAGE
    users = get_all_users(limit=USERS_PER_PAGE, offset=offset)

    text = f"📋 <b>Всего пользователей: {total}</b>\n"
    text += f"📄 Страница {page + 1} из {total_pages}\n\n"

    for user in users:
        text += _format_user_row(user) + "\n\n"

    text += "Для подробной информации: /user &lt;user_id&gt;"

    kb = get_users_pagination_kb(page, total_pages)

    if hasattr(message, "edit_text"):
        try:
            await message.edit_text(text, parse_mode="HTML", reply_markup=kb)
            return
        except Exception:
            pass

    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.message(Command("users"))
async def cmd_users(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ может смотреть список.")
        return

    total = count_users()
    if total == 0:
        await message.answer("📋 Список пользователей пуст.")
        return

    await _send_users_page(message, page=0)


@router.message(Command("user"))
async def cmd_user(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ может смотреть.")
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.answer(
            "📝 <b>Формат:</b> <code>/user &lt;user_id&gt;</code>\n\n<b>Пример:</b> <code>/user 123456789</code>",
            parse_mode="HTML"
        )
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом.")
        return

    user = get_user_details(target_id)
    if not user:
        await message.answer(f"❌ Пользователь с ID <code>{target_id}</code> не зарегистрирован.", parse_mode="HTML")
        return

    text = _format_user_details(user)
    is_star = user[5] == 'starosta'
    await message.answer(text, parse_mode="HTML", reply_markup=get_user_info_kb(target_id, is_starosta=is_star))


@router.callback_query(F.data.startswith("users_page_"))
async def users_page_nav(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    try:
        page = int(callback.data.replace("users_page_", ""))
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return
    await _send_users_page(callback.message, page)
    await callback.answer()


@router.callback_query(F.data == "users_close")
async def users_close(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.answer("Закрыто")


@router.callback_query(F.data == "user_close")
async def user_close(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.answer("Закрыто")


# ============ УДАЛЕНИЕ ПОЛЬЗОВАТЕЛЯ ============

@router.callback_query(F.data.startswith("user_delete_yes_"))
async def user_delete_yes(callback: types.CallbackQuery, bot: Bot):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    try:
        target_id = int(callback.data.replace("user_delete_yes_", ""))
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    user = get_user(target_id)
    if not user:
        await callback.answer("❌ Пользователь уже удалён.", show_alert=True)
        return

    if _is_admin(target_id):
        await callback.answer("⛔ Нельзя удалить администратора.", show_alert=True)
        return

    target_name = user[4]
    target_group = user[3]

    deleted = delete_user_completely(target_id)

    if not deleted:
        await callback.answer("❌ Не удалось удалить.", show_alert=True)
        return

    try:
        await bot.send_message(
            target_id,
            f"⚠️ <b>Ваш аккаунт был удалён администратором.</b>\n\n"
            f"Чтобы снова пользоваться ботом, пройдите регистрацию заново: /start",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"[admin] Не удалось уведомить {target_id}: {e}")

    await callback.message.edit_text(
        f"✅ <b>Пользователь удалён</b>\n\n"
        f"👤 {_escape_html(target_name)}\n"
        f"🆔 <code>{target_id}</code>\n"
        f"🎓 Группа: {_escape_html(target_group)}",
        parse_mode="HTML"
    )
    await callback.answer("Удалено", show_alert=True)


@router.callback_query(F.data.startswith("user_delete_no_"))
async def user_delete_no(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Удаление отменено.")
    await callback.answer("Отменено")


@router.callback_query(F.data.startswith("user_delete_"))
async def user_delete_start(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    try:
        target_id = int(callback.data.replace("user_delete_", ""))
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    user = get_user(target_id)
    if not user:
        await callback.answer("❌ Пользователь уже удалён.", show_alert=True)
        return

    if _is_admin(target_id):
        await callback.answer("⛔ Нельзя удалить администратора.", show_alert=True)
        return

    text = _format_user_details(user)

    await callback.message.edit_text(
        f"{text}\n\n"
        f"⚠️ <b>Удалить этого пользователя?</b>\n\n"
        f"<i>Он получит уведомление и сможет зарегистрироваться заново через /start.</i>",
        parse_mode="HTML",
        reply_markup=get_user_delete_confirm_kb(target_id)
    )
    await callback.answer()


@router.message(Command("banlist"))
async def banlist_command(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ может смотреть список.")
        return

    banned = get_banned_users()

    if not banned:
        await message.answer("📋 Список забаненных пуст.")
        return

    text = f"📋 <b>Забаненные пользователи ({len(banned)}):</b>\n\n"
    for ban_id, user_id, username, reason, banned_at in banned:
        if user_id:
            text += f"• ID: <code>{user_id}</code>"
        if username:
            if user_id:
                text += f" | @{_escape_html(username)}"
            else:
                text += f"• @{_escape_html(username)}"
        if reason:
            text += f"\n  <b>Причина:</b> {_escape_html(reason)}"
        text += f"\n  <i>{banned_at[:16]}</i>\n\n"

    text += "<i>Разбанить: /unban &lt;user_id&gt; или /unban @username</i>"

    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await message.answer(text[i:i+4000], parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")


# ============ РАССЫЛКА ============

from database import get_all_user_ids, get_group_user_ids


class BroadcastStates(StatesGroup):
    waiting_message_all = State()
    waiting_message_group = State()
    confirming_all = State()
    confirming_group = State()


@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ может делать рассылку.")
        return
    total = count_users()
    if total == 0:
        await message.answer("📋 В боте нет зарегистрированных пользователей.")
        return
    await message.answer(
        f"📢 <b>Рассылка всем пользователям</b>\n\n"
        f"👥 Получателей: <b>{total}</b>\n\n"
        f"Отправь сообщение для рассылки (можно с фото, видео, документом).\n\n"
        f"<i>Для отмены — /cancel</i>",
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.waiting_message_all)


@router.message(BroadcastStates.waiting_message_all)
async def broadcast_all_preview(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Рассылка отменена.")
        return
    await state.update_data(
        from_chat_id=message.chat.id,
        message_id=message.message_id,
    )
    total = count_users()
    await message.answer(
        f"📢 <b>Подтверди рассылку</b>\n\n"
        f"👥 Получателей: <b>{total}</b>\n\n"
        f"Отправить это сообщение всем?",
        parse_mode="HTML",
        reply_markup=get_broadcast_confirm_kb("all")
    )
    await state.set_state(BroadcastStates.confirming_all)


@router.callback_query(F.data == "broadcast_yes_all", BroadcastStates.confirming_all)
async def broadcast_all_send(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    from_chat_id = data.get("from_chat_id")
    message_id = data.get("message_id")

    if not from_chat_id or not message_id:
        await callback.answer("❌ Сообщение потеряно.", show_alert=True)
        await state.clear()
        return

    user_ids = get_all_user_ids()
    total = len(user_ids)

    await callback.message.edit_text(
        f"📤 <b>Рассылаю...</b>\n\n👥 Получателей: {total}",
        parse_mode="HTML"
    )

    success = 0
    failed = 0

    for user_id in user_ids:
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=from_chat_id,
                message_id=message_id
            )
            success += 1
        except Exception as e:
            failed += 1
            print(f"[broadcast] Не удалось отправить {user_id}: {e}")

    await callback.message.edit_text(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"📤 Отправлено: <b>{success}</b>\n"
        f"❌ Не дошло: <b>{failed}</b>\n"
        f"👥 Всего: {total}",
        parse_mode="HTML"
    )
    await state.clear()
    await callback.answer("Готово")


@router.callback_query(F.data == "broadcast_no_all", BroadcastStates.confirming_all)
async def broadcast_all_cancel(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Рассылка отменена.")
    await state.clear()
    await callback.answer("Отменено")


@router.message(Command("group_broadcast"))
async def cmd_group_broadcast(message: types.Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user or user[5] != 'starosta':
        await message.answer("⛔ Только староста может делать рассылку по группе.")
        return

    user_ids = get_group_user_ids(user[1], user[2], user[3])
    total = len(user_ids)

    if total == 0:
        await message.answer("📋 В твоей группе нет зарегистрированных.")
        return

    await message.answer(
        f"📢 <b>Рассылка по группе {user[3]}</b>\n\n"
        f"👥 Получателей: <b>{total}</b>\n\n"
        f"Отправь сообщение для рассылки (можно с фото, видео, документом).\n\n"
        f"<i>Для отмены — /cancel</i>",
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.waiting_message_group)


@router.message(BroadcastStates.waiting_message_group)
async def broadcast_group_preview(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Рассылка отменена.")
        return
    user = get_user(message.from_user.id)
    if not user or user[5] != 'starosta':
        await state.clear()
        await message.answer("⛔ Только староста.")
        return
    await state.update_data(
        from_chat_id=message.chat.id,
        message_id=message.message_id,
    )
    user_ids = get_group_user_ids(user[1], user[2], user[3])
    total = len(user_ids)
    await message.answer(
        f"📢 <b>Подтверди рассылку по группе {user[3]}</b>\n\n"
        f"👥 Получателей: <b>{total}</b>\n\n"
        f"Отправить это сообщение?",
        parse_mode="HTML",
        reply_markup=get_broadcast_confirm_kb("group")
    )
    await state.set_state(BroadcastStates.confirming_group)


@router.callback_query(F.data == "broadcast_yes_group", BroadcastStates.confirming_group)
async def broadcast_group_send(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    user = get_user(callback.from_user.id)
    if not user or user[5] != 'starosta':
        await callback.answer("⛔ Нет прав.", show_alert=True)
        await state.clear()
        return

    data = await state.get_data()
    from_chat_id = data.get("from_chat_id")
    message_id = data.get("message_id")

    if not from_chat_id or not message_id:
        await callback.answer("❌ Сообщение потеряно.", show_alert=True)
        await state.clear()
        return

    user_ids = get_group_user_ids(user[1], user[2], user[3])
    total = len(user_ids)

    await callback.message.edit_text(
        f"📤 <b>Рассылаю по группе {user[3]}...</b>\n\n👥 Получателей: {total}",
        parse_mode="HTML"
    )

    success = 0
    failed = 0

    for uid in user_ids:
        try:
            await bot.copy_message(
                chat_id=uid,
                from_chat_id=from_chat_id,
                message_id=message_id
            )
            success += 1
        except Exception as e:
            failed += 1
            print(f"[broadcast] Не удалось отправить {uid}: {e}")

    await callback.message.edit_text(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"📤 Отправлено: <b>{success}</b>\n"
        f"❌ Не дошло: <b>{failed}</b>\n"
        f"👥 Всего: {total}",
        parse_mode="HTML"
    )
    await state.clear()
    await callback.answer("Готово")


@router.callback_query(F.data == "broadcast_no_group", BroadcastStates.confirming_group)
async def broadcast_group_cancel(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Рассылка отменена.")
    await state.clear()
    await callback.answer("Отменено")


@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        return
    await state.clear()
    await message.answer("❌ Действие отменено.")


# ============ СНЯТИЕ РОЛИ СТАРОСТЫ ============

@router.message(Command("remove_starosta"))
async def cmd_remove_starosta(message: types.Message, bot: Bot):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ может снимать старосту.")
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.answer(
            "📝 <b>Формат:</b> <code>/remove_starosta &lt;user_id&gt;</code>",
            parse_mode="HTML"
        )
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом.")
        return

    user = get_user(target_id)
    if not user:
        await message.answer(f"❌ Пользователь с ID <code>{target_id}</code> не зарегистрирован.", parse_mode="HTML")
        return

    if user[5] != 'starosta':
        await message.answer(
            f"⚠️ Пользователь <b>{_escape_html(user[4])}</b> не является старостой.",
            parse_mode="HTML"
        )
        return

    success, full_name, group_name = remove_starosta(target_id)

    if not success:
        await message.answer(f"❌ Не удалось снять роль старосты.", parse_mode="HTML")
        return

    try:
        await bot.send_message(
            target_id,
            "⚠️ <b>С вас снята роль старосты.</b>\n\nТеперь вы обычный студент.",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"[admin] Не удалось уведомить {target_id}: {e}")

    await message.answer(
        f"✅ <b>Роль старосты снята</b>\n\n"
        f"👤 <b>{_escape_html(full_name)}</b>\n"
        f"🆔 <code>{target_id}</code>\n"
        f"🎓 Группа: {_escape_html(group_name)}",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("user_remove_starosta_yes_"))
async def user_remove_starosta_yes(callback: types.CallbackQuery, bot: Bot):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    try:
        target_id = int(callback.data.replace("user_remove_starosta_yes_", ""))
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    user = get_user(target_id)
    if not user:
        await callback.answer("❌ Пользователь уже удалён.", show_alert=True)
        return
    if user[5] != 'starosta':
        await callback.answer("⚠️ Уже не староста.", show_alert=True)
        return

    success, full_name, group_name = remove_starosta(target_id)

    if not success:
        await callback.answer("❌ Не удалось снять роль.", show_alert=True)
        return

    try:
        await bot.send_message(
            target_id,
            "⚠️ <b>С вас снята роль старосты.</b>\n\nТеперь вы обычный студент.",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"[admin] Не удалось уведомить {target_id}: {e}")

    await callback.message.edit_text(
        f"✅ <b>Роль старосты снята</b>\n\n"
        f"👤 <b>{_escape_html(full_name)}</b>\n"
        f"🆔 <code>{target_id}</code>\n"
        f"🎓 Группа: {_escape_html(group_name)}",
        parse_mode="HTML"
    )
    await callback.answer("Готово", show_alert=True)


@router.callback_query(F.data.startswith("user_remove_starosta_no_"))
async def user_remove_starosta_no(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer("Отменено")


@router.callback_query(F.data.startswith("user_remove_starosta_"))
async def user_remove_starosta_start(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    try:
        target_id = int(callback.data.replace("user_remove_starosta_", ""))
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    user = get_user(target_id)
    if not user:
        await callback.answer("❌ Пользователь не зарегистрирован.", show_alert=True)
        return
    if user[5] != 'starosta':
        await callback.answer("⚠️ Пользователь не староста.", show_alert=True)
        return

    text = _format_user_details(user)

    await callback.message.edit_text(
        f"{text}\n\n"
        f"⚠️ <b>Снять роль старосты?</b>\n\n"
        f"<i>Пользователь станет обычным студентом.</i>",
        parse_mode="HTML",
        reply_markup=get_remove_starosta_confirm_kb(target_id)
    )
    await callback.answer()


# ============ ОБНОВЛЕНИЕ РАСПИСАНИЯ (РГРТУ) ============

@router.message(Command("refresh_schedule"))
async def cmd_refresh_schedule(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ может запускать полное обновление.")
        return

    await message.answer(
        "🔄 <b>Запускаю полное обновление расписания (только РГРТУ)...</b>\n\n"
        "Это может занять 1–3 минуты.",
        parse_mode="HTML"
    )

    groups = get_all_groups()
    groups_rgrtu = [g for g in groups if g[0] == "РГРТУ"]

    if not groups_rgrtu:
        await message.answer("📋 В базе нет групп РГРТУ — нечего обновлять.")
        return

    today = datetime.now(MSK)

    total_groups = len(groups_rgrtu)
    groups_success = 0
    groups_failed = 0

    total_saved = 0
    total_updated = 0
    total_deleted = 0

    failed_groups = []

    for university, faculty, group_name in groups_rgrtu:
        try:
            date_iso = today.strftime("%Y-%m-%d")
            data = await fetch_schedule_from_api(group_name, date_iso)

            if not data:
                groups_failed += 1
                failed_groups.append(group_name)
                print(f"[refresh_schedule] ❌ Не удалось получить расписание для {group_name}")
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
                        lesson_type_full=None,
                    )
                    valid_keys.add((day_name, target_week, p["pair_number"], 0))

                    if existing:
                        updated += 1
                    else:
                        saved += 1

            deleted = delete_orphan_schedule_pairs(
                university, faculty, group_name, valid_keys
            )

            total_saved += saved
            total_updated += updated
            total_deleted += deleted
            groups_success += 1

            print(f"[refresh_schedule]   ✅ {group_name}: новых {saved}, обновлено {updated}, удалено {deleted}")

        except Exception as e:
            groups_failed += 1
            failed_groups.append(group_name)
            print(f"[refresh_schedule]   ❌ Ошибка для {group_name}: {e}")

    text = (
        f"✅ <b>Обновление расписания РГРТУ завершено</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"👥 Групп обработано: <b>{groups_success}</b> из <b>{total_groups}</b>\n"
        f"📚 Новых пар: <b>{total_saved}</b>\n"
        f"♻️ Обновлено пар: <b>{total_updated}</b>\n"
        f"🗑 Удалено пар: <b>{total_deleted}</b>\n"
    )

    if groups_failed > 0:
        text += f"\n⚠️ <b>Не удалось обновить:</b> {groups_failed} групп\n"
        preview = ", ".join(failed_groups[:10])
        if len(failed_groups) > 10:
            preview += f" и ещё {len(failed_groups) - 10}"
        text += f"<i>{preview}</i>"

    await message.answer(text, parse_mode="HTML")


# ============ УДАЛЕНИЕ ПАРЫ (РГУ) ============

@router.message(F.text == "🗑 Удалить пару")
async def delete_pair_start(message, state):
    user = get_user(message.from_user.id)
    if not user or user[5] != 'starosta':
        await message.answer("⛔ Только староста может удалять пары.")
        return

    if user[1] != "РГУ":
        await message.answer(
            "ℹ️ Удаление пар доступно только для <b>РГУ</b>.\n"
            "Расписание РГРТУ обновляется автоматически с сайта.",
            parse_mode="HTML"
        )
        return

    await state.clear()
    await message.answer(
        "🗑 <b>Удаление пары</b>\n\n"
        "Выбери <b>день недели</b>:",
        parse_mode="HTML",
        reply_markup=get_days_delete_kb()
    )


@router.callback_query(F.data.startswith("dpd_"))
async def delete_pair_choose_day(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user or user[5] != 'starosta':
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return

    if user[1] != "РГУ":
        await callback.answer("⛔ Только РГУ.", show_alert=True)
        return

    action = callback.data.replace("dpd_", "")

    if action == "cancel":
        await callback.message.edit_text("❌ Удаление отменено.")
        await callback.message.answer(
            "Панель старосты:",
            reply_markup=get_admin_panel_kb(university=user[1])
        )
        await callback.answer()
        return

    if action == "back":
        await callback.message.edit_text(
            "🗑 <b>Удаление пары</b>\n\n"
            "Выбери <b>день недели</b>:",
            parse_mode="HTML",
            reply_markup=get_days_delete_kb()
        )
        await callback.answer()
        return

    day = action
    pairs = get_pairs_for_delete(user[1], user[2], user[3], day)

    if not pairs:
        await callback.message.edit_text(
            f"📅 На <b>{day}</b> пар нет.",
            parse_mode="HTML",
            reply_markup=get_days_delete_kb()
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"🗑 <b>Выбери пару для удаления</b>\n"
        f"📅 День: <b>{day}</b>\n\n"
        f"⚠️ Удаление затронет <b>только</b> эту пару.",
        parse_mode="HTML",
        reply_markup=get_pairs_delete_kb(pairs)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dpair_yes_"))
async def delete_pair_yes(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user or user[5] != 'starosta':
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return

    if user[1] != "РГУ":
        await callback.answer("⛔ Только РГУ.", show_alert=True)
        return

    try:
        schedule_id = int(callback.data.replace("dpair_yes_", ""))
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    info = get_schedule_pair_info(schedule_id)
    if not info:
        await callback.answer("❌ Пара уже удалена.", show_alert=True)
        return

    if (info[0], info[1], info[2]) != (user[1], user[2], user[3]):
        await callback.answer("⛔ Эта пара не из вашей группы.", show_alert=True)
        return

    ok = delete_schedule_pair_by_id(schedule_id)
    if not ok:
        await callback.answer("❌ Не удалось удалить.", show_alert=True)
        return

    await callback.message.edit_text(
        f"✅ Пара удалена:\n\n"
        f"📖 <b>{info[5]}</b>\n"
        f"📅 {info[3]}, {info[4]} пара",
        parse_mode="HTML"
    )
    await callback.message.answer(
        "Панель старосты:",
        reply_markup=get_admin_panel_kb(university=user[1])
    )
    await callback.answer("Удалено")


@router.callback_query(F.data.startswith("dpair_no_"))
async def delete_pair_no(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text("❌ Удаление отменено.")
    except Exception as e:
        print(f"[admin] edit_text error: {e}")
    await callback.answer("Отменено")


@router.callback_query(F.data.startswith("dpair_"))
async def delete_pair_confirm(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user or user[5] != 'starosta':
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return

    if user[1] != "РГУ":
        await callback.answer("⛔ Только РГУ.", show_alert=True)
        return

    try:
        schedule_id = int(callback.data.replace("dpair_", ""))
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    info = get_schedule_pair_info(schedule_id)
    if not info:
        await callback.answer("❌ Пара уже удалена.", show_alert=True)
        return

    (s_uni, s_fac, s_grp, s_day, s_num,
     s_subject, s_wt, s_sg, s_start, s_teacher, s_room) = info

    if (s_uni, s_fac, s_grp) != (user[1], user[2], user[3]):
        await callback.answer("⛔ Эта пара не из вашей группы.", show_alert=True)
        return

    wt_label = "числитель" if s_wt == "числитель" else "знаменатель"
    sg_label = ""
    if s_sg == 1:
        sg_label = " [1 пг]"
    elif s_sg == 2:
        sg_label = " [2 пг]"

    text = (
        f"⚠️ <b>Удалить пару?</b>\n\n"
        f"📅 День: <b>{s_day}</b>\n"
        f"🔢 Номер: <b>{s_num}</b>\n"
        f"⏰ Начало: <b>{s_start}</b>\n"
        f"📆 Неделя: <b>{wt_label}</b>{sg_label}\n"
        f"📖 <b>{s_subject}</b>\n"
    )
    if s_teacher:
        text += f"👤 {s_teacher}\n"
    if s_room:
        text += f"🚪 {s_room}\n"

    text += "\n<i>Действие нельзя отменить.</i>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Удалить", callback_data=f"dpair_yes_{schedule_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"dpair_no_{schedule_id}"),
        ],
    ])

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


# ============ TEST BROADCAST ============

@router.message(Command("test_broadcast"))
async def cmd_test_broadcast(message: types.Message, bot: Bot):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ.")
        return
    await message.answer("🧪 Запускаю ручную рассылку «Отметь явку»...")
    from scheduler import manual_test_broadcast
    await manual_test_broadcast(bot)
    await message.answer("✅ Готово.")


# ============ ЗАЯВКИ НА СТАРОСТУ ============

@router.message(Command("applications"))
async def cmd_applications(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ.")
        return

    apps = get_pending_applications()
    if not apps:
        await message.answer("📋 Нет заявок на старосту.")
        return

    text = f"👑 <b>Заявки на старосту ({len(apps)})</b>\n\n"
    for app in apps:
        app_id, user_id, username, fio, university, faculty, group_name, *_ = app
        text += (
            f"<b>#{app_id}</b> — {_escape_html(fio)}\n"
            f"   @{_escape_html(username) if username else 'без username'} | <code>{user_id}</code>\n"
            f"   🏛 {_escape_html(university)} | 🎓 {_escape_html(faculty)} | 👥 {_escape_html(group_name)}\n\n"
        )
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_applications_list_kb(apps)
    )


@router.callback_query(F.data.startswith("app_view_"))
async def app_view(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    app_id = int(callback.data.replace("app_view_", ""))
    app = get_application_by_id(app_id)
    if not app:
        await callback.answer("❌ Заявка не найдена.", show_alert=True)
        return

    (app_id, user_id, username, fio, university, faculty,
     group_name, photo_group_id, photo_dean_id, status, created_at) = app

    status_label = {
        "pending": "⏳ На проверке",
        "approved": "✅ Одобрена",
        "rejected": "❌ Отклонена",
    }.get(status, status)

    text = (
        f"👑 <b>Заявка #{app_id}</b> — {status_label}\n\n"
        f"👤 @{_escape_html(username) if username else 'без username'} | <code>{user_id}</code>\n"
        f"📛 ФИО: <b>{_escape_html(fio)}</b>\n"
        f"🏛 ВУЗ: {_escape_html(university)}\n"
        f"🎓 Факультет: {_escape_html(faculty)}\n"
        f"👥 Группа: {_escape_html(group_name)}\n"
        f"📅 {created_at[:19]}"
    )

    if status == "pending":
        kb = get_application_review_kb(app_id)
    else:
        kb = None

    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    if photo_group_id:
        await callback.message.answer_photo(photo_group_id, caption="📎 Скрин из группы старост")
    if photo_dean_id:
        await callback.message.answer_photo(photo_dean_id, caption="📎 Скрин от декана")
    await callback.answer()


@router.callback_query(F.data.startswith("app_approve_"))
async def app_approve(callback: types.CallbackQuery, bot: Bot):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    app_id = int(callback.data.replace("app_approve_", ""))

    result = approve_application(app_id)
    if not result:
        await callback.answer("⚠️ Уже обработана.", show_alert=True)
        return

    user_id, fio, university, faculty, group_name = result

    try:
        await bot.send_message(
            user_id,
            f"🎉 <b>Твоя заявка на старосту одобрена!</b>\n\n"
            f"👥 Группа: {group_name}\n"
            f"Теперь ты староста.\n\n"
            f"👉 Отправь <b>/start</b>, чтобы обновить меню и получить кнопку "
            f"<b>«👑 Панель старосты»</b>.",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"[starosta] не смог уведомить {user_id}: {e}")

    await callback.message.edit_text(
        f"✅ <b>Заявка #{app_id} одобрена</b>\n\n"
        f"👤 {_escape_html(fio)}\n"
        f"👥 {_escape_html(group_name)}\n"
        f"Роль старосты выдана.",
        parse_mode="HTML"
    )
    await callback.answer("Одобрено")


@router.callback_query(F.data.startswith("app_reject_"))
async def app_reject(callback: types.CallbackQuery, bot: Bot):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    app_id = int(callback.data.replace("app_reject_", ""))

    result = reject_application(app_id)
    if not result:
        await callback.answer("⚠️ Уже обработана.", show_alert=True)
        return

    user_id, fio = result

    try:
        await bot.send_message(
            user_id,
            f"😔 <b>Заявка на старосту отклонена.</b>\n\n"
            f"Проверь доказательства и подай заново.",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"[starosta] не смог уведомить {user_id}: {e}")

    await callback.message.edit_text(
        f"❌ <b>Заявка #{app_id} отклонена</b>\n\n"
        f"👤 {_escape_html(fio)}",
        parse_mode="HTML"
    )
    await callback.answer("Отклонено")


@router.message(Command("starosta"))
async def cmd_starosta_list(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ.")
        return

    rows = get_all_starostas()
    if not rows:
        await message.answer("📋 Список старост пуст.")
        return

    text = f"👑 <b>Список старост ({len(rows)})</b>\n\n"
    for app_id, user_id, username, fio, university, faculty, group_name, created_at in rows:
        text += (
            f"<b>{_escape_html(fio)}</b>\n"
            f"   @{_escape_html(username) if username else 'без username'} | <code>{user_id}</code>\n"
            f"   🏛 {_escape_html(university)} | 🎓 {_escape_html(faculty)} | 👥 {_escape_html(group_name)}\n"
            f"   📅 заявка #{app_id} от {created_at[:10]}\n\n"
        )

    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await message.answer(text[i:i+4000], parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")


# ============ БЭКАПЫ ============

@router.message(Command("backup"))
async def cmd_backup(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ.")
        return

    try:
        path = backup_db()
        await message.answer_document(
            FSInputFile(path),
            caption=f"🗂 <b>Бэкап БД</b>\n"
                    f"📅 {datetime.now(MSK).strftime('%d.%m.%Y %H:%M')}\n"
                    f"📦 {os.path.getsize(path) // 1024} KB",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка бэкапа: {e}")


@router.message(Command("restore"))
async def cmd_restore(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ.")
        return

    await message.answer(
        "📥 <b>Пришли .db файл для восстановления.</b>\n\n"
        "⚠️ Текущая БД будет <b>полностью заменена</b>.\n"
        "Для отмены — /cancel",
        parse_mode="HTML"
    )


# ============ ПРОМОКОДЫ ============

@router.message(Command("create_promo"))
async def cmd_create_promo(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            f"📝 <b>Формат:</b>\n"
            f"<code>/create_promo &lt;код&gt; [xp] [uses]</code>\n\n"
            f"<b>Пример:</b>\n"
            f"<code>/create_promo WELCOME 5 10</code>\n\n"
            f"По умолчанию: xp={DEFAULT_PROMO_XP}, uses={DEFAULT_PROMO_USES}",
            parse_mode="HTML"
        )
        return

    code = parts[1].upper().strip()
    try:
        reward_xp = int(parts[2]) if len(parts) > 2 else DEFAULT_PROMO_XP
    except ValueError:
        reward_xp = DEFAULT_PROMO_XP

    try:
        uses = int(parts[3]) if len(parts) > 3 else DEFAULT_PROMO_USES
    except ValueError:
        uses = DEFAULT_PROMO_USES

    ok = create_promo_code(code, reward_xp, uses, created_by=message.from_user.id)

    if ok:
        await message.answer(
            f"✅ Промокод <code>{code}</code> создан!\n"
            f"🎁 XP: <b>{reward_xp}</b>\n"
            f"👥 Активаций: <b>{uses}</b>",
            parse_mode="HTML"
        )
    else:
        await message.answer(f"⚠️ Промокод <code>{code}</code> уже существует.", parse_mode="HTML")


@router.message(Command("promo_list"))
async def cmd_promo_list(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ.")
        return

    rows = get_all_promo_codes()
    if not rows:
        await message.answer("📋 Список промокодов пуст.")
        return

    text = f"🎁 <b>Промокоды ({len(rows)}):</b>\n\n"
    for code, reward_xp, uses_left, created_at in rows:
        text += (
            f"<code>{_escape_html(code)}</code> — "
            f"+{reward_xp} XP | "
            f"осталось: <b>{uses_left}</b>\n"
            f"   <i>{created_at[:16]}</i>\n\n"
        )

    text += "<i>Удалить: /delete_promo &lt;код&gt;</i>"

    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await message.answer(text[i:i+4000], parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")


@router.message(Command("delete_promo"))
async def cmd_delete_promo(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ.")
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("📝 <code>/delete_promo &lt;код&gt;</code>", parse_mode="HTML")
        return

    code = parts[1].upper()
    if delete_promo_code(code):
        await message.answer(f"✅ Промокод <code>{code}</code> удалён.", parse_mode="HTML")
    else:
        await message.answer(f"⚠️ Промокод <code>{code}</code> не найден.", parse_mode="HTML")


# ============ СБРОС XP ============

@router.message(Command("reset_xp"))
async def cmd_reset_xp(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ.")
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("📝 <code>/reset_xp &lt;user_id&gt;</code>", parse_mode="HTML")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом.")
        return

    user = get_user(target_id)
    if not user:
        await message.answer("❌ Пользователь не зарегистрирован.")
        return

    reset_user_xp(target_id)
    await message.answer(
        f"✅ XP сброшен у <b>{_escape_html(user[4])}</b> (ID <code>{target_id}</code>)",
        parse_mode="HTML"
    )


@router.message(Command("reset_group_xp"))
async def cmd_reset_group_xp(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer(
            "📝 <code>/reset_group_xp &lt;ВУЗ&gt; &lt;Факультет&gt; &lt;Группа&gt;</code>\n"
            "Пример: <code>/reset_group_xp РГРТУ ФВТ 1234</code>",
            parse_mode="HTML"
        )
        return

    # парсим остаток
    group_parts = parts[1].split()
    if len(group_parts) < 3:
        await message.answer("❌ Нужно 3 параметра: ВУЗ, Факультет, Группа")
        return

    university = group_parts[0]
    faculty = group_parts[1]
    group_name = group_parts[2]

    reset_group_xp(university, faculty, group_name)

    await message.answer(
        f"✅ XP сброшен у группы <b>{_escape_html(group_name)}</b>\n"
        f"🏛 {_escape_html(university)} | 🎓 {_escape_html(faculty)}",
        parse_mode="HTML"
    )

    # ============ ЭКСПОРТ ПОСЕЩАЕМОСТИ ============

@router.message(F.text == "📊 Экспорт за месяц")
async def export_month_start(message: types.Message):
    user = get_user(message.from_user.id)
    if not user or user[5] != 'starosta':
        await message.answer("⛔ Только староста.")
        return

    await message.answer(
        "📊 <b>Экспорт посещаемости</b>\n\n"
        "Выбери период:",
        parse_mode="HTML",
        reply_markup=get_export_month_kb()
    )


@router.callback_query(F.data.in_({"export_30", "export_7"}))
async def export_month_generate(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user or user[5] != 'starosta':
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return

    days = 30 if callback.data == "export_30" else 7

    await callback.answer("Готовлю файл...")

    rows = get_group_attendance_month(user[1], user[2], user[3], days=days)

    if not rows:
        await callback.message.edit_text(
            f"📊 За последние {days} дней нет отметок.",
            reply_markup=get_export_month_kb()
        )
        return

    status_map = {
        "will": "Буду",
        "absent": "Не приду",
        "sick": "Заболел",
        "late": "Задержусь",
    }

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Дата", "ФИО", "Пара", "Предмет", "Статус"])

    for date, full_name, pair_num, subject, status in rows:
        writer.writerow([
            date,
            full_name,
            pair_num,
            subject,
            status_map.get(status, status),
        ])

    csv_bytes = buf.getvalue().encode("utf-8-sig")

    file = types.BufferedInputFile(
        csv_bytes,
        filename=f"attendance_{user[3]}_{days}d.csv"
    )

    await callback.message.edit_text(
        f"✅ <b>Отчёт за {days} дней</b>\n\n"
        f"📊 Строк: <b>{len(rows)}</b>",
        parse_mode="HTML"
    )

    await callback.message.answer_document(
        file,
        caption=f"📊 Посещаемость группы {user[3]} за {days} дней"
    )


@router.callback_query(F.data == "export_cancel")
async def export_cancel(callback: CallbackQuery):
    try:
        await callback.message.edit_text("❌ Экспорт отменён.")
    except Exception:
        pass
    await callback.answer("Отменено")


# ============ ТЕСТ АЛЕРТА ПРОГУЛЬЩИКОВ ============

@router.message(Command("test_absentees"))
async def cmd_test_absentees(message: types.Message, bot: Bot):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ.")
        return
    from scheduler import check_absentees_streaks
    await message.answer("🧪 Запускаю проверку прогульщиков...")
    await check_absentees_streaks(bot)
    await message.answer("✅ Готово.")