from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from collections import OrderedDict
import re

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
)
from keyboards import (
    get_admin_panel_kb, get_main_menu,
    get_days_kb, get_confirm_kb,
    get_group_members_delete_kb, get_group_list_actions_kb, get_broadcast_confirm_kb, get_remove_starosta_confirm_kb,
)
from config import (
    ADMIN_IDS, get_current_week_type, get_week_type_for_date
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


class AdminActions(StatesGroup):
    waiting_homework = State()
    waiting_pair = State()


# ============ МАСТЕР ДОБАВЛЕНИЯ ПАРЫ ============

class AddPair(StatesGroup):
    choosing_week_type = State()
    choosing_day = State()
    entering_number = State()
    entering_time = State()
    entering_subject = State()
    entering_teacher = State()
    entering_room = State()
    confirming = State()
    confirming_repeat = State()


@router.message(F.text == "➕ Пара")
async def add_pair_start(message, state):
    user = get_user(message.from_user.id)
    if not user or user[5] != 'starosta':
        await message.answer("⛔ Только староста может добавлять пары.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Числитель", callback_data="weektype_числитель")],
        [InlineKeyboardButton(text="Знаменатель", callback_data="weektype_знаменатель")],
        [InlineKeyboardButton(text="Каждую неделю", callback_data="weektype_any")],
    ])
    await message.answer("📅 **Мастер добавления пары**\n\nВыбери **тип недели**:", parse_mode="Markdown", reply_markup=kb)
    await state.set_state(AddPair.choosing_week_type)


@router.callback_query(F.data.startswith("weektype_"), AddPair.choosing_week_type)
async def pair_choose_week_type(callback, state):
    week_type = callback.data.replace("weektype_", "")
    if week_type == "any":
        week_type = None
    await state.update_data(week_type=week_type)
    label = week_type if week_type else "каждую неделю"
    await callback.message.edit_text(f"📅 Тип недели: **{label}**\n\nВыбери **день недели**:", parse_mode="Markdown", reply_markup=get_days_kb("pairday"))
    await state.set_state(AddPair.choosing_day)
    await callback.answer()


@router.callback_query(F.data.startswith("pairday_"), AddPair.choosing_day)
async def pair_choose_day(callback, state):
    day = callback.data.replace("pairday_", "")
    await state.update_data(day=day)
    await callback.message.edit_text(f"📅 День: **{day}**\n\nВведи **номер пары** числом:", parse_mode="Markdown")
    await state.set_state(AddPair.entering_number)
    await callback.answer()


@router.message(AddPair.entering_number)
async def pair_enter_number(message, state):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Номер пары должен быть числом.")
        return
    await state.update_data(pair_number=int(text))
    await message.answer("⏰ Введи **время пары** (`09:55-11:30` или `09:55`):", parse_mode="Markdown")
    await state.set_state(AddPair.entering_time)


@router.message(AddPair.entering_time)
async def pair_enter_time(message, state):
    await state.update_data(time=message.text.strip())
    await message.answer("📖 Введи **название предмета**:")
    await state.set_state(AddPair.entering_subject)


@router.message(AddPair.entering_subject)
async def pair_enter_subject(message, state):
    await state.update_data(subject=message.text.strip())
    await message.answer("👤 Введи **преподавателя** (или `-`):")
    await state.set_state(AddPair.entering_teacher)


@router.message(AddPair.entering_teacher)
async def pair_enter_teacher(message, state):
    await state.update_data(teacher=message.text.strip())
    await message.answer("🚪 Введи **аудиторию** (или `-`):")
    await state.set_state(AddPair.entering_room)


@router.message(AddPair.entering_room)
async def pair_enter_room(message, state):
    await state.update_data(room=message.text.strip())
    data = await state.get_data()
    week_label = data.get('week_type') or "каждую неделю"
    text = (
        f"Проверь пару:\n\n"
        f"📆 Неделя: **{week_label}**\n"
        f"📅 День: **{data['day']}**\n"
        f"🔢 Номер: **{data['pair_number']}**\n"
        f"⏰ Время: **{data['time']}**\n"
        f"📖 Предмет: **{data['subject']}**\n"
        f"👤 Преподаватель: **{data['teacher']}**\n"
        f"🚪 Аудитория: **{data['room']}**\n\nСохранить?"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_confirm_kb("pairconfirm"))
    await state.set_state(AddPair.confirming)


@router.callback_query(F.data == "pairconfirm_yes", AddPair.confirming)
async def pair_confirm_yes(callback, state):
    data = await state.get_data()
    user = get_user(callback.from_user.id)
    await state.update_data(university=user[1], faculty=user[2], group_name=user[3])
    await callback.message.edit_text(
        f"📅 День: **{data['day']}**\n🔢 Номер: **{data['pair_number']}**\n⏰ Время: **{data['time']}**\n📖 Предмет: **{data['subject']}**\n\nСохранить?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Сохранить", callback_data="pairrepeat_yes"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="pairrepeat_no"),
        ]])
    )
    await state.set_state(AddPair.confirming_repeat)
    await callback.answer()


@router.callback_query(F.data == "pairrepeat_yes", AddPair.confirming_repeat)
async def pair_repeat_yes(callback, state):
    data = await state.get_data()
    week_type = data.get('week_type')
    if week_type is None:
        for wt in ["числитель", "знаменатель"]:
            add_schedule_pair(
                university=data['university'], faculty=data['faculty'], group_name=data['group_name'],
                day=data['day'], pair_num=data['pair_number'], subject=data['subject'],
                teacher=data['teacher'], room=data['room'], start=data['time'], end="",
                week_type=wt
            )
        week_label = "каждую неделю"
    else:
        add_schedule_pair(
            university=data['university'], faculty=data['faculty'], group_name=data['group_name'],
            day=data['day'], pair_num=data['pair_number'], subject=data['subject'],
            teacher=data['teacher'], room=data['room'], start=data['time'], end="",
            week_type=week_type
        )
        week_label = week_type
    await callback.message.edit_text(
        f"✅ Пара сохранена!\n\n📆 Неделя: **{week_label}**\n📅 {data['day']}, {data['pair_number']} пара\n📖 {data['subject']}\n⏰ {data['time']}",
        parse_mode="Markdown"
    )
    await callback.message.answer("Панель старосты:", reply_markup=get_admin_panel_kb())
    await state.clear()
    await callback.answer("Сохранено")


@router.callback_query(F.data == "pairrepeat_no", AddPair.confirming_repeat)
async def pair_repeat_no(callback, state):
    await callback.message.edit_text("❌ Отменено.")
    await callback.message.answer("Панель старосты:", reply_markup=get_admin_panel_kb())
    await state.clear()
    await callback.answer("Отменено")


@router.callback_query(F.data == "pairconfirm_no", AddPair.confirming)
async def pair_confirm_no(callback, state):
    await callback.message.edit_text("❌ Отменено.")
    await callback.message.answer("Панель старосты:", reply_markup=get_admin_panel_kb())
    await state.clear()
    await callback.answer("Отменено")



# ============ ПАНЕЛЬ СТАРОСТЫ ============

@router.message(F.text == "👑 Панель старосты")
async def admin_panel(message):
    user = get_user(message.from_user.id)
    if not user or user[5] != 'starosta':
        await message.answer("⛔ У тебя нет прав старосты.")
        return
    await message.answer("👑 Панель старосты", reply_markup=get_admin_panel_kb())


@router.message(F.text == "🔙 Назад")
async def back_to_menu(message):
    user = get_user(message.from_user.id)
    is_admin = user[5] == 'starosta' if user else False
    await message.answer("🏠 Главное меню:", reply_markup=get_main_menu(is_admin))


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
    await callback.message.answer("Панель старосты:", reply_markup=get_admin_panel_kb())
    await state.clear()
    await callback.answer("Сохранено")


@router.callback_query(F.data == "hwconfirm_no", AddHomework.confirming)
async def hw_confirm_no(callback, state):
    await callback.message.edit_text("❌ Отменено.")
    await callback.message.answer("Панель старосты:", reply_markup=get_admin_panel_kb())
    await state.clear()
    await callback.answer("Отменено")


# ============ ПОСЕЩАЕМОСТЬ (компактная) ============

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


# ============ ЛОГИ ПОСЕЩАЕМОСТИ ЗА НЕДЕЛЮ ============

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

    # Группируем: {date: {full_name: {pair_num: status}}}
    logs_by_date = OrderedDict()
    for date, full_name, pair_num, subject, status in rows:
        if date not in logs_by_date:
            logs_by_date[date] = OrderedDict()
        if full_name not in logs_by_date[date]:
            logs_by_date[date][full_name] = {}
        # Если несколько отметок по одной паре — берём последнюю
        logs_by_date[date][full_name][pair_num] = status

    text = f"📜 <b>Логи посещаемости группы {user[3]}</b>\n"
    text += f"Период: последние 7 дней\n\n"

    status_icons = {
        "will": "✅",
        "absent": "❌",
        "sick": "🤒",
        "late": "⏰"
    }

    for date, students in logs_by_date.items():
        # Форматируем дату: 2026-09-13 → 13.09.2026 (Сб)
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
            day_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][dt.weekday()]
            date_display = f"{dt.strftime('%d.%m.%Y')} ({day_ru})"
        except Exception:
            date_display = date

        text += f"📅 <b>{date_display}</b>\n"

        # Сортируем студентов по ФИО
        for full_name in sorted(students.keys()):
            short = _short_name(full_name)
            pairs_info = []

            # Сортируем пары по номеру
            for pair_num in sorted(students[full_name].keys()):
                status = students[full_name][pair_num]
                icon = status_icons.get(status, "?")
                pairs_info.append(f"{pair_num} пара — {icon}")

            text += f"  <b>{short}</b>: {', '.join(pairs_info)}\n"

        text += "\n"

    # Разбиваем, если длинное
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
    await message.answer(f"✅ {user[4]} (ID {target_id}) теперь староста.\nГруппа: {user[3]}")


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


# ============ ОБНОВЛЕНИЕ РАСПИСАНИЯ ============

@router.message(F.text == "🔄 Обновить")
async def update_schedule_from_api(message):
    user = get_user(message.from_user.id)
    if not user or user[5] != 'starosta':
        await message.answer("⛔ Только староста может обновлять расписание.")
        return
    await message.answer("🔄 Загружаю расписание с сайта...")
    today = datetime.now(MSK)
    date_iso = today.strftime("%Y-%m-%d")
    data = await fetch_schedule_from_api(user[3], date_iso)
    if not data:
        await message.answer("❌ Не удалось получить расписание.")
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
            existing = get_schedule_pair_by_key(user[1], user[2], user[3], day_name, target_week, p["pair_number"])
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
    deleted = delete_orphan_schedule_pairs(user[1], user[2], user[3], valid_keys)
    await message.answer(
        f"✅ Расписание обновлено!\n📚 Новых пар: **{saved}**\n♻️ Обновлено: **{updated}**\n🗑 Удалено: **{deleted}**",
        parse_mode="Markdown"
    )

# ============ БЛОКИРОВКА ============

def _is_admin(user_id):
    return user_id in ADMIN_IDS


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


# ============ АДМИН: СПИСОК ВСЕХ ПОЛЬЗОВАТЕЛЕЙ ============

from database import get_all_users, count_users, get_user_details
from keyboards import (
    get_users_pagination_kb,
    get_user_info_kb,
    get_user_delete_confirm_kb,
)

USERS_PER_PAGE = 10


def _escape_html(text):
    """Экранирует HTML-спецсимволы"""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def _format_user_row(user):
    user_id = user[0]
    group_name = user[3]
    full_name = user[4]
    role = user[5]
    registered_at = user[6]
    username = user[10] if len(user) > 10 else None

    role_icon = "👑" if role == "starosta" else "🎓"
    full_name_safe = _escape_html(full_name)
    group_safe = _escape_html(group_name or "")

    if username:
        username_str = f"@{_escape_html(username)}"
    else:
        username_str = "<i>без username</i>"

    return (
        f"{role_icon} <b>{full_name_safe}</b>\n"
        f"   {username_str}\n"
        f"   🆔 <code>{user_id}</code> | {group_safe} | {registered_at[:10]}"
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

    return (
        f"👤 <b>Информация о пользователе</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"<b>Username:</b> {username_str}\n"
        f"<b>ФИО:</b> {_escape_html(full_name)}\n"
        f"<b>Роль:</b> {role_text}\n\n"
        f"🏛 <b>ВУЗ:</b> {_escape_html(university)}\n"
        f"<b>Факультет:</b> {_escape_html(faculty)}\n"
        f"<b>Группа:</b> {_escape_html(group_name)}\n\n"
        f"📅 <b>Зарегистрирован:</b> {registered_at[:19]}\n"
        f"🔔 <b>Уведомления:</b> {notif_text}"
    )


async def _send_users_page(message: types.Message, page: int):
    """Отправляет страницу со списком пользователей"""
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


# ============ КОМАНДА /users ============

@router.message(Command("users"))
async def cmd_users(message: types.Message):
    """Список всех зарегистрированных пользователей"""
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ может смотреть список.")
        return

    total = count_users()
    if total == 0:
        await message.answer("📋 Список пользователей пуст.")
        return

    await _send_users_page(message, page=0)


# ============ КОМАНДА /user ============

@router.message(Command("user"))
async def cmd_user(message: types.Message):
    """Подробная информация о пользователе: /user <user_id>"""
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


# ============ ПАГИНАЦИЯ ============

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


# ============ КОМАНДА /banlist ============

@router.message(Command("banlist"))
async def banlist_command(message: types.Message):
    """Список забаненных"""
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

from aiogram import F
from database import get_all_user_ids, get_group_user_ids


class BroadcastStates(StatesGroup):
    waiting_message_all = State()
    waiting_message_group = State()
    confirming_all = State()
    confirming_group = State()


# ============ АДМИН: РАССЫЛКА ВСЕМ ============

@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    """Рассылка всем пользователям (только для админа)"""
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
    """Сохраняем сообщение и показываем подтверждение"""
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Рассылка отменена.")
        return

    # Сохраняем ID сообщения и чата
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
    """Отправляет сообщение всем"""
    data = await state.get_data()
    from_chat_id = data.get("from_chat_id")
    message_id = data.get("message_id")

    if not from_chat_id or not message_id:
        await callback.answer("❌ Сообщение потеряно. Попробуй ещё раз.", show_alert=True)
        await state.clear()
        return

    user_ids = get_all_user_ids()
    total = len(user_ids)

    await callback.message.edit_text(
        f"📤 <b>Рассылаю...</b>\n\n"
        f"👥 Получателей: {total}",
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


# ============ СТАРОСТА: РАССЫЛКА ПО ГРУППЕ ============

@router.message(Command("group_broadcast"))
async def cmd_group_broadcast(message: types.Message, state: FSMContext):
    """Рассылка по своей группе (только для старосты)"""
    user = get_user(message.from_user.id)
    if not user or user[5] != 'starosta':
        await message.answer("⛔ Только староста может делать рассылку по группе.")
        return

    # Считаем получателей
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
    """Сохраняем сообщение и показываем подтверждение"""
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
    """Отправляет сообщение группе"""
    user = get_user(callback.from_user.id)
    if not user or user[5] != 'starosta':
        await callback.answer("⛔ Нет прав.", show_alert=True)
        await state.clear()
        return

    data = await state.get_data()
    from_chat_id = data.get("from_chat_id")
    message_id = data.get("message_id")

    if not from_chat_id or not message_id:
        await callback.answer("❌ Сообщение потеряно. Попробуй ещё раз.", show_alert=True)
        await state.clear()
        return

    user_ids = get_group_user_ids(user[1], user[2], user[3])
    total = len(user_ids)

    await callback.message.edit_text(
        f"📤 <b>Рассылаю по группе {user[3]}...</b>\n\n"
        f"👥 Получателей: {total}",
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


# ============ ОТМЕНА ============

@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    """Отмена любого действия"""
    current = await state.get_state()
    if current is None:
        return
    await state.clear()
    await message.answer("❌ Действие отменено.")


# ============ СНЯТИЕ РОЛИ СТАРОСТЫ ============

@router.message(Command("remove_starosta"))
async def cmd_remove_starosta(message: types.Message, bot: Bot):
    """Снимает роль старосты: /remove_starosta <user_id>"""
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ может снимать старосту.")
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.answer(
            "📝 <b>Формат:</b> <code>/remove_starosta &lt;user_id&gt;</code>\n\n"
            "<b>Пример:</b> <code>/remove_starosta 123456789</code>",
            parse_mode="HTML"
        )
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом.")
        return

    if target_id == message.from_user.id and _is_admin(target_id):
        # Админ снимает старосту с себя — разрешаем
        pass

    user = get_user(target_id)
    if not user:
        await message.answer(f"❌ Пользователь с ID <code>{target_id}</code> не зарегистрирован.", parse_mode="HTML")
        return

    if user[5] != 'starosta':
        await message.answer(
            f"⚠️ Пользователь <b>{_escape_html(user[4])}</b> "
            f"(<code>{target_id}</code>) не является старостой.",
            parse_mode="HTML"
        )
        return

    # Снимаем роль
    success, full_name, group_name = remove_starosta(target_id)

    if not success:
        await message.answer(f"❌ Не удалось снять роль старосты с <code>{target_id}</code>.", parse_mode="HTML")
        return

    # Уведомляем бывшего старосту
    try:
        await bot.send_message(
            target_id,
            "⚠️ <b>С вас снята роль старосты.</b>\n\n"
            "Теперь вы обычный студент. Если нужно — обратитесь к администратору.",
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


# ============ INLINE: СНЯТИЕ РОЛИ ИЗ /user ============

@router.callback_query(F.data.startswith("user_remove_starosta_yes_"))
async def user_remove_starosta_yes(callback: types.CallbackQuery, bot: Bot):
    """Подтверждение снятия старосты через inline"""
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
            "⚠️ <b>С вас снята роль старосты.</b>\n\n"
            "Теперь вы обычный студент. Если нужно — обратитесь к администратору.",
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
    """Запрос подтверждения"""
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
        f"<i>Пользователь станет обычным студентом и получит уведомление.</i>",
        parse_mode="HTML",
        reply_markup=get_remove_starosta_confirm_kb(target_id)
    )
    await callback.answer()


    # ============ АДМИН: ПОЛНОЕ ОБНОВЛЕНИЕ РАСПИСАНИЯ ============

@router.message(Command("refresh_schedule"))
async def cmd_refresh_schedule(message: types.Message):
    """
    Полное обновление расписания для ВСЕХ групп.
    Обновляет только те пары, которые изменились — посещаемость сохраняется.
    
    Формат: /refresh_schedule
    """
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только админ может запускать полное обновление.")
        return

    await message.answer("🔄 <b>Запускаю полное обновление расписания для всех групп...</b>\n\nЭто может занять 1–3 минуты.", parse_mode="HTML")

    groups = get_all_groups()
    if not groups:
        await message.answer("📋 В базе нет групп — нечего обновлять.")
        return

    today = datetime.now(MSK)

    total_groups = len(groups)
    groups_success = 0
    groups_failed = 0

    total_saved = 0      # новых пар
    total_updated = 0    # обновлённых
    total_deleted = 0    # удалённых

    failed_groups = []   # какие группы не удалось обновить

    for university, faculty, group_name in groups:
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
                target_week = get_week_type_for_date(target.date())

                pairs = parse_schedule_for_day(data, target_iso, target_week)
                for p in pairs:
                    existing = get_schedule_pair_by_key(
                        university, faculty, group_name,
                        day_name, target_week, p["pair_number"]
                    )

                    upsert_schedule_pair(
                        university, faculty, group_name,
                        day_name, p["pair_number"], p["subject"],
                        p["teacher"], p["room"], p["start_time"], p["end_time"],
                        week_type=target_week,
                        lesson_type=p.get("lesson_type", "")
                    )
                    valid_keys.add((day_name, target_week, p["pair_number"]))

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

    # Формируем отчёт
    text = (
        f"✅ <b>Полное обновление расписания завершено</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"👥 Групп обработано: <b>{groups_success}</b> из <b>{total_groups}</b>\n"
        f"📚 Новых пар: <b>{total_saved}</b>\n"
        f"♻️ Обновлено пар: <b>{total_updated}</b>\n"
        f"🗑 Удалено пар: <b>{total_deleted}</b>\n"
    )

    if groups_failed > 0:
        text += f"\n⚠️ <b>Не удалось обновить:</b> {groups_failed} групп\n"
        # Показываем первые 10 проблемных групп
        preview = ", ".join(failed_groups[:10])
        if len(failed_groups) > 10:
            preview += f" и ещё {len(failed_groups) - 10}"
        text += f"<i>{preview}</i>"

    await message.answer(text, parse_mode="HTML")
